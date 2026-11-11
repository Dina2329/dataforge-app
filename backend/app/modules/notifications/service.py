import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.modules.notifications.models import Notification
from app.modules.notifications.repository import NotificationRepository


class NotificationService:
    """Always scoped to the requesting user's own id -- there's no
    workspace/role permission model here, a notification is either yours or
    it doesn't exist as far as you're concerned."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = NotificationRepository(db)

    async def create(self, *, user_id: uuid.UUID, title: str, message: str, link: str | None = None) -> Notification:
        notification = await self.repo.create(user_id=user_id, title=title, message=message, link=link)
        await self.db.commit()
        return notification

    async def list_for_user(self, *, user_id: uuid.UUID) -> tuple[list[Notification], int]:
        notifications = await self.repo.list_for_user(user_id)
        unread = await self.repo.unread_count(user_id)
        return notifications, unread

    async def mark_read(self, *, notification_id: uuid.UUID, user_id: uuid.UUID) -> None:
        notification = await self.repo.get(notification_id)
        if notification is None or notification.user_id != user_id:
            raise NotFoundError("Notification not found")
        notification.is_read = True
        await self.db.commit()

    async def mark_all_read(self, *, user_id: uuid.UUID) -> None:
        await self.repo.mark_all_read(user_id)
        await self.db.commit()
