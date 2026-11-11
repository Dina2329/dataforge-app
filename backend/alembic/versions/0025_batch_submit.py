"""add batch_submit_configs, batch_submit_jobs

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "batch_submit_configs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False, unique=True
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("headers", pg.JSON(), nullable=True),
        sa.Column("marker_field_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.fields.id", ondelete="SET NULL"), nullable=True),
        sa.Column("batch_size", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "batch_submit_jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("batch_size", sa.Integer(), nullable=False),
        sa.Column("total_rows", sa.BigInteger(), nullable=True),
        sa.Column("total_batches", sa.Integer(), nullable=True),
        sa.Column("sent_batches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_batches", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("batch_results", pg.JSON(), nullable=False, server_default="[]"),
        sa.Column("error", sa.String(1000), nullable=True),
        sa.Column("dismissed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    # Partial unique index, not a plain unique constraint -- only blocks
    # starting a SECOND batch send for a table while one is genuinely
    # active; once a job reaches any terminal status, a new one is always
    # allowed. Same pattern as missing_terms' uq_missing_terms_job_active_idempotency.
    op.create_index(
        "uq_batch_submit_job_active_per_table",
        "batch_submit_jobs",
        ["table_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    op.drop_index("uq_batch_submit_job_active_per_table", table_name="batch_submit_jobs", schema=SCHEMA)
    op.drop_table("batch_submit_jobs", schema=SCHEMA)
    op.drop_table("batch_submit_configs", schema=SCHEMA)
