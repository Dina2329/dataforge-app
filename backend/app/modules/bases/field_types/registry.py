"""Field type plugin registry (architecture plan, section 3).

Adding a new field type is a new file + one @register_field_type decorator —
no changes anywhere else. Each type owns both its DDL column type and its
value coercion, so schema_service and the records service never special-case
a field_type string themselves.
"""

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.types import TypeEngine

from app.core.errors import ValidationError

FIELD_TYPE_REGISTRY: dict[str, type["BaseFieldType"]] = {}


def register_field_type(key: str):
    def decorator(cls: type["BaseFieldType"]) -> type["BaseFieldType"]:
        FIELD_TYPE_REGISTRY[key] = cls
        return cls

    return decorator


class BaseFieldType(ABC):
    key: str
    # Virtual types (link_to_record, lookup, rollup, formula) have no real
    # column — schema_service skips them when building/altering the physical
    # table, and records.service computes their value separately per row
    # instead of reading it out of the row mapping.
    is_virtual: bool = False

    @abstractmethod
    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        """The physical column type used when this field's column is created.
        Never called for a virtual type -- every call site checks is_virtual first."""

    def to_storage(self, value: Any, options: dict[str, Any]) -> Any:
        """Validate/coerce an incoming API value before it is written to the column."""
        return value

    def from_storage(self, raw: Any, options: dict[str, Any]) -> Any:
        """Format a stored value before it is returned over the API."""
        return raw


def get_field_type(key: str) -> BaseFieldType:
    field_type_cls = FIELD_TYPE_REGISTRY.get(key)
    if field_type_cls is None:
        raise ValidationError(f"Unknown field type: {key}")
    return field_type_cls()
