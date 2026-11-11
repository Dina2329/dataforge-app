import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.modules.audit.service import AuditService
from app.modules.bases.service import BasesService
from app.modules.connectors.models import TableSyncConfig
from app.modules.connectors.repository import TableSyncConfigRepository
from app.modules.connectors.service import WRITABLE_SOURCE_TYPES
from app.modules.workspaces.permissions import Permission

# After this many consecutive failed pushes, sync auto-disables itself rather
# than notifying on every subsequent edit forever -- a persistently broken
# connection (revoked credentials, a dropped external table) shouldn't turn
# into an unbounded stream of "sync failed" notifications.
AUTO_DISABLE_THRESHOLD = 5


class TableSyncService:
    """Owns table_sync_configs -- used both by ImportService (creating the
    initial link) and by the push-to-source worker task (reading/updating
    sync health). Deliberately separate from ImportService: this is ongoing
    per-table state, not a one-shot import concern."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = TableSyncConfigRepository(db)
        self.bases = BasesService(db)
        self.audit = AuditService(db)

    async def get_config_for_table(self, table_id: uuid.UUID) -> TableSyncConfig | None:
        """Unchecked -- for internal callers only (the push-to-source worker
        task, which already validated the table another way). API endpoints
        must use get_config_for_table_checked instead."""
        return await self.repo.get_for_table(table_id)

    async def get_config_for_table_checked(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> TableSyncConfig | None:
        await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        return await self.repo.get_for_table(table_id)

    async def _check_permission(self, table_id: uuid.UUID, user_id: uuid.UUID) -> TableSyncConfig:
        config = await self.repo.get_for_table(table_id)
        if config is None:
            raise NotFoundError("This table isn't synced with a data source")
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.DATA_SOURCE_WRITE)
        return config

    async def set_enabled(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, enabled: bool, requires_approval: bool | None = None
    ) -> TableSyncConfig:
        config = await self._check_permission(table_id, user_id)
        config.sync_enabled = enabled
        if enabled:
            config.consecutive_failures = 0
        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="table_sync.enabled" if enabled else "table_sync.disabled",
            resource_type="table", resource_id=str(table_id),
        )
        if requires_approval is not None:
            # Deliberately a stricter, separate permission check than the
            # sync_enabled toggle above: if any editor could flip this back
            # off themselves, the entire approval gate would be trivially
            # bypassable by the exact people it exists to put a check on.
            await self.bases.workspaces.require_permission(
                workspace_id=workspace_id, user_id=user_id, permission=Permission.SYNC_APPROVAL_MANAGE
            )
            config.push_requires_approval = requires_approval
            await self.audit.log(
                workspace_id=workspace_id, user_id=user_id,
                action="table_sync.approval_required" if requires_approval else "table_sync.approval_not_required",
                resource_type="table", resource_id=str(table_id),
            )
        await self.db.commit()
        return config

    async def unlink(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> None:
        config = await self._check_permission(table_id, user_id)
        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="table_sync.unlinked", resource_type="table", resource_id=str(table_id),
        )
        await self.repo.delete(config)
        await self.db.commit()

    async def prepare_manual_poll(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> TableSyncConfig:
        """"Sync now" -- runs a pull immediately instead of waiting for
        poll_interval_seconds. Also doubles as the only way to recover from
        poll_paused today: _poll_table_sync returns immediately without
        attempting anything once paused (see sync_tasks.py), and
        configure_pull only clears poll_paused when external_updated_at_column
        is actually changed to a *different* value -- there was previously no
        way to just retry with the same column. An explicit manual trigger
        clearing pause state is a reasonable, low-risk recovery action: if
        the underlying problem isn't fixed, the very next poll just re-pauses
        it via the normal failure path, no worse off than before."""
        config = await self._check_permission(table_id, user_id)
        if config.external_updated_at_column is None:
            raise ValidationError("Configure pull (pick an updated-at column) before running a manual sync")
        if config.poll_paused:
            config.poll_paused = False
            config.poll_consecutive_failures = 0
            config.poll_last_error = None
            config.poll_last_error_at = None
        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="table_sync.manual_poll_triggered",
            resource_type="table", resource_id=str(table_id),
        )
        await self.db.commit()
        return config

    # -- Worker-side (no permission check -- called from the push-to-source
    # task's own session, on data it already validated by loading the config) --

    async def record_success(self, config: TableSyncConfig) -> None:
        config.consecutive_failures = 0
        config.last_error = None
        config.last_error_at = None

    async def record_failure(self, config: TableSyncConfig, error: str) -> bool:
        """Returns True if this failure just crossed the auto-disable threshold."""
        config.consecutive_failures += 1
        config.last_error = error[:1000]
        config.last_error_at = datetime.now(timezone.utc)
        if config.consecutive_failures >= AUTO_DISABLE_THRESHOLD and config.sync_enabled:
            config.sync_enabled = False
            return True
        return False

    # -- Pull health (Stage 2) -- deliberately separate fields/counters from
    # the push ones above, so a broken poll can never silently disable a
    # healthy push (or vice versa). Same threshold, independent axis.

    async def record_poll_success(self, config: TableSyncConfig) -> None:
        config.poll_consecutive_failures = 0
        config.poll_last_error = None
        config.poll_last_error_at = None

    async def record_poll_failure(self, config: TableSyncConfig, error: str) -> bool:
        """Returns True if this failure just crossed the auto-pause threshold."""
        config.poll_consecutive_failures += 1
        config.poll_last_error = error[:1000]
        config.poll_last_error_at = datetime.now(timezone.utc)
        if config.poll_consecutive_failures >= AUTO_DISABLE_THRESHOLD and not config.poll_paused:
            config.poll_paused = True
            return True
        return False

    # -- Pull configuration --

    async def configure_pull(
        self,
        *,
        table_id: uuid.UUID,
        user_id: uuid.UUID,
        external_updated_at_column: str | None,
        poll_interval_seconds: int | None,
        deletion_check_interval_seconds: int | None,
        server_time: datetime | None,
    ) -> TableSyncConfig:
        """server_time is the external DB's own current time (from
        connector.get_server_time()), passed in by the caller (the API
        handler, which is the one place already holding a live connector) --
        this service has no connector of its own to fetch it with. Only
        needed when external_updated_at_column is actually changing."""
        config = await self._check_permission(table_id, user_id)
        column_changed = external_updated_at_column != config.external_updated_at_column
        config.external_updated_at_column = external_updated_at_column
        config.poll_interval_seconds = poll_interval_seconds
        config.deletion_check_interval_seconds = deletion_check_interval_seconds
        if column_changed:
            # A stale watermark compared against a *different* column's value
            # domain can silently skip that column's whole history, or force
            # a needless full rescan -- reset rather than reuse it. Starting
            # from "now" means anything that changed externally before pull
            # was turned on for this column is not retroactively reconciled
            # (documented limitation, not a bug).
            config.last_polled_at = server_time if external_updated_at_column else None
            config.next_poll_at = None
            config.poll_paused = False
            config.poll_consecutive_failures = 0
        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="table_sync.pull_configured",
            resource_type="table", resource_id=str(table_id),
            details={"external_updated_at_column": external_updated_at_column, "poll_interval_seconds": poll_interval_seconds},
        )
        await self.db.commit()
        return config


def require_writable_source_type(source_type: str) -> None:
    if source_type not in WRITABLE_SOURCE_TYPES:
        raise ValidationError(f"Sync isn't supported for '{source_type}' sources yet — only Postgres and MySQL")
