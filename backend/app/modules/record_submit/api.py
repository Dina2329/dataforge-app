import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.record_submit.schemas import RecordSubmitConfigResponse, RecordSubmitConfigUpsertRequest
from app.modules.record_submit.service import RecordSubmitService
from app.modules.records.schemas import RecordResponse

router = APIRouter(tags=["record-submit"])


@router.get("/api/tables/{table_id}/submit-config", response_model=RecordSubmitConfigResponse | None)
async def get_submit_config(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> RecordSubmitConfigResponse | None:
    config = await RecordSubmitService(db).get_config(table_id=table_id, user_id=current_user.id)
    return RecordSubmitConfigResponse.model_validate(config) if config else None


@router.put("/api/tables/{table_id}/submit-config", response_model=RecordSubmitConfigResponse)
async def upsert_submit_config(
    table_id: uuid.UUID, payload: RecordSubmitConfigUpsertRequest, current_user: CurrentUser, db: DbSession
) -> RecordSubmitConfigResponse:
    config = await RecordSubmitService(db).upsert_config(
        table_id=table_id, user_id=current_user.id, url=payload.url, headers=payload.headers, status_field_id=payload.status_field_id
    )
    return RecordSubmitConfigResponse.model_validate(config)


@router.post("/api/tables/{table_id}/rows/{row_id}/submit", response_model=RecordResponse)
async def submit_row(table_id: uuid.UUID, row_id: int, current_user: CurrentUser, db: DbSession) -> RecordResponse:
    return await RecordSubmitService(db).submit_row(table_id=table_id, row_id=row_id, user_id=current_user.id)
