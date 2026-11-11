"""Shared filter DSL — compiled to parameterized SQLAlchemy Core expressions.

Generalizes the AND-then-OR filter-group pattern proven in the workspace's
existing bulk_update/app.py tool. This is the ONE filter language reused by:
grid view filters, bulk-ops preview/execute, automation trigger conditions,
and dashboard widget filters — see the architecture plan, section 2.

Fields and operators are always validated against a caller-supplied whitelist
of real SQLAlchemy columns (never raw column names from the client), so a
malformed or malicious filter can only reference columns the caller allows.
"""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, TypeAdapter
from sqlalchemy import ColumnElement, and_, not_, or_
from sqlalchemy.sql.elements import ColumnClause

from app.core.errors import ValidationError

Operator = Literal[
    "eq",
    "neq",
    "contains",
    "not_contains",
    "starts_with",
    "ends_with",
    "gt",
    "gte",
    "lt",
    "lte",
    "is_null",
    "is_not_null",
    "in",
    "not_in",
]

_NO_VALUE_OPERATORS = {"is_null", "is_not_null"}


class FilterCondition(BaseModel):
    kind: Literal["condition"] = "condition"
    field: str
    operator: Operator
    value: object | None = None


class FilterGroup(BaseModel):
    kind: Literal["group"] = "group"
    logic: Literal["and", "or"] = "and"
    items: list["FilterExpr"] = Field(default_factory=list)


FilterExpr = Annotated[Union[FilterCondition, FilterGroup], Field(discriminator="kind")]
FilterGroup.model_rebuild()

_filter_expr_adapter = TypeAdapter(FilterExpr)


def parse_filter_expr(data: dict) -> FilterCondition | FilterGroup:
    """Parse a raw dict (from an API request body or JSON storage column) into
    the correct discriminated-union member."""
    return _filter_expr_adapter.validate_python(data)


ColumnMap = dict[str, ColumnClause]


def _compile_condition(condition: FilterCondition, columns: ColumnMap) -> ColumnElement[bool]:
    column = columns.get(condition.field)
    if column is None:
        raise ValidationError(f"Unknown or non-filterable field: {condition.field}")

    op = condition.operator
    if op not in _NO_VALUE_OPERATORS and condition.value is None:
        raise ValidationError(f"Operator '{op}' on field '{condition.field}' requires a value")

    match op:
        case "eq":
            return column == condition.value
        case "neq":
            return column != condition.value
        case "contains":
            return column.ilike(f"%{condition.value}%")
        case "not_contains":
            return ~column.ilike(f"%{condition.value}%")
        case "starts_with":
            return column.ilike(f"{condition.value}%")
        case "ends_with":
            return column.ilike(f"%{condition.value}")
        case "gt":
            return column > condition.value
        case "gte":
            return column >= condition.value
        case "lt":
            return column < condition.value
        case "lte":
            return column <= condition.value
        case "is_null":
            return column.is_(None)
        case "is_not_null":
            return column.is_not(None)
        case "in":
            return column.in_(condition.value)
        case "not_in":
            return not_(column.in_(condition.value))
    raise ValidationError(f"Unsupported operator: {op}")  # pragma: no cover — exhaustive match above


def compile_filter(expr: FilterCondition | FilterGroup, columns: ColumnMap) -> ColumnElement[bool]:
    if isinstance(expr, FilterCondition):
        return _compile_condition(expr, columns)

    if not expr.items:
        raise ValidationError("Filter group must contain at least one item")

    compiled = [compile_filter(item, columns) for item in expr.items]
    return and_(*compiled) if expr.logic == "and" else or_(*compiled)


def _evaluate_condition(condition: FilterCondition, values: dict[str, object]) -> bool:
    """Mirrors _compile_condition's operator semantics, but evaluated directly
    against an in-memory record dict — used by automation trigger conditions,
    which check a just-written row without a DB round trip."""
    actual = values.get(condition.field)
    op = condition.operator
    expected = condition.value

    match op:
        case "eq":
            return actual == expected
        case "neq":
            return actual != expected
        case "contains":
            return actual is not None and str(expected).lower() in str(actual).lower()
        case "not_contains":
            return actual is None or str(expected).lower() not in str(actual).lower()
        case "starts_with":
            return actual is not None and str(actual).lower().startswith(str(expected).lower())
        case "ends_with":
            return actual is not None and str(actual).lower().endswith(str(expected).lower())
        case "gt":
            return actual is not None and actual > expected
        case "gte":
            return actual is not None and actual >= expected
        case "lt":
            return actual is not None and actual < expected
        case "lte":
            return actual is not None and actual <= expected
        case "is_null":
            return actual is None
        case "is_not_null":
            return actual is not None
        case "in":
            return actual in expected
        case "not_in":
            return actual not in expected
    raise ValidationError(f"Unsupported operator: {op}")  # pragma: no cover — exhaustive match above


def evaluate_filter(expr: FilterCondition | FilterGroup, values: dict[str, object]) -> bool:
    if isinstance(expr, FilterCondition):
        return _evaluate_condition(expr, values)

    if not expr.items:
        raise ValidationError("Filter group must contain at least one item")

    results = (evaluate_filter(item, values) for item in expr.items)
    return all(results) if expr.logic == "and" else any(results)
