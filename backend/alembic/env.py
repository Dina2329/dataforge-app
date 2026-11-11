from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool, text

import app.all_models  # noqa: F401  (registers every ORM model before autogenerate runs)
from app.config import settings
from app.core.db import META_SCHEMA, Model

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Model.metadata

# Migrations run on a plain synchronous engine (psycopg2) — simpler and more
# predictable than bridging SQLAlchemy's async engine through Alembic's sync
# migration runner, and there's no benefit to async here since this only ever
# runs as a one-off CLI command, never inside the request path.
sync_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
config.set_main_option("sqlalchemy.url", sync_url)


def run_migrations_offline() -> None:
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        version_table_schema=META_SCHEMA,
        include_schemas=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(sync_url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{META_SCHEMA}"'))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=META_SCHEMA,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
