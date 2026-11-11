"""add bulk_operations and bulk_operation_logs tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "bulk_operations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filter_json", sa.JSON(), nullable=False),
        sa.Column("values_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("matched_count", sa.BigInteger(), nullable=True),
        sa.Column("affected_count", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.String(1000), nullable=True),
        sa.Column("undone_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )

    op.create_table(
        "bulk_operation_logs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "batch_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.bulk_operations.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_id", sa.BigInteger(), nullable=False),
        sa.Column("old_values", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_bulk_operation_logs_batch_id", "bulk_operation_logs", ["batch_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_bulk_operation_logs_batch_id", table_name="bulk_operation_logs", schema=SCHEMA)
    op.drop_table("bulk_operation_logs", schema=SCHEMA)
    op.drop_table("bulk_operations", schema=SCHEMA)
