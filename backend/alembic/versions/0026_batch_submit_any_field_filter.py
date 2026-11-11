"""batch_submit_configs: replace marker_field_id with an arbitrary filter_json

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.drop_column("batch_submit_configs", "marker_field_id", schema=SCHEMA)
    op.add_column(
        "batch_submit_configs",
        sa.Column("filter_json", pg.JSON(), nullable=False, server_default="{}"),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_column("batch_submit_configs", "filter_json", schema=SCHEMA)
    op.add_column(
        "batch_submit_configs",
        sa.Column("marker_field_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.fields.id", ondelete="SET NULL"), nullable=True),
        schema=SCHEMA,
    )
