import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class AuditLogEntry(Model):
    """Append-only record of who did what, when (architecture plan, section 5).
    Written via AuditService.log() from the same transaction as the mutation
    it records -- never on its own commit, so a rolled-back action never
    leaves an orphaned entry."""

    __tablename__ = "audit_log_entries"
    __table_args__ = (Index("ix_audit_log_workspace_created", "workspace_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    # Nullable: a future system-initiated action (e.g. a scheduled automation
    # tick) has no acting user.
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100))  # e.g. "record.created", "field.deleted"
    resource_type: Mapped[str] = mapped_column(String(50))  # e.g. "record", "field", "automation"
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resource_label: Mapped[str | None] = mapped_column(String(255), nullable=True)  # human-readable name/title
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
