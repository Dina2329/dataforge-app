"""add base_snapshots + base_snapshot_tables

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "base_snapshots",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("base_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(255), nullable=False),
        sa.Column("is_automatic", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_table(
        "base_snapshot_tables",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "snapshot_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.base_snapshots.id", ondelete="CASCADE"), nullable=False
        ),
        # SET NULL, not CASCADE -- deleting the live table later must never
        # delete the snapshot data that exists specifically to recover from
        # things like that deletion. See the model's own docstring.
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="SET NULL"), nullable=True),
        sa.Column("table_name", sa.String(255), nullable=False),
        sa.Column("physical_snapshot_table", sa.String(63), nullable=False),
        sa.Column("field_defs", sa.JSON(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("base_snapshot_tables", schema=SCHEMA)
    op.drop_table("base_snapshots", schema=SCHEMA)
