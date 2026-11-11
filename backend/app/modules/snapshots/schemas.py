import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class CreateSnapshotRequest(BaseModel):
    label: str | None = None


class UpdateSnapshotSettingsRequest(BaseModel):
    auto_snapshots_enabled: bool


class BaseSnapshotResponse(BaseModel):
    id: uuid.UUID
    base_id: uuid.UUID
    label: str
    is_automatic: bool
    created_by: uuid.UUID
    created_at: datetime
    table_count: int

    model_config = {"from_attributes": True}


class SnapshotTableRestoreResult(BaseModel):
    table_name: str
    skipped: bool = False
    skip_reason: str | None = None
    created: int = 0
    updated: int = 0
    deleted: int = 0
    unchanged: int = 0
    failed: int = 0
    failures: list[dict[str, Any]] = []


class RestoreSnapshotResponse(BaseModel):
    snapshot_id: uuid.UUID
    tables: list[SnapshotTableRestoreResult]
