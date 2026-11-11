import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class BatchSubmitConfig(Model):
    """Per-table "send matching rows to an external API in batches" target --
    deliberately separate from RecordSubmitConfig (the per-row Submit
    button's own config/URL): different trigger entirely (an arbitrary
    condition the user sets up, plus one manual "Send batch" button, not a
    per-row action), so kept as its own config rather than bolted onto the
    existing one.

    filter_json is a serialized FilterExpr (app.core.query.filter_dsl, the
    same filter language records/bulk_ops/dashboards all already use) --
    NOT restricted to a single boolean field. "Status equals Ready", "Reviewed
    is not empty", or any other condition a person can build in the regular
    Filter dialog works here identically; a plain boolean checkbox is just
    the simplest possible case of it (field = true)."""

    __tablename__ = "batch_submit_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"), unique=True)
    url: Mapped[str] = mapped_column(String(2048))
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    filter_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    batch_size: Mapped[int] = mapped_column(default=100)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BatchSubmitJob(Model):
    """One "Send batch to API" click. Snapshots batch_size at creation time
    so a later config change never retroactively changes an in-flight job.

    Rows matching the configured filter are NOT auto-cleared after a
    successful send (nothing about the row is changed) -- by explicit
    choice, re-clicking Send resends every row that still matches.
    batch_results is how a user tells, after the fact, which batches landed
    and which failed (a batch failure never stops the rest -- see
    run_batch_submit_job's docstring).

    A partial unique index on table_id WHERE status IN ('queued','running')
    (added in the migration directly, same pattern as
    uq_missing_terms_job_active_idempotency) blocks starting a second batch
    send for a table while one is already in flight -- not a row-set dedup,
    just "don't run two overlapping sends for the same table at once."""

    __tablename__ = "batch_submit_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|completed|partially_failed|failed
    batch_size: Mapped[int] = mapped_column()
    total_rows: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    total_batches: Mapped[int | None] = mapped_column(nullable=True)
    sent_batches: Mapped[int] = mapped_column(default=0)
    failed_batches: Mapped[int] = mapped_column(default=0)
    # [{batch_index, row_ids, status: "sent"|"failed", error?}, ...] -- one
    # entry per batch, appended to as each batch finishes (not written once
    # at the end), so polling mid-run shows real progress.
    batch_results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    dismissed: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
