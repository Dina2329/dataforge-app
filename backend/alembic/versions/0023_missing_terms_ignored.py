"""add missing_terms_ignored_terms

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "missing_terms_ignored_terms",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sub_domain", sa.String(255), nullable=False),
        sa.Column("term_name", sa.String(255), nullable=False),
        sa.Column("sub_domain_norm", sa.String(255), nullable=False),
        sa.Column("term_name_norm", sa.String(255), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("table_id", "sub_domain_norm", "term_name_norm", name="uq_missing_terms_ignored_term"),
        schema=SCHEMA,
    )
    op.create_index("ix_missing_terms_ignored_terms_table", "missing_terms_ignored_terms", ["table_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_missing_terms_ignored_terms_table", table_name="missing_terms_ignored_terms", schema=SCHEMA)
    op.drop_table("missing_terms_ignored_terms", schema=SCHEMA)
