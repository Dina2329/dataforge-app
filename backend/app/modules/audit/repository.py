import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLogEntry


class AuditLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        resource_label: str | None,
        details: dict[str, Any],
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            workspace_id=workspace_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_label=resource_label,
            details=details,
        )
        self.db.add(entry)
        await self.db.flush()
        return entry

    async def list_for_workspace(
        self, workspace_id: uuid.UUID, *, limit: int, resource_type: str | None
    ) -> list[AuditLogEntry]:
        stmt = select(AuditLogEntry).where(AuditLogEntry.workspace_id == workspace_id)
        if resource_type:
            stmt = stmt.where(AuditLogEntry.resource_type == resource_type)
        stmt = stmt.order_by(AuditLogEntry.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
