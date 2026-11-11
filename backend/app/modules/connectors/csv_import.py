"""Standalone CSV import — deliberately not a BaseConnector (see base.py):
a CSV upload is a one-off file with no persistent connection and no multiple
tables to browse, so it doesn't fit that connection-oriented interface.
"""

import csv
import io
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from app.modules.connectors.base import ColumnDef

# TextFieldType stores a bounded VARCHAR(255) (see field_types/types.py) --
# anything longer needs the unbounded "long_text" type instead, or the bulk
# insert fails with asyncpg's StringDataRightTruncationError. Inference below
# scans every row (not a sample) to catch a long value anywhere in the file --
# the full CSV is already loaded into memory as csv_text by the time this
# runs, so sampling would only trade correctness for a saving that doesn't
# exist.
_MAX_TEXT_LENGTH = 255


def _looks_like_number(value: str) -> bool:
    try:
        float(value)
        return True
    except ValueError:
        return False


def _looks_like_boolean(value: str) -> bool:
    return value.strip().lower() in {"true", "false"}


def _looks_like_date(value: str) -> bool:
    try:
        date.fromisoformat(value.strip())
        return True
    except ValueError:
        return False


def _infer_field_type(values: list[str]) -> str:
    non_empty = [v for v in values if v not in (None, "")]
    if not non_empty:
        return "text"
    if all(_looks_like_boolean(v) for v in non_empty):
        return "boolean"
    if all(_looks_like_number(v) for v in non_empty):
        return "number"
    if all(_looks_like_date(v) for v in non_empty):
        return "date"
    if any(len(v) > _MAX_TEXT_LENGTH for v in non_empty):
        return "long_text"
    return "text"


def introspect_csv(csv_text: str) -> list[ColumnDef]:
    reader = csv.DictReader(io.StringIO(csv_text))
    headers = reader.fieldnames or []
    rows = list(reader)
    return [
        ColumnDef(name=header, inferred_field_type=_infer_field_type([row.get(header, "") for row in rows]))
        for header in headers
    ]


async def stream_csv_rows(csv_text: str, *, batch_size: int) -> AsyncIterator[list[dict[str, Any]]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    batch: list[dict[str, Any]] = []
    for row in reader:
        batch.append(row)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
