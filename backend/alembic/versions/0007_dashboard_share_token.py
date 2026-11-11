"""add share_token to dashboards

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.add_column("dashboards", sa.Column("share_token", sa.String(64), nullable=True), schema=SCHEMA)
    op.create_unique_constraint("uq_dashboards_share_token", "dashboards", ["share_token"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_constraint("uq_dashboards_share_token", "dashboards", schema=SCHEMA, type_="unique")
    op.drop_column("dashboards", "share_token", schema=SCHEMA)
