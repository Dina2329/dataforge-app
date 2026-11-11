"""Automation execution — runs in the arq worker, triggered either by
RecordService.dispatch_record_event() (record_created/record_updated) or by
tick_scheduled_automations() (scheduled/cron), never on the request thread.

Deliberately a linear trigger->ordered-actions chain with a fixed action
vocabulary (send_webhook, create_record, update_record) — not a generic
workflow/DAG engine (architecture plan, section 3's scope-creep risk).
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from croniter import croniter
from sqlalchemy import func, insert, select
from sqlalchemy import update as sa_update

from app.core.db import SessionLocal
from app.core.webhook_client import post_json
from app.core.ws_manager import manager as ws_manager
from app.modules.automations.models import Automation, AutomationAction
from app.modules.automations.repository import AutomationActionRepository, AutomationRepository, AutomationRunRepository
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.models import Field, Table
from app.modules.notifications.service import NotificationService


def _json_safe(values: dict[str, Any]) -> dict[str, Any]:
    """Record values can contain Decimal/date/datetime (from field_type
    .from_storage()) — none are natively JSON-serializable, which breaks both
    the webhook payload (httpx's json= uses stdlib json.dumps) and the
    AutomationRun.trigger_payload JSON column."""

    def convert(value: Any) -> Any:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        return value

    return {k: convert(v) for k, v in values.items()}


def _substitute(value: Any, row_values: dict[str, Any]) -> Any:
    """A config value of the form "{{FieldName}}" is replaced with that
    field's value from the triggering row — the only templating this
    supports, deliberately, to avoid building a general template engine."""
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        return row_values.get(value[2:-2].strip())
    return value


async def _load_fields(db, table_id: uuid.UUID) -> list[Field]:
    result = await db.execute(select(Field).where(Field.table_id == table_id))
    return list(result.scalars().all())


def _resolve_values(config_values: dict[str, Any], fields_by_name: dict[str, Field], row_values: dict[str, Any]) -> dict[str, Any]:
    db_values: dict[str, Any] = {}
    for field_name, raw in config_values.items():
        field = fields_by_name.get(field_name)
        if field is None:
            continue
        resolved = _substitute(raw, row_values)
        db_values[field.db_column_name] = get_field_type(field.field_type).to_storage(resolved, field.options)
    return db_values


async def _execute_action(db, action: AutomationAction, automation: Automation, row_id: int | None, row_values: dict[str, Any]) -> None:
    if action.action_type == "send_webhook":
        payload = {"automation_id": str(automation.id), "table_id": str(automation.table_id), "row_id": row_id, "values": row_values}
        await post_json(action.config["url"], action.config.get("headers"), payload)
        return

    if action.action_type == "create_record":
        target_table_id = uuid.UUID(action.config["target_table_id"])
        table = await db.get(Table, target_table_id)
        if table is None:
            raise ValueError(f"Target table {target_table_id} not found")
        fields = await _load_fields(db, target_table_id)
        fields_by_name = {f.name: f for f in fields}
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        db_values = _resolve_values(action.config.get("values", {}), fields_by_name, row_values)
        await db.execute(insert(sa_table).values(**db_values))
        # This writes through SQLAlchemy Core directly rather than
        # RecordService (which broadcasts on every write) -- without this,
        # anyone with the target table's grid open would only see the new
        # row after a manual reload, since there's no other refresh signal.
        await ws_manager.broadcast(target_table_id, {"row_id": None})
        return

    if action.action_type == "update_record":
        if row_id is None:
            raise ValueError("update_record requires a triggering row (not valid on scheduled automations)")
        table = await db.get(Table, automation.table_id)
        fields = await _load_fields(db, automation.table_id)
        fields_by_name = {f.name: f for f in fields}
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        db_values = _resolve_values(action.config.get("values", {}), fields_by_name, row_values)
        if db_values:
            # _updated_at must be bumped explicitly here -- it has no ON
            # UPDATE trigger, only a server_default for row creation, so a
            # direct Core UPDATE like this one is otherwise invisible to
            # anything that treats _updated_at as "this row changed" (table
            # sync's conflict detection, notably).
            await db.execute(
                sa_update(sa_table)
                .where(sa_table.c._row_id == row_id)
                .values(**db_values, _version=sa_table.c._version + 1, _updated_at=func.now())
            )
            # Same reasoning as create_record above -- this bypasses
            # RecordService, so the live grid needs its own nudge to refetch.
            await ws_manager.broadcast(automation.table_id, {"row_id": row_id})
        return

    raise ValueError(f"Unknown action type: {action.action_type}")


async def run_automation(ctx, automation_id: str, row_id: int | None, row_values: dict[str, Any]) -> None:
    row_values = _json_safe(row_values)
    automation_uuid = uuid.UUID(automation_id)
    async with SessionLocal() as db:
        automation = await db.get(Automation, automation_uuid)
        if automation is None or not automation.is_enabled:
            return

        action_repo = AutomationActionRepository(db)
        run_repo = AutomationRunRepository(db)
        actions = await action_repo.list_for_automation(automation.id)
        # Captured up front: an async session expires EVERY attribute on
        # already-loaded objects after rollback() -- including the primary
        # key -- and re-accessing one afterward tries to lazily refresh it,
        # which crashes outside a greenlet context (SQLAlchemy's async/await
        # bridge) instead of just quietly re-querying the way a sync session
        # would. automation_uuid (the function's own argument, never touching
        # the ORM object) stands in for automation.id everywhere below.
        automation_name = automation.name
        automation_created_by = automation.created_by
        automation_table_id = automation.table_id

        try:
            for action in actions:
                await _execute_action(db, action, automation, row_id, row_values)
            await db.commit()
            await run_repo.create(automation_id=automation_uuid, status="success", trigger_payload=row_values, error=None)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            error_message = str(exc)[:1000]
            await run_repo.create(automation_id=automation_uuid, status="failed", trigger_payload=row_values, error=error_message)
            await db.commit()
            # Surfaced to whoever created the automation -- they're the one
            # who can actually fix a broken webhook URL or field reference,
            # and a failure that only shows up in a "Recent runs" list nobody
            # is looking at might otherwise go unnoticed indefinitely.
            await NotificationService(db).create(
                user_id=automation_created_by,
                title=f'Automation "{automation_name}" failed',
                message=error_message,
                link=f"/tables/{automation_table_id}/automations",
            )


async def tick_scheduled_automations(ctx) -> None:
    """Runs every minute via arq's native cron_jobs. A single-replica arq
    deployment doesn't need distributed leader election for this to be safe."""
    from app.worker.arq_app import get_arq_pool

    async with SessionLocal() as db:
        repo = AutomationRepository(db)
        now = datetime.now(timezone.utc)
        due = await repo.list_due_scheduled(now)
        if not due:
            return
        pool = await get_arq_pool()
        for automation in due:
            cron = automation.trigger_config.get("cron")
            automation.next_run_at = croniter(cron, now).get_next(datetime) if cron else None
            await pool.enqueue_job("run_automation", str(automation.id), None, {})
        await db.commit()
