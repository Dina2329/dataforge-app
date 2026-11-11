import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.modules.audit.service import AuditService
from app.modules.auth.repository import UserRepository
from app.modules.bases import schema_service
from app.modules.bases.models import Base, Field, Table
from app.modules.workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole
from app.modules.workspaces.permissions import Permission, role_has_permission
from app.modules.workspaces.repository import WorkspaceRepository


class WorkspaceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = WorkspaceRepository(db)
        self.users = UserRepository(db)
        self.audit = AuditService(db)

    async def create(self, *, name: str, owner_id: uuid.UUID) -> Workspace:
        workspace = await self.repo.create(name=name, owner_id=owner_id)
        await self.db.commit()
        return workspace

    async def list_for_user(self, user_id: uuid.UUID) -> list[Workspace]:
        return await self.repo.list_for_user(user_id)

    async def delete(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Deleting a workspace is irreversible and takes every base, table,
        dashboard, automation, connection, and audit entry in it down too --
        restricted to owner/admin by role-literal check (see
        require_owner_or_admin) rather than the generic Permission system,
        which currently grants editors the same schema.write permission this
        would otherwise ride on."""
        await self.require_owner_or_admin(workspace_id=workspace_id, user_id=user_id)
        workspace = await self.repo.get(workspace_id)
        if workspace is None:
            raise NotFoundError("Workspace not found")

        # Every real physical df_data table (and link_to_record join table)
        # lives outside the df_meta FK graph, so it won't be touched by the
        # cascade below -- drop them explicitly first, or they'd become
        # permanently orphaned disk space with no metadata pointing at them.
        bases = (await self.db.execute(select(Base).where(Base.workspace_id == workspace_id))).scalars().all()
        for base in bases:
            tables = (await self.db.execute(select(Table).where(Table.base_id == base.id))).scalars().all()
            for table in tables:
                fields = (await self.db.execute(select(Field).where(Field.table_id == table.id))).scalars().all()
                for field in fields:
                    if field.field_type == "link_to_record":
                        await schema_service.drop_link_table(self.db, field.options["link_table_name"])
                await schema_service.drop_physical_table(self.db, table.physical_table_name)

        # No audit.log() call here -- audit_log_entries cascades from
        # workspaces too, so logging this action would just delete the log
        # entry along with everything else in the same transaction.
        await self.repo.delete(workspace)
        await self.db.commit()

    async def require_member(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceMembership:
        """Any role may read — this only gates that the user belongs to the
        workspace at all. Mutations go through require_permission instead."""
        membership = await self.repo.get_membership(workspace_id=workspace_id, user_id=user_id)
        if membership is None:
            if await self.repo.get(workspace_id) is None:
                raise NotFoundError("Workspace not found")
            raise ForbiddenError("You are not a member of this workspace")
        return membership

    async def require_permission(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, permission: Permission
    ) -> WorkspaceMembership:
        """The PolicyEngine stand-in (architecture plan, section 3) — every
        module that mutates a workspace-scoped resource calls this before
        acting, so RBAC has one enforcement seam instead of ad hoc role
        checks scattered through each module's endpoints."""
        membership = await self.require_member(workspace_id=workspace_id, user_id=user_id)
        if not role_has_permission(membership.role, permission):
            raise ForbiddenError(f"Your role ({membership.role}) does not have permission to do this")
        return membership

    async def list_member_ids_with_permission(self, *, workspace_id: uuid.UUID, permission: Permission) -> list[uuid.UUID]:
        """For fan-out notifications (e.g. sync approval) that need every
        member able to act on something, not just membership -- unlike
        require_permission this doesn't raise, an empty result just means
        nobody in this workspace currently holds that permission (a role
        change mid-flight, or a workspace with no admin yet)."""
        memberships = await self.repo.list_memberships(workspace_id)
        return [m.user_id for m in memberships if role_has_permission(m.role, permission)]

    async def require_owner_or_admin(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> WorkspaceMembership:
        """Creating or deleting something irreversible-ish at the base level
        (a whole workspace's base, taking real data and schema down with it
        if later deleted) is deliberately gated stricter than the generic
        Permission system: EDITOR currently shares schema.write with
        OWNER/ADMIN for tables/fields *inside* an existing base, but standing
        up or tearing down a base's container itself is reserved for
        owner/admin specifically, by role literal rather than by permission
        flag."""
        membership = await self.require_member(workspace_id=workspace_id, user_id=user_id)
        if membership.role not in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
            raise ForbiddenError("Only a workspace owner or admin can do this")
        return membership

    # -- Members -----------------------------------------------------------

    async def list_members(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> list[tuple[WorkspaceMembership, str, str]]:
        await self.require_member(workspace_id=workspace_id, user_id=user_id)
        memberships = await self.repo.list_memberships(workspace_id)
        result = []
        for membership in memberships:
            user = await self.users.get_by_id(membership.user_id)
            result.append((membership, user.email, user.name))
        return result

    async def invite_member(
        self, *, workspace_id: uuid.UUID, inviter_id: uuid.UUID, email: str, role: WorkspaceRole
    ) -> WorkspaceMembership:
        await self.require_permission(workspace_id=workspace_id, user_id=inviter_id, permission=Permission.WORKSPACE_MANAGE_MEMBERS)

        user = await self.users.get_by_email(email)
        if user is None:
            raise NotFoundError(f"No user with email {email} — they must register an account first")
        if await self.repo.get_membership(workspace_id=workspace_id, user_id=user.id) is not None:
            raise ValidationError(f"{email} is already a member of this workspace")

        membership = await self.repo.add_membership(workspace_id=workspace_id, user_id=user.id, role=role)
        await self.audit.log(
            workspace_id=workspace_id,
            user_id=inviter_id,
            action="member.invited",
            resource_type="member",
            resource_id=str(user.id),
            resource_label=email,
            details={"role": role.value},
        )
        await self.db.commit()
        return membership

    async def update_member_role(
        self, *, workspace_id: uuid.UUID, actor_id: uuid.UUID, target_user_id: uuid.UUID, role: WorkspaceRole
    ) -> WorkspaceMembership:
        await self.require_permission(workspace_id=workspace_id, user_id=actor_id, permission=Permission.WORKSPACE_MANAGE_MEMBERS)

        membership = await self.repo.get_membership(workspace_id=workspace_id, user_id=target_user_id)
        if membership is None:
            raise NotFoundError("That user is not a member of this workspace")

        if membership.role == WorkspaceRole.OWNER and role != WorkspaceRole.OWNER:
            if await self.repo.count_owners(workspace_id) <= 1:
                raise ValidationError("A workspace must have at least one owner")

        old_role = membership.role
        membership.role = role
        target_user = await self.users.get_by_id(target_user_id)
        await self.audit.log(
            workspace_id=workspace_id,
            user_id=actor_id,
            action="member.role_changed",
            resource_type="member",
            resource_id=str(target_user_id),
            resource_label=target_user.email if target_user else None,
            # old_role comes from an already-loaded ORM attribute -- the
            # role column is a plain String(50), not a SQLAlchemy Enum, so
            # what's loaded back is a raw str rather than a WorkspaceRole
            # instance. role.value is safe: it's the enum the API layer
            # already validated from the request body, never DB-loaded.
            details={"old_role": old_role, "new_role": role.value},
        )
        await self.db.commit()
        return membership

    async def remove_member(self, *, workspace_id: uuid.UUID, actor_id: uuid.UUID, target_user_id: uuid.UUID) -> None:
        await self.require_permission(workspace_id=workspace_id, user_id=actor_id, permission=Permission.WORKSPACE_MANAGE_MEMBERS)

        membership = await self.repo.get_membership(workspace_id=workspace_id, user_id=target_user_id)
        if membership is None:
            raise NotFoundError("That user is not a member of this workspace")

        if membership.role == WorkspaceRole.OWNER and await self.repo.count_owners(workspace_id) <= 1:
            raise ValidationError("A workspace must have at least one owner — transfer ownership before removing this member")

        target_user = await self.users.get_by_id(target_user_id)
        old_role = membership.role
        await self.repo.delete_membership(membership)
        await self.audit.log(
            workspace_id=workspace_id,
            user_id=actor_id,
            action="member.removed",
            resource_type="member",
            resource_id=str(target_user_id),
            resource_label=target_user.email if target_user else None,
            # Same DB-loaded-str reasoning as update_member_role above.
            details={"role": old_role},
        )
        await self.db.commit()
