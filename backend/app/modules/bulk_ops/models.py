import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class BulkOperation(Model):
    """One bulk-update batch. Its own id doubles as the batch_id shared by all
    BulkOperationLog rows it produces, so undo only needs one foreign key."""

    __tablename__ = "bulk_operations"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    # Serialized FilterExpr (app.core.query.filter_dsl) that selected the rows.
    filter_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    # {field_name: new_value} applied uniformly to every matched row.
    values_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|completed|failed
    matched_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    affected_count: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BulkOperationLog(Model):
    """Append-only per-row change record — undo cost is proportional to rows
    *changed*, not table size (architecture plan, section 4)."""

    __tablename__ = "bulk_operation_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bulk_operations.id", ondelete="CASCADE"))
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    row_id: Mapped[int] = mapped_column(BigInteger)
    # {db_column_name: old_value} — only the columns this batch actually changed.
    old_values: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
