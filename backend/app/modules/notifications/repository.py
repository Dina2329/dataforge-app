import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import Notification

DEFAULT_LIST_LIMIT = 50


class NotificationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, user_id: uuid.UUID, title: str, message: str, link: str | None) -> Notification:
        notification = Notification(user_id=user_id, title=title, message=message, link=link)
        self.db.add(notification)
        await self.db.flush()
        return notification

    async def list_for_user(self, user_id: uuid.UUID, *, limit: int = DEFAULT_LIST_LIMIT) -> list[Notification]:
        stmt = select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc()).limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def unread_count(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
        return (await self.db.execute(stmt)).scalar_one()

    async def get(self, notification_id: uuid.UUID) -> Notification | None:
        return await self.db.get(Notification, notification_id)

    async def mark_all_read(self, user_id: uuid.UUID) -> None:
        await self.db.execute(
            update(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False)).values(is_read=True)
        )
