import uuid
from typing import Any

from pydantic import BaseModel


class BaseCreateRequest(BaseModel):
    name: str


class BaseResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    auto_snapshots_enabled: bool

    model_config = {"from_attributes": True}


class TableCreateRequest(BaseModel):
    name: str


class FieldCreateRequest(BaseModel):
    name: str
    field_type: str
    options: dict[str, Any] = {}
    required: bool = False


class FieldUpdateRequest(BaseModel):
    name: str | None = None
    required: bool | None = None
    options: dict[str, Any] | None = None


class FieldResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    name: str
    field_type: str
    options: dict[str, Any]
    position: int
    is_primary: bool
    required: bool

    model_config = {"from_attributes": True}


class ViewCreateRequest(BaseModel):
    name: str
    view_type: str = "grid"
    config: dict[str, Any] = {}


class ViewUpdateRequest(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None


class ViewResponse(BaseModel):
    id: uuid.UUID
    table_id: uuid.UUID
    name: str
    view_type: str
    config: dict[str, Any]
    share_token: str | None

    model_config = {"from_attributes": True}


class PublicFormFieldResponse(BaseModel):
    id: uuid.UUID
    name: str
    field_type: str
    options: dict[str, Any]
    required: bool

    model_config = {"from_attributes": True}


class PublicFormResponse(BaseModel):
    table_name: str
    view_name: str
    description: str | None = None
    fields: list[PublicFormFieldResponse]


class PublicFormSubmitRequest(BaseModel):
    values: dict[str, Any] = {}


class TableResponse(BaseModel):
    id: uuid.UUID
    base_id: uuid.UUID
    name: str
    fields: list[FieldResponse] = []
    views: list[ViewResponse] = []

    model_config = {"from_attributes": True}


def table_to_response(table: Any, fields: list, views: list) -> TableResponse:
    return TableResponse(
        id=table.id,
        base_id=table.base_id,
        name=table.name,
        fields=[FieldResponse.model_validate(f) for f in fields],
        views=[ViewResponse.model_validate(v) for v in views],
    )
