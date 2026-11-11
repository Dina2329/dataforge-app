import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.query.filter_dsl import compile_filter, parse_filter_expr
from app.modules.audit.service import AuditService
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.models import Field
from app.modules.bases.service import BasesService
from app.modules.bulk_ops.models import BulkOperation
from app.modules.bulk_ops.repository import BulkOperationRepository
from app.modules.workspaces.permissions import Permission
from app.worker.arq_app import get_arq_pool

PREVIEW_SAMPLE_SIZE = 10


class BulkOpsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bases = BasesService(db)
        self.repo = BulkOperationRepository(db)
        self.audit = AuditService(db)

    async def _prepare(self, *, table_id: uuid.UUID, user_id: uuid.UUID, filter_dict: dict[str, Any], values: dict[str, Any]):
        table = await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.BULK_OP_EXECUTE)
        fields = await self.bases.fields.list_for_table(table_id)
        fields_by_name = {f.name: f for f in fields}

        unknown = set(values) - set(fields_by_name)
        if unknown:
            raise ValidationError(f"Unknown field(s): {', '.join(sorted(unknown))}")
        for field_name, raw_value in values.items():
            field = fields_by_name[field_name]
            if field.is_primary:
                raise ValidationError("The primary field cannot be bulk-updated")
            field_type = get_field_type(field.field_type)
            if field_type.is_virtual:
                raise ValidationError(f"'{field_name}' is a computed/linked field and can't be bulk-updated")
            field_type.to_storage(raw_value, field.options)  # raises ValidationError on bad input

        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        filter_expr = parse_filter_expr(filter_dict)
        # Virtual fields have no real column to filter/select on -- compile_filter
        # already 404s cleanly on an unresolvable field name via its column map lookup.
        columns_map = {f.name: sa_table.c[f.db_column_name] for f in fields if not get_field_type(f.field_type).is_virtual}
        where_clause = compile_filter(filter_expr, columns_map)
        return table, fields, sa_table, where_clause

    async def preview(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, filter_dict: dict[str, Any], values: dict[str, Any]
    ) -> dict[str, Any]:
        _, fields, sa_table, where_clause = await self._prepare(
            table_id=table_id, user_id=user_id, filter_dict=filter_dict, values=values
        )

        matched_count = (await self.db.execute(select(func.count()).select_from(sa_table).where(where_clause))).scalar_one()
        sample_stmt = select(sa_table).where(where_clause).order_by(sa_table.c._row_id).limit(PREVIEW_SAMPLE_SIZE)
        sample_rows = (await self.db.execute(sample_stmt)).all()

        sample = []
        for row in sample_rows:
            mapping = row._mapping
            row_values = {
                f.name: get_field_type(f.field_type).from_storage(mapping[f.db_column_name], f.options)
                for f in fields
                if not get_field_type(f.field_type).is_virtual
            }
            sample.append({"row_id": mapping["_row_id"], "values": row_values})

        return {"matched_count": matched_count, "sample_rows": sample}

    async def execute(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, filter_dict: dict[str, Any], values: dict[str, Any], confirm: bool
    ) -> BulkOperation:
        if not confirm:
            raise ValidationError("Set confirm=true to execute a bulk update (preview it first)")
        if not values:
            raise ValidationError("No fields to update")

        await self._prepare(table_id=table_id, user_id=user_id, filter_dict=filter_dict, values=values)

        operation = await self.repo.create(table_id=table_id, filter_json=filter_dict, values_json=values, created_by=user_id)
        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="bulk_op.executed", resource_type="bulk_op",
            resource_id=str(operation.id), details={"table_id": str(table_id), "fields": sorted(values.keys())},
        )
        await self.db.commit()

        pool = await get_arq_pool()
        await pool.enqueue_job("run_bulk_update", str(operation.id))
        return operation

    async def get_status(self, *, operation_id: uuid.UUID, user_id: uuid.UUID) -> BulkOperation:
        operation = await self.repo.get(operation_id)
        if operation is None:
            raise NotFoundError("Bulk operation not found")
        await self.bases.check_table_access(table_id=operation.table_id, user_id=user_id)
        return operation

    async def undo(self, *, operation_id: uuid.UUID, user_id: uuid.UUID) -> BulkOperation:
        operation = await self.get_status(operation_id=operation_id, user_id=user_id)
        if operation.status != "completed":
            raise ValidationError("Only a completed operation can be undone")
        if operation.undone_at is not None:
            raise ValidationError("This operation has already been undone")

        await self.bases.check_table_permission(table_id=operation.table_id, user_id=user_id, permission=Permission.BULK_OP_EXECUTE)

        pool = await get_arq_pool()
        await pool.enqueue_job("undo_bulk_update", str(operation.id))
        return operation
