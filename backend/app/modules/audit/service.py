import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError
from app.modules.audit.models import AuditLogEntry
from app.modules.audit.repository import AuditLogRepository
from app.modules.auth.repository import UserRepository
from app.modules.workspaces.models import WorkspaceMembership
from app.modules.workspaces.permissions import Permission, role_has_permission

DEFAULT_LIST_LIMIT = 200


class AuditService:
    """Deliberately does not depend on WorkspaceService (which would create
    app.modules.workspaces.service <-> app.modules.audit.service import
    cycle, since half of workspaces/service.py's own mutations call
    AuditService.log()) -- it only imports the workspaces *models* and the
    pure role_has_permission() function, matching the architecture plan's
    dependency order (audit sits just above auth, below workspaces)."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AuditLogRepository(db)
        self.users = UserRepository(db)

    async def log(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        resource_label: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Adds+flushes onto the caller's own session/transaction and does NOT
        commit -- the caller's existing commit (for the mutation being logged)
        covers this too, so a rollback never leaves an orphaned entry."""
        await self.repo.create(
            workspace_id=workspace_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_label=resource_label,
            details=details or {},
        )

    async def log_deferred(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None,
        action: str,
        resource_type: str,
        resource_id: str | None = None,
        resource_label: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Same audit entry as log(), but written by the arq worker instead
        of inline in the caller's own transaction -- for a hot, frequent,
        latency-sensitive path (record create/update/delete) where the audit
        trail doesn't need to block the user's response, just eventually
        exist. Enqueuing to Redis is a few round-trip-free milliseconds
        versus a full Postgres INSERT+flush on the request path (confirmed
        via load testing).

        Call this ONLY after the caller's own commit has already succeeded --
        unlike log(), a rollback after this point can't take the queued job
        back. Everywhere that isn't a hot path keeps using log() instead,
        deliberately, for its stronger same-transaction rollback guarantee."""
        from app.worker.arq_app import get_arq_pool

        pool = await get_arq_pool()
        await pool.enqueue_job(
            "write_audit_log_entry",
            workspace_id=str(workspace_id),
            user_id=str(user_id) if user_id else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_label=resource_label,
            details=details or {},
        )

    async def _require_read_permission(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id, WorkspaceMembership.user_id == user_id
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None or not role_has_permission(membership.role, Permission.AUDIT_LOG_READ):
            raise ForbiddenError("You don't have permission to view this workspace's audit log")

    async def list_for_workspace(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = DEFAULT_LIST_LIMIT,
        resource_type: str | None = None,
    ) -> tuple[list[AuditLogEntry], dict[uuid.UUID, str]]:
        await self._require_read_permission(workspace_id=workspace_id, user_id=user_id)
        entries = await self.repo.list_for_workspace(workspace_id, limit=limit, resource_type=resource_type)

        actor_emails: dict[uuid.UUID, str] = {}
        for actor_id in {e.user_id for e in entries if e.user_id is not None}:
            user = await self.users.get_by_id(actor_id)
            if user is not None:
                actor_emails[actor_id] = user.email
        return entries, actor_emails
