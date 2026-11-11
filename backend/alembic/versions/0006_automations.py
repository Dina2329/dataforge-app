"""add automations, automation_actions, automation_runs tables

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SCHEMA = "df_meta"


def upgrade() -> None:
    op.create_table(
        "automations",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("table_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.tables.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False),
        sa.Column("trigger_config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )

    op.create_table(
        "automation_actions",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("automation_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.automations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("action_type", sa.String(20), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        schema=SCHEMA,
    )

    op.create_table(
        "automation_runs",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("automation_id", pg.UUID(as_uuid=True), sa.ForeignKey(f"{SCHEMA}.automations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("trigger_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("error", sa.String(1000), nullable=True),
        sa.Column("ran_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema=SCHEMA,
    )
    op.create_index("ix_automation_runs_automation_id", "automation_runs", ["automation_id"], schema=SCHEMA)


def downgrade() -> None:
    op.drop_index("ix_automation_runs_automation_id", table_name="automation_runs", schema=SCHEMA)
    op.drop_table("automation_runs", schema=SCHEMA)
    op.drop_table("automation_actions", schema=SCHEMA)
    op.drop_table("automations", schema=SCHEMA)
