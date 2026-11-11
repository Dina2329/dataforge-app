import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import User
from app.modules.bases.models import Base, Table
from app.modules.connectors.models import DataSource, PendingSyncChange, SyncChangeBatch, TableSyncConfig


class DataSourceRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, workspace_id: uuid.UUID, name: str, source_type: str, config_encrypted: str, created_by: uuid.UUID) -> DataSource:
        data_source = DataSource(
            workspace_id=workspace_id,
            name=name,
            source_type=source_type,
            config_encrypted=config_encrypted,
            created_by=created_by,
        )
        self.db.add(data_source)
        await self.db.flush()
        return data_source

    async def list_for_workspace(self, workspace_id: uuid.UUID) -> list[DataSource]:
        result = await self.db.execute(select(DataSource).where(DataSource.workspace_id == workspace_id))
        return list(result.scalars().all())

    async def get(self, data_source_id: uuid.UUID) -> DataSource | None:
        return await self.db.get(DataSource, data_source_id)

    async def delete(self, data_source: DataSource) -> None:
        await self.db.delete(data_source)
        await self.db.flush()


class TableSyncConfigRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        table_id: uuid.UUID,
        data_source_id: uuid.UUID,
        external_schema: str | None,
        external_table_name: str,
        external_pk_column: str,
        created_by: uuid.UUID,
    ) -> TableSyncConfig:
        config = TableSyncConfig(
            table_id=table_id,
            data_source_id=data_source_id,
            external_schema=external_schema,
            external_table_name=external_table_name,
            external_pk_column=external_pk_column,
            created_by=created_by,
        )
        self.db.add(config)
        await self.db.flush()
        return config

    async def get_for_table(self, table_id: uuid.UUID) -> TableSyncConfig | None:
        result = await self.db.execute(select(TableSyncConfig).where(TableSyncConfig.table_id == table_id))
        return result.scalar_one_or_none()

    async def exists_for_data_source(self, data_source_id: uuid.UUID) -> bool:
        result = await self.db.execute(select(TableSyncConfig.id).where(TableSyncConfig.data_source_id == data_source_id).limit(1))
        return result.scalar_one_or_none() is not None

    async def delete(self, config: TableSyncConfig) -> None:
        await self.db.delete(config)
        await self.db.flush()

    async def list_due_for_poll(self, now: datetime) -> list[TableSyncConfig]:
        result = await self.db.execute(
            select(TableSyncConfig).where(
                TableSyncConfig.sync_enabled.is_(True),
                TableSyncConfig.poll_paused.is_(False),
                TableSyncConfig.external_updated_at_column.isnot(None),
                or_(TableSyncConfig.next_poll_at.is_(None), TableSyncConfig.next_poll_at <= now),
            )
        )
        return list(result.scalars().all())

    async def list_due_for_deletion_check(self, now: datetime) -> list[TableSyncConfig]:
        result = await self.db.execute(
            select(TableSyncConfig).where(
                TableSyncConfig.sync_enabled.is_(True),
                TableSyncConfig.poll_paused.is_(False),
                TableSyncConfig.external_updated_at_column.isnot(None),
                TableSyncConfig.deletion_check_interval_seconds.isnot(None),
                or_(TableSyncConfig.next_deletion_check_at.is_(None), TableSyncConfig.next_deletion_check_at <= now),
            )
        )
        return list(result.scalars().all())


class PendingSyncChangeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_pending_for_row(self, *, table_id: uuid.UUID, row_id: int) -> PendingSyncChange | None:
        """Any not-yet-resolved row -- draft (still being accumulated by its
        editor) or pending (already submitted, awaiting approval) -- since a
        second local edit collapses into either the same way (see
        PendingSyncChangeService.request)."""
        result = await self.db.execute(
            select(PendingSyncChange).where(
                PendingSyncChange.table_id == table_id,
                PendingSyncChange.row_id == row_id,
                PendingSyncChange.status.in_(["draft", "pending"]),
            )
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        table_id: uuid.UUID,
        row_id: int,
        operation: str,
        values: dict[str, Any] | None,
        external_pk: str | None,
        requested_by: uuid.UUID,
        previous_values: dict[str, Any] | None = None,
    ) -> PendingSyncChange:
        change = PendingSyncChange(
            table_id=table_id, row_id=row_id, operation=operation, values=values, external_pk=external_pk,
            requested_by=requested_by, previous_values=previous_values,
        )
        self.db.add(change)
        await self.db.flush()
        return change

    async def delete(self, change: PendingSyncChange) -> None:
        await self.db.delete(change)
        await self.db.flush()

    async def get(self, change_id: uuid.UUID) -> PendingSyncChange | None:
        return await self.db.get(PendingSyncChange, change_id)

    async def list_drafts_for_user(self, *, workspace_id: uuid.UUID, requested_by: uuid.UUID) -> list[tuple[PendingSyncChange, str]]:
        """Returns (change, table_name) tuples -- one editor's own
        not-yet-submitted edits, the "review before you submit" view."""
        # PendingSyncChange has no workspace_id of its own -- join through the
        # same table_id -> base_id -> workspace_id chain every other
        # per-table resource in this codebase resolves through.
        result = await self.db.execute(
            select(PendingSyncChange, Table.name)
            .join(Table, Table.id == PendingSyncChange.table_id)
            .join(Base, Base.id == Table.base_id)
            .where(
                Base.workspace_id == workspace_id,
                PendingSyncChange.requested_by == requested_by,
                PendingSyncChange.status == "draft",
            )
            .order_by(PendingSyncChange.requested_at.asc())
        )
        return [(change, table_name) for change, table_name in result.all()]

    async def list_for_batch(self, batch_id: uuid.UUID) -> list[tuple[PendingSyncChange, str]]:
        """Returns (change, table_name) tuples for every row bundled into one
        submitted batch -- the detail an approver sees inside a batch card."""
        result = await self.db.execute(
            select(PendingSyncChange, Table.name)
            .join(Table, Table.id == PendingSyncChange.table_id)
            .where(PendingSyncChange.batch_id == batch_id)
            .order_by(PendingSyncChange.requested_at.asc())
        )
        return [(change, table_name) for change, table_name in result.all()]

    async def mark_all_draft_as_submitted(self, *, workspace_id: uuid.UUID, requested_by: uuid.UUID, batch_id: uuid.UUID) -> int:
        """Flips every one of this user's draft rows in this workspace to
        pending + this batch, atomically with the batch's own creation.
        Returns how many rows were moved, so the caller can refuse to submit
        an empty batch."""
        result = await self.db.execute(
            select(PendingSyncChange)
            .join(Table, Table.id == PendingSyncChange.table_id)
            .join(Base, Base.id == Table.base_id)
            .where(
                Base.workspace_id == workspace_id,
                PendingSyncChange.requested_by == requested_by,
                PendingSyncChange.status == "draft",
            )
        )
        drafts = list(result.scalars().all())
        for draft in drafts:
            draft.status = "pending"
            draft.batch_id = batch_id
            draft.requested_at = datetime.now(timezone.utc)
        await self.db.flush()
        return len(drafts)


class SyncChangeBatchRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, workspace_id: uuid.UUID, requested_by: uuid.UUID) -> SyncChangeBatch:
        batch = SyncChangeBatch(workspace_id=workspace_id, requested_by=requested_by)
        self.db.add(batch)
        await self.db.flush()
        return batch

    async def get(self, batch_id: uuid.UUID) -> SyncChangeBatch | None:
        return await self.db.get(SyncChangeBatch, batch_id)

    async def list_pending_for_workspace(self, workspace_id: uuid.UUID) -> list[tuple[SyncChangeBatch, str]]:
        """Returns (batch, requester_name) tuples -- open batches an
        owner/admin still needs to act on."""
        result = await self.db.execute(
            select(SyncChangeBatch, User.name)
            .join(User, User.id == SyncChangeBatch.requested_by)
            .where(SyncChangeBatch.workspace_id == workspace_id, SyncChangeBatch.status == "pending")
            .order_by(SyncChangeBatch.submitted_at.asc())
        )
        return [(batch, requester_name) for batch, requester_name in result.all()]
