from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RecordCreateRequest(BaseModel):
    values: dict[str, Any] = {}


class RecordUpdateRequest(BaseModel):
    values: dict[str, Any] = {}
    expected_version: int | None = None


class RecordResponse(BaseModel):
    row_id: int
    version: int
    created_at: datetime
    updated_at: datetime
    values: dict[str, Any]


class RecordListResponse(BaseModel):
    rows: list[RecordResponse]
    next_cursor: str | None
    has_more: bool
