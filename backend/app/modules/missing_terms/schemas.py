import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class PrerequestUploadResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    original_filename: str
    row_count: int
    uploaded_by: uuid.UUID
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class MissingTermsApiConfigUpsertRequest(BaseModel):
    api_url: str
    headers: dict[str, Any] | None = None


class MissingTermsApiConfigResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    api_url: str
    headers: dict[str, Any] | None
    updated_by: uuid.UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MissingTermsConfigUpsertRequest(BaseModel):
    estate: str | None = None
    building: str | None = None
    unit: str | None = None
    field_mapping: dict[str, str] = {}


class MissingTermsConfigResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    estate: str | None
    building: str | None
    unit: str | None
    field_mapping: dict[str, str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MissingTermRow(BaseModel):
    estate: str | None
    building: str | None
    unit: str | None
    sub_domain: str
    term_name: str


class MissingTermsSummary(BaseModel):
    total: int
    matched: int
    missing: int
    in_progress: int
    ignored: int


class IgnoreTermRequest(BaseModel):
    sub_domain: str
    term_name: str


class IgnoredTermRow(BaseModel):
    sub_domain: str
    term_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MissingTermsResponse(BaseModel):
    summary: MissingTermsSummary
    rows: list[MissingTermRow]
    next_cursor: str | None
    has_more: bool


class MissingTermsJobSubmitRow(BaseModel):
    sub_domain: str
    term_name: str
    estate: str | None = None
    building: str | None = None
    unit: str | None = None
    page: str | None = None
    pdf_image: str | None = None
    pdf_name: str | None = None
    keywords: str | None = None


class MissingTermsJobCreateRequest(BaseModel):
    rows: list[MissingTermsJobSubmitRow]


class MissingTermsJobResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    status: str
    submitted_rows: list[dict[str, Any]]
    response_rows: list[dict[str, Any]] | None
    imported_keys: list[str] | None
    error: str | None
    dismissed: bool
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}


class ImportSelection(BaseModel):
    sub_domain: str
    term_name: str
    candidate_index: int
    columns: list[str]
    overrides: dict[str, Any] | None = None  # user-edited values from the review screen, keyed by the candidate's own column names


class ImportRequest(BaseModel):
    selections: list[ImportSelection]


class ImportResultRow(BaseModel):
    sub_domain: str
    term_name: str
    status: str  # "inserted" | "skipped" (skipped only for re-importing the same job+candidate twice)
    row_id: int | None


class ImportResponse(BaseModel):
    results: list[ImportResultRow]


class ManualInsertRequest(BaseModel):
    sub_domain: str
    term_name: str
    values: dict[str, Any]
    on_conflict: str = "skip"
