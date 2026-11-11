import uuid

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.modules.workspaces.schemas import (
    AddTeamMemberRequest,
    InviteMemberRequest,
    MemberResponse,
    TeamCreateRequest,
    TeamMemberResponse,
    TeamResponse,
    UpdateMemberRoleRequest,
    WorkspaceCreateRequest,
    WorkspaceResponse,
)
from app.modules.workspaces.service import WorkspaceService
from app.modules.workspaces.team_service import TeamService

router = APIRouter(prefix="/api/workspaces", tags=["workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(payload: WorkspaceCreateRequest, current_user: CurrentUser, db: DbSession) -> WorkspaceResponse:
    workspace = await WorkspaceService(db).create(name=payload.name, owner_id=current_user.id)
    return WorkspaceResponse.model_validate(workspace)


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(current_user: CurrentUser, db: DbSession) -> list[WorkspaceResponse]:
    workspaces = await WorkspaceService(db).list_for_user(current_user.id)
    return [WorkspaceResponse.model_validate(w) for w in workspaces]


@router.delete("/{workspace_id}", status_code=204)
async def delete_workspace(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await WorkspaceService(db).delete(workspace_id=workspace_id, user_id=current_user.id)


@router.get("/{workspace_id}/members", response_model=list[MemberResponse])
async def list_members(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[MemberResponse]:
    members = await WorkspaceService(db).list_members(workspace_id=workspace_id, user_id=current_user.id)
    return [MemberResponse(user_id=m.user_id, email=email, name=name, role=m.role) for m, email, name in members]


@router.post("/{workspace_id}/members", response_model=MemberResponse, status_code=201)
async def invite_member(
    workspace_id: uuid.UUID, payload: InviteMemberRequest, current_user: CurrentUser, db: DbSession
) -> MemberResponse:
    service = WorkspaceService(db)
    membership = await service.invite_member(
        workspace_id=workspace_id, inviter_id=current_user.id, email=payload.email, role=payload.role
    )
    user = await service.users.get_by_id(membership.user_id)
    return MemberResponse(user_id=user.id, email=user.email, name=user.name, role=membership.role)


@router.patch("/{workspace_id}/members/{target_user_id}", response_model=MemberResponse)
async def update_member_role(
    workspace_id: uuid.UUID, target_user_id: uuid.UUID, payload: UpdateMemberRoleRequest, current_user: CurrentUser, db: DbSession
) -> MemberResponse:
    service = WorkspaceService(db)
    membership = await service.update_member_role(
        workspace_id=workspace_id, actor_id=current_user.id, target_user_id=target_user_id, role=payload.role
    )
    user = await service.users.get_by_id(membership.user_id)
    return MemberResponse(user_id=user.id, email=user.email, name=user.name, role=membership.role)


@router.delete("/{workspace_id}/members/{target_user_id}", status_code=204)
async def remove_member(workspace_id: uuid.UUID, target_user_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await WorkspaceService(db).remove_member(workspace_id=workspace_id, actor_id=current_user.id, target_user_id=target_user_id)


@router.post("/{workspace_id}/teams", response_model=TeamResponse, status_code=201)
async def create_team(workspace_id: uuid.UUID, payload: TeamCreateRequest, current_user: CurrentUser, db: DbSession) -> TeamResponse:
    team = await TeamService(db).create(workspace_id=workspace_id, user_id=current_user.id, name=payload.name)
    return TeamResponse.model_validate(team)


@router.get("/{workspace_id}/teams", response_model=list[TeamResponse])
async def list_teams(workspace_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[TeamResponse]:
    teams = await TeamService(db).list_for_workspace(workspace_id=workspace_id, user_id=current_user.id)
    return [TeamResponse.model_validate(t) for t in teams]


@router.delete("/{workspace_id}/teams/{team_id}", status_code=204)
async def delete_team(workspace_id: uuid.UUID, team_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> None:
    await TeamService(db).delete(team_id=team_id, user_id=current_user.id)


@router.get("/{workspace_id}/teams/{team_id}/members", response_model=list[TeamMemberResponse])
async def list_team_members(workspace_id: uuid.UUID, team_id: uuid.UUID, current_user: CurrentUser, db: DbSession) -> list[TeamMemberResponse]:
    members = await TeamService(db).list_members(team_id=team_id, user_id=current_user.id)
    return [TeamMemberResponse(user_id=uid, email=email, name=name) for uid, email, name in members]


@router.post("/{workspace_id}/teams/{team_id}/members", status_code=201)
async def add_team_member(
    workspace_id: uuid.UUID, team_id: uuid.UUID, payload: AddTeamMemberRequest, current_user: CurrentUser, db: DbSession
) -> None:
    await TeamService(db).add_member(team_id=team_id, actor_id=current_user.id, email=payload.email)


@router.delete("/{workspace_id}/teams/{team_id}/members/{target_user_id}", status_code=204)
async def remove_team_member(
    workspace_id: uuid.UUID, team_id: uuid.UUID, target_user_id: uuid.UUID, current_user: CurrentUser, db: DbSession
) -> None:
    await TeamService(db).remove_member(team_id=team_id, actor_id=current_user.id, target_user_id=target_user_id)
