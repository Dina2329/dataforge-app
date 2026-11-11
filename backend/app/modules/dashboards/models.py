import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class Dashboard(Model):
    __tablename__ = "dashboards"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set when the owner creates a public share link; null means not shared.
    # Presence alone gates the public_api.py routes -- no separate is_public flag.
    share_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)


class Widget(Model):
    __tablename__ = "widgets"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dashboard_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dashboards.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    widget_type: Mapped[str] = mapped_column(String(20))  # bar|line|pie|kpi|table|pivot
    source_type: Mapped[str] = mapped_column(String(20), default="table")  # table|audit_log
    # Null only when source_type == "audit_log" -- that source has no single
    # table, it reads this widget's dashboard's own workspace_id instead
    # (see DashboardService.get_widget_data).
    table_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"), nullable=True)
    # {x_field, y_field?, aggregate: count|sum|avg|min|max, filter?: FilterExpr}
    # pivot also uses: row_field, column_field, date_granularity? (day|week|month,
    # only applied when column_field is itself a date-type field)
    # audit_log source fields are fixed: action, resource_type, resource_id,
    # resource_label, actor_email, created_at (see audit_query_service.py)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # react-grid-layout position: {x, y, w, h}
    position: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
