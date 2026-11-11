from app.modules.connectors.csv_import import _infer_field_type, introspect_csv
from tests.conftest import create_workspace_base_table, register_user


def test_infer_field_type_long_value_becomes_long_text():
    long_value = "x" * 300
    assert _infer_field_type([long_value, "short"]) == "long_text"


def test_infer_field_type_short_value_stays_text():
    assert _infer_field_type(["short", "also short"]) == "text"


def test_infer_field_type_at_the_255_boundary():
    assert _infer_field_type(["x" * 255]) == "text"
    assert _infer_field_type(["x" * 256]) == "long_text"


def test_infer_field_type_long_value_past_old_sample_window():
    # Regression: introspect_csv used to only sample the first 200 rows, so a
    # long value first appearing later in the file was missed entirely and
    # the column got created as a bounded "text" field -- then the bulk
    # insert blew up with asyncpg's StringDataRightTruncationError once it
    # reached that row. _infer_field_type itself must see every value.
    values = ["short"] * 250 + ["x" * 300]
    assert _infer_field_type(values) == "long_text"


def test_introspect_csv_long_value_past_old_sample_window():
    rows = "\n".join(f"Row {i},short" for i in range(250))
    csv_text = f"Title,Description\n{rows}\nRow 250,\"{'x' * 300}\"\n"
    columns = introspect_csv(csv_text)
    desc_column = next(c for c in columns if c.name == "Description")
    assert desc_column.inferred_field_type == "long_text"


async def test_import_csv_with_long_description_column(client):
    await register_user(client, email="csvlongtext@example.com")
    ws, base, table = await create_workspace_base_table(client)

    long_description = "word " * 100  # 500 chars, well past the old VARCHAR(255) cap
    csv_text = f"Title,Description\nRow One,\"{long_description}\"\nRow Two,short\n"

    resp = await client.post(
        f"/api/bases/{base['id']}/import-csv",
        files={"file": ("data.csv", csv_text, "text/csv")},
        data={"table_name": "Long Text Import"},
    )
    assert resp.status_code == 201, resp.text
    imported_table = resp.json()

    desc_field = next(f for f in imported_table["fields"] if f["name"] == "Description")
    assert desc_field["field_type"] == "long_text"

    rows = (await client.get(f"/api/tables/{imported_table['id']}/rows")).json()["rows"]
    assert any(r["values"]["Description"].strip() == long_description.strip() for r in rows)
