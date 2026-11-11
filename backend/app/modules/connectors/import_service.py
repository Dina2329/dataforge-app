import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Text, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import check_circuit, record_failure, record_success
from app.core.errors import ValidationError
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.models import Field, Table
from app.modules.bases.service import BasesService
from app.modules.connectors import csv_import, excel_import
from app.modules.connectors.base import ColumnDef, ConnectorError, TableRef
from app.modules.connectors.registry import get_connector
from app.modules.connectors.repository import TableSyncConfigRepository
from app.modules.connectors.service import DataSourceService, breaker_key
from app.modules.connectors.sync_service import require_writable_source_type
from app.modules.connectors.types.sql_common import stringify_external_pk

_IMPORT_BATCH_SIZE = 2000


def coerce_external_row(raw_row: dict[str, Any], fields_by_name: dict[str, Field]) -> dict[str, Any]:
    """Raw external row dict (column name -> raw value) -> DataForge storage
    values (db_column_name -> coerced value), per field type. Shared by
    import (_insert_rows below) and Stage 2's pull-upsert
    (worker/tasks/sync_tasks.py) -- both need the exact same "external value
    -> DataForge storage value" coercion, and duplicating it would risk the
    two silently drifting apart. A column with no matching DataForge field
    (by name) is dropped, not erroring -- this is also how schema drift on
    the external side is tolerated: a new external column never appears as
    a DataForge field just because it showed up in a row."""
    db_values: dict[str, Any] = {}
    for column_name, raw_value in raw_row.items():
        field = fields_by_name.get(column_name)
        if field is None:
            continue
        field_type = get_field_type(field.field_type)
        try:
            db_values[field.db_column_name] = field_type.to_storage(raw_value, field.options)
        except ValidationError:
            # Tolerate a stray malformed cell rather than aborting the whole
            # batch -- this is a stand-in for a per-row error report.
            db_values[field.db_column_name] = None
    return db_values


class ImportService:
    """Bridges a connector's (or CSV's) introspected columns/row stream into a
    new native Table — the only place connectors and bases/records
    intentionally couple (architecture plan, section 3)."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.bases = BasesService(db)
        self.data_sources = DataSourceService(db)

    async def import_csv(self, *, base_id: uuid.UUID, table_name: str, csv_text: str, user_id: uuid.UUID) -> Table:
        columns = csv_import.introspect_csv(csv_text)
        if not columns:
            raise ValidationError("The CSV file has no columns")

        table, fields = await self._create_table_for_columns(
            base_id=base_id, table_name=table_name, user_id=user_id, columns=columns
        )
        await self._insert_rows(table, fields, csv_import.stream_csv_rows(csv_text, batch_size=_IMPORT_BATCH_SIZE), user_id)
        await self.db.commit()
        return table

    async def inspect_excel(self, *, base_id: uuid.UUID, file_bytes: bytes, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Read-only preview -- no table is created here, so this only needs
        the base to be visible to the user (any member), not schema-write.
        The real permission check happens in create_table_with_fields, inside
        import_excel_sheet, when a sheet is actually imported."""
        await self.bases.get_base(base_id=base_id, user_id=user_id)
        return excel_import.list_sheets(file_bytes)

    async def import_excel_sheet(
        self, *, base_id: uuid.UUID, table_name: str, file_bytes: bytes, sheet_name: str, user_id: uuid.UUID
    ) -> Table:
        columns = excel_import.introspect_sheet(file_bytes, sheet_name)
        if not columns:
            raise ValidationError(f"Sheet '{sheet_name}' has no columns")

        table, fields = await self._create_table_for_columns(
            base_id=base_id, table_name=table_name, user_id=user_id, columns=columns
        )
        await self._insert_rows(
            table, fields, excel_import.stream_sheet_rows(file_bytes, sheet_name, batch_size=_IMPORT_BATCH_SIZE), user_id
        )
        await self.db.commit()
        return table

    async def import_from_data_source(
        self,
        *,
        data_source_id: uuid.UUID,
        base_id: uuid.UUID,
        table_name: str,
        new_table_name: str,
        table_schema: str | None,
        user_id: uuid.UUID,
        sync_enabled: bool = False,
    ) -> Table:
        data_source, config = await self.data_sources.get_decrypted_config(data_source_id=data_source_id, user_id=user_id)
        if sync_enabled:
            require_writable_source_type(data_source.source_type)
        # This calls the connector directly rather than going through
        # DataSourceService.introspect_columns/stream_rows, so it needs its
        # own circuit-breaker check -- see call_connector's docstring.
        key = breaker_key(data_source_id)
        await check_circuit(key)

        connector = get_connector(data_source.source_type, config)
        table_ref = TableRef(name=table_name, schema=table_schema)
        try:
            columns = await connector.introspect_columns(table_ref)
            if not columns:
                raise ValidationError(f"Table '{table_name}' has no columns")
            pk_column = self._resolve_sync_pk_column(columns) if sync_enabled else None

            table, fields = await self._create_table_for_columns(
                base_id=base_id, table_name=new_table_name, user_id=user_id, columns=columns
            )
            if sync_enabled:
                await schema_service.add_sync_tracking_columns(self.db, table.physical_table_name)
                await TableSyncConfigRepository(self.db).create(
                    table_id=table.id,
                    data_source_id=data_source_id,
                    external_schema=table_schema,
                    external_table_name=table_name,
                    external_pk_column=pk_column,
                    created_by=user_id,
                )
            await self._insert_rows(
                table, fields, connector.stream_rows(table_ref, batch_size=_IMPORT_BATCH_SIZE), user_id, sync_pk_column=pk_column
            )
        except ConnectorError as exc:
            await record_failure(key)
            raise ValidationError(str(exc)) from exc
        finally:
            await connector.close()

        await record_success(key)
        await self.db.commit()
        return table

    @staticmethod
    def _resolve_sync_pk_column(columns: list[ColumnDef]) -> str:
        pk_columns = [c.name for c in columns if c.is_primary_key]
        if len(pk_columns) != 1:
            raise ValidationError(
                "Sync requires the source table to have exactly one primary key column "
                f"(found {len(pk_columns)}) — import without sync instead."
            )
        return pk_columns[0]

    async def _create_table_for_columns(
        self, *, base_id: uuid.UUID, table_name: str, user_id: uuid.UUID, columns: list
    ) -> tuple[Table, list[Field]]:
        field_defs = [
            {"name": column.name, "field_type": column.inferred_field_type, "options": {}, "required": False}
            for column in columns
        ]
        table = await self.bases.create_table_with_fields(
            base_id=base_id, name=table_name, user_id=user_id, field_defs=field_defs, assign_primary=False
        )
        fields = await self.bases.fields.list_for_table(table.id)
        return table, fields

    async def _insert_rows(
        self,
        table: Table,
        fields: list[Field],
        row_batches: AsyncIterator[list[dict[str, Any]]],
        user_id: uuid.UUID,
        sync_pk_column: str | None = None,
    ) -> None:
        fields_by_name = {f.name: f for f in fields}
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        if sync_pk_column is not None:
            # build_data_table() only knows about Field-derived columns --
            # the two reserved sync columns were added separately via raw DDL
            # (add_sync_tracking_columns), so the in-memory Table object needs
            # to know about them too before an insert can reference them.
            sa_table.append_column(Column("_external_pk", Text))
            sa_table.append_column(Column("_last_synced_at", DateTime(timezone=True)))
        now = datetime.now(timezone.utc)

        async for batch in row_batches:
            db_rows = []
            for row in batch:
                db_row: dict[str, Any] = {"_created_by": user_id}
                if sync_pk_column is not None:
                    # Stamped from the same raw source row already in hand --
                    # no separate backfill pass needed. stringify_external_pk,
                    # not a bare str(), so this matches every other call site
                    # that must produce the same string for the same PK value
                    # (push's post-insert stamp, Stage 2's pull upsert).
                    db_row["_external_pk"] = stringify_external_pk(row[sync_pk_column])
                    db_row["_last_synced_at"] = now
                db_row.update(coerce_external_row(row, fields_by_name))
                db_rows.append(db_row)
            if db_rows:
                await self.db.execute(insert(sa_table), db_rows)
