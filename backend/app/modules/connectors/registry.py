from typing import Any

from app.core.errors import ValidationError
from app.modules.connectors.base import BaseConnector

CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {}


def register_connector(key: str):
    def decorator(cls: type[BaseConnector]) -> type[BaseConnector]:
        cls.key = key
        CONNECTOR_REGISTRY[key] = cls
        return cls

    return decorator


def get_connector(key: str, config: dict[str, Any]) -> BaseConnector:
    connector_cls = CONNECTOR_REGISTRY.get(key)
    if connector_cls is None:
        raise ValidationError(f"Unknown connector type: {key}")
    return connector_cls(config)
