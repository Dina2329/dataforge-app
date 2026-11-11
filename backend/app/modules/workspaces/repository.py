import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workspaces.models import Team, TeamMembership, Workspace, WorkspaceMembership, WorkspaceRole


class WorkspaceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, name: str, owner_id: uuid.UUID) -> Workspace:
        workspace = Workspace(name=name, created_by=owner_id)
        self.db.add(workspace)
        await self.db.flush()
        self.db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=owner_id, role=WorkspaceRole.OWNER))
        await self.db.flush()
        return workspace

    async def list_for_user(self, user_id: uuid.UUID) -> list[Workspace]:
        stmt = (
            select(Workspace)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .where(WorkspaceMembership.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_membership(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceMembership | None:
        stmt = select(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get(self, workspace_id: uuid.UUID) -> Workspace | None:
        return await self.db.get(Workspace, workspace_id)

    async def list_memberships(self, workspace_id: uuid.UUID) -> list[WorkspaceMembership]:
        result = await self.db.execute(select(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace_id))
        return list(result.scalars().all())

    async def count_owners(self, workspace_id: uuid.UUID) -> int:
        stmt = select(func.count()).where(
            WorkspaceMembership.workspace_id == workspace_id, WorkspaceMembership.role == WorkspaceRole.OWNER
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def add_membership(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, role: WorkspaceRole) -> WorkspaceMembership:
        membership = WorkspaceMembership(workspace_id=workspace_id, user_id=user_id, role=role)
        self.db.add(membership)
        await self.db.flush()
        return membership

    async def delete_membership(self, membership: WorkspaceMembership) -> None:
        await self.db.delete(membership)
        await self.db.flush()

    async def delete(self, workspace: Workspace) -> None:
        # Every df_meta child table (bases, dashboards, data_sources, teams,
        # memberships, audit log...) has an ON DELETE CASCADE FK back to
        # workspaces, so this one delete clears all of it. The df_data
        # physical tables are NOT part of that FK graph -- the caller
        # (WorkspaceService.delete) must drop those first.
        await self.db.delete(workspace)
        await self.db.flush()


class TeamRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, workspace_id: uuid.UUID, name: str, created_by: uuid.UUID) -> Team:
        team = Team(workspace_id=workspace_id, name=name, created_by=created_by)
        self.db.add(team)
        await self.db.flush()
        return team

    async def list_for_workspace(self, workspace_id: uuid.UUID) -> list[Team]:
        result = await self.db.execute(select(Team).where(Team.workspace_id == workspace_id))
        return list(result.scalars().all())

    async def get(self, team_id: uuid.UUID) -> Team | None:
        return await self.db.get(Team, team_id)

    async def delete(self, team: Team) -> None:
        await self.db.delete(team)
        await self.db.flush()

    async def list_members(self, team_id: uuid.UUID) -> list[TeamMembership]:
        result = await self.db.execute(select(TeamMembership).where(TeamMembership.team_id == team_id))
        return list(result.scalars().all())

    async def get_member(self, *, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamMembership | None:
        stmt = select(TeamMembership).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def add_member(self, *, team_id: uuid.UUID, user_id: uuid.UUID) -> TeamMembership:
        member = TeamMembership(team_id=team_id, user_id=user_id)
        self.db.add(member)
        await self.db.flush()
        return member

    async def remove_member(self, member: TeamMembership) -> None:
        await self.db.delete(member)
        await self.db.flush()
