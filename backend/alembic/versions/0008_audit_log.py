"""add audit_log_entries table

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "audit_log_entries",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("resource_label", sa.String(255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_audit_log_workspace_created", "audit_log_entries", ["workspace_id", "created_at"], schema=SCHEMA
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_workspace_created", table_name="audit_log_entries", schema=SCHEMA)
    op.drop_table("audit_log_entries", schema=SCHEMA)
