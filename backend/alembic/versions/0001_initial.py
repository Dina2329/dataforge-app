"""initial df_meta schema: auth, workspaces, bases/tables/fields/views

Revision ID: 0001
Revises:
Create Date: 2026-07-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "workspaces",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "workspace_memberships",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="owner"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_member"),
        schema=SCHEMA,
    )

    op.create_table(
        "bases",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            pg.UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "tables",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("base_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("physical_table_name", sa.String(63), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "fields",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("db_column_name", sa.String(63), nullable=False),
        sa.Column("field_type", sa.String(50), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("table_id", "db_column_name", name="uq_field_db_column"),
        schema=SCHEMA,
    )

    op.create_table(
        "views",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("view_type", sa.String(50), nullable=False, server_default="grid"),
        sa.Column("filters", sa.JSON(), nullable=True),
        sa.Column("sorts", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_table("views", schema=SCHEMA)
    op.drop_table("fields", schema=SCHEMA)
    op.drop_table("tables", schema=SCHEMA)
    op.drop_table("bases", schema=SCHEMA)
    op.drop_table("workspace_memberships", schema=SCHEMA)
    op.drop_table("workspaces", schema=SCHEMA)
    op.drop_table("users", schema=SCHEMA)
