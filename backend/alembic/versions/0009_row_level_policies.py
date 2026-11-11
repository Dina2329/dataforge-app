"""add row_level_policies table

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "row_level_policies",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filter", sa.JSON(), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("table_id", "user_id", name="uq_row_level_policy_table_user"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("row_level_policies", schema=SCHEMA)
