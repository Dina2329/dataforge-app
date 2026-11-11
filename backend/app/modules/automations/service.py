import uuid
from datetime import datetime, timezone
from typing import Any

from croniter import croniter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.query.filter_dsl import evaluate_filter, parse_filter_expr
from app.modules.audit.service import AuditService
from app.modules.automations.models import Automation, AutomationAction, AutomationRun
from app.modules.automations.repository import AutomationActionRepository, AutomationRepository, AutomationRunRepository
from app.modules.bases.field_types import get_field_type
from app.modules.bases.service import BasesService
from app.modules.workspaces.permissions import Permission
from app.worker.arq_app import get_arq_pool

TRIGGER_TYPES = {"record_created", "record_updated", "scheduled"}
ACTION_TYPES = {"send_webhook", "create_record", "update_record"}


class AutomationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AutomationRepository(db)
        self.actions = AutomationActionRepository(db)
        self.runs = AutomationRunRepository(db)
        self.bases = BasesService(db)
        self.audit = AuditService(db)

    async def _validate_trigger_config(self, *, table_id: uuid.UUID, trigger_type: str, trigger_config: dict[str, Any]) -> datetime | None:
        if trigger_type == "scheduled":
            cron = trigger_config.get("cron")
            if not cron or not croniter.is_valid(cron):
                raise ValidationError("Scheduled automations require a valid 'cron' expression")
            return croniter(cron, datetime.now(timezone.utc)).get_next(datetime)
        if "filter" in trigger_config and trigger_config["filter"] is not None:
            parse_filter_expr(trigger_config["filter"])  # raises ValidationError if malformed

        # watched_fields: fire only when at least one of these columns was
        # part of THIS write's values (see dispatch_record_event) -- distinct
        # from `filter` above, which checks the row's resulting values, not
        # which columns a given write actually touched. Only meaningful for
        # record_updated: record_created has no prior state to compare
        # against (every field is "new"), and scheduled has no triggering
        # write at all.
        watched_fields = trigger_config.get("watched_fields")
        if watched_fields is not None:
            if trigger_type != "record_updated":
                raise ValidationError("watched_fields only applies to the 'record_updated' trigger")
            if not isinstance(watched_fields, list) or not all(isinstance(f, str) for f in watched_fields):
                raise ValidationError("watched_fields must be a list of field names")
            # Attachments are written through their own dedicated upload
            # endpoint, never through update_record's `values` dict -- a
            # watched attachment field could never actually appear in
            # changed_fields, so it's excluded here too, not just virtual
            # fields.
            fields = await self.bases.fields.list_for_table(table_id)
            watchable_names = {f.name for f in fields if not get_field_type(f.field_type).is_virtual and f.field_type != "attachment"}
            unknown = set(watched_fields) - watchable_names
            if unknown:
                raise ValidationError(f"watched_fields references unknown or non-writable field(s): {', '.join(sorted(unknown))}")
        return None

    async def create(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, name: str, trigger_type: str, trigger_config: dict[str, Any]
    ) -> Automation:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.AUTOMATION_WRITE)
        if trigger_type not in TRIGGER_TYPES:
            raise ValidationError(f"Unknown trigger type: {trigger_type}")
        next_run_at = await self._validate_trigger_config(table_id=table_id, trigger_type=trigger_type, trigger_config=trigger_config)

        automation = await self.repo.create(
            table_id=table_id, name=name, trigger_type=trigger_type, trigger_config=trigger_config, created_by=user_id
        )
        automation.next_run_at = next_run_at
        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="automation.created", resource_type="automation",
            resource_id=str(automation.id), resource_label=name, details={"trigger_type": trigger_type},
        )
        await self.db.commit()
        return automation

    async def list_for_table(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> list[Automation]:
        await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        return await self.repo.list_for_table(table_id)

    async def _get_or_404(self, automation_id: uuid.UUID) -> Automation:
        automation = await self.repo.get(automation_id)
        if automation is None:
            raise NotFoundError("Automation not found")
        return automation

    async def _check_permission(self, automation_id: uuid.UUID, user_id: uuid.UUID) -> Automation:
        automation = await self._get_or_404(automation_id)
        await self.bases.check_table_permission(table_id=automation.table_id, user_id=user_id, permission=Permission.AUTOMATION_WRITE)
        return automation

    async def update(
        self,
        *,
        automation_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None,
        is_enabled: bool | None,
        trigger_config: dict[str, Any] | None,
    ) -> Automation:
        automation = await self._check_permission(automation_id, user_id)
        if name is not None:
            automation.name = name
        if is_enabled is not None:
            automation.is_enabled = is_enabled
        if trigger_config is not None:
            automation.next_run_at = await self._validate_trigger_config(
                table_id=automation.table_id, trigger_type=automation.trigger_type, trigger_config=trigger_config
            )
            automation.trigger_config = trigger_config
        workspace_id = await self.bases.get_workspace_id_for_table(automation.table_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="automation.updated", resource_type="automation",
            resource_id=str(automation.id), resource_label=automation.name,
            details={"is_enabled": automation.is_enabled},
        )
        await self.db.commit()
        return automation

    async def delete(self, *, automation_id: uuid.UUID, user_id: uuid.UUID) -> None:
        automation = await self._check_permission(automation_id, user_id)
        workspace_id = await self.bases.get_workspace_id_for_table(automation.table_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="automation.deleted", resource_type="automation",
            resource_id=str(automation.id), resource_label=automation.name,
        )
        await self.repo.delete(automation)
        await self.db.commit()

    async def create_action(
        self, *, automation_id: uuid.UUID, user_id: uuid.UUID, action_type: str, config: dict[str, Any]
    ) -> AutomationAction:
        await self._check_permission(automation_id, user_id)
        if action_type not in ACTION_TYPES:
            raise ValidationError(f"Unknown action type: {action_type}")
        existing = await self.actions.list_for_automation(automation_id)
        action = await self.actions.create(automation_id=automation_id, position=len(existing), action_type=action_type, config=config)
        await self.db.commit()
        return action

    async def list_actions(self, *, automation_id: uuid.UUID, user_id: uuid.UUID) -> list[AutomationAction]:
        automation = await self._get_or_404(automation_id)
        await self.bases.check_table_access(table_id=automation.table_id, user_id=user_id)
        return await self.actions.list_for_automation(automation_id)

    async def delete_action(self, *, automation_id: uuid.UUID, action_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self._check_permission(automation_id, user_id)
        action = await self.actions.get(action_id)
        if action is None or action.automation_id != automation_id:
            raise NotFoundError("Action not found")
        await self.actions.delete(action)
        await self.db.commit()

    async def list_runs(self, *, automation_id: uuid.UUID, user_id: uuid.UUID) -> list[AutomationRun]:
        automation = await self._get_or_404(automation_id)
        await self.bases.check_table_access(table_id=automation.table_id, user_id=user_id)
        return await self.runs.list_for_automation(automation_id)

    # -- Dispatch (internal — called from RecordService, not permission-gated) --

    async def dispatch_record_event(
        self,
        *,
        table_id: uuid.UUID,
        trigger_type: str,
        row_values: dict[str, Any],
        row_id: int,
        changed_fields: set[str] | None = None,
    ) -> None:
        # record_updated means a record's data actually changed -- committing
        # a cell back to its own existing value (click into it, blur without
        # typing anything) is a write, but not a change, and no
        # record_updated automation should fire for it, watched_fields or
        # not. changed_fields is only ever passed (non-None) for
        # record_updated (see RecordService.update_record); record_created
        # has no prior state to diff against, so this never applies there.
        if trigger_type == "record_updated" and changed_fields is not None and not changed_fields:
            return

        automations = await self.repo.list_enabled_for_table_and_trigger(table_id, trigger_type)
        if not automations:
            return

        pool = await get_arq_pool()
        for automation in automations:
            watched_fields = automation.trigger_config.get("watched_fields")
            # changed_fields is only ever passed for record_updated (the only
            # trigger watched_fields can be configured for -- see
            # _validate_trigger_config), so a configured-but-unmatched set
            # here always means "none of the watched columns were part of
            # this write."
            if watched_fields and not (changed_fields and changed_fields.intersection(watched_fields)):
                continue

            filter_expr_dict = automation.trigger_config.get("filter")
            if filter_expr_dict:
                try:
                    if not evaluate_filter(parse_filter_expr(filter_expr_dict), row_values):
                        continue
                except ValidationError:
                    continue  # a malformed stored filter shouldn't crash the write path
            await pool.enqueue_job("run_automation", str(automation.id), row_id, row_values)
