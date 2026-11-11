import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bulk_ops.models import BulkOperation


class BulkOperationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, *, table_id: uuid.UUID, filter_json: dict[str, Any], values_json: dict[str, Any], created_by: uuid.UUID
    ) -> BulkOperation:
        operation = BulkOperation(table_id=table_id, filter_json=filter_json, values_json=values_json, created_by=created_by)
        self.db.add(operation)
        await self.db.flush()
        return operation

    async def get(self, operation_id: uuid.UUID) -> BulkOperation | None:
        return await self.db.get(BulkOperation, operation_id)
