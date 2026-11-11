import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class Automation(Model):
    """A trigger + its ordered actions. Deliberately a linear trigger->actions
    chain with a fixed action vocabulary, not a generic workflow/DAG engine —
    see architecture plan, section 3 and the "automation scope creep" risk."""

    __tablename__ = "automations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    trigger_type: Mapped[str] = mapped_column(String(20))  # record_created|record_updated|scheduled
    # record_created/record_updated: {filter?: FilterExpr}. scheduled: {cron: str}.
    trigger_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AutomationAction(Model):
    __tablename__ = "automation_actions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    automation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    action_type: Mapped[str] = mapped_column(String(20))  # send_webhook|create_record|update_record
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class AutomationRun(Model):
    __tablename__ = "automation_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    automation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("automations.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20))  # success|failed
    trigger_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
