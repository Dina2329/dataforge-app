import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.bases.schemas import (
    BaseCreateRequest,
    BaseResponse,
    FieldCreateRequest,
    FieldResponse,
    FieldUpdateRequest,
    TableCreateRequest,
    TableResponse,
    ViewCreateRequest,
    ViewResponse,
    ViewUpdateRequest,
    table_to_response,
)
from app.modules.bases.service import BasesService

router = APIRouter(tags=["bases"])


@router.post("/api/workspaces/{workspace_id}/bases", response_model=BaseResponse, status_code=201)
async def create_base(workspace_id: uuid.UUID, payload: BaseCreateRequest, current_user: CurrentUser, db: DbSession) -> BaseResponse:
    base = await BasesService(db).create_base(workspace_id=workspace_id, name=payload.name, user_id=current_user.id)
    return BaseResponse.model_validate(base)


@router.get("/api/workspaces/{workspace_id}/bases", response_model=list[BaseResponse])
async def list_bases(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[BaseResponse]:
    bases = await BasesService(db).list_bases(workspace_id=workspace_id, user_id=current_user.id)
    return [BaseResponse.model_validate(b) for b in bases]


@router.get("/api/bases/{base_id}", response_model=BaseResponse)
async def get_base(base_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> BaseResponse:
    base = await BasesService(db).get_base(base_id=base_id, user_id=current_user.id)
    return BaseResponse.model_validate(base)


@router.delete("/api/bases/{base_id}", status_code=204)
async def delete_base(base_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await BasesService(db).delete_base(base_id=base_id, user_id=current_user.id)


@router.post("/api/bases/{base_id}/tables", response_model=TableResponse, status_code=201)
async def create_table(base_id: uuid.UUID, payload: TableCreateRequest, current_user: CurrentUser, db: DbSession) -> TableResponse:
    service = BasesService(db)
    table = await service.create_table(base_id=base_id, name=payload.name, user_id=current_user.id)
    _, fields, views = await service.get_table_detail(table_id=table.id, user_id=current_user.id)
    return table_to_response(table, fields, views)


@router.get("/api/bases/{base_id}/tables", response_model=list[TableResponse])
async def list_tables(base_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[TableResponse]:
    service = BasesService(db)
    tables = await service.list_tables(base_id=base_id, user_id=current_user.id)
    responses = []
    for table in tables:
        _, fields, views = await service.get_table_detail(table_id=table.id, user_id=current_user.id)
        responses.append(table_to_response(table, fields, views))
    return responses


@router.get("/api/tables/{table_id}", response_model=TableResponse)
async def get_table(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> TableResponse:
    table, fields, views = await BasesService(db).get_table_detail(table_id=table_id, user_id=current_user.id)
    return table_to_response(table, fields, views)


@router.delete("/api/tables/{table_id}", status_code=204)
async def delete_table(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await BasesService(db).delete_table(table_id=table_id, user_id=current_user.id)


@router.post("/api/tables/{table_id}/fields", response_model=FieldResponse, status_code=201)
async def create_field(table_id: uuid.UUID, payload: FieldCreateRequest, current_user: CurrentUser, db: DbSession) -> FieldResponse:
    field = await BasesService(db).create_field(
        table_id=table_id,
        user_id=current_user.id,
        name=payload.name,
        field_type=payload.field_type,
        options=payload.options,
        required=payload.required,
    )
    return FieldResponse.model_validate(field)


@router.patch("/api/tables/{table_id}/fields/{field_id}", response_model=FieldResponse)
async def update_field(
    table_id: uuid.UUID, field_id: uuid.UUID, payload: FieldUpdateRequest, current_user: CurrentUser, db: DbSession
) -> FieldResponse:
    field = await BasesService(db).update_field(
        table_id=table_id,
        field_id=field_id,
        user_id=current_user.id,
        name=payload.name,
        required=payload.required,
        options=payload.options,
    )
    return FieldResponse.model_validate(field)


@router.delete("/api/tables/{table_id}/fields/{field_id}", status_code=204)
async def delete_field(table_id: uuid.UUID, field_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await BasesService(db).delete_field(table_id=table_id, field_id=field_id, user_id=current_user.id)


@router.post("/api/tables/{table_id}/views", response_model=ViewResponse, status_code=201)
async def create_view(table_id: uuid.UUID, payload: ViewCreateRequest, current_user: CurrentUser, db: DbSession) -> ViewResponse:
    view = await BasesService(db).create_view(
        table_id=table_id, user_id=current_user.id, name=payload.name, view_type=payload.view_type, config=payload.config
    )
    return ViewResponse.model_validate(view)


@router.patch("/api/tables/{table_id}/views/{view_id}", response_model=ViewResponse)
async def update_view(
    table_id: uuid.UUID, view_id: uuid.UUID, payload: ViewUpdateRequest, current_user: CurrentUser, db: DbSession
) -> ViewResponse:
    view = await BasesService(db).update_view(
        table_id=table_id, view_id=view_id, user_id=current_user.id, name=payload.name, config=payload.config
    )
    return ViewResponse.model_validate(view)


@router.delete("/api/tables/{table_id}/views/{view_id}", status_code=204)
async def delete_view(table_id: uuid.UUID, view_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await BasesService(db).delete_view(table_id=table_id, view_id=view_id, user_id=current_user.id)


@router.post("/api/tables/{table_id}/views/{view_id}/share", response_model=ViewResponse)
async def create_view_share_link(table_id: uuid.UUID, view_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> ViewResponse:
    view = await BasesService(db).create_view_share_link(table_id=table_id, view_id=view_id, user_id=current_user.id)
    return ViewResponse.model_validate(view)


@router.delete("/api/tables/{table_id}/views/{view_id}/share", response_model=ViewResponse)
async def revoke_view_share_link(table_id: uuid.UUID, view_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> ViewResponse:
    view = await BasesService(db).revoke_view_share_link(table_id=table_id, view_id=view_id, user_id=current_user.id)
    return ViewResponse.model_validate(view)
