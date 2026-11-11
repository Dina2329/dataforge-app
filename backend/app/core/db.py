from collections.abc import AsyncGenerator

from sqlalchemy import MetaData
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Fixed-schema metadata (users, workspaces, tables/fields/views definitions, connectors, jobs...)
# lives in the "df_meta" Postgres schema. Dynamic per-table data lives in "df_data",
# built at runtime by modules/bases/schema_service.py — kept out of the ORM entirely.
META_SCHEMA = "df_meta"
DATA_SCHEMA = "df_data"
# Base-snapshot copies (modules/snapshots) -- each is a raw CREATE TABLE ... AS
# SELECT * FROM <df_data table>, kept in its own schema rather than df_data so
# "every table in df_data is a live, currently-in-use Table" stays true; a
# snapshot copy is neither.
SNAPSHOT_SCHEMA = "df_snapshots"

# pool_pre_ping is deliberately omitted: its connection-validation ping runs
# outside SQLAlchemy's greenlet bridge for the asyncpg dialect and raises
# MissingGreenlet in worker processes (confirmed via a real automation-run
# failure). Not worth it at this deployment scale — a single self-hosted
# Postgres instance rarely drops idle connections underneath us.
engine = create_async_engine(
    settings.database_url,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


class Model(DeclarativeBase):
    """Declarative base for all fixed-schema (df_meta) ORM models."""

    metadata = MetaData(schema=META_SCHEMA)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
