"""Excel (.xlsx) import -- each worksheet becomes its own DataForge table,
picked and named by the user after an inspect pass lists what's in the
workbook. Deliberately mirrors csv_import.py's shape (introspect, then
stream rows) so ImportService's generic _create_table_for_columns/
_insert_rows work unchanged for both -- only column inference and row
reading are Excel-specific here.
"""

import io
from collections.abc import AsyncIterator
from datetime import date, datetime
from typing import Any

from openpyxl import load_workbook

from app.core.errors import ValidationError
from app.modules.connectors.base import ColumnDef

# Same cap as attachments/service.py's MAX_ATTACHMENT_SIZE -- untrusted file
# content, and a worksheet of any reasonable size for "import this as a
# table" fits well within it; mainly a guard against a deliberately huge or
# zip-bomb-shaped upload tying up a worker parsing it.
MAX_EXCEL_FILE_SIZE = 25 * 1024 * 1024

_MAX_TEXT_LENGTH = 255


def _infer_field_type(values: list[Any]) -> str:
    """Excel cells already carry a native Python type (openpyxl resolves
    them), so this checks types directly rather than re-parsing strings the
    way csv_import._infer_field_type has to -- bool is checked before
    int/float since bool is a subclass of int in Python."""
    non_empty = [v for v in values if v is not None and v != ""]
    if not non_empty:
        return "text"
    if all(isinstance(v, bool) for v in non_empty):
        return "boolean"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_empty):
        return "number"
    if all(isinstance(v, (datetime, date)) for v in non_empty):
        return "date"
    if any(len(str(v)) > _MAX_TEXT_LENGTH for v in non_empty):
        return "long_text"
    return "text"


def _open(file_bytes: bytes):
    if len(file_bytes) > MAX_EXCEL_FILE_SIZE:
        raise ValidationError(f"Excel files are limited to {MAX_EXCEL_FILE_SIZE // (1024 * 1024)}MB")
    try:
        # read_only streams rather than materializing the whole workbook;
        # data_only resolves formula cells to their last-calculated value
        # instead of handing back the formula text itself.
        return load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:
        # openpyxl can raise several different exception types (zip errors,
        # XML parsing errors, its own InvalidFileException...) for a
        # malformed or non-Excel upload -- all of them mean the same thing to
        # the caller, so they're collapsed to one clean, expected error
        # rather than leaking as a raw 500.
        raise ValidationError("File must be a valid .xlsx workbook") from exc


def _headers_and_columns(rows: list[tuple[Any, ...]]) -> tuple[list[str], list[ColumnDef]]:
    if not rows:
        return [], []
    headers = [str(h) if h is not None and str(h).strip() else f"Column {i + 1}" for i, h in enumerate(rows[0])]
    data_rows = rows[1:]
    columns = [
        ColumnDef(name=header, inferred_field_type=_infer_field_type([row[i] for row in data_rows if i < len(row)]))
        for i, header in enumerate(headers)
    ]
    return headers, columns


def list_sheets(file_bytes: bytes) -> list[dict[str, Any]]:
    """One entry per worksheet: name, inferred columns, and row_count, so the
    frontend can show a pick list before anything is imported. Scans every
    row (not a sample) for the same reason csv_import.introspect_csv does --
    the whole sheet is already being read into memory regardless."""
    workbook = _open(file_bytes)
    try:
        sheets = []
        for name in workbook.sheetnames:
            rows = list(workbook[name].iter_rows(values_only=True))
            _, columns = _headers_and_columns(rows)
            sheets.append({"name": name, "columns": columns, "row_count": max(0, len(rows) - 1)})
        return sheets
    finally:
        workbook.close()


def introspect_sheet(file_bytes: bytes, sheet_name: str) -> list[ColumnDef]:
    workbook = _open(file_bytes)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValidationError(f"Sheet '{sheet_name}' not found in this workbook")
        rows = list(workbook[sheet_name].iter_rows(values_only=True))
        _, columns = _headers_and_columns(rows)
        return columns
    finally:
        workbook.close()


async def stream_sheet_rows(file_bytes: bytes, sheet_name: str, *, batch_size: int) -> AsyncIterator[list[dict[str, Any]]]:
    workbook = _open(file_bytes)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValidationError(f"Sheet '{sheet_name}' not found in this workbook")
        rows_iter = workbook[sheet_name].iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            return
        headers, _ = _headers_and_columns([header_row])

        batch: list[dict[str, Any]] = []
        for row in rows_iter:
            batch.append({headers[i]: row[i] for i in range(min(len(headers), len(row)))})
            if len(batch) >= batch_size:
                yield batch
                batch = []
        if batch:
            yield batch
    finally:
        workbook.close()
