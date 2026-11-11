import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bases.models import Base, Field, Table, View


class BaseRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, workspace_id: uuid.UUID, name: str, created_by: uuid.UUID) -> Base:
        base = Base(workspace_id=workspace_id, name=name, created_by=created_by)
        self.db.add(base)
        await self.db.flush()
        return base

    async def list_for_workspace(self, workspace_id: uuid.UUID) -> list[Base]:
        result = await self.db.execute(select(Base).where(Base.workspace_id == workspace_id))
        return list(result.scalars().all())

    async def list_all(self) -> list[Base]:
        """System-wide -- only for the daily automatic-snapshot cron task
        (snapshot_tasks.py), which has no workspace/user context to scope by."""
        result = await self.db.execute(select(Base))
        return list(result.scalars().all())

    async def get(self, base_id: uuid.UUID) -> Base | None:
        return await self.db.get(Base, base_id)

    async def delete(self, base: Base) -> None:
        await self.db.delete(base)
        await self.db.flush()


class TableRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, base_id: uuid.UUID, name: str, physical_table_name: str) -> Table:
        table = Table(base_id=base_id, name=name, physical_table_name=physical_table_name)
        self.db.add(table)
        await self.db.flush()
        return table

    async def list_for_base(self, base_id: uuid.UUID) -> list[Table]:
        result = await self.db.execute(select(Table).where(Table.base_id == base_id))
        return list(result.scalars().all())

    async def get(self, table_id: uuid.UUID) -> Table | None:
        return await self.db.get(Table, table_id)

    async def delete(self, table: Table) -> None:
        await self.db.delete(table)
        await self.db.flush()


class FieldRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        table_id: uuid.UUID,
        name: str,
        db_column_name: str,
        field_type: str,
        options: dict,
        position: int,
        is_primary: bool,
        required: bool,
    ) -> Field:
        field = Field(
            table_id=table_id,
            name=name,
            db_column_name=db_column_name,
            field_type=field_type,
            options=options,
            position=position,
            is_primary=is_primary,
            required=required,
        )
        self.db.add(field)
        await self.db.flush()
        return field

    async def list_for_table(self, table_id: uuid.UUID) -> list[Field]:
        result = await self.db.execute(select(Field).where(Field.table_id == table_id).order_by(Field.position))
        return list(result.scalars().all())

    async def get(self, field_id: uuid.UUID) -> Field | None:
        return await self.db.get(Field, field_id)

    async def delete(self, field: Field) -> None:
        await self.db.delete(field)
        await self.db.flush()


class ViewRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, table_id: uuid.UUID, name: str, view_type: str = "grid", config: dict | None = None) -> View:
        view = View(table_id=table_id, name=name, view_type=view_type, config=config or {})
        self.db.add(view)
        await self.db.flush()
        return view

    async def list_for_table(self, table_id: uuid.UUID) -> list[View]:
        result = await self.db.execute(select(View).where(View.table_id == table_id))
        return list(result.scalars().all())

    async def get(self, view_id: uuid.UUID) -> View | None:
        return await self.db.get(View, view_id)

    async def get_by_share_token(self, token: str) -> View | None:
        result = await self.db.execute(select(View).where(View.share_token == token))
        return result.scalar_one_or_none()

    async def delete(self, view: View) -> None:
        await self.db.delete(view)
        await self.db.flush()
