import json

from tests.conftest import create_workspace_base_table, register_user


async def _add_text_field(client, table_id: str, name: str) -> dict:
    resp = await client.post(f"/api/tables/{table_id}/fields", json={"name": name, "field_type": "text", "options": {}})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_filter_values_excludes_values_already_in_mapped_table(client):
    await register_user(client, email="exclusion1@example.com")
    ws, base_a, table_a = await create_workspace_base_table(client, base_name="Main Base", table_name="Main")
    main_field = await _add_text_field(client, table_a["id"], "Category")

    table_b = (await client.post(f"/api/bases/{base_a['id']}/tables", json={"name": "Reference"})).json()
    ref_field = await _add_text_field(client, table_b["id"], "Term Name")

    for value in ["Retail", "Office"]:
        resp = await client.post(f"/api/tables/{table_a['id']}/rows", json={"values": {"Category": value}})
        assert resp.status_code == 201

    # Configure the mapping -- deliberately a differently-named field
    # ("Term Name" on B excludes values already in "Category" on A).
    patch = await client.patch(
        f"/api/tables/{table_b['id']}/fields/{ref_field['id']}",
        json={"options": {"exclude_values_from": {"table_id": table_a["id"], "field_id": main_field["id"]}}},
    )
    assert patch.status_code == 200, patch.text

    for value in ["Retail", "Office", "Warehouse", "Warehouse", None]:
        resp = await client.post(f"/api/tables/{table_b['id']}/rows", json={"values": {"Term Name": value}})
        assert resp.status_code == 201

    resp = await client.get(f"/api/fields/{ref_field['id']}/filter-values")
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == ["Warehouse"]

    # The exclusion never hides rows -- all 5 of B's rows are still listed.
    listing = await client.get(f"/api/tables/{table_b['id']}/rows")
    assert len(listing.json()["rows"]) == 5

    # apply_exclusion=False (the column-header AutoFilter checklist's use
    # case) ignores the mapping entirely and returns every distinct value
    # actually present in this column.
    raw = await client.get(f"/api/fields/{ref_field['id']}/filter-values", params={"apply_exclusion": "false"})
    assert raw.status_code == 200, raw.text
    assert raw.json()["values"] == ["Office", "Retail", "Warehouse"]


async def test_filter_values_without_mapping_returns_plain_distinct_values(client):
    # The same endpoint doubles as a general "show me values already used in
    # this column" picker for ordinary (non-exclusion-mapped) fields -- no
    # mapping configured just means no second table to diff against.
    await register_user(client, email="exclusion2@example.com")
    ws, base, table = await create_workspace_base_table(client)
    field = await _add_text_field(client, table["id"], "Plain")

    for value in ["Beta", "Alpha", "Beta", None]:
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Plain": value}})
        assert resp.status_code == 201

    resp = await client.get(f"/api/fields/{field['id']}/filter-values")
    assert resp.status_code == 200, resp.text
    assert resp.json()["values"] == ["Alpha", "Beta"]  # distinct, non-null, sorted -- no duplicate, no None


async def test_filter_values_cascade_against_other_active_filters(client):
    # Excel's own AutoFilter does this: once one column is already filtered,
    # a second column's checklist should only offer values that actually
    # occur among rows matching the FIRST column's filter -- not every value
    # in the whole table, which would let someone check a value that then
    # produces zero rows with no indication why.
    await register_user(client, email="exclusion5@example.com")
    ws, base, table = await create_workspace_base_table(client)
    status_field = await _add_text_field(client, table["id"], "Status")
    owner_field = await _add_text_field(client, table["id"], "Owner")

    rows = [
        {"Status": "todo", "Owner": "Alice"},
        {"Status": "todo", "Owner": "Bob"},
        {"Status": "done", "Owner": "Carol"},
        {"Status": "done", "Owner": "Alice"},
    ]
    for values in rows:
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": values})
        assert resp.status_code == 201

    # No other filter active -- Owner's checklist sees everyone.
    unscoped = await client.get(f"/api/fields/{owner_field['id']}/filter-values", params={"apply_exclusion": "false"})
    assert unscoped.json()["values"] == ["Alice", "Bob", "Carol"]

    # Status already filtered to "todo" -- Owner's checklist must only offer
    # Alice/Bob (the owners of todo rows), not Carol.
    other_filter = json.dumps({"kind": "condition", "field": "Status", "operator": "in", "value": ["todo"]})
    scoped = await client.get(
        f"/api/fields/{owner_field['id']}/filter-values", params={"apply_exclusion": "false", "filter": other_filter}
    )
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["values"] == ["Alice", "Bob"]

    # And the reverse direction also cascades correctly.
    other_filter2 = json.dumps({"kind": "condition", "field": "Owner", "operator": "in", "value": ["Carol"]})
    scoped2 = await client.get(
        f"/api/fields/{status_field['id']}/filter-values", params={"apply_exclusion": "false", "filter": other_filter2}
    )
    assert scoped2.json()["values"] == ["done"]


async def test_exclude_mapping_rejects_cross_workspace_table(client):
    await register_user(client, email="exclusion3@example.com")
    ws1, base1, table1 = await create_workspace_base_table(client, workspace_name="WS1")
    field1 = await _add_text_field(client, table1["id"], "A")

    ws2 = (await client.post("/api/workspaces", json={"name": "WS2"})).json()
    base2 = (await client.post(f"/api/workspaces/{ws2['id']}/bases", json={"name": "Base2"})).json()
    table2 = (await client.post(f"/api/bases/{base2['id']}/tables", json={"name": "Table2"})).json()
    field2 = await _add_text_field(client, table2["id"], "B")

    resp = await client.patch(
        f"/api/tables/{table1['id']}/fields/{field1['id']}",
        json={"options": {"exclude_values_from": {"table_id": table2["id"], "field_id": field2["id"]}}},
    )
    assert resp.status_code == 422


async def test_exclude_mapping_rejects_virtual_field_type(client):
    await register_user(client, email="exclusion4@example.com")
    ws, base, table = await create_workspace_base_table(client)
    other_field = await _add_text_field(client, table["id"], "Other")

    formula_resp = await client.post(
        f"/api/tables/{table['id']}/fields",
        json={"name": "Computed", "field_type": "formula", "options": {"expression": "Other"}},
    )
    assert formula_resp.status_code == 201, formula_resp.text
    formula_field = formula_resp.json()

    resp = await client.patch(
        f"/api/tables/{table['id']}/fields/{formula_field['id']}",
        json={"options": {"exclude_values_from": {"table_id": table["id"], "field_id": other_field["id"]}}},
    )
    assert resp.status_code == 422
