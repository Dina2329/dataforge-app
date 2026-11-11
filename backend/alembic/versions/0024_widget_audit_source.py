"""widgets: add source_type, make table_id nullable (for audit_log-sourced widgets)

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.add_column("widgets", sa.Column("source_type", sa.String(20), nullable=False, server_default="table"), schema=SCHEMA)
    op.alter_column("widgets", "table_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=True, schema=SCHEMA)


def downgrade() -> None:
    op.alter_column("widgets", "table_id", existing_type=sa.dialects.postgresql.UUID(as_uuid=True), nullable=False, schema=SCHEMA)
    op.drop_column("widgets", "source_type", schema=SCHEMA)
