"""Connector plugin interface for connection-based external data sources
(architecture plan, section 3).

CSV is intentionally NOT a BaseConnector — it's a one-off upload with no
persistent connection and no multiple tables to browse; see
connectors.csv_import for that separate, simpler flow.

Read/introspect-only by design, matching the internal-first storage decision:
connectors bring data IN to a native DataForge table via import_service. The
one deliberate exception is opt-in table sync (sync_service.py, Stage 1):
SqlAlchemyConnector (Postgres/MySQL only, gated by WRITABLE_SOURCE_TYPES in
service.py) grows insert_row/update_row/delete_row for that path specifically.
Those live on SqlAlchemyConnector itself, not as abstract methods here, so
Elasticsearch/CSV/SQLite never need a no-op write stub -- BaseConnector stays
read-only as an interface even though one concrete subclass now isn't.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any


@dataclass
class ColumnDef:
    name: str
    inferred_field_type: str
    native_type: str = ""
    is_primary_key: bool = False


@dataclass
class TableRef:
    name: str
    schema: str | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.schema}.{self.name}" if self.schema else self.name


class ConnectorError(Exception):
    """Raised by a connector on connection failure or an unsupported source shape."""


class ConnectorRowNotFoundError(ConnectorError):
    """Raised by update_row when the target row no longer exists on the
    external side -- distinct from a generic ConnectorError so callers (the
    push-to-source worker task) can treat "row vanished" as a non-retryable
    failure instead of burning retries against a permanently-gone row."""


class BaseConnector(ABC):
    key: str

    def __init__(self, config: dict[str, Any]):
        self.config = config

    @abstractmethod
    async def test_connection(self) -> None:
        """Raise ConnectorError with a human-readable message if the connection fails."""

    @abstractmethod
    async def list_tables(self) -> list[TableRef]:
        """List tables visible to this connection."""

    @abstractmethod
    async def introspect_columns(self, table: TableRef) -> list[ColumnDef]:
        """Return the column names/types for a specific table."""

    @abstractmethod
    def stream_rows(self, table: TableRef, *, batch_size: int) -> AsyncIterator[list[dict[str, Any]]]:
        """Yield row batches as {column_name: raw_value} dicts, never loading the full table into memory."""

    async def close(self) -> None:
        """Release any held connections/pools. Default no-op for stateless connectors."""
