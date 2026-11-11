import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BulkUpdatePreviewRequest(BaseModel):
    filter: dict[str, Any]
    values: dict[str, Any] = {}


class SampleRow(BaseModel):
    row_id: int
    values: dict[str, Any]


class BulkUpdatePreviewResponse(BaseModel):
    matched_count: int
    sample_rows: list[SampleRow]


class BulkUpdateExecuteRequest(BaseModel):
    filter: dict[str, Any]
    values: dict[str, Any]
    confirm: bool = False


class BulkOperationResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    status: str
    matched_count: int | None
    affected_count: int | None
    error: str | None
    undone_at: datetime | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
