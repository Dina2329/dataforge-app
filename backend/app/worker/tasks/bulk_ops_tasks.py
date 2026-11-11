"""Bulk update execution — runs in the arq worker, never the request thread
(architecture plan, section 4). Generalizes the CASE-WHEN single-statement
technique proven in the workspace's existing bulk_update/app.py tool: forward
updates apply one uniform value so a single UPDATE per chunk suffices, while
undo (each row restoring its own captured old value) needs CASE-WHEN.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case, func, select, update

from app.core.db import SessionLocal
from app.core.json_safe import json_safe
from app.core.query.filter_dsl import parse_filter_expr, compile_filter
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.models import Field, Table
from app.modules.bulk_ops.models import BulkOperation, BulkOperationLog

CHUNK_SIZE = 2000
MAX_BULK_ROWS = 200_000


async def _load_fields(db, table_id: uuid.UUID) -> list[Field]:
    result = await db.execute(select(Field).where(Field.table_id == table_id))
    return list(result.scalars().all())


async def run_bulk_update(ctx, bulk_operation_id: str) -> None:
    async with SessionLocal() as db:
        operation = await db.get(BulkOperation, uuid.UUID(bulk_operation_id))
        if operation is None:
            return

        try:
            operation.status = "running"
            await db.commit()

            table = await db.get(Table, operation.table_id)
            fields = await _load_fields(db, table.id)
            fields_by_name = {f.name: f for f in fields}
            sa_table = schema_service.build_data_table(table.physical_table_name, fields)

            filter_expr = parse_filter_expr(operation.filter_json)
            columns_map = {f.name: sa_table.c[f.db_column_name] for f in fields if not get_field_type(f.field_type).is_virtual}
            where_clause = compile_filter(filter_expr, columns_map)

            new_values_by_db_col: dict[str, object] = {}
            for field_name, raw_value in operation.values_json.items():
                field = fields_by_name[field_name]
                field_type = get_field_type(field.field_type)
                new_values_by_db_col[field.db_column_name] = field_type.to_storage(raw_value, field.options)
            changed_db_cols = list(new_values_by_db_col.keys())

            count_result = await db.execute(select(func.count()).select_from(sa_table).where(where_clause))
            matched_count = count_result.scalar_one()
            if matched_count > MAX_BULK_ROWS:
                raise ValueError(
                    f"This operation would affect {matched_count:,} rows, over the {MAX_BULK_ROWS:,}-row bulk update limit. "
                    "Narrow the filter and try again."
                )

            select_cols = [sa_table.c._row_id, *[sa_table.c[c] for c in changed_db_cols]]
            rows = (await db.execute(select(*select_cols).where(where_clause))).all()

            affected_count = 0
            for start in range(0, len(rows), CHUNK_SIZE):
                chunk = rows[start : start + CHUNK_SIZE]
                row_ids = [r._mapping["_row_id"] for r in chunk]

                db.add_all(
                    BulkOperationLog(
                        batch_id=operation.id,
                        table_id=table.id,
                        row_id=r._mapping["_row_id"],
                        old_values={col: json_safe(r._mapping[col]) for col in changed_db_cols},
                    )
                    for r in chunk
                )

                stmt = (
                    update(sa_table)
                    .where(sa_table.c._row_id.in_(row_ids))
                    .values(**new_values_by_db_col, _version=sa_table.c._version + 1, _updated_at=func.now())
                )
                result = await db.execute(stmt)
                affected_count += result.rowcount
                await db.commit()

            operation.status = "completed"
            operation.matched_count = matched_count
            operation.affected_count = affected_count
            operation.completed_at = datetime.now(timezone.utc)
            await db.commit()
        except Exception as exc:
            await db.rollback()
            operation.status = "failed"
            operation.error = str(exc)[:1000]
            await db.commit()


async def undo_bulk_update(ctx, bulk_operation_id: str) -> None:
    async with SessionLocal() as db:
        operation = await db.get(BulkOperation, uuid.UUID(bulk_operation_id))
        if operation is None or operation.status != "completed" or operation.undone_at is not None:
            return

        table = await db.get(Table, operation.table_id)
        fields = await _load_fields(db, table.id)
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        fields_by_db_col = {f.db_column_name: f for f in fields}

        logs = list(
            (await db.execute(select(BulkOperationLog).where(BulkOperationLog.batch_id == operation.id))).scalars().all()
        )

        for start in range(0, len(logs), CHUNK_SIZE):
            chunk = logs[start : start + CHUNK_SIZE]
            # A field may have been deleted since the bulk update ran — its column
            # no longer exists, so that piece of history is simply unrestorable.
            changed_cols = {col for log in chunk for col in log.old_values if col in fields_by_db_col}

            def _restore(col: str, raw: Any) -> Any:
                field = fields_by_db_col[col]
                return get_field_type(field.field_type).to_storage(raw, field.options)

            case_values = {
                col: case(
                    *[
                        (sa_table.c._row_id == log.row_id, _restore(col, log.old_values[col]))
                        for log in chunk
                        if col in log.old_values
                    ],
                    else_=sa_table.c[col],
                )
                for col in changed_cols
            }
            row_ids = [log.row_id for log in chunk]
            stmt = (
                update(sa_table)
                .where(sa_table.c._row_id.in_(row_ids))
                .values(**case_values, _version=sa_table.c._version + 1, _updated_at=func.now())
            )
            await db.execute(stmt)
            await db.commit()

        operation.undone_at = datetime.now(timezone.utc)
        await db.commit()
