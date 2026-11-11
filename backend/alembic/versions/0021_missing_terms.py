"""add missing terms check: prerequest_uploads, prerequest_terms,
missing_terms_configs, missing_terms_jobs, missing_terms_job_rows

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "prerequest_uploads",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"), nullable=False, unique=True
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "prerequest_terms",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("estate", sa.String(255), nullable=True),
        sa.Column("building", sa.String(255), nullable=True),
        sa.Column("unit", sa.String(255), nullable=True),
        sa.Column("sub_domain", sa.String(255), nullable=False),
        sa.Column("term_name", sa.String(255), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_prerequest_terms_workspace", "prerequest_terms", ["workspace_id"], schema=SCHEMA)

    op.create_table(
        "missing_terms_configs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False, unique=True
        ),
        sa.Column("estate", sa.String(255), nullable=True),
        sa.Column("building", sa.String(255), nullable=True),
        sa.Column("unit", sa.String(255), nullable=True),
        sa.Column("field_mapping", pg.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "missing_terms_jobs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("submitted_rows", pg.JSON(), nullable=False),
        sa.Column("response_rows", pg.JSON(), nullable=True),
        sa.Column("imported_keys", pg.JSON(), nullable=True),
        sa.Column("error", sa.String(1000), nullable=True),
        sa.Column("dismissed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    # Partial unique index, not a plain unique constraint -- only blocks a
    # genuinely ACTIVE duplicate submission of the exact same batch. The
    # moment a job reaches a terminal status this stops applying to it, so
    # resubmitting the identical set of rows later is always allowed again.
    # Same pattern as 0019's uq_pending_sync_change_row.
    op.create_index(
        "uq_missing_terms_job_active_idempotency",
        "missing_terms_jobs",
        ["table_id", "idempotency_key"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "missing_terms_job_rows",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.missing_terms_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sub_domain_norm", sa.String(255), nullable=False),
        sa.Column("term_name_norm", sa.String(255), nullable=False),
        schema=SCHEMA,
    )
    op.create_index("ix_missing_terms_job_rows_job", "missing_terms_job_rows", ["job_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_table("missing_terms_job_rows", schema=SCHEMA)
    op.drop_index("uq_missing_terms_job_active_idempotency", table_name="missing_terms_jobs", schema=SCHEMA)
    op.drop_table("missing_terms_jobs", schema=SCHEMA)
    op.drop_table("missing_terms_configs", schema=SCHEMA)
    op.drop_index("ix_prerequest_terms_workspace", table_name="prerequest_terms", schema=SCHEMA)
    op.drop_table("prerequest_terms", schema=SCHEMA)
    op.drop_table("prerequest_uploads", schema=SCHEMA)
