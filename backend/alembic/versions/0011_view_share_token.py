"""add share_token to views (for public form views)

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.add_column("views", sa.Column("share_token", sa.String(64), nullable=True), schema=SCHEMA)
    op.create_unique_constraint("uq_views_share_token", "views", ["share_token"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_constraint("uq_views_share_token", "views", schema=SCHEMA, type_="unique")
    op.drop_column("views", "share_token", schema=SCHEMA)
