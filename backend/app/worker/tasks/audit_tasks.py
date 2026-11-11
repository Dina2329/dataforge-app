"""Background audit-log writes.

Enqueued from the hot record create/update/delete path (see
AuditService.log_deferred) instead of being written inline in the same
transaction as the mutation being logged. An audit entry doesn't need to be
durable *before* the user's response returns, just durable *eventually* --
which is exactly why this goes through the arq/Redis queue rather than a bare
asyncio.create_task: a fire-and-forget in-process task would silently lose
the entry if the process restarted before it got a chance to run, and an
audit trail that can vanish isn't much of one. Everywhere else, AuditService.log()
still writes inline in the caller's own transaction, deliberately -- see its
docstring on why non-hot-path mutations keep the stronger "rolls back
together with what it's logging" guarantee.
"""

import uuid
from typing import Any

from app.core.db import SessionLocal
from app.modules.audit.repository import AuditLogRepository


async def write_audit_log_entry(
    ctx: dict,
    *,
    workspace_id: str,
    user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None,
    resource_label: str | None,
    details: dict[str, Any],
) -> None:
    async with SessionLocal() as db:
        repo = AuditLogRepository(db)
        await repo.create(
            workspace_id=uuid.UUID(workspace_id),
            user_id=uuid.UUID(user_id) if user_id else None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_label=resource_label,
            details=details,
        )
        await db.commit()
