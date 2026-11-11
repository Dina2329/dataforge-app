import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.automations.models import Automation, AutomationAction, AutomationRun


class AutomationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, *, table_id: uuid.UUID, name: str, trigger_type: str, trigger_config: dict[str, Any], created_by: uuid.UUID
    ) -> Automation:
        automation = Automation(
            table_id=table_id, name=name, trigger_type=trigger_type, trigger_config=trigger_config, created_by=created_by
        )
        self.db.add(automation)
        await self.db.flush()
        return automation

    async def list_for_table(self, table_id: uuid.UUID) -> list[Automation]:
        result = await self.db.execute(select(Automation).where(Automation.table_id == table_id))
        return list(result.scalars().all())

    async def get(self, automation_id: uuid.UUID) -> Automation | None:
        return await self.db.get(Automation, automation_id)

    async def delete(self, automation: Automation) -> None:
        await self.db.delete(automation)
        await self.db.flush()

    async def list_enabled_for_table_and_trigger(self, table_id: uuid.UUID, trigger_type: str) -> list[Automation]:
        stmt = select(Automation).where(
            Automation.table_id == table_id, Automation.trigger_type == trigger_type, Automation.is_enabled.is_(True)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_due_scheduled(self, now: datetime) -> list[Automation]:
        stmt = select(Automation).where(
            Automation.trigger_type == "scheduled", Automation.is_enabled.is_(True), Automation.next_run_at <= now
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


class AutomationActionRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, automation_id: uuid.UUID, position: int, action_type: str, config: dict[str, Any]) -> AutomationAction:
        action = AutomationAction(automation_id=automation_id, position=position, action_type=action_type, config=config)
        self.db.add(action)
        await self.db.flush()
        return action

    async def list_for_automation(self, automation_id: uuid.UUID) -> list[AutomationAction]:
        stmt = select(AutomationAction).where(AutomationAction.automation_id == automation_id).order_by(AutomationAction.position)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get(self, action_id: uuid.UUID) -> AutomationAction | None:
        return await self.db.get(AutomationAction, action_id)

    async def delete(self, action: AutomationAction) -> None:
        await self.db.delete(action)
        await self.db.flush()


class AutomationRunRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self, *, automation_id: uuid.UUID, status: str, trigger_payload: dict[str, Any], error: str | None
    ) -> AutomationRun:
        run = AutomationRun(automation_id=automation_id, status=status, trigger_payload=trigger_payload, error=error)
        self.db.add(run)
        await self.db.flush()
        return run

    async def list_for_automation(self, automation_id: uuid.UUID, limit: int = 20) -> list[AutomationRun]:
        stmt = (
            select(AutomationRun)
            .where(AutomationRun.automation_id == automation_id)
            .order_by(AutomationRun.ran_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
