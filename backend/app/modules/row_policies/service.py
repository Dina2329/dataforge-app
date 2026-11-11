import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.query.filter_dsl import FilterCondition, FilterGroup, compile_filter, parse_filter_expr
from app.modules.audit.service import AuditService
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.service import BasesService
from app.modules.row_policies.models import RowLevelPolicy
from app.modules.row_policies.repository import RowLevelPolicyRepository
from app.modules.workspaces.models import WorkspaceRole
from app.modules.workspaces.permissions import Permission


class RowPolicyService:
    """Row-level RBAC overrides (architecture plan, section 3). A policy scopes
    one member's visibility on one table to rows matching a stored FilterExpr
    -- read-side enforcement lives in RecordService.get_effective_filter,
    called on every list/update/delete so a scoped-out row is invisible and
    unmodifiable, not just hidden from the grid."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = RowLevelPolicyRepository(db)
        self.bases = BasesService(db)
        self.audit = AuditService(db)

    async def _validate_filter(self, *, table, filter_dict: dict[str, Any]) -> FilterCondition | FilterGroup:
        filter_expr = parse_filter_expr(filter_dict)
        fields = await self.bases.fields.list_for_table(table.id)
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        columns_map = {f.name: sa_table.c[f.db_column_name] for f in fields if not get_field_type(f.field_type).is_virtual}
        compile_filter(filter_expr, columns_map)  # raises ValidationError on an unknown/virtual field -- validation only
        return filter_expr

    async def create_or_replace(
        self, *, table_id: uuid.UUID, actor_id: uuid.UUID, target_user_id: uuid.UUID, filter_dict: dict[str, Any]
    ) -> RowLevelPolicy:
        table = await self.bases.check_table_permission(table_id=table_id, user_id=actor_id, permission=Permission.ROW_LEVEL_POLICY_WRITE)
        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        await self.bases.workspaces.require_member(workspace_id=workspace_id, user_id=target_user_id)
        await self._validate_filter(table=table, filter_dict=filter_dict)

        existing = await self.repo.get_for_table_and_user(table_id, target_user_id)
        if existing is not None:
            existing.filter = filter_dict
            policy = existing
        else:
            policy = await self.repo.create(table_id=table_id, user_id=target_user_id, filter=filter_dict, created_by=actor_id)

        await self.audit.log(
            workspace_id=workspace_id, user_id=actor_id, action="row_level_policy.set", resource_type="row_level_policy",
            resource_id=str(policy.id), details={"table_id": str(table_id), "target_user_id": str(target_user_id), "filter": filter_dict},
        )
        await self.db.commit()
        return policy

    async def list_for_table(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> list[RowLevelPolicy]:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.ROW_LEVEL_POLICY_WRITE)
        return await self.repo.list_for_table(table_id)

    async def delete(self, *, table_id: uuid.UUID, actor_id: uuid.UUID, policy_id: uuid.UUID) -> None:
        await self.bases.check_table_permission(table_id=table_id, user_id=actor_id, permission=Permission.ROW_LEVEL_POLICY_WRITE)
        policy = await self.repo.get(policy_id)
        if policy is None or policy.table_id != table_id:
            raise NotFoundError("Row-level policy not found")

        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=actor_id, action="row_level_policy.removed", resource_type="row_level_policy",
            resource_id=str(policy.id), details={"table_id": str(table_id), "target_user_id": str(policy.user_id)},
        )
        await self.repo.delete(policy)
        await self.db.commit()

    async def get_effective_filter(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, role: WorkspaceRole | None = None
    ) -> FilterCondition | FilterGroup | None:
        """None means unscoped (owners/admins always bypass, and a member with
        no stored policy sees everything, same as today).

        `role` lets a caller that already ran a permission check moments ago
        (e.g. RecordService's create/update/delete, via
        BasesService.check_table_permission_with_context) pass its result
        straight through instead of this re-deriving the same role via its
        own table+base+membership lookup right after."""
        if role is None:
            role = await self.bases.get_role_for_table(table_id=table_id, user_id=user_id)
        if role in (WorkspaceRole.OWNER, WorkspaceRole.ADMIN):
            return None
        policy = await self.repo.get_for_table_and_user(table_id, user_id)
        if policy is None:
            return None
        return parse_filter_expr(policy.filter)
