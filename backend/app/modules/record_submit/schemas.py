import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RecordSubmitConfigUpsertRequest(BaseModel):
    url: str
    headers: dict[str, Any] | None = None
    status_field_id: uuid.UUID


class RecordSubmitConfigResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    url: str
    headers: dict[str, Any] | None
    status_field_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
