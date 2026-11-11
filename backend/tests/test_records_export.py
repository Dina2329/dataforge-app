import csv
import io

from tests.conftest import create_workspace_base_table, register_user


async def test_export_csv_contains_header_and_rows(client):
    await register_user(client, email="exporter@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})

    for i, n in enumerate([10, 20, 30]):
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": f"Row{i}", "N": n}})
        assert resp.status_code == 201

    resp = await client.get(f"/api/tables/{table['id']}/export-csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert reader.fieldnames == ["Name", "N"]
    # number fields round-trip as float (from_storage always returns float()
    # for a NUMERIC column, matching the plain GET /rows endpoint)
    assert sorted(float(r["N"]) for r in rows) == [10.0, 20.0, 30.0]


async def test_export_csv_respects_filter_and_sort(client):
    await register_user(client, email="exportfilter@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})

    for n in [1, 2, 3, 4]:
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"N": n}})
        assert resp.status_code == 201

    import json as jsonlib

    condition = jsonlib.dumps({"kind": "condition", "field": "N", "operator": "gt", "value": 1})
    sort = jsonlib.dumps([{"field": "N", "direction": "desc"}])
    resp = await client.get(f"/api/tables/{table['id']}/export-csv", params={"filter": condition, "sort": sort})
    assert resp.status_code == 200
    reader = csv.DictReader(io.StringIO(resp.text))
    values = [float(r["N"]) for r in reader]
    assert values == [4.0, 3.0, 2.0]


async def test_export_csv_requires_membership(client, make_client):
    await register_user(client, email="exportowner@example.com")
    ws, base, table = await create_workspace_base_table(client)

    outsider = await make_client()
    await register_user(outsider, email="exportoutsider@example.com")
    resp = await outsider.get(f"/api/tables/{table['id']}/export-csv")
    assert resp.status_code in (403, 404)
