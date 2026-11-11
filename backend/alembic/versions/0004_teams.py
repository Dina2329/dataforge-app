"""add teams and team_memberships tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "team_memberships",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("team_memberships", schema=SCHEMA)
    op.drop_table("teams", schema=SCHEMA)
