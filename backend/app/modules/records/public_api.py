"""Unauthenticated route for a form view the owner has explicitly shared (see
BasesService.create_view_share_link). No CurrentUser dependency anywhere in
this file -- that's deliberate, not an oversight."""

from fastapi import APIRouter, Depends

from app.core.deps import DbSession
from app.core.rate_limit import rate_limit
from app.modules.bases.schemas import PublicFormFieldResponse, PublicFormResponse, PublicFormSubmitRequest
from app.modules.bases.service import BasesService
from app.modules.records.schemas import RecordResponse
from app.modules.records.service import RecordService

router = APIRouter(prefix="/api/public/forms", tags=["public-forms"])

# Generous enough for a real person submitting/retrying a form, tight enough
# to block a scripted flood -- this is the one write path in the whole public
# surface, so it's the highest-value place to rate limit by far.
_form_submit_rate_limit = rate_limit(key_prefix="form_submit", max_requests=10, window_seconds=60)


@router.get("/{token}", response_model=PublicFormResponse)
async def get_public_form(token: str, db: DbSession) -> PublicFormResponse:
    table, view, fields = await BasesService(db).get_public_form(token=token)
    return PublicFormResponse(
        table_name=table.name,
        view_name=view.name,
        description=view.config.get("description"),
        fields=[PublicFormFieldResponse.model_validate(f) for f in fields],
    )


@router.post("/{token}/submit", response_model=RecordResponse, status_code=201, dependencies=[Depends(_form_submit_rate_limit)])
async def submit_public_form(token: str, payload: PublicFormSubmitRequest, db: DbSession) -> RecordResponse:
    return await RecordService(db).create_record_via_form(view_token=token, values=payload.values)
