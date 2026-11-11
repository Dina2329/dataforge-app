import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.dashboards.models import Dashboard, Widget


class DashboardRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, workspace_id: uuid.UUID, name: str, created_by: uuid.UUID) -> Dashboard:
        dashboard = Dashboard(workspace_id=workspace_id, name=name, created_by=created_by)
        self.db.add(dashboard)
        await self.db.flush()
        return dashboard

    async def list_for_workspace(self, workspace_id: uuid.UUID) -> list[Dashboard]:
        result = await self.db.execute(select(Dashboard).where(Dashboard.workspace_id == workspace_id))
        return list(result.scalars().all())

    async def get(self, dashboard_id: uuid.UUID) -> Dashboard | None:
        return await self.db.get(Dashboard, dashboard_id)

    async def get_by_share_token(self, token: str) -> Dashboard | None:
        result = await self.db.execute(select(Dashboard).where(Dashboard.share_token == token))
        return result.scalar_one_or_none()

    async def delete(self, dashboard: Dashboard) -> None:
        await self.db.delete(dashboard)
        await self.db.flush()


class WidgetRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        dashboard_id: uuid.UUID,
        name: str,
        widget_type: str,
        source_type: str,
        table_id: uuid.UUID | None,
        config: dict[str, Any],
        position: dict[str, Any],
    ) -> Widget:
        widget = Widget(
            dashboard_id=dashboard_id, name=name, widget_type=widget_type, source_type=source_type,
            table_id=table_id, config=config, position=position,
        )
        self.db.add(widget)
        await self.db.flush()
        return widget

    async def list_for_dashboard(self, dashboard_id: uuid.UUID) -> list[Widget]:
        result = await self.db.execute(select(Widget).where(Widget.dashboard_id == dashboard_id))
        return list(result.scalars().all())

    async def get(self, widget_id: uuid.UUID) -> Widget | None:
        return await self.db.get(Widget, widget_id)

    async def delete(self, widget: Widget) -> None:
        await self.db.delete(widget)
        await self.db.flush()
