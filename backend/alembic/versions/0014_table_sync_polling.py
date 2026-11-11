"""add table sync polling fields

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"
TABLE = "table_sync_configs"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("external_updated_at_column", sa.String(255), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("poll_interval_seconds", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)

    op.add_column(TABLE, sa.Column("deletion_check_interval_seconds", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("next_deletion_check_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)

    # Pull health is tracked independently of push's existing sync_enabled/
    # consecutive_failures -- see sync_tasks.py -- so a broken poll can never
    # silently disable a healthy push, or vice versa.
    op.add_column(TABLE, sa.Column("poll_paused", sa.Boolean(), nullable=False, server_default=sa.false()), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("poll_consecutive_failures", sa.Integer(), nullable=False, server_default="0"), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("poll_last_error", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("poll_last_error_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    for col in (
        "poll_last_error_at",
        "poll_last_error",
        "poll_consecutive_failures",
        "poll_paused",
        "next_deletion_check_at",
        "deletion_check_interval_seconds",
        "next_poll_at",
        "last_polled_at",
        "poll_interval_seconds",
        "external_updated_at_column",
    ):
        op.drop_column(TABLE, col, schema=SCHEMA)
