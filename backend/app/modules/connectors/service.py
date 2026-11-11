import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import check_circuit, record_failure, record_success
from app.core.encryption import decrypt_json, encrypt_json
from app.core.errors import NotFoundError, ValidationError
from app.modules.audit.service import AuditService
from app.modules.connectors.base import ColumnDef, ConnectorError, TableRef
from app.modules.connectors.models import DataSource
from app.modules.connectors.registry import get_connector
from app.modules.connectors.repository import DataSourceRepository, TableSyncConfigRepository
from app.modules.workspaces.permissions import Permission
from app.modules.workspaces.service import WorkspaceService

_T = TypeVar("_T")


def breaker_key(data_source_id: uuid.UUID) -> str:
    return f"data_source:{data_source_id}"


async def call_connector(data_source_id: uuid.UUID, fn: Callable[[], Awaitable[_T]]) -> _T:
    """Wraps one connector call with the per-data-source circuit breaker:
    raises CircuitOpenError without touching the network if the breaker is
    open, otherwise normalizes a ConnectorError into a ValidationError while
    recording the failure. Shared by DataSourceService and ImportService --
    the latter calls a connector directly, bypassing DataSourceService's own
    methods, so it needs this exact same protection at its own call site."""
    key = breaker_key(data_source_id)
    await check_circuit(key)
    try:
        result = await fn()
    except ConnectorError as exc:
        await record_failure(key)
        raise ValidationError(str(exc)) from exc
    await record_success(key)
    return result

SQLITE_UPLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "sqlite_sources"

REQUIRED_CONFIG_KEYS = {
    "postgres": {"host", "database", "username", "password"},
    "mysql": {"host", "database", "username", "password"},
    "elasticsearch": {"url"},
}

# Gates table-sync write-back at the service layer rather than the connector
# class hierarchy -- SQLite also inherits SqlAlchemyConnector (and therefore
# technically has insert_row/update_row/delete_row available), but a synced
# local file isn't a supported sync target, and CSV never gained write
# methods at all. Checked wherever a table is linked for sync.
WRITABLE_SOURCE_TYPES = {"postgres", "mysql", "elasticsearch"}


class DataSourceService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = DataSourceRepository(db)
        self.workspaces = WorkspaceService(db)
        self.audit = AuditService(db)

    async def create(
        self,
        *,
        workspace_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        source_type: str,
        config: dict[str, Any],
        sqlite_file: bytes | None = None,
    ) -> DataSource:
        await self.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.DATA_SOURCE_WRITE)

        if source_type == "sqlite":
            if not sqlite_file:
                raise ValidationError("A .sqlite file upload is required for sqlite sources")
            SQLITE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            file_path = SQLITE_UPLOAD_DIR / f"{uuid.uuid4().hex}.sqlite"
            file_path.write_bytes(sqlite_file)
            config = {"file_path": str(file_path)}
        else:
            required = REQUIRED_CONFIG_KEYS.get(source_type)
            if required is None:
                raise ValidationError(f"Unsupported source type: {source_type}")
            missing = required - config.keys()
            if missing:
                raise ValidationError(f"Missing connection field(s): {', '.join(sorted(missing))}")

        config_encrypted = encrypt_json(config)
        data_source = await self.repo.create(
            workspace_id=workspace_id,
            name=name,
            source_type=source_type,
            config_encrypted=config_encrypted,
            created_by=user_id,
        )
        # Never put `config` itself in details -- it holds a plaintext
        # password/api_key at this point, before encryption is even relevant
        # (the log entry must not become a second place secrets leak from).
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="data_source.created", resource_type="data_source",
            resource_id=str(data_source.id), resource_label=name, details={"source_type": source_type},
        )
        await self.db.commit()
        return data_source

    async def list_for_workspace(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> list[DataSource]:
        await self.workspaces.require_member(workspace_id=workspace_id, user_id=user_id)
        return await self.repo.list_for_workspace(workspace_id)

    async def _get_with_access_check(self, *, data_source_id: uuid.UUID, user_id: uuid.UUID) -> DataSource:
        data_source = await self.repo.get(data_source_id)
        if data_source is None:
            raise NotFoundError("Data source not found")
        await self.workspaces.require_member(workspace_id=data_source.workspace_id, user_id=user_id)
        return data_source

    async def get_decrypted_config(self, *, data_source_id: uuid.UUID, user_id: uuid.UUID) -> tuple[DataSource, dict[str, Any]]:
        data_source = await self._get_with_access_check(data_source_id=data_source_id, user_id=user_id)
        return data_source, decrypt_json(data_source.config_encrypted)

    async def delete(self, *, data_source_id: uuid.UUID, user_id: uuid.UUID) -> None:
        data_source = await self._get_with_access_check(data_source_id=data_source_id, user_id=user_id)
        await self.workspaces.require_permission(
            workspace_id=data_source.workspace_id, user_id=user_id, permission=Permission.DATA_SOURCE_WRITE
        )
        # The FK itself is CASCADE (so deleting a whole workspace isn't
        # blocked by this) -- this is the actual "don't silently orphan a
        # live sync" guard for deleting just the data source on its own.
        if await TableSyncConfigRepository(self.db).exists_for_data_source(data_source_id):
            raise ValidationError(
                "This connection is still syncing one or more tables — unlink sync on each of them first."
            )
        if data_source.source_type == "sqlite":
            config = decrypt_json(data_source.config_encrypted)
            Path(config["file_path"]).unlink(missing_ok=True)
        await self.audit.log(
            workspace_id=data_source.workspace_id, user_id=user_id, action="data_source.deleted", resource_type="data_source",
            resource_id=str(data_source.id), resource_label=data_source.name, details={"source_type": data_source.source_type},
        )
        await self.repo.delete(data_source)
        await self.db.commit()

    async def test_connection(self, *, data_source_id: uuid.UUID, user_id: uuid.UUID) -> None:
        data_source, config = await self.get_decrypted_config(data_source_id=data_source_id, user_id=user_id)
        connector = get_connector(data_source.source_type, config)
        try:
            await call_connector(data_source_id, connector.test_connection)
        finally:
            await connector.close()

    async def list_tables(self, *, data_source_id: uuid.UUID, user_id: uuid.UUID) -> list[TableRef]:
        data_source, config = await self.get_decrypted_config(data_source_id=data_source_id, user_id=user_id)
        connector = get_connector(data_source.source_type, config)
        try:
            return await call_connector(data_source_id, connector.list_tables)
        finally:
            await connector.close()

    async def introspect_columns(
        self, *, data_source_id: uuid.UUID, user_id: uuid.UUID, table_name: str, table_schema: str | None
    ) -> list[ColumnDef]:
        data_source, config = await self.get_decrypted_config(data_source_id=data_source_id, user_id=user_id)
        connector = get_connector(data_source.source_type, config)
        try:
            table_ref = TableRef(name=table_name, schema=table_schema)
            return await call_connector(data_source_id, lambda: connector.introspect_columns(table_ref))
        finally:
            await connector.close()
