import secrets
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.modules.audit.service import AuditService
from app.modules.bases.service import BasesService
from app.modules.dashboards.models import Dashboard, Widget
from app.modules.dashboards.query_service import compute_audit_widget_data, compute_widget_data
from app.modules.dashboards.repository import DashboardRepository, WidgetRepository
from app.modules.workspaces.permissions import Permission
from app.modules.workspaces.service import WorkspaceService


class DashboardService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = DashboardRepository(db)
        self.widgets = WidgetRepository(db)
        self.bases = BasesService(db)
        self.workspaces = WorkspaceService(db)
        self.audit = AuditService(db)

    async def create(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, name: str) -> Dashboard:
        await self.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.DASHBOARD_WRITE)
        dashboard = await self.repo.create(workspace_id=workspace_id, name=name, created_by=user_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="dashboard.created", resource_type="dashboard",
            resource_id=str(dashboard.id), resource_label=name,
        )
        await self.db.commit()
        return dashboard

    async def list_for_workspace(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> list[Dashboard]:
        await self.workspaces.require_member(workspace_id=workspace_id, user_id=user_id)
        return await self.repo.list_for_workspace(workspace_id)

    async def _get_dashboard_or_404(self, dashboard_id: uuid.UUID) -> Dashboard:
        dashboard = await self.repo.get(dashboard_id)
        if dashboard is None:
            raise NotFoundError("Dashboard not found")
        return dashboard

    async def check_dashboard_access(self, *, dashboard_id: uuid.UUID, user_id: uuid.UUID) -> Dashboard:
        dashboard = await self._get_dashboard_or_404(dashboard_id)
        await self.workspaces.require_member(workspace_id=dashboard.workspace_id, user_id=user_id)
        return dashboard

    async def check_dashboard_permission(self, *, dashboard_id: uuid.UUID, user_id: uuid.UUID) -> Dashboard:
        dashboard = await self._get_dashboard_or_404(dashboard_id)
        await self.workspaces.require_permission(workspace_id=dashboard.workspace_id, user_id=user_id, permission=Permission.DASHBOARD_WRITE)
        return dashboard

    async def delete(self, *, dashboard_id: uuid.UUID, user_id: uuid.UUID) -> None:
        dashboard = await self.check_dashboard_permission(dashboard_id=dashboard_id, user_id=user_id)
        await self.audit.log(
            workspace_id=dashboard.workspace_id, user_id=user_id, action="dashboard.deleted", resource_type="dashboard",
            resource_id=str(dashboard.id), resource_label=dashboard.name,
        )
        await self.repo.delete(dashboard)
        await self.db.commit()

    async def list_widgets(self, *, dashboard_id: uuid.UUID, user_id: uuid.UUID) -> list[Widget]:
        await self.check_dashboard_access(dashboard_id=dashboard_id, user_id=user_id)
        return await self.widgets.list_for_dashboard(dashboard_id)

    async def create_widget(
        self,
        *,
        dashboard_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        widget_type: str,
        source_type: str,
        table_id: uuid.UUID | None,
        config: dict[str, Any],
        position: dict[str, Any],
    ) -> Widget:
        dashboard = await self.check_dashboard_permission(dashboard_id=dashboard_id, user_id=user_id)
        if source_type == "audit_log":
            # Audit data is sensitive -- building a widget on it needs the
            # same permission as viewing the Audit Log page itself, not just
            # "can edit this dashboard."
            await self.workspaces.require_permission(workspace_id=dashboard.workspace_id, user_id=user_id, permission=Permission.AUDIT_LOG_READ)
            table_id = None
        else:
            if table_id is None:
                raise ValidationError("table_id is required for a table-sourced widget")
            table = await self.bases.check_table_access(table_id=table_id, user_id=user_id)
            base = await self.bases.get_base(base_id=table.base_id, user_id=user_id)
            if base.workspace_id != dashboard.workspace_id:
                raise ValidationError("That table doesn't belong to this dashboard's workspace")

        widget = await self.widgets.create(
            dashboard_id=dashboard_id, name=name, widget_type=widget_type, source_type=source_type,
            table_id=table_id, config=config, position=position,
        )
        await self.db.commit()
        return widget

    async def _get_widget_or_404(self, widget_id: uuid.UUID) -> Widget:
        widget = await self.widgets.get(widget_id)
        if widget is None:
            raise NotFoundError("Widget not found")
        return widget

    async def update_widget(
        self,
        *,
        dashboard_id: uuid.UUID,
        widget_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None,
        config: dict[str, Any] | None,
        position: dict[str, Any] | None,
    ) -> Widget:
        await self.check_dashboard_permission(dashboard_id=dashboard_id, user_id=user_id)
        widget = await self._get_widget_or_404(widget_id)
        if widget.dashboard_id != dashboard_id:
            raise NotFoundError("Widget not found")

        if name is not None:
            widget.name = name
        if config is not None:
            widget.config = config
        if position is not None:
            widget.position = position
        await self.db.commit()
        return widget

    async def delete_widget(self, *, dashboard_id: uuid.UUID, widget_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.check_dashboard_permission(dashboard_id=dashboard_id, user_id=user_id)
        widget = await self._get_widget_or_404(widget_id)
        if widget.dashboard_id != dashboard_id:
            raise NotFoundError("Widget not found")
        await self.widgets.delete(widget)
        await self.db.commit()

    async def get_widget_data(self, *, dashboard_id: uuid.UUID, widget_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, Any]:
        dashboard = await self.check_dashboard_access(dashboard_id=dashboard_id, user_id=user_id)
        widget = await self._get_widget_or_404(widget_id)
        if widget.dashboard_id != dashboard_id:
            raise NotFoundError("Widget not found")

        if widget.source_type == "audit_log":
            await self.workspaces.require_permission(workspace_id=dashboard.workspace_id, user_id=user_id, permission=Permission.AUDIT_LOG_READ)
            return await compute_audit_widget_data(self.db, dashboard.workspace_id, widget)

        table, fields, _ = await self.bases.get_table_detail(table_id=widget.table_id, user_id=user_id)
        return await compute_widget_data(self.db, table, fields, widget)

    async def preview_widget_data(
        self,
        *,
        user_id: uuid.UUID,
        widget_type: str,
        source_type: str,
        table_id: uuid.UUID | None,
        workspace_id: uuid.UUID | None,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Computes the same data a real widget would, for a widget that
        doesn't exist yet (the Add Widget dialog's live preview) -- table
        access (or Audit Log read access) is enough here since nothing is
        persisted; a transient, never-added-to-session Widget just carries
        the fields compute_widget_data/compute_audit_widget_data actually
        read (widget_type, config)."""
        if source_type == "audit_log":
            if workspace_id is None:
                raise ValidationError("workspace_id is required to preview an audit_log widget")
            await self.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.AUDIT_LOG_READ)
            widget = Widget(widget_type=widget_type, source_type=source_type, config=config)
            return await compute_audit_widget_data(self.db, workspace_id, widget)

        if table_id is None:
            raise ValidationError("table_id is required to preview a table widget")
        table, fields, _ = await self.bases.get_table_detail(table_id=table_id, user_id=user_id)
        widget = Widget(widget_type=widget_type, source_type=source_type, config=config)
        return await compute_widget_data(self.db, table, fields, widget)

    # -- Public sharing --------------------------------------------------
    # A share link grants read-only, unauthenticated access to exactly one
    # dashboard's widgets/data -- the owner opts in explicitly per-dashboard.

    async def create_share_link(self, *, dashboard_id: uuid.UUID, user_id: uuid.UUID) -> Dashboard:
        dashboard = await self.check_dashboard_permission(dashboard_id=dashboard_id, user_id=user_id)
        if not dashboard.share_token:
            dashboard.share_token = secrets.token_urlsafe(24)
            await self.audit.log(
                workspace_id=dashboard.workspace_id, user_id=user_id, action="dashboard.share_link_created",
                resource_type="dashboard", resource_id=str(dashboard.id), resource_label=dashboard.name,
            )
            await self.db.commit()
        return dashboard

    async def revoke_share_link(self, *, dashboard_id: uuid.UUID, user_id: uuid.UUID) -> Dashboard:
        dashboard = await self.check_dashboard_permission(dashboard_id=dashboard_id, user_id=user_id)
        dashboard.share_token = None
        await self.audit.log(
            workspace_id=dashboard.workspace_id, user_id=user_id, action="dashboard.share_link_revoked",
            resource_type="dashboard", resource_id=str(dashboard.id), resource_label=dashboard.name,
        )
        await self.db.commit()
        return dashboard

    async def get_by_share_token(self, *, token: str) -> Dashboard:
        dashboard = await self.repo.get_by_share_token(token)
        if dashboard is None:
            raise NotFoundError("Shared dashboard not found")
        return dashboard

    async def list_public_widgets(self, *, token: str) -> list[Widget]:
        dashboard = await self.get_by_share_token(token=token)
        return await self.widgets.list_for_dashboard(dashboard.id)

    async def get_public_widget_data(self, *, token: str, widget_id: uuid.UUID) -> dict[str, Any]:
        dashboard = await self.get_by_share_token(token=token)
        widget = await self._get_widget_or_404(widget_id)
        if widget.dashboard_id != dashboard.id:
            raise NotFoundError("Widget not found")
        if widget.source_type == "audit_log":
            # Never exposed via an unauthenticated public share link,
            # regardless of who shared the dashboard -- the Audit Log's own
            # access control (Permission.AUDIT_LOG_READ) must never be
            # bypassable this way.
            raise NotFoundError("Widget not found")

        table, fields = await self.bases.get_table_fields_unchecked(table_id=widget.table_id)
        return await compute_widget_data(self.db, table, fields, widget)
