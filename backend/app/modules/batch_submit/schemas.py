import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BatchSubmitConfigUpsertRequest(BaseModel):
    url: str
    headers: dict[str, Any] | None = None
    # A serialized FilterExpr (app.core.query.filter_dsl) -- any condition a
    # row can match, not restricted to a single boolean field.
    filter: dict[str, Any]
    batch_size: int = 100


class BatchSubmitConfigResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    url: str
    headers: dict[str, Any] | None
    filter: dict[str, Any]
    batch_size: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BatchSubmitPreviewResponse(BaseModel):
    matched_count: int
    batch_size: int
    total_batches: int


class BatchSubmitJobResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    status: str
    batch_size: int
    total_rows: int | None
    total_batches: int | None
    sent_batches: int
    failed_batches: int
    batch_results: list[dict[str, Any]]
    error: str | None
    dismissed: bool
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
