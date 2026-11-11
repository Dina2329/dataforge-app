import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import RetryError

from app.core.errors import ExternalServiceError, ValidationError
from app.core.json_safe import json_safe
from app.core.webhook_client import post_json
from app.modules.audit.service import AuditService
from app.modules.bases.service import BasesService
from app.modules.record_submit.models import RecordSubmitConfig
from app.modules.record_submit.repository import RecordSubmitConfigRepository
from app.modules.records.schemas import RecordResponse
from app.modules.records.service import RecordService
from app.modules.workspaces.permissions import Permission

# Sane stamp targets only -- a status field the Submit action writes an ISO
# timestamp into has to actually hold one; anything else (number, boolean,
# single_select, ...) would need a conversion story nobody's asked for yet.
_STATUS_FIELD_TYPES = {"date", "text", "long_text"}


class RecordSubmitService:
    """Per-table "Submit row to an external API" config + the submit action
    itself. Kept separate from the automations module on purpose: automations
    are trigger-dispatched (record_created/updated/scheduled) and have no
    "manual button click" trigger, and their webhook payload is only ever the
    row's own stored values -- this needs an on-demand, synchronous call so
    the UI can show immediate success/failure, reusing the same post_json
    helper automations' send_webhook action also uses."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.bases = BasesService(db)
        self.repo = RecordSubmitConfigRepository(db)
        self.audit = AuditService(db)

    async def get_config(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> RecordSubmitConfig | None:
        await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        return await self.repo.get_for_table(table_id)

    async def upsert_config(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, url: str, headers: dict | None, status_field_id: uuid.UUID
    ) -> RecordSubmitConfig:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)

        if not url.strip() or not url.strip().lower().startswith(("http://", "https://")):
            raise ValidationError("url must be a non-empty http(s):// URL")

        status_field = await self.bases.fields.get(status_field_id)
        if status_field is None or status_field.table_id != table_id:
            raise ValidationError("status_field_id must reference a field on this table")
        if status_field.field_type not in _STATUS_FIELD_TYPES:
            raise ValidationError(f"status_field_id must reference a {'/'.join(sorted(_STATUS_FIELD_TYPES))} field")

        config = await self.repo.upsert(
            table_id=table_id, url=url.strip(), headers=headers, status_field_id=status_field_id, created_by=user_id
        )
        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="record_submit_config.updated", resource_type="table",
            resource_id=str(table_id), details={"url": config.url, "status_field_id": str(status_field_id)},
        )
        await self.db.commit()
        return config

    async def submit_row(self, *, table_id: uuid.UUID, row_id: int, user_id: uuid.UUID) -> RecordResponse:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.RECORD_WRITE)

        config = await self.repo.get_for_table(table_id)
        if config is None:
            raise ValidationError("No submit target configured for this table")

        record_service = RecordService(self.db)
        response = await record_service.get_record(table_id=table_id, row_id=row_id, user_id=user_id)

        payload = {"table_id": str(table_id), "row_id": row_id, "values": json_safe(response.values)}
        try:
            await post_json(config.url, config.headers, payload)
        except (httpx.HTTPStatusError, httpx.RequestError, RetryError) as exc:
            # post_json retries transient failures itself (tenacity); once
            # its own retries are exhausted it raises RetryError wrapping
            # the real httpx exception, not that exception directly --
            # without catching RetryError too, a genuine network failure
            # here escaped as a raw unhandled error instead of this clean
            # ExternalServiceError.
            raise ExternalServiceError(f"Submitting the row failed: {exc}") from exc

        if config.status_field_id is None:
            # The configured status field was deleted since -- still a
            # successful submit, just nothing to stamp.
            return response

        status_field = await self.bases.fields.get(config.status_field_id)
        if status_field is None or status_field.table_id != table_id:
            return response

        # A plain ISO string, not a pre-converted storage value -- update_record
        # runs this through the status field's own to_storage() internally
        # (_coerce_values), same as any other field write; pre-converting here
        # too would double-process it.
        stamp = datetime.now(timezone.utc).isoformat()
        return await record_service.update_record(
            table_id=table_id, row_id=row_id, user_id=user_id, values={status_field.name: stamp}, expected_version=None
        )
