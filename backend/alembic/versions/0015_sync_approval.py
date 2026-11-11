"""add push approval gate + pending_sync_changes table

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.add_column(
        "table_sync_configs",
        sa.Column("push_requires_approval", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema=SCHEMA,
    )

    op.create_table(
        "pending_sync_changes",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("row_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("values", sa.JSON(), nullable=True),
        sa.Column("external_pk", sa.String(255), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("requested_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("reviewed_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        schema=SCHEMA,
    )
    # At most one row per (table_id, row_id) may be *pending* at a time (see
    # PendingSyncChangeService.request) -- enforced at the DB level, not just
    # in application logic, since two concurrent edits to the same row racing
    # to create a pending change is exactly the kind of thing a unique index
    # catches and app code might not. A partial index, not a blanket one:
    # approved/rejected rows are kept for history (so a requester can see why
    # their change was rejected), and a row can legitimately be edited again
    # after a prior change was resolved -- a non-partial unique index would
    # make that second pending change impossible to create.
    op.create_index(
        "uq_pending_sync_change_row",
        "pending_sync_changes",
        ["table_id", "row_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_pending_sync_change_row", table_name="pending_sync_changes", schema=SCHEMA)
    op.drop_table("pending_sync_changes", schema=SCHEMA)
    op.drop_column("table_sync_configs", "push_requires_approval", schema=SCHEMA)
