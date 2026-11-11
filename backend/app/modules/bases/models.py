import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class Base(Model):
    """An Airtable-style "base": a named grouping of Tables within a Workspace."""

    __tablename__ = "bases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Off switch for the daily automatic snapshot (snapshot_tasks.py) --
    # manual snapshots (SnapshotService.create_snapshot) are never gated by
    # this, only the unattended nightly one. Defaults true so existing bases
    # keep today's behavior unless someone opts out (e.g. a base with a
    # genuinely large table, where a full-copy snapshot every night is
    # wasted disk -- see the "each snapshot is a full copy" discussion).
    auto_snapshots_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Table(Model):
    __tablename__ = "tables"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bases.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    # Physical table name in the df_data schema, e.g. "tbl_<uuid hex>" — decoupled
    # from the user-facing `name` so renaming a table is metadata-only, no DDL.
    physical_table_name: Mapped[str] = mapped_column(String(63), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Field(Model):
    __tablename__ = "fields"
    __table_args__ = (UniqueConstraint("table_id", "db_column_name", name="uq_field_db_column"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    # Physical column name in the table's df_data table, e.g. "col_<uuid hex>".
    db_column_name: Mapped[str] = mapped_column(String(63))
    field_type: Mapped[str] = mapped_column(String(50))
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class View(Model):
    __tablename__ = "views"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    view_type: Mapped[str] = mapped_column(String(50), default="grid")
    # Serialized FilterExpr / sort spec (app.core.query.filter_dsl) — the same
    # DSL bulk_ops and automations will reuse in later phases.
    filters: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    sorts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # view_type-specific settings, e.g. kanban's {"group_field_id": "<uuid>"} --
    # generic JSON like Field.options/Automation.trigger_config, so a new view
    # type never needs its own migration.
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Set when a form view is made public (mirrors Dashboard.share_token) --
    # only form views ever populate this; grid/kanban have no public-submit story.
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
