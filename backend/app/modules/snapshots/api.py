import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.bases.schemas import BaseResponse
from app.modules.snapshots.schemas import (
    BaseSnapshotResponse,
    CreateSnapshotRequest,
    RestoreSnapshotResponse,
    UpdateSnapshotSettingsRequest,
)
from app.modules.snapshots.service import SnapshotService

router = APIRouter(tags=["snapshots"])


def _snapshot_response(snapshot, table_count: int) -> BaseSnapshotResponse:
    return BaseSnapshotResponse(
        id=snapshot.id, base_id=snapshot.base_id, label=snapshot.label, is_automatic=snapshot.is_automatic,
        created_by=snapshot.created_by, created_at=snapshot.created_at, table_count=table_count,
    )


@router.post("/api/bases/{base_id}/snapshots", response_model=BaseSnapshotResponse, status_code=201)
async def create_snapshot(
    base_id: uuid.UUID, payload: CreateSnapshotRequest, current_user: CurrentUser, db: DbSession
) -> BaseSnapshotResponse:
    snapshot, table_count = await SnapshotService(db).create_snapshot(base_id=base_id, user_id=current_user.id, label=payload.label)
    return _snapshot_response(snapshot, table_count)


@router.get("/api/bases/{base_id}/snapshots", response_model=list[BaseSnapshotResponse])
async def list_snapshots(base_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[BaseSnapshotResponse]:
    snapshots = await SnapshotService(db).list_for_base(base_id=base_id, user_id=current_user.id)
    return [_snapshot_response(s, count) for s, count in snapshots]


@router.delete("/api/snapshots/{snapshot_id}", status_code=204)
async def delete_snapshot(snapshot_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await SnapshotService(db).delete_snapshot(snapshot_id=snapshot_id, user_id=current_user.id)


@router.get("/api/snapshots/{snapshot_id}/preview", response_model=RestoreSnapshotResponse)
async def preview_restore(snapshot_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> RestoreSnapshotResponse:
    """Read-only -- what restore_snapshot below would do, without doing it,
    so the confirmation step can show exactly which tables/how many rows
    would change before the user commits to it."""
    results = await SnapshotService(db).preview_restore(snapshot_id=snapshot_id, user_id=current_user.id)
    return RestoreSnapshotResponse(snapshot_id=snapshot_id, tables=results)


@router.post("/api/snapshots/{snapshot_id}/restore", response_model=RestoreSnapshotResponse)
async def restore_snapshot(snapshot_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> RestoreSnapshotResponse:
    results = await SnapshotService(db).restore_snapshot(snapshot_id=snapshot_id, user_id=current_user.id)
    return RestoreSnapshotResponse(snapshot_id=snapshot_id, tables=results)


@router.patch("/api/bases/{base_id}/snapshots/settings", response_model=BaseResponse)
async def update_snapshot_settings(
    base_id: uuid.UUID, payload: UpdateSnapshotSettingsRequest, current_user: CurrentUser, db: DbSession
) -> BaseResponse:
    base = await SnapshotService(db).set_auto_snapshots_enabled(
        base_id=base_id, user_id=current_user.id, enabled=payload.auto_snapshots_enabled
    )
    return BaseResponse.model_validate(base)
