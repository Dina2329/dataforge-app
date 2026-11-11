import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class RecordSubmitConfig(Model):
    """Marks a Table as having an external "Submit row" target -- one row per
    table (see record_submit/service.py). Absence of a row for a given
    table_id means "no submit target configured," the common case; kept as
    its own table rather than columns on Table for the same reason
    TableSyncConfig/row_level_policies are (optional, low-cardinality
    per-table config)."""

    __tablename__ = "record_submit_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"), unique=True)
    url: Mapped[str] = mapped_column(String(2048))
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # SET NULL, not CASCADE/RESTRICT -- deleting the status field should only
    # disable stamping, never block deleting the field or break this config.
    status_field_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("fields.id", ondelete="SET NULL"), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
