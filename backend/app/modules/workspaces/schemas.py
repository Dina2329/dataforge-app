import uuid

from pydantic import BaseModel

from app.modules.workspaces.models import WorkspaceRole


class WorkspaceCreateRequest(BaseModel):
    name: str


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: WorkspaceRole


class InviteMemberRequest(BaseModel):
    email: str
    role: WorkspaceRole = WorkspaceRole.EDITOR


class UpdateMemberRoleRequest(BaseModel):
    role: WorkspaceRole


class TeamCreateRequest(BaseModel):
    name: str


class TeamResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str

    model_config = {"from_attributes": True}


class TeamMemberResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str


class AddTeamMemberRequest(BaseModel):
    email: str
