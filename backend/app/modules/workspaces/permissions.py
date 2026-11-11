"""Permission model (architecture plan, section 3's PolicyEngine).

Namespaced permission strings + a fixed role->permission mapping. Every
module that touches a workspace-scoped resource calls
WorkspaceService.require_permission() before mutating anything, so RBAC has
one enforcement seam instead of ad hoc role checks scattered through
endpoints. Reads stay gated on plain membership (require_member) — any role
can view; only mutations are permission-gated.
"""

from enum import StrEnum

from app.modules.workspaces.models import WorkspaceRole


class Permission(StrEnum):
    WORKSPACE_MANAGE_MEMBERS = "workspace.manage_members"
    SCHEMA_WRITE = "schema.write"  # create/delete bases, tables, fields
    RECORD_WRITE = "record.write"  # create/update records
    RECORD_DELETE = "record.delete"
    BULK_OP_EXECUTE = "bulk_op.execute"
    DATA_SOURCE_WRITE = "data_source.write"  # create/delete connections, import
    DASHBOARD_WRITE = "dashboard.write"  # create/edit/delete dashboards and widgets
    AUTOMATION_WRITE = "automation.write"  # create/edit/delete automations and actions
    AUDIT_LOG_READ = "audit_log.read"  # view the workspace's audit log
    ROW_LEVEL_POLICY_WRITE = "row_level_policy.write"  # scope another member's row visibility on a table
    SYNC_APPROVAL_MANAGE = "sync_approval.manage"  # approve/reject a pending push-to-source change
    PREREQUEST_MANAGE = "prerequest.manage"  # upload/replace/view the workspace's shared Missing Terms prerequest list


_ALL_PERMISSIONS = frozenset(Permission)
# Owner/admin only -- membership management, the audit log, row-level policy
# management, sync approval, and the shared prerequest list are all things a
# scoped-down editor/viewer shouldn't be able to see or touch (row-level
# policy doubly so: it would let an editor grant themselves or others row
# visibility; sync approval exists specifically so an editor's own edits need
# a second set of eyes before reaching a live external system -- an editor
# approving their own request would defeat the entire point; the prerequest
# list is shared across every table in the workspace, so an editor replacing
# it would silently change what every other table's Missing Terms Check
# compares against).
_ADMIN_ONLY = frozenset(
    {
        Permission.WORKSPACE_MANAGE_MEMBERS,
        Permission.AUDIT_LOG_READ,
        Permission.ROW_LEVEL_POLICY_WRITE,
        Permission.SYNC_APPROVAL_MANAGE,
        Permission.PREREQUEST_MANAGE,
    }
)
_NON_MEMBER_MANAGEMENT = frozenset(p for p in Permission if p not in _ADMIN_ONLY)

ROLE_PERMISSIONS: dict[WorkspaceRole, frozenset[Permission]] = {
    WorkspaceRole.OWNER: _ALL_PERMISSIONS,
    WorkspaceRole.ADMIN: _ALL_PERMISSIONS,
    WorkspaceRole.EDITOR: _NON_MEMBER_MANAGEMENT,
    WorkspaceRole.VIEWER: frozenset(),
}


def role_has_permission(role: str, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[WorkspaceRole(role)]
