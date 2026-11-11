import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

WidgetType = Literal["bar", "line", "pie", "kpi", "table", "pivot"]
WidgetSourceType = Literal["table", "audit_log"]


class DashboardCreateRequest(BaseModel):
    name: str


class DashboardResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    share_token: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PublicDashboardResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class WidgetCreateRequest(BaseModel):
    name: str
    widget_type: WidgetType
    source_type: WidgetSourceType = "table"
    # Required when source_type == "table"; ignored (the dashboard's own
    # workspace is used instead) when source_type == "audit_log".
    table_id: uuid.UUID | None = None
    config: dict[str, Any] = {}
    position: dict[str, Any] = {"x": 0, "y": 0, "w": 4, "h": 4}


class WidgetPreviewRequest(BaseModel):
    """Same shape as the widget-specific fields of WidgetCreateRequest, minus
    name/position -- used by the Add Widget dialog to render a live chart
    preview before the widget (and its name/position) actually exist. A
    table-sourced preview needs table_id; an audit_log-sourced preview needs
    workspace_id instead (there's no table to derive it from)."""

    widget_type: WidgetType
    source_type: WidgetSourceType = "table"
    table_id: uuid.UUID | None = None
    workspace_id: uuid.UUID | None = None
    config: dict[str, Any] = {}


class WidgetUpdateRequest(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    position: dict[str, Any] | None = None


class WidgetResponse(BaseModel):
    id: uuid.UUID
    dashboard_id: uuid.UUID
    name: str
    widget_type: str
    source_type: str
    table_id: uuid.UUID | None
    config: dict[str, Any]
    position: dict[str, Any]

    model_config = {"from_attributes": True}


class PivotData(BaseModel):
    rows: list[str]
    columns: list[str]
    cells: list[list[float | int]]
    row_totals: list[float | int]
    column_totals: list[float | int]
    grand_total: float | int


class WidgetDataResponse(BaseModel):
    data: list[dict[str, Any]] | None = None
    value: Any = None
    rows: list[dict[str, Any]] | None = None
    pivot: PivotData | None = None
