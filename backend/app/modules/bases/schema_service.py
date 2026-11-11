"""Dynamic DDL for native DataForge tables (architecture plan, section 1).

Every DataForge Table is backed by a real physical Postgres table in the
df_data schema — one real typed column per Field — rather than an EAV or
JSONB-blob design, so filtering/sorting/indexing behave like an ordinary
hand-designed schema at scale. This module is the ONLY place that issues DDL
against df_data; app.modules.records builds queries against the Table object
returned by build_data_table() but never runs DDL itself.
"""

import uuid

from sqlalchemy import BigInteger, Column, DateTime, Integer, MetaData, Table as SATable, Text, func, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateTable, DropTable

from app.core.db import DATA_SCHEMA, SNAPSHOT_SCHEMA
from app.modules.bases.field_types import get_field_type
from app.modules.bases.models import Field


def generate_physical_table_name() -> str:
    return f"tbl_{uuid.uuid4().hex}"


def generate_db_column_name() -> str:
    return f"col_{uuid.uuid4().hex}"


def generate_link_table_name() -> str:
    return f"lnk_{uuid.uuid4().hex}"


def generate_snapshot_table_name() -> str:
    return f"snap_{uuid.uuid4().hex}"


def _field_column(field: Field) -> Column:
    field_type = get_field_type(field.field_type)
    return Column(field.db_column_name, field_type.sqlalchemy_type(field.options), nullable=not field.required)


def build_data_table(physical_name: str, fields: list[Field]) -> SATable:
    """Construct a fresh SQLAlchemy Core Table reflecting current Field metadata.
    A new MetaData() is used per call — cheap, and avoids stale-cache bugs
    when fields change; caching this becomes worth it once profiling says so.
    Virtual fields (link_to_record/lookup/rollup/formula) have no real column
    and are skipped -- their values are computed separately, see
    records.service._compute_virtual_values."""
    from sqlalchemy import Uuid as UuidType

    metadata = MetaData(schema=DATA_SCHEMA)
    columns = [Column("_row_id", BigInteger, primary_key=True, autoincrement=True)]
    columns.append(Column("_created_at", DateTime(timezone=True), server_default=func.now()))
    columns.append(Column("_updated_at", DateTime(timezone=True), server_default=func.now()))
    columns.append(Column("_created_by", UuidType(as_uuid=True), nullable=True))
    columns.append(Column("_version", Integer, server_default=text("1")))
    columns.extend(_field_column(field) for field in fields if not get_field_type(field.field_type).is_virtual)
    return SATable(physical_name, metadata, *columns)


def build_sync_columns_table(physical_name: str) -> SATable:
    """A narrow view of a synced table's reserved sync-tracking columns
    (_row_id, _external_pk, _last_synced_at, _updated_at) -- everything the
    push-to-source and pull-polling worker tasks need to read/write, without
    pulling in build_data_table()'s full Field-derived column set (which they
    have no use for and would need a fields list to even construct).
    _updated_at is one of build_data_table()'s own reserved columns (added
    there, not by add_sync_tracking_columns) -- included here too since
    Stage 2's conflict detection needs to compare it against
    _last_synced_at without loading the full data table."""
    metadata = MetaData(schema=DATA_SCHEMA)
    return SATable(
        physical_name,
        metadata,
        Column("_row_id", BigInteger, primary_key=True),
        Column("_external_pk", Text),
        Column("_last_synced_at", DateTime(timezone=True)),
        Column("_updated_at", DateTime(timezone=True)),
    )


def build_link_table(link_table_name: str) -> SATable:
    """A managed many-to-many join table backing one link_to_record field:
    (left_row_id, right_row_id) pairs, left = a row on the field's own table,
    right = a row on the field's target table. The composite primary key both
    de-dupes a pair and gives an index on left_row_id for the field's own
    lookup direction (WHERE left_row_id = :row_id) -- the only direction this
    MVP queries; a reverse/symmetric field on the target table is future work."""
    metadata = MetaData(schema=DATA_SCHEMA)
    return SATable(
        link_table_name,
        metadata,
        Column("left_row_id", BigInteger, primary_key=True),
        Column("right_row_id", BigInteger, primary_key=True),
    )


async def create_link_table(db: AsyncSession, link_table_name: str) -> None:
    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DATA_SCHEMA}"'))
    await db.execute(CreateTable(build_link_table(link_table_name)))


async def drop_link_table(db: AsyncSession, link_table_name: str) -> None:
    await db.execute(DropTable(build_link_table(link_table_name), if_exists=True))


async def create_physical_table(db: AsyncSession, physical_name: str) -> None:
    empty_table = build_data_table(physical_name, fields=[])
    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{DATA_SCHEMA}"'))
    await db.execute(CreateTable(empty_table))


async def drop_physical_table(db: AsyncSession, physical_name: str) -> None:
    empty_table = build_data_table(physical_name, fields=[])
    await db.execute(DropTable(empty_table, if_exists=True))


async def add_field_column(db: AsyncSession, physical_name: str, field: Field) -> None:
    # SQLAlchemy Core has no portable "ADD COLUMN" DDL construct (unlike
    # CreateTable/DropTable), so this compiles the column type and issues raw
    # DDL — safe here because physical_name/db_column_name are always
    # internally generated hex identifiers, never user input.
    column = _field_column(field)
    type_sql = column.type.compile(dialect=postgresql.dialect())
    nullable_sql = "" if column.nullable else " NOT NULL"
    stmt = text(f'ALTER TABLE "{DATA_SCHEMA}"."{physical_name}" ADD COLUMN "{field.db_column_name}" {type_sql}{nullable_sql}')
    await db.execute(stmt)


async def add_sync_tracking_columns(db: AsyncSession, physical_name: str) -> None:
    """Adds the two reserved columns a table needs once it's linked to an
    external data source for push-to-source sync (sync_service.py) — never
    present on an ordinary table. Same raw-DDL approach as add_field_column,
    safe for the same reason: physical_name is always internally generated.

    The unique index on _external_pk is a correctness backstop, not just a
    performance one: every call site that produces this value (import,
    push's post-insert stamp, Stage 2's pull-upsert) must stringify a given
    PK the same way (see sql_common.stringify_external_pk) -- if one of them
    ever drifts, this turns a silent duplicate-inserted row into a loud
    constraint violation instead. NULL is exempt from uniqueness in Postgres
    (rows awaiting their first push, or never linked, can all be NULL at
    once), which is exactly the behavior wanted here."""
    await db.execute(text(f'ALTER TABLE "{DATA_SCHEMA}"."{physical_name}" ADD COLUMN "_external_pk" TEXT'))
    await db.execute(text(f'ALTER TABLE "{DATA_SCHEMA}"."{physical_name}" ADD COLUMN "_last_synced_at" TIMESTAMPTZ'))
    await db.execute(
        text(f'CREATE UNIQUE INDEX "{physical_name}_external_pk_idx" ON "{DATA_SCHEMA}"."{physical_name}" ("_external_pk")')
    )


async def drop_field_column(db: AsyncSession, physical_name: str, field: Field) -> None:
    stmt = text(f'ALTER TABLE "{DATA_SCHEMA}"."{physical_name}" DROP COLUMN "{field.db_column_name}"')
    await db.execute(stmt)


async def create_snapshot_copy(db: AsyncSession, snapshot_physical_name: str, source_physical_name: str) -> None:
    """A base snapshot's per-table storage: a byte-for-byte structural +
    data copy of one df_data table, taken with a single CREATE TABLE ... AS
    SELECT (a server-side copy, not a row-by-row read+reinsert -- fast even
    for a large table, and atomic). physical_name/source_physical_name are
    always internally generated hex identifiers, never user input, so this
    raw-SQL string build is the same safe pattern as add_field_column."""
    await db.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SNAPSHOT_SCHEMA}"'))
    await db.execute(
        text(
            f'CREATE TABLE "{SNAPSHOT_SCHEMA}"."{snapshot_physical_name}" AS '
            f'SELECT * FROM "{DATA_SCHEMA}"."{source_physical_name}"'
        )
    )


async def drop_snapshot_copy(db: AsyncSession, snapshot_physical_name: str) -> None:
    await db.execute(text(f'DROP TABLE IF EXISTS "{SNAPSHOT_SCHEMA}"."{snapshot_physical_name}"'))
