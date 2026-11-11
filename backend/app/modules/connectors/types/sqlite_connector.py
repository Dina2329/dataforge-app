from app.modules.connectors.registry import register_connector
from app.modules.connectors.types.sql_common import SqlAlchemyConnector


@register_connector("sqlite")
class SQLiteConnector(SqlAlchemyConnector):
    """config['file_path'] is a server-side path to an uploaded .sqlite file
    (saved by DataSourceService.create when source_type == "sqlite") — SQLite
    files are uploaded like CSV, not reached over a network connection."""

    key = "sqlite"

    def _build_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.config['file_path']}"
