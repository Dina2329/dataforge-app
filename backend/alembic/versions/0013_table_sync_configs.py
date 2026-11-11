"""add table_sync_configs table

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "table_sync_configs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False, unique=True
        ),
        # CASCADE at the DB level (so deleting a whole workspace correctly
        # sweeps away its data sources' sync configs along with everything
        # else in one statement) -- the "don't delete a data source out from
        # under a live sync without saying so" guard is enforced in
        # DataSourceService.delete() instead, one level up, where it can
        # target that specific action without fighting workspace deletion's
        # own cascade.
        sa.Column(
            "data_source_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.data_sources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("external_schema", sa.String(255), nullable=True),
        sa.Column("external_table_name", sa.String(255), nullable=False),
        sa.Column("external_pk_column", sa.String(255), nullable=False),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("table_sync_configs", schema=SCHEMA)
