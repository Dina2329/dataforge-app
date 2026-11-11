"""Unauthenticated, read-only routes for dashboards the owner has explicitly
shared (see DashboardService.create_share_link). No CurrentUser dependency
anywhere in this file -- that's deliberate, not an oversight."""

import uuid

from fastapi import APIRouter, Depends

from app.core.deps import DbSession
from app.core.rate_limit import rate_limit
from app.modules.dashboards.schemas import PublicDashboardResponse, WidgetDataResponse, WidgetResponse
from app.modules.dashboards.service import DashboardService

router = APIRouter(prefix="/api/public/dashboards", tags=["public-dashboards"])

# Widget data runs a real aggregation query per call and the page auto-polls
# every 15s per widget, so the limit has to stay generous (a 6-widget
# dashboard alone is ~24 req/min from one legitimate viewer) -- this guards
# against scripted hammering, not normal viewing.
_widget_data_rate_limit = rate_limit(key_prefix="public_widget_data", max_requests=120, window_seconds=60)


@router.get("/{token}", response_model=PublicDashboardResponse)
async def get_public_dashboard(token: str, db: DbSession) -> PublicDashboardResponse:
    dashboard = await DashboardService(db).get_by_share_token(token=token)
    return PublicDashboardResponse.model_validate(dashboard)


@router.get("/{token}/widgets", response_model=list[WidgetResponse])
async def list_public_widgets(token: str, db: DbSession) -> list[WidgetResponse]:
    widgets = await DashboardService(db).list_public_widgets(token=token)
    return [WidgetResponse.model_validate(w) for w in widgets]


@router.get("/{token}/widgets/{widget_id}/data", response_model=WidgetDataResponse, dependencies=[Depends(_widget_data_rate_limit)])
async def get_public_widget_data(token: str, widget_id: uuid.UUID, db: DbSession) -> WidgetDataResponse:
    data = await DashboardService(db).get_public_widget_data(token=token, widget_id=widget_id)
    return WidgetDataResponse.model_validate(data)
