import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.automations.schemas import (
    AutomationActionCreateRequest,
    AutomationActionResponse,
    AutomationCreateRequest,
    AutomationResponse,
    AutomationRunResponse,
    AutomationUpdateRequest,
)
from app.modules.automations.service import AutomationService

router = APIRouter(tags=["automations"])


@router.post("/api/tables/{table_id}/automations", response_model=AutomationResponse, status_code=201)
async def create_automation(table_id: uuid.UUID, payload: AutomationCreateRequest, current_user: CurrentUser, db: DbSession) -> AutomationResponse:
    automation = await AutomationService(db).create(
        table_id=table_id, user_id=current_user.id, name=payload.name, trigger_type=payload.trigger_type, trigger_config=payload.trigger_config
    )
    return AutomationResponse.model_validate(automation)


@router.get("/api/tables/{table_id}/automations", response_model=list[AutomationResponse])
async def list_automations(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[AutomationResponse]:
    automations = await AutomationService(db).list_for_table(table_id=table_id, user_id=current_user.id)
    return [AutomationResponse.model_validate(a) for a in automations]


@router.patch("/api/automations/{automation_id}", response_model=AutomationResponse)
async def update_automation(automation_id: uuid.UUID, payload: AutomationUpdateRequest, current_user: CurrentUser, db: DbSession) -> AutomationResponse:
    automation = await AutomationService(db).update(
        automation_id=automation_id,
        user_id=current_user.id,
        name=payload.name,
        is_enabled=payload.is_enabled,
        trigger_config=payload.trigger_config,
    )
    return AutomationResponse.model_validate(automation)


@router.delete("/api/automations/{automation_id}", status_code=204)
async def delete_automation(automation_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await AutomationService(db).delete(automation_id=automation_id, user_id=current_user.id)


@router.post("/api/automations/{automation_id}/actions", response_model=AutomationActionResponse, status_code=201)
async def create_automation_action(
    automation_id: uuid.UUID, payload: AutomationActionCreateRequest, current_user: CurrentUser, db: DbSession
) -> AutomationActionResponse:
    action = await AutomationService(db).create_action(
        automation_id=automation_id, user_id=current_user.id, action_type=payload.action_type, config=payload.config
    )
    return AutomationActionResponse.model_validate(action)


@router.get("/api/automations/{automation_id}/actions", response_model=list[AutomationActionResponse])
async def list_automation_actions(automation_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[AutomationActionResponse]:
    actions = await AutomationService(db).list_actions(automation_id=automation_id, user_id=current_user.id)
    return [AutomationActionResponse.model_validate(a) for a in actions]


@router.delete("/api/automations/{automation_id}/actions/{action_id}", status_code=204)
async def delete_automation_action(automation_id: uuid.UUID, action_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await AutomationService(db).delete_action(automation_id=automation_id, action_id=action_id, user_id=current_user.id)


@router.get("/api/automations/{automation_id}/runs", response_model=list[AutomationRunResponse])
async def list_automation_runs(automation_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[AutomationRunResponse]:
    runs = await AutomationService(db).list_runs(automation_id=automation_id, user_id=current_user.id)
    return [AutomationRunResponse.model_validate(r) for r in runs]
