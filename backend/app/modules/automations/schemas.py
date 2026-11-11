import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

TriggerType = Literal["record_created", "record_updated", "scheduled"]
ActionType = Literal["send_webhook", "create_record", "update_record"]


class AutomationCreateRequest(BaseModel):
    name: str
    trigger_type: TriggerType
    trigger_config: dict[str, Any] = {}


class AutomationUpdateRequest(BaseModel):
    name: str | None = None
    is_enabled: bool | None = None
    trigger_config: dict[str, Any] | None = None


class AutomationResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    name: str
    trigger_type: str
    trigger_config: dict[str, Any]
    is_enabled: bool
    next_run_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AutomationActionCreateRequest(BaseModel):
    action_type: ActionType
    config: dict[str, Any] = {}


class AutomationActionResponse(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    position: int
    action_type: str
    config: dict[str, Any]

    model_config = {"from_attributes": True}


class AutomationRunResponse(BaseModel):
    id: uuid.UUID
    automation_id: uuid.UUID
    status: str
    trigger_payload: dict[str, Any]
    error: str | None
    ran_at: datetime

    model_config = {"from_attributes": True}
