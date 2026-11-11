import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.row_policies.models import RowLevelPolicy


class RowLevelPolicyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for_table_and_user(self, table_id: uuid.UUID, user_id: uuid.UUID) -> RowLevelPolicy | None:
        result = await self.db.execute(
            select(RowLevelPolicy).where(RowLevelPolicy.table_id == table_id, RowLevelPolicy.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_for_table(self, table_id: uuid.UUID) -> list[RowLevelPolicy]:
        result = await self.db.execute(select(RowLevelPolicy).where(RowLevelPolicy.table_id == table_id))
        return list(result.scalars().all())

    async def create(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, filter: dict[str, Any], created_by: uuid.UUID
    ) -> RowLevelPolicy:
        policy = RowLevelPolicy(table_id=table_id, user_id=user_id, filter=filter, created_by=created_by)
        self.db.add(policy)
        await self.db.flush()
        return policy

    async def get(self, policy_id: uuid.UUID) -> RowLevelPolicy | None:
        return await self.db.get(RowLevelPolicy, policy_id)

    async def delete(self, policy: RowLevelPolicy) -> None:
        await self.db.delete(policy)
        await self.db.flush()
