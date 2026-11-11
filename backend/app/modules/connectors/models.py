import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class DataSource(Model):
    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255))
    source_type: Mapped[str] = mapped_column(String(50))
    # Fernet-encrypted JSON blob (host/port/database/username/password, or
    # file_path for sqlite) — see app.core.encryption. Never stored plaintext.
    config_encrypted: Mapped[str] = mapped_column(Text)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TableSyncConfig(Model):
    """Marks a Table as kept in sync with the external table it was imported
    from -- one row per synced Table (see sync_service.py). Absence of a row
    for a given table_id means "not synced," the common case; this is kept as
    its own table rather than columns on Table for the same reason
    row_level_policies is (optional, low-cardinality per-table config)."""

    __tablename__ = "table_sync_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"), unique=True)
    # CASCADE, not RESTRICT -- see the migration's comment: workspace
    # deletion cascades through this in one DB statement, so it can't also
    # be the thing that blocks a lone data-source deletion. That guard lives
    # in DataSourceService.delete() instead.
    data_source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("data_sources.id", ondelete="CASCADE"))
    external_schema: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_table_name: Mapped[str] = mapped_column(String(255))
    external_pk_column: Mapped[str] = mapped_column(String(255))
    sync_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # Reset to 0 on every successful push; once it reaches AUTO_DISABLE_THRESHOLD
    # (sync_service.py) sync_enabled flips false automatically so a persistently
    # broken connection can't notify on every single edit forever.
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # -- Stage 2: pulling external changes (null external_updated_at_column
    # means "push-only," the state every Stage 1 table starts in) --
    external_updated_at_column: Mapped[str | None] = mapped_column(String(255), nullable=True)
    poll_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Watermark for stream_changed_rows' WHERE clause -- always the external
    # DB's own clock (see sql_common.get_server_time), never DataForge's, so
    # the comparison is never cross-server.
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    deletion_check_interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_deletion_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Pull health -- deliberately separate from sync_enabled/consecutive_failures
    # above (which govern push only): a broken poll must never silently stop a
    # healthy push, or vice versa.
    poll_paused: Mapped[bool] = mapped_column(Boolean, default=False)
    poll_consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    poll_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    poll_last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Approval gate on push only (see PendingSyncChange) -- pull's conflict
    # policy (external always wins) is a separate, already-settled question
    # this doesn't touch. False means today's behavior: every local edit
    # pushes immediately, unchanged.
    push_requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)


class SyncChangeBatch(Model):
    """One "submit for approval" action -- bundles however many
    PendingSyncChange rows an editor had accumulated as drafts (any number of
    rows, across any number of gated tables) at the moment they submitted, so
    an owner/admin reviews and approves/rejects everything in one action
    instead of one row at a time. Scoped to a single workspace (the one the
    submit call was made against) purely to keep listing/permission-checking
    simple -- nothing stops an editor editing tables in two different
    workspaces, they just submit each workspace's drafts separately."""

    __tablename__ = "sync_change_batches"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(10), default="pending")  # pending | approved | rejected
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PendingSyncChange(Model):
    """One row per (table_id, row_id) currently either still being drafted by
    its editor or awaiting owner/admin approval as part of a submitted
    SyncChangeBatch -- a gate in front of push_record_to_source, not a
    parallel push mechanism. Not a history log: a second local edit to the
    same row while one is still unresolved (draft OR pending -- see
    PendingSyncChangeService.request) overwrites this row's values in place
    rather than queuing a second entry, so approving always pushes the row's
    latest state, never a stale intermediate snapshot."""

    __tablename__ = "pending_sync_changes"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    row_id: Mapped[int] = mapped_column(Integer)
    # "insert" | "update" | "delete" -- always re-derived from whether the
    # row already has a real external_pk (see PendingSyncChangeService.request),
    # never just the local operation label passed in, since e.g. a row's
    # *first* edit under approval mode is still an "insert" externally no
    # matter what the local caller calls it.
    operation: Mapped[str] = mapped_column(String(10))
    # Full current row values (insert/update) -- None for a delete, which
    # carries nothing but the external_pk to remove.
    values: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # The row's values immediately before THIS pending change's edit --
    # None for insert (there was no "before"; a rejection restores by
    # deleting, not by reverting to some prior state). Captured once, when
    # this pending row is first created, and never overwritten by a later
    # collapsed edit (see request()) -- rejecting must always be able to
    # undo back to before *any* of the edits that piled up while this sat
    # unreviewed, not just the most recent one.
    previous_values: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    external_pk: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # draft (not yet submitted, visible only to the editor who made it) |
    # pending (submitted, part of an open SyncChangeBatch, visible to
    # approvers) | approved | rejected.
    status: Mapped[str] = mapped_column(String(10), default="draft")
    # Set only once this row's batch is submitted (see
    # PendingSyncChangeService.submit) -- None the whole time it's a draft.
    batch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("sync_change_batches.id", ondelete="CASCADE"), nullable=True)
    requested_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
