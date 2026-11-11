from app.modules.connectors.registry import register_connector
from app.modules.connectors.types.sql_common import SqlAlchemyConnector


@register_connector("postgres")
class PostgresConnector(SqlAlchemyConnector):
    key = "postgres"

    def _build_url(self) -> str:
        c = self.config
        port = c.get("port", 5432)
        return f"postgresql+asyncpg://{c['username']}:{c['password']}@{c['host']}:{port}/{c['database']}"
