import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class Notification(Model):
    """A per-user inbox item -- deliberately narrow in scope (no read/unread
    sync across devices beyond the DB row, no push delivery) since the only
    producer today is an automation run failing. `link` is an app-relative
    path (e.g. /tables/{id}/automations), not a full URL, since it's always
    opened from inside the app that already knows its own origin."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_created", "user_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(String(1000))
    link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
