import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.batch_submit.models import BatchSubmitConfig, BatchSubmitJob


class BatchSubmitConfigRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for_table(self, table_id: uuid.UUID) -> BatchSubmitConfig | None:
        result = await self.db.execute(select(BatchSubmitConfig).where(BatchSubmitConfig.table_id == table_id))
        return result.scalar_one_or_none()

    async def upsert(
        self, *, table_id: uuid.UUID, url: str, headers: dict[str, Any] | None, filter_dict: dict[str, Any], batch_size: int, created_by: uuid.UUID
    ) -> BatchSubmitConfig:
        existing = await self.get_for_table(table_id)
        if existing is not None:
            existing.url = url
            existing.headers = headers
            existing.filter_json = filter_dict
            existing.batch_size = batch_size
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            return existing

        config = BatchSubmitConfig(
            table_id=table_id, url=url, headers=headers, filter_json=filter_dict, batch_size=batch_size, created_by=created_by
        )
        self.db.add(config)
        await self.db.flush()
        return config


class BatchSubmitJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, table_id: uuid.UUID, batch_size: int, total_rows: int, total_batches: int, created_by: uuid.UUID) -> BatchSubmitJob:
        job = BatchSubmitJob(
            table_id=table_id, batch_size=batch_size, total_rows=total_rows, total_batches=total_batches, created_by=created_by
        )
        self.db.add(job)
        await self.db.flush()
        return job

    async def get(self, job_id: uuid.UUID) -> BatchSubmitJob | None:
        return await self.db.get(BatchSubmitJob, job_id)

    async def list_for_table(self, *, table_id: uuid.UUID, created_by: uuid.UUID, include_dismissed: bool) -> list[BatchSubmitJob]:
        stmt = select(BatchSubmitJob).where(BatchSubmitJob.table_id == table_id, BatchSubmitJob.created_by == created_by)
        if not include_dismissed:
            stmt = stmt.where(BatchSubmitJob.dismissed.is_(False))
        stmt = stmt.order_by(BatchSubmitJob.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
