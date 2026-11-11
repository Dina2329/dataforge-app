import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.bulk_ops.schemas import (
    BulkOperationResponse,
    BulkUpdateExecuteRequest,
    BulkUpdatePreviewRequest,
    BulkUpdatePreviewResponse,
)
from app.modules.bulk_ops.service import BulkOpsService

router = APIRouter(tags=["bulk_ops"])


@router.post("/api/tables/{table_id}/bulk-update/preview", response_model=BulkUpdatePreviewResponse)
async def preview_bulk_update(
    table_id: uuid.UUID, payload: BulkUpdatePreviewRequest, current_user: CurrentUser, db: DbSession
) -> BulkUpdatePreviewResponse:
    result = await BulkOpsService(db).preview(
        table_id=table_id, user_id=current_user.id, filter_dict=payload.filter, values=payload.values
    )
    return BulkUpdatePreviewResponse.model_validate(result)


@router.post("/api/tables/{table_id}/bulk-update/execute", response_model=BulkOperationResponse, status_code=202)
async def execute_bulk_update(
    table_id: uuid.UUID, payload: BulkUpdateExecuteRequest, current_user: CurrentUser, db: DbSession
) -> BulkOperationResponse:
    operation = await BulkOpsService(db).execute(
        table_id=table_id, user_id=current_user.id, filter_dict=payload.filter, values=payload.values, confirm=payload.confirm
    )
    return BulkOperationResponse.model_validate(operation)


@router.get("/api/bulk-operations/{operation_id}", response_model=BulkOperationResponse)
async def get_bulk_operation(operation_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> BulkOperationResponse:
    operation = await BulkOpsService(db).get_status(operation_id=operation_id, user_id=current_user.id)
    return BulkOperationResponse.model_validate(operation)


@router.post("/api/bulk-operations/{operation_id}/undo", response_model=BulkOperationResponse, status_code=202)
async def undo_bulk_operation(operation_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> BulkOperationResponse:
    operation = await BulkOpsService(db).undo(operation_id=operation_id, user_id=current_user.id)
    return BulkOperationResponse.model_validate(operation)
