import uuid

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.modules.group_cleanup.schemas import GroupCleanupPreviewResponse, GroupCleanupRequest, GroupCleanupResultResponse
from app.modules.group_cleanup.service import GroupCleanupService

router = APIRouter(tags=["group-cleanup"])


@router.get("/api/tables/{table_id}/group-cleanup-preview", response_model=GroupCleanupPreviewResponse)
async def preview_group_cleanup(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    group_field: str = Query(...),
    value_field: str = Query(...),
    score_field: str = Query(...),
) -> GroupCleanupPreviewResponse:
    result = await GroupCleanupService(db).preview(
        table_id=table_id, user_id=current_user.id, group_field=group_field, value_field=value_field, score_field=score_field
    )
    return GroupCleanupPreviewResponse(**result)


@router.post("/api/tables/{table_id}/group-cleanup", response_model=GroupCleanupResultResponse)
async def execute_group_cleanup(
    table_id: uuid.UUID, payload: GroupCleanupRequest, current_user: CurrentUser, db: DbSession
) -> GroupCleanupResultResponse:
    result = await GroupCleanupService(db).execute(
        table_id=table_id,
        user_id=current_user.id,
        group_field=payload.group_field,
        value_field=payload.value_field,
        score_field=payload.score_field,
    )
    return GroupCleanupResultResponse(**result)
