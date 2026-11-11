"""add missing_terms_api_configs table (per-workspace, admin-editable,
replaces the MISSING_TERMS_API_URL env var as the source of truth)

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "missing_terms_api_configs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"), nullable=False, unique=True
        ),
        sa.Column("api_url", sa.String(2048), nullable=False),
        sa.Column("headers", pg.JSON(), nullable=True),
        sa.Column("updated_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("missing_terms_api_configs", schema=SCHEMA)
