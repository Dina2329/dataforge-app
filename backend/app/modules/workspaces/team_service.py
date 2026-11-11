import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.modules.auth.repository import UserRepository
from app.modules.workspaces.models import Team
from app.modules.workspaces.permissions import Permission
from app.modules.workspaces.repository import TeamRepository
from app.modules.workspaces.service import WorkspaceService


class TeamService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TeamRepository(db)
        self.users = UserRepository(db)
        self.workspaces = WorkspaceService(db)

    async def create(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, name: str) -> Team:
        await self.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.WORKSPACE_MANAGE_MEMBERS)
        team = await self.repo.create(workspace_id=workspace_id, name=name, created_by=user_id)
        await self.db.commit()
        return team

    async def list_for_workspace(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> list[Team]:
        await self.workspaces.require_member(workspace_id=workspace_id, user_id=user_id)
        return await self.repo.list_for_workspace(workspace_id)

    async def _get_team_or_404(self, team_id: uuid.UUID) -> Team:
        team = await self.repo.get(team_id)
        if team is None:
            raise NotFoundError("Team not found")
        return team

    async def delete(self, *, team_id: uuid.UUID, user_id: uuid.UUID) -> None:
        team = await self._get_team_or_404(team_id)
        await self.workspaces.require_permission(workspace_id=team.workspace_id, user_id=user_id, permission=Permission.WORKSPACE_MANAGE_MEMBERS)
        await self.repo.delete(team)
        await self.db.commit()

    async def list_members(self, *, team_id: uuid.UUID, user_id: uuid.UUID) -> list[tuple[uuid.UUID, str, str]]:
        team = await self._get_team_or_404(team_id)
        await self.workspaces.require_member(workspace_id=team.workspace_id, user_id=user_id)
        members = await self.repo.list_members(team_id)
        result = []
        for member in members:
            user = await self.users.get_by_id(member.user_id)
            result.append((user.id, user.email, user.name))
        return result

    async def add_member(self, *, team_id: uuid.UUID, actor_id: uuid.UUID, email: str) -> None:
        team = await self._get_team_or_404(team_id)
        await self.workspaces.require_permission(workspace_id=team.workspace_id, user_id=actor_id, permission=Permission.WORKSPACE_MANAGE_MEMBERS)

        user = await self.users.get_by_email(email)
        if user is None:
            raise NotFoundError(f"No user with email {email}")
        if await self.workspaces.repo.get_membership(workspace_id=team.workspace_id, user_id=user.id) is None:
            raise ValidationError(f"{email} must be a workspace member before joining a team")
        if await self.repo.get_member(team_id=team_id, user_id=user.id) is not None:
            raise ValidationError(f"{email} is already on this team")

        await self.repo.add_member(team_id=team_id, user_id=user.id)
        await self.db.commit()

    async def remove_member(self, *, team_id: uuid.UUID, actor_id: uuid.UUID, target_user_id: uuid.UUID) -> None:
        team = await self._get_team_or_404(team_id)
        await self.workspaces.require_permission(workspace_id=team.workspace_id, user_id=actor_id, permission=Permission.WORKSPACE_MANAGE_MEMBERS)

        member = await self.repo.get_member(team_id=team_id, user_id=target_user_id)
        if member is None:
            raise NotFoundError("That user is not on this team")
        await self.repo.remove_member(member)
        await self.db.commit()
