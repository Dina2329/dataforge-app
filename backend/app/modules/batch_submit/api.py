import uuid

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.modules.batch_submit.schemas import (
    BatchSubmitConfigResponse,
    BatchSubmitConfigUpsertRequest,
    BatchSubmitJobResponse,
    BatchSubmitPreviewResponse,
)
from app.modules.batch_submit.service import BatchSubmitService

router = APIRouter(tags=["batch-submit"])


def _config_response(config) -> BatchSubmitConfigResponse:
    # Not a plain .model_validate(config, from_attributes=True) -- the ORM
    # column is named filter_json (avoiding the Python builtin `filter` as an
    # attribute name), but the API's own field is just `filter`, so this one
    # field needs an explicit mapping rather than relying on an automatic,
    # same-name attribute pickup that wouldn't exist here.
    return BatchSubmitConfigResponse(
        id=config.id, table_id=config.table_id, url=config.url, headers=config.headers,
        filter=config.filter_json, batch_size=config.batch_size, created_at=config.created_at, updated_at=config.updated_at,
    )


@router.get("/api/tables/{table_id}/batch-submit-config", response_model=BatchSubmitConfigResponse | None)
async def get_batch_submit_config(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> BatchSubmitConfigResponse | None:
    config = await BatchSubmitService(db).get_config(table_id=table_id, user_id=current_user.id)
    return _config_response(config) if config else None


@router.put("/api/tables/{table_id}/batch-submit-config", response_model=BatchSubmitConfigResponse)
async def upsert_batch_submit_config(
    table_id: uuid.UUID, payload: BatchSubmitConfigUpsertRequest, current_user: CurrentUser, db: DbSession
) -> BatchSubmitConfigResponse:
    config = await BatchSubmitService(db).upsert_config(
        table_id=table_id, user_id=current_user.id, url=payload.url, headers=payload.headers,
        filter_dict=payload.filter, batch_size=payload.batch_size,
    )
    return _config_response(config)


@router.get("/api/tables/{table_id}/batch-submit-preview", response_model=BatchSubmitPreviewResponse)
async def preview_batch_submit(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> BatchSubmitPreviewResponse:
    result = await BatchSubmitService(db).preview(table_id=table_id, user_id=current_user.id)
    return BatchSubmitPreviewResponse(**result)


@router.post("/api/tables/{table_id}/batch-submit-jobs", response_model=BatchSubmitJobResponse, status_code=202)
async def create_batch_submit_job(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> BatchSubmitJobResponse:
    job = await BatchSubmitService(db).create_job(table_id=table_id, user_id=current_user.id)
    return BatchSubmitJobResponse.model_validate(job)


@router.get("/api/tables/{table_id}/batch-submit-jobs", response_model=list[BatchSubmitJobResponse])
async def list_batch_submit_jobs(
    table_id: uuid.UUID, current_user: CurrentUser, db: DbSession, include_dismissed: bool = Query(default=False)
) -> list[BatchSubmitJobResponse]:
    jobs = await BatchSubmitService(db).list_jobs(table_id=table_id, user_id=current_user.id, include_dismissed=include_dismissed)
    return [BatchSubmitJobResponse.model_validate(j) for j in jobs]


@router.get("/api/batch-submit-jobs/{job_id}", response_model=BatchSubmitJobResponse)
async def get_batch_submit_job(job_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> BatchSubmitJobResponse:
    job = await BatchSubmitService(db).get_job(job_id=job_id, user_id=current_user.id)
    return BatchSubmitJobResponse.model_validate(job)


@router.post("/api/batch-submit-jobs/{job_id}/dismiss", status_code=204)
async def dismiss_batch_submit_job(job_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await BatchSubmitService(db).dismiss_job(job_id=job_id, user_id=current_user.id)
