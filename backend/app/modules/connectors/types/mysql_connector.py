from app.modules.connectors.registry import register_connector
from app.modules.connectors.types.sql_common import SqlAlchemyConnector


@register_connector("mysql")
class MySQLConnector(SqlAlchemyConnector):
    key = "mysql"

    def _build_url(self) -> str:
        c = self.config
        port = c.get("port", 3306)
        return f"mysql+asyncmy://{c['username']}:{c['password']}@{c['host']}:{port}/{c['database']}"
