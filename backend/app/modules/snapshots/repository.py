import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.snapshots.models import BaseSnapshot, BaseSnapshotTable


class SnapshotRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_snapshot(self, *, base_id: uuid.UUID, label: str, is_automatic: bool, created_by: uuid.UUID) -> BaseSnapshot:
        snapshot = BaseSnapshot(base_id=base_id, label=label, is_automatic=is_automatic, created_by=created_by)
        self.db.add(snapshot)
        await self.db.flush()
        return snapshot

    async def add_snapshot_table(
        self,
        *,
        snapshot_id: uuid.UUID,
        table_id: uuid.UUID,
        table_name: str,
        physical_snapshot_table: str,
        field_defs: list[dict[str, Any]],
        row_count: int,
    ) -> BaseSnapshotTable:
        snapshot_table = BaseSnapshotTable(
            snapshot_id=snapshot_id, table_id=table_id, table_name=table_name,
            physical_snapshot_table=physical_snapshot_table, field_defs=field_defs, row_count=row_count,
        )
        self.db.add(snapshot_table)
        await self.db.flush()
        return snapshot_table

    async def list_for_base(self, base_id: uuid.UUID) -> list[BaseSnapshot]:
        result = await self.db.execute(
            select(BaseSnapshot).where(BaseSnapshot.base_id == base_id).order_by(BaseSnapshot.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, snapshot_id: uuid.UUID) -> BaseSnapshot | None:
        return await self.db.get(BaseSnapshot, snapshot_id)

    async def list_tables(self, snapshot_id: uuid.UUID) -> list[BaseSnapshotTable]:
        result = await self.db.execute(select(BaseSnapshotTable).where(BaseSnapshotTable.snapshot_id == snapshot_id))
        return list(result.scalars().all())

    async def delete(self, snapshot: BaseSnapshot) -> None:
        await self.db.delete(snapshot)
        await self.db.flush()

    async def list_automatic_for_base(self, base_id: uuid.UUID) -> list[BaseSnapshot]:
        result = await self.db.execute(
            select(BaseSnapshot)
            .where(BaseSnapshot.base_id == base_id, BaseSnapshot.is_automatic.is_(True))
            .order_by(BaseSnapshot.created_at.desc())
        )
        return list(result.scalars().all())
