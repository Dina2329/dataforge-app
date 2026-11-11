"""add pending_sync_changes.previous_values

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-29

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.add_column("pending_sync_changes", sa.Column("previous_values", sa.JSON(), nullable=True), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("pending_sync_changes", "previous_values", schema=SCHEMA)
