import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.audit.schemas import AuditLogEntryResponse
from app.modules.audit.service import AuditService

router = APIRouter(tags=["audit"])


@router.get("/api/workspaces/{workspace_id}/audit-log", response_model=list[AuditLogEntryResponse])
async def list_audit_log(
    workspace_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    resource_type: str | None = None,
    limit: int = 200,
) -> list[AuditLogEntryResponse]:
    entries, actor_emails = await AuditService(db).list_for_workspace(
        workspace_id=workspace_id, user_id=current_user.id, resource_type=resource_type, limit=limit
    )
    return [
        AuditLogEntryResponse(
            id=e.id,
            workspace_id=e.workspace_id,
            user_id=e.user_id,
            actor_email=actor_emails.get(e.user_id) if e.user_id else None,
            action=e.action,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            resource_label=e.resource_label,
            details=e.details,
            created_at=e.created_at,
        )
        for e in entries
    ]
