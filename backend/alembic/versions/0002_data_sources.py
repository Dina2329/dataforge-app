"""add data_sources table

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("config_encrypted", sa.Text(), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("data_sources", schema=SCHEMA)
