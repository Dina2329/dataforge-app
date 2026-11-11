"""Shared implementation for connectors reachable via a SQLAlchemy async engine
(PostgreSQL, MySQL, SQLite) — they differ only in URL/driver and excluded
system schemas, so table listing, column introspection, and row streaming are
implemented once here.
"""

from collections.abc import AsyncIterator
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import MetaData, Table as SATable, delete, inspect, insert, select, text, update
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.modules.connectors.base import BaseConnector, ColumnDef, ConnectorError, ConnectorRowNotFoundError, TableRef

STREAM_BATCH_DEFAULT = 2000


def _map_sa_type_to_field_type(sa_type: Any) -> str:
    # MySQL has no native boolean type — BOOLEAN columns round-trip as
    # TINYINT(display_width=1), which python_type reports as plain int.
    if type(sa_type).__name__ == "TINYINT" and getattr(sa_type, "display_width", None) == 1:
        return "boolean"
    try:
        py_type = sa_type.python_type
    except (NotImplementedError, AttributeError):
        return "text"
    if py_type is bool:
        return "boolean"
    if py_type in (int, float, Decimal):
        return "number"
    if py_type in (date, datetime):
        return "date"
    return "text"


def stringify_external_pk(value: Any) -> str:
    """The one canonical way to turn an external row's raw primary-key value
    into the string stored in _external_pk -- every call site that produces
    or compares this value (import, push's post-insert stamp, Stage 2's pull
    upsert and deletion diff) MUST go through this, not roll its own
    str(...). A Decimal's string form is scale-sensitive (Decimal("5") vs
    Decimal("5.00")), and a mismatch here means two representations of the
    same key silently fail to match -- see add_sync_tracking_columns' unique
    index, which exists specifically to catch this class of bug loudly
    instead of letting it insert a duplicate row."""
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return str(value)


def _coerce_pk_value(column, pk_value: Any) -> Any:
    """_external_pk is stored locally as plain TEXT (a stand-in that works
    for any PK type -- int, uuid, string), but comparing a str literal
    against e.g. a real INTEGER column fails outright on Postgres/asyncpg
    ("operator does not exist: integer = character varying") -- unlike
    SQLite, it never implicitly casts. Coerce back to the column's real
    Python type before it's ever used in a WHERE clause."""
    if not isinstance(pk_value, str):
        return pk_value
    try:
        return column.type.python_type(pk_value)
    except (NotImplementedError, ValueError, TypeError):
        return pk_value


class SqlAlchemyConnector(BaseConnector):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config)
        self._engine: AsyncEngine | None = None

    def _build_url(self) -> str:
        raise NotImplementedError

    def _schema(self) -> str | None:
        return self.config.get("schema")

    def _engine_instance(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(self._build_url(), pool_pre_ping=True)
        return self._engine

    async def test_connection(self) -> None:
        try:
            engine = self._engine_instance()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:
            raise ConnectorError(f"Could not connect: {exc}") from exc

    async def list_tables(self) -> list[TableRef]:
        engine = self._engine_instance()
        schema = self._schema()
        try:
            async with engine.connect() as conn:

                def _reflect(sync_conn):
                    inspector = inspect(sync_conn)
                    return [TableRef(name=name, schema=schema) for name in inspector.get_table_names(schema=schema)]

                return await conn.run_sync(_reflect)
        except Exception as exc:
            raise ConnectorError(f"Could not list tables: {exc}") from exc

    async def _reflect_table(self, table: TableRef) -> SATable:
        from sqlalchemy.exc import NoSuchTableError

        engine = self._engine_instance()

        def _reflect(sync_conn):
            metadata = MetaData()
            return SATable(table.name, metadata, autoload_with=sync_conn, schema=table.schema)

        try:
            async with engine.connect() as conn:
                return await conn.run_sync(_reflect)
        except NoSuchTableError as exc:
            raise ConnectorError(f"Table '{table.qualified_name}' does not exist") from exc

    async def introspect_columns(self, table: TableRef) -> list[ColumnDef]:
        try:
            sa_table = await self._reflect_table(table)
        except ConnectorError:
            raise
        except Exception as exc:
            raise ConnectorError(f"Could not introspect table '{table.name}': {exc}") from exc
        pk_columns = {col.name for col in sa_table.primary_key.columns}
        return [
            ColumnDef(
                name=col.name,
                native_type=str(col.type),
                inferred_field_type=_map_sa_type_to_field_type(col.type),
                is_primary_key=col.name in pk_columns,
            )
            for col in sa_table.columns
        ]

    async def stream_rows(self, table: TableRef, *, batch_size: int = STREAM_BATCH_DEFAULT) -> AsyncIterator[list[dict[str, Any]]]:
        sa_table = await self._reflect_table(table)
        engine = self._engine_instance()
        async with engine.connect() as conn:
            result = await conn.stream(select(sa_table))
            batch: list[dict[str, Any]] = []
            async for row in result:
                batch.append(dict(row._mapping))
                if len(batch) >= batch_size:
                    yield batch
                    batch = []
            if batch:
                yield batch

    async def get_server_time(self) -> datetime:
        """The external DB's own clock -- used as the polling watermark so
        it never has to be compared against DataForge's clock (only ever
        against this same DB's own timestamp columns, which is safe).

        MySQL/asyncmy returns a naive datetime for any TIMESTAMP-family
        value regardless of query -- CURRENT_TIMESTAMP would return the
        server's *local* time with no tzinfo attached, which is both
        ambiguous (naive) and wrong if that server isn't itself set to UTC.
        UTC_TIMESTAMP(6) sidesteps the server's configured timezone entirely
        (always UTC, by definition), and tzinfo=utc is attached explicitly
        here since the driver won't. Postgres's CURRENT_TIMESTAMP already
        returns a proper tz-aware value natively -- no adjustment needed.
        (6) matches Postgres's native microsecond precision; MySQL's bare
        CURRENT_TIMESTAMP/UTC_TIMESTAMP with no argument is only
        second-granularity."""
        engine = self._engine_instance()
        is_mysql = engine.dialect.name == "mysql"
        stmt = "SELECT UTC_TIMESTAMP(6)" if is_mysql else "SELECT CURRENT_TIMESTAMP"
        try:
            async with engine.connect() as conn:
                result = await conn.execute(text(stmt))
                server_time = result.scalar_one()
        except Exception as exc:
            raise ConnectorError(f"Could not read server time: {exc}") from exc
        if is_mysql and server_time.tzinfo is None:
            server_time = server_time.replace(tzinfo=timezone.utc)
        # A naive datetime written into a tz-aware Postgres column doesn't
        # error -- it's silently reinterpreted using whatever timezone the
        # DB session happens to be in, which is exactly how this bug shipped
        # once already (a stray naive value landed 5.5 hours off, matching
        # an IST offset, with no exception anywhere to catch it). Asserting
        # here means any future connector/dialect that forgets to attach
        # tzinfo fails loudly at the source instead of silently corrupting
        # the watermark it feeds into.
        assert server_time.tzinfo is not None, f"{type(self).__name__}.get_server_time() returned a naive datetime"
        return server_time

    async def stream_changed_rows(
        self, table: TableRef, *, updated_at_column: str, since: datetime, batch_size: int = STREAM_BATCH_DEFAULT
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Like stream_rows, but only rows whose updated_at_column is >= since.
        >=, not > -- a row exactly at the watermark gets reprocessed once
        (harmless: the caller's upsert is idempotent by _external_pk) rather
        than risking a row with the same truncated timestamp as the watermark
        being excluded from both this poll and the next one's `since`."""
        sa_table = await self._reflect_table(table)
        engine = self._engine_instance()
        try:
            async with engine.connect() as conn:
                stmt = select(sa_table).where(sa_table.c[updated_at_column] >= since)
                result = await conn.stream(stmt)
                batch: list[dict[str, Any]] = []
                async for row in result:
                    batch.append(dict(row._mapping))
                    if len(batch) >= batch_size:
                        yield batch
                        batch = []
                if batch:
                    yield batch
        except Exception as exc:
            raise ConnectorError(f"Could not read changed rows from '{table.qualified_name}': {exc}") from exc

    async def fetch_primary_keys(self, table: TableRef, pk_column: str) -> set[str]:
        """Just the primary-key column, stringified via stringify_external_pk
        -- cheap even at real table sizes, used for the deletion diff, which
        deliberately never pulls full rows to answer "does this still exist?"."""
        sa_table = await self._reflect_table(table)
        engine = self._engine_instance()
        try:
            async with engine.connect() as conn:
                result = await conn.stream(select(sa_table.c[pk_column]))
                pks: set[str] = set()
                async for row in result:
                    pks.add(stringify_external_pk(row[0]))
                return pks
        except Exception as exc:
            raise ConnectorError(f"Could not fetch primary keys from '{table.qualified_name}': {exc}") from exc

    # -- Write path (Stage 1 table sync, Postgres/MySQL only -- see
    # WRITABLE_SOURCE_TYPES in service.py, which gates who can ever reach
    # these). Unlike the read methods above, these open a real transaction
    # (engine.begin(), not engine.connect()) since a write with no commit
    # would just sit uncommitted against the external database forever.

    async def insert_row(self, table: TableRef, values: dict[str, Any]) -> Any:
        sa_table = await self._reflect_table(table)
        engine = self._engine_instance()
        try:
            async with engine.begin() as conn:
                result = await conn.execute(insert(sa_table).values(**values))
                # .returning() isn't portable here -- MySQL/asyncmy has no
                # RETURNING on INSERT. inserted_primary_key works across both
                # dialects (RETURNING under the hood on Postgres, lastrowid on
                # MySQL) and is exactly what SQLAlchemy Core provides it for.
                return result.inserted_primary_key[0]
        except Exception as exc:
            raise ConnectorError(f"Could not insert into '{table.qualified_name}': {exc}") from exc

    async def update_row(self, table: TableRef, pk_column: str, pk_value: Any, values: dict[str, Any]) -> None:
        sa_table = await self._reflect_table(table)
        pk_value = _coerce_pk_value(sa_table.c[pk_column], pk_value)
        engine = self._engine_instance()
        try:
            async with engine.begin() as conn:
                result = await conn.execute(update(sa_table).where(sa_table.c[pk_column] == pk_value).values(**values))
        except Exception as exc:
            raise ConnectorError(f"Could not update '{table.qualified_name}': {exc}") from exc
        if result.rowcount == 0:
            raise ConnectorRowNotFoundError(f"Row {pk_column}={pk_value!r} no longer exists in '{table.qualified_name}'")

    async def delete_row(self, table: TableRef, pk_column: str, pk_value: Any) -> None:
        sa_table = await self._reflect_table(table)
        pk_value = _coerce_pk_value(sa_table.c[pk_column], pk_value)
        engine = self._engine_instance()
        try:
            async with engine.begin() as conn:
                # 0 rows affected means the desired end state (row gone) is
                # already true -- unlike update, that's success, not an error.
                await conn.execute(delete(sa_table).where(sa_table.c[pk_column] == pk_value))
        except Exception as exc:
            raise ConnectorError(f"Could not delete from '{table.qualified_name}': {exc}") from exc

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
