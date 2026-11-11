import uuid
from datetime import datetime

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    link: str | None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    notifications: list[NotificationResponse]
    unread_count: int
