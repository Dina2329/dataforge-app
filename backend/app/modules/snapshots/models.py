import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class BaseSnapshot(Model):
    """A point-in-time checkpoint of an entire Base -- every Table's schema
    and data at the moment it was taken (see BaseSnapshotTable), so a
    restore always brings the whole Base back to one consistent instant
    rather than mixing table states from different times."""

    __tablename__ = "base_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bases.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(255))
    is_automatic: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BaseSnapshotTable(Model):
    """One row per Table captured in a BaseSnapshot. table_id is
    ON DELETE SET NULL, not CASCADE -- deleting the live Table later must
    never delete the snapshot data that's the whole reason to keep a
    snapshot around (e.g. to recover from that exact deletion); a null
    table_id just means "the original Table is gone," and restore skips it
    with a note rather than failing the whole restore.

    field_defs is a snapshot of each non-virtual Field's
    {id, name, db_column_name, field_type, options} at capture time --
    virtual fields (link_to_record/lookup/rollup/formula) have no real
    column and are deliberately excluded, see SnapshotService's module
    docstring for what that means for restore."""

    __tablename__ = "base_snapshot_tables"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("base_snapshots.id", ondelete="CASCADE"))
    table_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tables.id", ondelete="SET NULL"), nullable=True)
    table_name: Mapped[str] = mapped_column(String(255))
    physical_snapshot_table: Mapped[str] = mapped_column(String(63))
    field_defs: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    row_count: Mapped[int] = mapped_column(Integer, default=0)
