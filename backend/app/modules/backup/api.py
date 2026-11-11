import uuid

from fastapi import APIRouter, Response

from app.core.deps import CurrentUser, DbSession
from app.modules.backup.schemas import BaseExport
from app.modules.backup.service import BackupService
from app.modules.bases.schemas import BaseResponse

router = APIRouter(tags=["backup"])


@router.get("/api/bases/{base_id}/export", response_model=BaseExport)
async def export_base(base_id: uuid.UUID, current_user: CurrentUser, db: DbSession, response: Response) -> BaseExport:
    export = await BackupService(db).export_base(base_id=base_id, user_id=current_user.id)
    safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in export.name).strip() or "base"
    response.headers["Content-Disposition"] = f'attachment; filename="{safe_name}.json"'
    return export


@router.post("/api/workspaces/{workspace_id}/bases/import", response_model=BaseResponse, status_code=201)
async def import_base(workspace_id: uuid.UUID, payload: BaseExport, current_user: CurrentUser, db: DbSession) -> BaseResponse:
    base = await BackupService(db).import_base(workspace_id=workspace_id, user_id=current_user.id, data=payload)
    return BaseResponse.model_validate(base)
