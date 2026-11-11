"""add record_submit_configs table

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "record_submit_configs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False, unique=True
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("headers", pg.JSON(), nullable=True),
        # SET NULL, not CASCADE/RESTRICT -- deleting the status field should
        # only disable stamping, never block deleting the field or break this
        # config (see RecordSubmitService.submit_row's None-handling).
        sa.Column(
            "status_field_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.fields.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("record_submit_configs", schema=SCHEMA)
