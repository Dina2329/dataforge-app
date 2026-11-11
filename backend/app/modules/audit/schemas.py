import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogEntryResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    user_id: uuid.UUID | None
    actor_email: str | None
    action: str
    resource_type: str
    resource_id: str | None
    resource_label: str | None
    details: dict[str, Any]
    created_at: datetime
