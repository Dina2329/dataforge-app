import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

from app.modules.bases.schemas import TableResponse

SourceType = Literal["postgres", "mysql", "sqlite", "elasticsearch"]


class DataSourceCreateRequest(BaseModel):
    name: str
    source_type: SourceType
    # For postgres/mysql: {host, port?, database, username, password}.
    # For elasticsearch: {url, api_key?} or {url, username?, password?}.
    # For sqlite: omitted — the file arrives as a multipart upload instead.
    config: dict[str, Any] = {}


class DataSourceResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    source_type: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TableRefResponse(BaseModel):
    name: str
    schema_name: str | None = None


class ColumnDefResponse(BaseModel):
    name: str
    native_type: str
    inferred_field_type: str
    is_primary_key: bool = False


class ExcelSheetPreview(BaseModel):
    name: str
    columns: list[ColumnDefResponse]
    row_count: int


class ExcelInspectResponse(BaseModel):
    sheets: list[ExcelSheetPreview]


class ExcelImportResult(BaseModel):
    sheet_name: str
    table: TableResponse | None = None
    error: str | None = None


class ExcelImportResponse(BaseModel):
    results: list[ExcelImportResult]


class ImportFromSourceRequest(BaseModel):
    table_name: str
    table_schema: str | None = None
    new_table_name: str
    # Postgres/MySQL only, and only when the source table has exactly one
    # primary key column -- see ImportService._resolve_sync_pk_column.
    sync_enabled: bool = False


class TableSyncConfigResponse(BaseModel):
    table_id: uuid.UUID
    data_source_id: uuid.UUID
    external_table_name: str
    sync_enabled: bool
    push_requires_approval: bool
    consecutive_failures: int
    last_error: str | None
    last_error_at: datetime | None

    # Stage 2: pulling external changes -- external_updated_at_column is
    # null whenever this table is push-only (every Stage 1 table starts out
    # this way).
    external_updated_at_column: str | None
    poll_interval_seconds: int | None
    deletion_check_interval_seconds: int | None
    last_polled_at: datetime | None
    poll_paused: bool
    poll_consecutive_failures: int
    poll_last_error: str | None
    poll_last_error_at: datetime | None

    model_config = {"from_attributes": True}


class UpdateTableSyncRequest(BaseModel):
    sync_enabled: bool
    # Omitted (None) leaves the current setting alone -- unlike sync_enabled,
    # which this endpoint always sets explicitly either way.
    push_requires_approval: bool | None = None


class ConfigurePullRequest(BaseModel):
    # None clears pull entirely (table goes back to push-only).
    external_updated_at_column: str | None = None
    poll_interval_seconds: int | None = None
    deletion_check_interval_seconds: int | None = None


class PendingSyncChangeResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    table_name: str
    row_id: int
    operation: str
    values: dict[str, Any] | None
    previous_values: dict[str, Any] | None
    external_pk: str | None
    status: str
    requested_by: uuid.UUID
    requested_by_name: str
    requested_at: datetime
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None


class RejectSyncChangeRequest(BaseModel):
    reason: str | None = None
    restore: bool = False


class SyncChangeBatchResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    status: str
    requested_by: uuid.UUID
    requested_by_name: str
    submitted_at: datetime
    reviewed_by: uuid.UUID | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    changes: list[PendingSyncChangeResponse]


class SubmitDraftsResponse(BaseModel):
    batch_id: uuid.UUID
    change_count: int
