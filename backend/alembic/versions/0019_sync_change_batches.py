"""add sync_change_batches + pending_sync_changes.batch_id, switch to a
draft/submit workflow

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-29

"""
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "sync_change_batches",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("requested_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("reviewed_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        schema=SCHEMA,
    )

    op.add_column(
        "pending_sync_changes",
        sa.Column("batch_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.sync_change_batches.id", ondelete="CASCADE"), nullable=True),
        schema=SCHEMA,
    )
    op.alter_column("pending_sync_changes", "status", schema=SCHEMA, server_default="draft")

    # Existing unreviewed rows predate the draft/submit split entirely --
    # they were created under the old "every edit is immediately visible to
    # approvers" model, so they're already conceptually "submitted." Group
    # them by (requested_by, workspace) and auto-create one batch per group
    # rather than orphaning them out of the approval queue.
    bind = op.get_bind()
    groups = bind.execute(
        sa.text(
            f"""
            SELECT DISTINCT psc.requested_by, b.workspace_id
            FROM {SCHEMA}.pending_sync_changes psc
            JOIN {SCHEMA}.tables t ON t.id = psc.table_id
            JOIN {SCHEMA}.bases b ON b.id = t.base_id
            WHERE psc.status = 'pending' AND psc.batch_id IS NULL
            """
        )
    ).fetchall()
    for requested_by, workspace_id in groups:
        batch_id = uuid.uuid4()
        bind.execute(
            sa.text(
                f"""
                INSERT INTO {SCHEMA}.sync_change_batches (id, workspace_id, status, requested_by, submitted_at)
                VALUES (:id, :workspace_id, 'pending', :requested_by, now())
                """
            ),
            {"id": batch_id, "workspace_id": workspace_id, "requested_by": requested_by},
        )
        bind.execute(
            sa.text(
                f"""
                UPDATE {SCHEMA}.pending_sync_changes psc
                SET batch_id = :batch_id
                FROM {SCHEMA}.tables t, {SCHEMA}.bases b
                WHERE psc.table_id = t.id AND t.base_id = b.id
                  AND psc.status = 'pending' AND psc.batch_id IS NULL
                  AND psc.requested_by = :requested_by AND b.workspace_id = :workspace_id
                """
            ),
            {"batch_id": batch_id, "requested_by": requested_by, "workspace_id": workspace_id},
        )

    # A row can be collapsed into (draft or pending), not just pending --
    # the old index only ever allowed one true row per (table_id, row_id)
    # while "pending"; now the same must hold while "draft" too.
    op.drop_index("uq_pending_sync_change_row", table_name="pending_sync_changes", schema=SCHEMA)
    op.create_index(
        "uq_pending_sync_change_row",
        "pending_sync_changes",
        ["table_id", "row_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status IN ('draft', 'pending')"),
    )


def downgrade() -> None:
    op.drop_index("uq_pending_sync_change_row", table_name="pending_sync_changes", schema=SCHEMA)
    op.create_index(
        "uq_pending_sync_change_row",
        "pending_sync_changes",
        ["table_id", "row_id"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.alter_column("pending_sync_changes", "status", schema=SCHEMA, server_default="pending")
    op.drop_column("pending_sync_changes", "batch_id", schema=SCHEMA)
    op.drop_table("sync_change_batches", schema=SCHEMA)
