import uuid
from typing import Any

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.modules.audit.service import AuditService
from app.modules.backup.schemas import BaseExport, FieldExport, TableExport
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.models import Base, Field, Table
from app.modules.bases.service import BasesService
from app.modules.records.service import RecordService
from app.modules.workspaces.permissions import Permission

_EXPORT_PAGE_SIZE = 1000
_INSERT_CHUNK_SIZE = 2000


class BackupService:
    """Export/import a Base as a self-contained JSON archive (architecture
    plan, section 9: backup/restore). "Restore" deliberately always creates a
    NEW base rather than overwriting an existing one -- an in-place restore
    is exactly the kind of destructive, hard-to-reverse operation this
    project's own safety conventions call for extra caution around; importing
    into a fresh base is safe, reversible (just delete it), and just as
    useful for the "I lost my data, get it back" story."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.bases = BasesService(db)
        self.records = RecordService(db)
        self.audit = AuditService(db)

    async def export_base(self, *, base_id: uuid.UUID, user_id: uuid.UUID) -> BaseExport:
        base = await self.bases.get_base(base_id=base_id, user_id=user_id)  # require_member -- exporting is a read
        tables = await self.bases.list_tables(base_id=base_id, user_id=user_id)

        table_exports = []
        for table in tables:
            _, fields, _ = await self.bases.get_table_detail(table_id=table.id, user_id=user_id)
            plain_fields = [f for f in fields if not get_field_type(f.field_type).is_virtual]
            field_names = [f.name for f in plain_fields]
            field_exports = [
                FieldExport(name=f.name, field_type=f.field_type, options=f.options, required=f.required, is_primary=f.is_primary)
                for f in plain_fields
            ]

            # Row-level policies apply here exactly as they do in the grid --
            # list_records is the same call the API uses, so a scoped-down
            # viewer's export contains only what they could already see.
            rows: list[dict[str, Any]] = []
            cursor: int | None = None
            while True:
                page = await self.records.list_records(table_id=table.id, user_id=user_id, cursor=cursor, limit=_EXPORT_PAGE_SIZE)
                rows.extend({name: r.values.get(name) for name in field_names} for r in page.rows)
                if not page.has_more:
                    break
                cursor = page.next_cursor

            table_exports.append(TableExport(name=table.name, fields=field_exports, rows=rows))

        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="base.exported", resource_type="base",
            resource_id=str(base.id), resource_label=base.name, details={"table_count": len(table_exports)},
        )
        await self.db.commit()
        return BaseExport(name=base.name, tables=table_exports)

    async def import_base(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, data: BaseExport) -> Base:
        await self.bases.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)

        new_base = await self.bases.create_base(workspace_id=workspace_id, name=data.name, user_id=user_id)
        imported_tables = 0
        for table_export in data.tables:
            if not table_export.fields:
                continue  # a table that ended up with zero real (non-virtual) fields on export -- nothing to recreate
            # The primary field must land first: create_table_with_fields always
            # makes position 0 the primary field, regardless of what's in field_defs.
            ordered_fields = sorted(table_export.fields, key=lambda f: not f.is_primary)
            field_defs = [
                {"name": f.name, "field_type": f.field_type, "options": f.options, "required": f.required}
                for f in ordered_fields
            ]
            table = await self.bases.create_table_with_fields(
                base_id=new_base.id, name=table_export.name, user_id=user_id, field_defs=field_defs
            )
            fields = await self.bases.fields.list_for_table(table.id)
            await self._bulk_insert(table, fields, table_export.rows, user_id)
            imported_tables += 1

        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="base.imported", resource_type="base",
            resource_id=str(new_base.id), resource_label=new_base.name, details={"table_count": imported_tables},
        )
        await self.db.commit()
        return new_base

    async def _bulk_insert(self, table: Table, fields: list[Field], rows: list[dict[str, Any]], user_id: uuid.UUID) -> None:
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        fields_by_name = {f.name: f for f in fields}

        for start in range(0, len(rows), _INSERT_CHUNK_SIZE):
            chunk = rows[start : start + _INSERT_CHUNK_SIZE]
            db_rows = []
            for row_values in chunk:
                db_row: dict[str, Any] = {"_created_by": user_id}
                for field_name, raw_value in row_values.items():
                    field = fields_by_name.get(field_name)
                    if field is None:
                        continue
                    field_type = get_field_type(field.field_type)
                    try:
                        db_row[field.db_column_name] = field_type.to_storage(raw_value, field.options)
                    except ValidationError:
                        # Tolerate a stray malformed cell rather than aborting the whole import.
                        db_row[field.db_column_name] = None
                db_rows.append(db_row)
            if db_rows:
                await self.db.execute(insert(sa_table), db_rows)
