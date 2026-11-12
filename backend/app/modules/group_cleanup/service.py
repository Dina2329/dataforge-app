import uuid
from typing import Any

from sqlalchemy import String, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.modules.audit.service import AuditService
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.service import BasesService
from app.modules.workspaces.permissions import Permission

SAMPLE_SIZE = 20


class GroupCleanupService:
    """"Move to missing term": deletes a table's rows wherever every row
    sharing one group field's value (e.g. a component code) has an empty
    value field AND a zero score field -- a data point an extraction
    pipeline matched nothing for at all. A group with even one populated
    row, or a non-zero score anywhere in it, is left completely untouched.

    Nothing here is tied to any one table's schema -- group/value/score are
    just field names the caller picks per use, re-selected each time rather
    than saved as per-table config (this is a one-off cleanup action, not an
    ongoing per-table feature like Batch Submit/Missing Terms Check)."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.bases = BasesService(db)
        self.audit = AuditService(db)

    async def _resolve(self, *, table_id: uuid.UUID, user_id: uuid.UUID, group_field: str, value_field: str, score_field: str):
        table = await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.RECORD_DELETE)
        fields = await self.bases.fields.list_for_table(table_id)
        fields_by_name = {f.name: f for f in fields}

        for name in (group_field, value_field, score_field):
            field = fields_by_name.get(name)
            if field is None or get_field_type(field.field_type).is_virtual:
                raise ValidationError(f"Unknown or non-filterable field: {name}")

        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        group_col = sa_table.c[fields_by_name[group_field].db_column_name]
        value_col = sa_table.c[fields_by_name[value_field].db_column_name]
        score_col = sa_table.c[fields_by_name[score_field].db_column_name]
        return table, sa_table, group_col, value_col, score_col

    async def _qualifying_group_values(self, *, sa_table, group_col, value_col, score_col) -> list[Any]:
        # "Empty" matches this app's own "--" display convention for a blank
        # cell: NULL, or an empty/whitespace-only string once cast to text
        # (covers text/single_select-typed value fields; a real non-null
        # number or date never collapses to "" here, so it's never wrongly
        # treated as empty).
        is_empty = or_(value_col.is_(None), func.trim(cast(value_col, String)) == "")
        is_zero = score_col == 0
        stmt = (
            select(group_col)
            .select_from(sa_table)
            .group_by(group_col)
            .having(func.bool_and(is_empty) & func.bool_and(is_zero))
        )
        return [row[0] for row in (await self.db.execute(stmt)).all()]

    async def preview(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, group_field: str, value_field: str, score_field: str
    ) -> dict[str, Any]:
        _, sa_table, group_col, value_col, score_col = await self._resolve(
            table_id=table_id, user_id=user_id, group_field=group_field, value_field=value_field, score_field=score_field
        )
        qualifying = await self._qualifying_group_values(sa_table=sa_table, group_col=group_col, value_col=value_col, score_col=score_col)
        rows_to_delete = 0
        if qualifying:
            rows_to_delete = (
                await self.db.execute(select(func.count()).select_from(sa_table).where(group_col.in_(qualifying)))
            ).scalar_one()
        return {
            "group_field": group_field,
            "value_field": value_field,
            "score_field": score_field,
            "qualifying_groups": len(qualifying),
            "rows_to_delete": rows_to_delete,
            "sample_group_values": [str(v) for v in qualifying[:SAMPLE_SIZE]],
        }

    async def execute(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, group_field: str, value_field: str, score_field: str
    ) -> dict[str, int]:
        table, sa_table, group_col, value_col, score_col = await self._resolve(
            table_id=table_id, user_id=user_id, group_field=group_field, value_field=value_field, score_field=score_field
        )
        qualifying = await self._qualifying_group_values(sa_table=sa_table, group_col=group_col, value_col=value_col, score_col=score_col)
        if not qualifying:
            return {"groups_deleted": 0, "rows_deleted": 0}

        rows_to_delete = (
            await self.db.execute(select(func.count()).select_from(sa_table).where(group_col.in_(qualifying)))
        ).scalar_one()
        await self.db.execute(delete(sa_table).where(group_col.in_(qualifying)))

        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        await self.audit.log(
            workspace_id=workspace_id,
            user_id=user_id,
            action="records.group_cleanup_deleted",
            resource_type="table",
            resource_id=str(table_id),
            resource_label=f'{table.name}: "Move to missing term"',
            details={
                "group_field": group_field,
                "value_field": value_field,
                "score_field": score_field,
                "groups_deleted": len(qualifying),
                "rows_deleted": rows_to_delete,
            },
        )
        await self.db.commit()
        return {"groups_deleted": len(qualifying), "rows_deleted": rows_to_delete}
