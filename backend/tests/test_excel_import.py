import io
import json
from datetime import date

from openpyxl import Workbook

from app.modules.connectors import excel_import
from tests.conftest import create_workspace_base_table, register_user


def _build_workbook(sheets: dict[str, list[list]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_infer_field_type_uses_native_cell_types():
    assert excel_import._infer_field_type([True, False]) == "boolean"
    assert excel_import._infer_field_type([1, 2.5]) == "number"
    assert excel_import._infer_field_type([date(2026, 1, 1)]) == "date"
    assert excel_import._infer_field_type(["x" * 300]) == "long_text"
    assert excel_import._infer_field_type(["short"]) == "text"
    assert excel_import._infer_field_type([None, None]) == "text"


def test_list_sheets_returns_every_sheet_with_columns_and_row_count():
    content = _build_workbook(
        {
            "Customers": [["Name", "Active"], ["Alice", True], ["Bob", False]],
            "Orders": [["Order", "Amount"], ["A1", 10.5]],
        }
    )
    sheets = excel_import.list_sheets(content)
    by_name = {s["name"]: s for s in sheets}
    assert set(by_name) == {"Customers", "Orders"}
    assert by_name["Customers"]["row_count"] == 2
    assert {c.name: c.inferred_field_type for c in by_name["Customers"]["columns"]} == {"Name": "text", "Active": "boolean"}
    assert by_name["Orders"]["row_count"] == 1
    assert {c.name: c.inferred_field_type for c in by_name["Orders"]["columns"]} == {"Order": "text", "Amount": "number"}


async def test_inspect_excel_endpoint(client):
    await register_user(client, email="excel1@example.com")
    ws, base, table = await create_workspace_base_table(client)
    content = _build_workbook({"Sheet A": [["Col1"], ["val1"]], "Sheet B": [["Col2"], [42]]})

    resp = await client.post(
        f"/api/bases/{base['id']}/import-excel/inspect",
        files={"file": ("book.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = {s["name"] for s in body["sheets"]}
    assert names == {"Sheet A", "Sheet B"}


async def test_import_excel_creates_one_table_per_selected_sheet(client):
    await register_user(client, email="excel2@example.com")
    ws, base, table = await create_workspace_base_table(client)
    content = _build_workbook(
        {
            "Customers": [["Name", "Age"], ["Alice", 30], ["Bob", 40]],
            "Orders": [["Order", "Total"], ["A1", 99.5]],
            "Skip Me": [["X"], ["y"]],
        }
    )

    resp = await client.post(
        f"/api/bases/{base['id']}/import-excel",
        files={"file": ("book.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={
            "sheets": json.dumps(
                [
                    {"sheet_name": "Customers", "table_name": "Customers"},
                    {"sheet_name": "Orders", "table_name": "Orders"},
                ]
            )
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["results"]) == 2
    assert all(r["error"] is None for r in body["results"])

    customers_table = next(r["table"] for r in body["results"] if r["sheet_name"] == "Customers")
    rows = (await client.get(f"/api/tables/{customers_table['id']}/rows")).json()["rows"]
    assert sorted(r["values"]["Age"] for r in rows) == [30, 40]

    tables = (await client.get(f"/api/bases/{base['id']}/tables")).json()
    table_names = {t["name"] for t in tables}
    assert "Customers" in table_names and "Orders" in table_names and "Skip Me" not in table_names


async def test_import_excel_reports_per_sheet_failure_without_losing_other_sheets(client):
    await register_user(client, email="excel3@example.com")
    ws, base, table = await create_workspace_base_table(client)
    content = _build_workbook({"Good": [["Name"], ["Alice"]]})

    resp = await client.post(
        f"/api/bases/{base['id']}/import-excel",
        files={"file": ("book.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={
            "sheets": json.dumps(
                [
                    {"sheet_name": "Good", "table_name": "Good Table"},
                    {"sheet_name": "Does Not Exist", "table_name": "Bad Table"},
                ]
            )
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    results_by_sheet = {r["sheet_name"]: r for r in body["results"]}
    assert results_by_sheet["Good"]["table"] is not None
    assert results_by_sheet["Good"]["error"] is None
    assert results_by_sheet["Does Not Exist"]["table"] is None
    assert results_by_sheet["Does Not Exist"]["error"]

    tables = (await client.get(f"/api/bases/{base['id']}/tables")).json()
    assert "Good Table" in {t["name"] for t in tables}


async def test_import_excel_rejects_non_excel_file(client):
    await register_user(client, email="excel4@example.com")
    ws, base, table = await create_workspace_base_table(client)

    resp = await client.post(
        f"/api/bases/{base['id']}/import-excel/inspect",
        files={"file": ("not-excel.xlsx", b"this is not a real xlsx file", "application/octet-stream")},
    )
    assert resp.status_code == 422


async def test_import_excel_rejects_oversized_file(client, monkeypatch):
    monkeypatch.setattr("app.modules.connectors.excel_import.MAX_EXCEL_FILE_SIZE", 10)
    await register_user(client, email="excel5@example.com")
    ws, base, table = await create_workspace_base_table(client)
    content = _build_workbook({"Sheet": [["Col"], ["val"]]})
    assert len(content) > 10

    resp = await client.post(
        f"/api/bases/{base['id']}/import-excel/inspect",
        files={"file": ("book.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 422
