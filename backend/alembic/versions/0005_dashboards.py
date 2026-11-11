"""add dashboards and widgets tables

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "dashboards",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "widgets",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("dashboard_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.dashboards.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("widget_type", sa.String(20), nullable=False),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("position", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("widgets", schema=SCHEMA)
    op.drop_table("dashboards", schema=SCHEMA)
