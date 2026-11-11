import json

from tests.conftest import create_workspace_base_table, register_user


async def test_filter_query_param_narrows_rows(client):
    await register_user(client, email="filterer@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})

    for n in [1, 2, 3, 4]:
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"N": n}})
        assert resp.status_code == 201

    condition = json.dumps({"kind": "condition", "field": "N", "operator": "gt", "value": 2})
    page = (await client.get(f"/api/tables/{table['id']}/rows", params={"filter": condition})).json()
    assert sorted(r["values"]["N"] for r in page["rows"]) == [3, 4]


async def test_filter_group_and_logic(client):
    await register_user(client, email="filtergroup@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})

    for n in [1, 2, 3, 4, 5]:
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"N": n}})
        assert resp.status_code == 201

    group = json.dumps(
        {
            "kind": "group",
            "logic": "and",
            "items": [
                {"kind": "condition", "field": "N", "operator": "gt", "value": 1},
                {"kind": "condition", "field": "N", "operator": "lt", "value": 5},
            ],
        }
    )
    page = (await client.get(f"/api/tables/{table['id']}/rows", params={"filter": group})).json()
    assert sorted(r["values"]["N"] for r in page["rows"]) == [2, 3, 4]


async def test_filter_unknown_field_rejected(client):
    await register_user(client, email="filterunknown@example.com")
    ws, base, table = await create_workspace_base_table(client)

    condition = json.dumps({"kind": "condition", "field": "NotAField", "operator": "eq", "value": "x"})
    resp = await client.get(f"/api/tables/{table['id']}/rows", params={"filter": condition})
    assert resp.status_code == 422


async def test_view_config_persists_valid_filter(client):
    await register_user(client, email="filterview@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})
    view_id = table["views"][0]["id"]

    filter_dict = {"kind": "condition", "field": "N", "operator": "gt", "value": 1}
    resp = await client.patch(f"/api/tables/{table['id']}/views/{view_id}", json={"config": {"filter": filter_dict}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["filter"] == filter_dict


async def test_view_config_rejects_filter_on_virtual_field(client):
    await register_user(client, email="filterviewbad@example.com")
    ws, base, table = await create_workspace_base_table(client)
    view_id = table["views"][0]["id"]

    filter_dict = {"kind": "condition", "field": "NotAField", "operator": "eq", "value": "x"}
    resp = await client.patch(f"/api/tables/{table['id']}/views/{view_id}", json={"config": {"filter": filter_dict}})
    assert resp.status_code == 422
