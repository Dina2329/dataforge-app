import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.record_submit.models import RecordSubmitConfig


class RecordSubmitConfigRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for_table(self, table_id: uuid.UUID) -> RecordSubmitConfig | None:
        result = await self.db.execute(select(RecordSubmitConfig).where(RecordSubmitConfig.table_id == table_id))
        return result.scalar_one_or_none()

    async def upsert(
        self, *, table_id: uuid.UUID, url: str, headers: dict[str, Any] | None, status_field_id: uuid.UUID, created_by: uuid.UUID
    ) -> RecordSubmitConfig:
        existing = await self.get_for_table(table_id)
        if existing is not None:
            existing.url = url
            existing.headers = headers
            existing.status_field_id = status_field_id
            existing.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            return existing

        config = RecordSubmitConfig(
            table_id=table_id, url=url, headers=headers, status_field_id=status_field_id, created_by=created_by
        )
        self.db.add(config)
        await self.db.flush()
        return config
