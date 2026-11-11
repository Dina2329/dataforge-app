"""Virtual field types -- link_to_record, lookup, rollup, formula. None of
these back a real column (registry.BaseFieldType.is_virtual = True), so
sqlalchemy_type is unreachable in practice; it raises rather than returning a
placeholder so a call-site bug that forgets the is_virtual check fails loudly
instead of silently creating a bogus column."""

from typing import Any

from sqlalchemy.types import TypeEngine

from app.modules.bases.field_types.registry import BaseFieldType, register_field_type

ROLLUP_AGGREGATES = ("count", "sum", "avg", "min", "max")


@register_field_type("link_to_record")
class LinkToRecordFieldType(BaseFieldType):
    key = "link_to_record"
    is_virtual = True

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        raise NotImplementedError("link_to_record has no physical column")


@register_field_type("lookup")
class LookupFieldType(BaseFieldType):
    key = "lookup"
    is_virtual = True

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        raise NotImplementedError("lookup has no physical column")


@register_field_type("rollup")
class RollupFieldType(BaseFieldType):
    key = "rollup"
    is_virtual = True

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        raise NotImplementedError("rollup has no physical column")


@register_field_type("formula")
class FormulaFieldType(BaseFieldType):
    key = "formula"
    is_virtual = True

    def sqlalchemy_type(self, options: dict[str, Any]) -> TypeEngine:
        raise NotImplementedError("formula has no physical column")
