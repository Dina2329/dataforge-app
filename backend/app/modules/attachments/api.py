import uuid

from fastapi import APIRouter, File, Response, UploadFile

from app.core.deps import CurrentUser, DbSession
from app.modules.attachments.service import AttachmentService
from app.modules.records.schemas import RecordResponse

router = APIRouter(tags=["attachments"])


@router.post(
    "/api/tables/{table_id}/rows/{row_id}/fields/{field_id}/attachments",
    response_model=RecordResponse,
    status_code=201,
)
async def upload_attachment(
    table_id: uuid.UUID,
    row_id: int,
    field_id: uuid.UUID,
    current_user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> RecordResponse:
    data = await file.read()
    return await AttachmentService(db).upload(
        table_id=table_id,
        row_id=row_id,
        field_id=field_id,
        user_id=current_user.id,
        filename=file.filename or "upload",
        content_type=file.content_type,
        data=data,
    )


@router.delete(
    "/api/tables/{table_id}/rows/{row_id}/fields/{field_id}/attachments/{attachment_id}",
    response_model=RecordResponse,
)
async def delete_attachment(
    table_id: uuid.UUID, row_id: int, field_id: uuid.UUID, attachment_id: str, current_user: CurrentUser, db: DbSession
) -> RecordResponse:
    return await AttachmentService(db).delete(
        table_id=table_id, row_id=row_id, field_id=field_id, attachment_id=attachment_id, user_id=current_user.id
    )


@router.get("/api/tables/{table_id}/rows/{row_id}/fields/{field_id}/attachments/{attachment_id}/download")
async def download_attachment(
    table_id: uuid.UUID, row_id: int, field_id: uuid.UUID, attachment_id: str, current_user: CurrentUser, db: DbSession
) -> Response:
    data, descriptor = await AttachmentService(db).download(
        table_id=table_id, row_id=row_id, field_id=field_id, attachment_id=attachment_id, user_id=current_user.id
    )
    return Response(
        content=data,
        media_type=descriptor["content_type"],
        headers={"Content-Disposition": f'attachment; filename="{descriptor["filename"]}"'},
    )
