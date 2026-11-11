"""Recursively converts a value (or dict/list of values) into something
plain `json.dumps` can serialize -- for storage in a JSON/JSONB column, or
an opaque encoded payload (e.g. a pagination cursor). Decimal (from NUMERIC
columns) and date/datetime (from date columns -- DateFieldType.to_storage
returns real date/datetime objects, never strings, see its own docstring)
are the two coerced field-value types Python's json module doesn't handle
natively; this is the one place that conversion happens, so every caller
that needs to persist a raw row-values dict stays correct without having to
remember this itself.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any


def json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    return value
