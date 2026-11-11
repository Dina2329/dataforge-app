"""add bases.auto_snapshots_enabled

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.add_column("bases", sa.Column("auto_snapshots_enabled", sa.Boolean(), nullable=False, server_default=sa.true()), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("bases", "auto_snapshots_enabled", schema=SCHEMA)
