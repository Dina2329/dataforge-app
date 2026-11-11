"""add config column to views

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.add_column("views", sa.Column("config", sa.JSON(), nullable=False, server_default="{}"), schema=SCHEMA)


def downgrade() -> None:
    op.drop_column("views", "config", schema=SCHEMA)
