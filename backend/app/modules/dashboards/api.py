import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.dashboards.schemas import (
    DashboardCreateRequest,
    DashboardResponse,
    WidgetCreateRequest,
    WidgetDataResponse,
    WidgetPreviewRequest,
    WidgetResponse,
    WidgetUpdateRequest,
)
from app.modules.dashboards.service import DashboardService

router = APIRouter(tags=["dashboards"])


@router.post("/api/workspaces/{workspace_id}/dashboards", response_model=DashboardResponse, status_code=201)
async def create_dashboard(workspace_id: uuid.UUID, payload: DashboardCreateRequest, current_user: CurrentUser, db: DbSession) -> DashboardResponse:
    dashboard = await DashboardService(db).create(workspace_id=workspace_id, user_id=current_user.id, name=payload.name)
    return DashboardResponse.model_validate(dashboard)


@router.get("/api/workspaces/{workspace_id}/dashboards", response_model=list[DashboardResponse])
async def list_dashboards(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[DashboardResponse]:
    dashboards = await DashboardService(db).list_for_workspace(workspace_id=workspace_id, user_id=current_user.id)
    return [DashboardResponse.model_validate(d) for d in dashboards]


@router.get("/api/dashboards/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(dashboard_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> DashboardResponse:
    dashboard = await DashboardService(db).check_dashboard_access(dashboard_id=dashboard_id, user_id=current_user.id)
    return DashboardResponse.model_validate(dashboard)


@router.delete("/api/dashboards/{dashboard_id}", status_code=204)
async def delete_dashboard(dashboard_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await DashboardService(db).delete(dashboard_id=dashboard_id, user_id=current_user.id)


@router.post("/api/dashboards/{dashboard_id}/share", response_model=DashboardResponse)
async def create_share_link(dashboard_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> DashboardResponse:
    dashboard = await DashboardService(db).create_share_link(dashboard_id=dashboard_id, user_id=current_user.id)
    return DashboardResponse.model_validate(dashboard)


@router.delete("/api/dashboards/{dashboard_id}/share", response_model=DashboardResponse)
async def revoke_share_link(dashboard_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> DashboardResponse:
    dashboard = await DashboardService(db).revoke_share_link(dashboard_id=dashboard_id, user_id=current_user.id)
    return DashboardResponse.model_validate(dashboard)


@router.post("/api/dashboards/widgets/preview", response_model=WidgetDataResponse)
async def preview_widget(payload: WidgetPreviewRequest, current_user: CurrentUser, db: DbSession) -> WidgetDataResponse:
    data = await DashboardService(db).preview_widget_data(
        user_id=current_user.id, widget_type=payload.widget_type, source_type=payload.source_type,
        table_id=payload.table_id, workspace_id=payload.workspace_id, config=payload.config,
    )
    return WidgetDataResponse.model_validate(data)


@router.get("/api/dashboards/{dashboard_id}/widgets", response_model=list[WidgetResponse])
async def list_widgets(dashboard_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[WidgetResponse]:
    widgets = await DashboardService(db).list_widgets(dashboard_id=dashboard_id, user_id=current_user.id)
    return [WidgetResponse.model_validate(w) for w in widgets]


@router.post("/api/dashboards/{dashboard_id}/widgets", response_model=WidgetResponse, status_code=201)
async def create_widget(dashboard_id: uuid.UUID, payload: WidgetCreateRequest, current_user: CurrentUser, db: DbSession) -> WidgetResponse:
    widget = await DashboardService(db).create_widget(
        dashboard_id=dashboard_id,
        user_id=current_user.id,
        name=payload.name,
        widget_type=payload.widget_type,
        source_type=payload.source_type,
        table_id=payload.table_id,
        config=payload.config,
        position=payload.position,
    )
    return WidgetResponse.model_validate(widget)


@router.patch("/api/dashboards/{dashboard_id}/widgets/{widget_id}", response_model=WidgetResponse)
async def update_widget(
    dashboard_id: uuid.UUID, widget_id: uuid.UUID, payload: WidgetUpdateRequest, current_user: CurrentUser, db: DbSession
) -> WidgetResponse:
    widget = await DashboardService(db).update_widget(
        dashboard_id=dashboard_id,
        widget_id=widget_id,
        user_id=current_user.id,
        name=payload.name,
        config=payload.config,
        position=payload.position,
    )
    return WidgetResponse.model_validate(widget)


@router.delete("/api/dashboards/{dashboard_id}/widgets/{widget_id}", status_code=204)
async def delete_widget(dashboard_id: uuid.UUID, widget_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await DashboardService(db).delete_widget(dashboard_id=dashboard_id, widget_id=widget_id, user_id=current_user.id)


@router.get("/api/dashboards/{dashboard_id}/widgets/{widget_id}/data", response_model=WidgetDataResponse)
async def get_widget_data(dashboard_id: uuid.UUID, widget_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> WidgetDataResponse:
    data = await DashboardService(db).get_widget_data(dashboard_id=dashboard_id, widget_id=widget_id, user_id=current_user.id)
    return WidgetDataResponse.model_validate(data)
