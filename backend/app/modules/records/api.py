import json
import re
import uuid

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from app.core.deps import CurrentUser, DbSession
from app.core.errors import ValidationError
from app.modules.records.schemas import RecordCreateRequest, RecordListResponse, RecordResponse, RecordUpdateRequest
from app.modules.records.service import DEFAULT_PAGE_SIZE, RecordService

router = APIRouter(tags=["records"])


def _parse_filter_param(filter: str | None) -> dict | None:
    if filter is None:
        return None
    try:
        return json.loads(filter)
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid filter") from exc


def _parse_sort_param(sort: str | None) -> list[dict] | None:
    """JSON-encoded array of {field, direction}, in priority order -- e.g.
    '[{"field":"Status","direction":"asc"},{"field":"Name","direction":"desc"}]'."""
    if sort is None:
        return None
    try:
        parsed = json.loads(sort)
    except json.JSONDecodeError as exc:
        raise ValidationError("Invalid sort") from exc
    if not isinstance(parsed, list):
        raise ValidationError("sort must be a JSON array")
    return parsed


@router.get("/api/tables/{table_id}/rows", response_model=RecordListResponse)
async def list_rows(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    cursor: str | None = Query(default=None),
    limit: int = Query(default=DEFAULT_PAGE_SIZE),
    sort: str | None = Query(default=None),
    filter: str | None = Query(default=None),
) -> RecordListResponse:
    return await RecordService(db).list_records(
        table_id=table_id,
        user_id=current_user.id,
        cursor=cursor,
        limit=limit,
        sort=_parse_sort_param(sort),
        view_filter=_parse_filter_param(filter),
    )


@router.get("/api/fields/{field_id}/filter-values")
async def distinct_field_values(
    field_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=500, le=1000),
    apply_exclusion: bool = Query(default=True),
    filter: str | None = Query(default=None),
) -> dict:
    values = await RecordService(db).distinct_field_values(
        field_id=field_id,
        user_id=current_user.id,
        limit=limit,
        apply_exclusion=apply_exclusion,
        other_filter=_parse_filter_param(filter),
    )
    return {"values": values}


@router.get("/api/tables/{table_id}/export-csv")
async def export_csv(
    table_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    sort: str | None = Query(default=None),
    filter: str | None = Query(default=None),
) -> StreamingResponse:
    service = RecordService(db)
    table_name = await service.get_table_name_checked(table_id=table_id, user_id=current_user.id)
    safe_name = re.sub(r"[^A-Za-z0-9 _-]", "", table_name).strip() or "export"
    rows = service.export_csv_rows(
        table_id=table_id,
        user_id=current_user.id,
        sort=_parse_sort_param(sort),
        view_filter=_parse_filter_param(filter),
    )
    return StreamingResponse(
        rows,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.csv"'},
    )


@router.post("/api/tables/{table_id}/rows", response_model=RecordResponse, status_code=201)
async def create_row(table_id: uuid.UUID, payload: RecordCreateRequest, current_user: CurrentUser, db: DbSession) -> RecordResponse:
    return await RecordService(db).create_record(table_id=table_id, user_id=current_user.id, values=payload.values)


@router.patch("/api/tables/{table_id}/rows/{row_id}", response_model=RecordResponse)
async def update_row(
    table_id: uuid.UUID, row_id: int, payload: RecordUpdateRequest, current_user: CurrentUser, db: DbSession
) -> RecordResponse:
    return await RecordService(db).update_record(
        table_id=table_id,
        row_id=row_id,
        user_id=current_user.id,
        values=payload.values,
        expected_version=payload.expected_version,
    )


@router.delete("/api/tables/{table_id}/rows/{row_id}", status_code=204)
async def delete_row(table_id: uuid.UUID, row_id: int, current_user: CurrentUser, db: DbSession) -> None:
    await RecordService(db).delete_record(table_id=table_id, row_id=row_id, user_id=current_user.id)
