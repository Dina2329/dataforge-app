import uuid
from typing import Any

import anyio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.modules.attachments.storage import get_storage
from app.modules.bases import schema_service
from app.modules.bases.models import Field, Table
from app.modules.bases.service import BasesService
from app.modules.records.schemas import RecordResponse
from app.modules.records.service import RecordService
from app.modules.workspaces.permissions import Permission

MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25MB


class AttachmentService:
    """Upload/delete write through RecordService.update_record — reusing its
    existing permission check, audit log, version bump, and automation-event
    dispatch rather than duplicating any of that here. This service only
    handles the file bytes and the read-modify-write of the attachment list."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.bases = BasesService(db)
        self.records = RecordService(db)
        self.storage = get_storage()

    async def _load_attachment_field(
        self, *, table_id: uuid.UUID, field_id: uuid.UUID, user_id: uuid.UUID, permission: Permission | None
    ) -> tuple[Table, list[Field], Field]:
        table = (
            await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=permission)
            if permission is not None
            else await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        )
        fields = await self.bases.fields.list_for_table(table_id)
        field = next((f for f in fields if f.id == field_id), None)
        if field is None:
            raise NotFoundError("Field not found")
        if field.field_type != "attachment":
            raise ValidationError(f"'{field.name}' is not an attachment field")
        return table, fields, field

    async def _current_list(self, table: Table, fields: list[Field], field: Field, row_id: int) -> list[dict[str, Any]]:
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        result = await self.db.execute(select(sa_table.c[field.db_column_name]).where(sa_table.c._row_id == row_id))
        row = result.one_or_none()
        if row is None:
            raise NotFoundError("Row not found")
        return list(row[0] or [])

    async def upload(
        self,
        *,
        table_id: uuid.UUID,
        row_id: int,
        field_id: uuid.UUID,
        user_id: uuid.UUID,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> RecordResponse:
        if len(data) > MAX_ATTACHMENT_SIZE:
            raise ValidationError(f"Attachments are limited to {MAX_ATTACHMENT_SIZE // (1024 * 1024)}MB")
        table, fields, field = await self._load_attachment_field(
            table_id=table_id, field_id=field_id, user_id=user_id, permission=Permission.RECORD_WRITE
        )
        current = await self._current_list(table, fields, field, row_id)
        storage_key = await anyio.to_thread.run_sync(lambda: self.storage.save(data=data, filename=filename))
        descriptor = {
            "id": uuid.uuid4().hex,
            "filename": filename,
            "size": len(data),
            "content_type": content_type or "application/octet-stream",
            "storage_key": storage_key,
        }
        new_list = [*current, descriptor]
        return await self.records.update_record(
            table_id=table_id, row_id=row_id, user_id=user_id, values={field.name: new_list}, expected_version=None
        )

    async def delete(
        self, *, table_id: uuid.UUID, row_id: int, field_id: uuid.UUID, attachment_id: str, user_id: uuid.UUID
    ) -> RecordResponse:
        table, fields, field = await self._load_attachment_field(
            table_id=table_id, field_id=field_id, user_id=user_id, permission=Permission.RECORD_WRITE
        )
        current = await self._current_list(table, fields, field, row_id)
        target = next((a for a in current if a["id"] == attachment_id), None)
        if target is None:
            raise NotFoundError("Attachment not found")
        new_list = [a for a in current if a["id"] != attachment_id]
        response = await self.records.update_record(
            table_id=table_id, row_id=row_id, user_id=user_id, values={field.name: new_list}, expected_version=None
        )
        await anyio.to_thread.run_sync(lambda: self.storage.delete(target["storage_key"]))
        return response

    async def download(
        self, *, table_id: uuid.UUID, row_id: int, field_id: uuid.UUID, attachment_id: str, user_id: uuid.UUID
    ) -> tuple[bytes, dict[str, Any]]:
        table, fields, field = await self._load_attachment_field(
            table_id=table_id, field_id=field_id, user_id=user_id, permission=None
        )
        current = await self._current_list(table, fields, field, row_id)
        descriptor = next((a for a in current if a["id"] == attachment_id), None)
        if descriptor is None:
            raise NotFoundError("Attachment not found")
        data = await anyio.to_thread.run_sync(lambda: self.storage.read(descriptor["storage_key"]))
        return data, descriptor
