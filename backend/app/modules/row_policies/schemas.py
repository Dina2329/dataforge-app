import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class RowLevelPolicyCreateRequest(BaseModel):
    target_user_id: uuid.UUID
    filter: dict[str, Any]


class RowLevelPolicyResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    user_id: uuid.UUID
    filter: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}
