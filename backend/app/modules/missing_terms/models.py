import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Model


class PrerequestUpload(Model):
    """One row per workspace -- its existence is what gates "a prerequest list
    exists for this workspace." Only Owner/Admin (Permission.PREREQUEST_MANAGE)
    can create/replace/view it (see missing_terms/service.py); every table in
    the workspace compares against the one shared PrerequestTerm set below."""

    __tablename__ = "prerequest_uploads"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    row_count: Mapped[int] = mapped_column()
    uploaded_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PrerequestTerm(Model):
    """The actual shared list -- replacing the prerequest (re-upload) deletes
    every row for that workspace and inserts the new set in one transaction."""

    __tablename__ = "prerequest_terms"
    __table_args__ = (Index("ix_prerequest_terms_workspace", "workspace_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"))
    estate: Mapped[str | None] = mapped_column(String(255), nullable=True)
    building: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sub_domain: Mapped[str] = mapped_column(String(255))
    term_name: Mapped[str] = mapped_column(String(255))


class MissingTermsApiConfig(Model):
    """The external lookup API's URL (+ optional headers), per workspace --
    not a single app-wide env var, since this app has no "platform admin"
    separate from workspace Owner/Admin to safely gate a truly global value.
    Editable live from the Prerequest admin page (Permission.PREREQUEST_MANAGE,
    same gate as the shared prerequest list itself); the worker looks this up
    by the submitting table's workspace_id, no restart needed to change it."""

    __tablename__ = "missing_terms_api_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), unique=True)
    api_url: Mapped[str] = mapped_column(String(2048))
    headers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    updated_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MissingTermsConfig(Model):
    """Per-table opt-in: this table's own Estate/Building/Unit scope (all
    optional -- null means "compare against the whole workspace prerequest
    list, unscoped") plus field_mapping, the one thing the Enrichment
    feature's three build/delete cycles this session made clear is never
    optional in practice: a real table's field names essentially never match
    an external schema's column names exactly. Keys are slot names
    ("sub_domain", "term_name", "page", "pdf_image", "pdf_name", "keywords"); values are
    this table's real field ids. sub_domain/term_name must be mapped before
    the feature can be used; the rest are optional."""

    __tablename__ = "missing_terms_configs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"), unique=True)
    estate: Mapped[str | None] = mapped_column(String(255), nullable=True)
    building: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_mapping: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MissingTermsJob(Model):
    """queued -> running -> completed | partially_failed | failed.
    `idempotency_key` + the partial unique index (migration) block a
    duplicate submission of the exact same batch only while a job for this
    table is genuinely active -- same pattern as 0019's
    uq_pending_sync_change_row and the (removed) Enrichment feature's
    dedupe_key, just hashing a whole submitted-row list instead of one row."""

    __tablename__ = "missing_terms_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(20), default="queued")
    idempotency_key: Mapped[str] = mapped_column(String(64))
    submitted_rows: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    response_rows: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    imported_keys: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    dismissed: Mapped[bool] = mapped_column(default=False)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MissingTermsJobRow(Model):
    """One row per submitted item in a job -- exists purely so "exclude rows
    belonging to a queued/running job" (gap detection) can be a plain SQL
    join against active jobs' rows, rather than querying inside a JSON
    column."""

    __tablename__ = "missing_terms_job_rows"
    __table_args__ = (Index("ix_missing_terms_job_rows_job", "job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("missing_terms_jobs.id", ondelete="CASCADE"))
    sub_domain_norm: Mapped[str] = mapped_column(String(255))
    term_name_norm: Mapped[str] = mapped_column(String(255))


class MissingTermsIgnoredTerm(Model):
    """A missing term the user has chosen to hide from this table's
    Sub-Domain/Term Name pickers -- e.g. it genuinely doesn't apply to this
    table. Scoped per table, not per workspace: whether a term is relevant
    is a property of the table, not the shared prerequest list. Revertible
    any time from the panel's "Ignored" list -- a plain delete of this row,
    never a destructive change to PrerequestTerm itself."""

    __tablename__ = "missing_terms_ignored_terms"
    __table_args__ = (
        Index("ix_missing_terms_ignored_terms_table", "table_id"),
        UniqueConstraint("table_id", "sub_domain_norm", "term_name_norm", name="uq_missing_terms_ignored_term"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    table_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tables.id", ondelete="CASCADE"))
    sub_domain: Mapped[str] = mapped_column(String(255))
    term_name: Mapped[str] = mapped_column(String(255))
    sub_domain_norm: Mapped[str] = mapped_column(String(255))
    term_name_norm: Mapped[str] = mapped_column(String(255))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
