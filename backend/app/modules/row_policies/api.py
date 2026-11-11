import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.row_policies.schemas import RowLevelPolicyCreateRequest, RowLevelPolicyResponse
from app.modules.row_policies.service import RowPolicyService

router = APIRouter(tags=["row-policies"])


@router.post("/api/tables/{table_id}/row-level-policies", response_model=RowLevelPolicyResponse, status_code=201)
async def set_row_level_policy(
    table_id: uuid.UUID, payload: RowLevelPolicyCreateRequest, current_user: CurrentUser, db: DbSession
) -> RowLevelPolicyResponse:
    policy = await RowPolicyService(db).create_or_replace(
        table_id=table_id, actor_id=current_user.id, target_user_id=payload.target_user_id, filter_dict=payload.filter
    )
    return RowLevelPolicyResponse.model_validate(policy)


@router.get("/api/tables/{table_id}/row-level-policies", response_model=list[RowLevelPolicyResponse])
async def list_row_level_policies(table_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[RowLevelPolicyResponse]:
    policies = await RowPolicyService(db).list_for_table(table_id=table_id, user_id=current_user.id)
    return [RowLevelPolicyResponse.model_validate(p) for p in policies]


@router.delete("/api/tables/{table_id}/row-level-policies/{policy_id}", status_code=204)
async def delete_row_level_policy(table_id: uuid.UUID, policy_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await RowPolicyService(db).delete(table_id=table_id, actor_id=current_user.id, policy_id=policy_id)
