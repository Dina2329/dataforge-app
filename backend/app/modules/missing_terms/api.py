import uuid

from fastapi import APIRouter, Query, UploadFile

from app.core.deps import CurrentUser, DbSession
from app.core.errors import ValidationError
from app.modules.missing_terms.schemas import (
    IgnoredTermRow,
    IgnoreTermRequest,
    ImportRequest,
    ImportResponse,
    ImportResultRow,
    ManualInsertRequest,
    MissingTermsApiConfigResponse,
    MissingTermsApiConfigUpsertRequest,
    MissingTermsConfigResponse,
    MissingTermsConfigUpsertRequest,
    MissingTermsJobCreateRequest,
    MissingTermsJobResponse,
    MissingTermsResponse,
    MissingTermsSummary,
    PrerequestUploadResponse,
)
from app.modules.missing_terms.service import MissingTermsService
from app.modules.records.schemas import RecordResponse

router = APIRouter(tags=["missing-terms"])


@router.get("/api/workspaces/{workspace_id}/prerequest", response_model=PrerequestUploadResponse | None)
async def get_prerequest(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> PrerequestUploadResponse | None:
    upload = await MissingTermsService(db).get_prerequest(workspace_id=workspace_id, user_id=current_user.id)
    return PrerequestUploadResponse.model_validate(upload) if upload else None


@router.put("/api/workspaces/{workspace_id}/prerequest", response_model=PrerequestUploadResponse)
async def replace_prerequest(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession, file: UploadFile) -> PrerequestUploadResponse:
    raw = await file.read()
    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("CSV file must be UTF-8 encoded") from exc
    upload = await MissingTermsService(db).replace_prerequest(
        workspace_id=workspace_id, user_id=current_user.id, filename=file.filename or "prerequest.csv", csv_text=csv_text
    )
    return PrerequestUploadResponse.model_validate(upload)


@router.delete("/api/workspaces/{workspace_id}/prerequest", status_code=204)
async def delete_prerequest(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await MissingTermsService(db).delete_prerequest(workspace_id=workspace_id, user_id=current_user.id)


@router.get("/api/workspaces/{workspace_id}/missing-terms-api-config", response_model=MissingTermsApiConfigResponse | None)
async def get_api_config(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> MissingTermsApiConfigResponse | None:
    config = await MissingTermsService(db).get_api_config(workspace_id=workspace_id, user_id=current_user.id)
    return MissingTermsApiConfigResponse.model_validate(config) if config else None


@router.put("/api/workspaces/{workspace_id}/missing-terms-api-config", response_model=MissingTermsApiConfigResponse)
async def upsert_api_config(
    workspace_id: uuid.UUID, payload: MissingTermsApiConfigUpsertRequest, current_user: CurrentUser, db: DbSession
) -> MissingTermsApiConfigResponse:
    config = await MissingTermsService(db).upsert_api_config(
        workspace_id=workspace_id, user_id=current_user.id, api_url=payload.api_url, headers=payload.headers
    )
    return MissingTermsApiConfigResponse.model_validate(config)


@router.get("/api/tables/{table_id}/missing-terms-config", response_model=MissingTermsConfigResponse | None)
async def get_config(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> MissingTermsConfigResponse | None:
    config = await MissingTermsService(db).get_config(table_id=table_id, user_id=current_user.id)
    return MissingTermsConfigResponse.model_validate(config) if config else None


@router.put("/api/tables/{table_id}/missing-terms-config", response_model=MissingTermsConfigResponse)
async def upsert_config(
    table_id: uuid.UUID, payload: MissingTermsConfigUpsertRequest, current_user: CurrentUser, db: DbSession
) -> MissingTermsConfigResponse:
    config = await MissingTermsService(db).upsert_config(
        table_id=table_id, user_id=current_user.id, estate=payload.estate, building=payload.building, unit=payload.unit, field_mapping=payload.field_mapping
    )
    return MissingTermsConfigResponse.model_validate(config)


@router.get("/api/tables/{table_id}/missing-terms", response_model=MissingTermsResponse)
async def get_missing_terms(
    table_id: uuid.UUID, current_user: CurrentUser, db: DbSession, cursor: int = Query(default=0), limit: int = Query(default=50, le=200)
) -> MissingTermsResponse:
    summary, rows, has_more = await MissingTermsService(db).get_missing_terms(table_id=table_id, user_id=current_user.id, cursor=cursor, limit=limit)
    return MissingTermsResponse(
        summary=MissingTermsSummary(**summary),
        rows=rows,
        next_cursor=str(cursor + limit) if has_more else None,
        has_more=has_more,
    )


@router.post("/api/tables/{table_id}/missing-terms/ignore", status_code=204)
async def ignore_term(table_id: uuid.UUID, payload: IgnoreTermRequest, current_user: CurrentUser, db: DbSession) -> None:
    await MissingTermsService(db).ignore_term(table_id=table_id, user_id=current_user.id, sub_domain=payload.sub_domain, term_name=payload.term_name)


@router.post("/api/tables/{table_id}/missing-terms/unignore", status_code=204)
async def unignore_term(table_id: uuid.UUID, payload: IgnoreTermRequest, current_user: CurrentUser, db: DbSession) -> None:
    await MissingTermsService(db).unignore_term(table_id=table_id, user_id=current_user.id, sub_domain=payload.sub_domain, term_name=payload.term_name)


@router.get("/api/tables/{table_id}/missing-terms/ignored", response_model=list[IgnoredTermRow])
async def list_ignored_terms(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[IgnoredTermRow]:
    rows = await MissingTermsService(db).list_ignored(table_id=table_id, user_id=current_user.id)
    return [IgnoredTermRow.model_validate(r) for r in rows]


@router.post("/api/tables/{table_id}/missing-terms-jobs", response_model=MissingTermsJobResponse, status_code=202)
async def create_job(table_id: uuid.UUID, payload: MissingTermsJobCreateRequest, current_user: CurrentUser, db: DbSession) -> MissingTermsJobResponse:
    job = await MissingTermsService(db).create_job(table_id=table_id, user_id=current_user.id, rows=[r.model_dump() for r in payload.rows])
    return MissingTermsJobResponse.model_validate(job)


@router.get("/api/tables/{table_id}/missing-terms-jobs", response_model=list[MissingTermsJobResponse])
async def list_jobs(
    table_id: uuid.UUID, current_user: CurrentUser, db: DbSession, include_dismissed: bool = Query(default=False)
) -> list[MissingTermsJobResponse]:
    jobs = await MissingTermsService(db).list_jobs(table_id=table_id, user_id=current_user.id, include_dismissed=include_dismissed)
    return [MissingTermsJobResponse.model_validate(j) for j in jobs]


@router.get("/api/missing-terms-jobs/{job_id}", response_model=MissingTermsJobResponse)
async def get_job(job_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> MissingTermsJobResponse:
    job = await MissingTermsService(db).get_job(job_id=job_id, user_id=current_user.id)
    return MissingTermsJobResponse.model_validate(job)


@router.post("/api/missing-terms-jobs/{job_id}/retry", response_model=MissingTermsJobResponse)
async def retry_job(job_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> MissingTermsJobResponse:
    job = await MissingTermsService(db).retry_job(job_id=job_id, user_id=current_user.id)
    return MissingTermsJobResponse.model_validate(job)


@router.post("/api/missing-terms-jobs/{job_id}/dismiss", status_code=204)
async def dismiss_job(job_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await MissingTermsService(db).dismiss_job(job_id=job_id, user_id=current_user.id)


@router.post("/api/missing-terms-jobs/{job_id}/import", response_model=ImportResponse)
async def import_results(job_id: uuid.UUID, payload: ImportRequest, current_user: CurrentUser, db: DbSession) -> ImportResponse:
    results = await MissingTermsService(db).import_results(
        job_id=job_id, user_id=current_user.id, selections=[s.model_dump() for s in payload.selections]
    )
    return ImportResponse(results=[ImportResultRow(**r) for r in results])


@router.post("/api/tables/{table_id}/missing-terms/manual-insert", response_model=RecordResponse)
async def manual_insert(table_id: uuid.UUID, payload: ManualInsertRequest, current_user: CurrentUser, db: DbSession) -> RecordResponse:
    return await MissingTermsService(db).manual_insert(
        table_id=table_id, user_id=current_user.id, sub_domain=payload.sub_domain, term_name=payload.term_name, values=payload.values, on_conflict=payload.on_conflict
    )
