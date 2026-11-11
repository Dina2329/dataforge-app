import json

from tests.conftest import create_workspace_base_table, register_user


def _sort_param(specs):
    return json.dumps(specs)


async def test_sort_asc_and_desc(client):
    await register_user(client, email="sorter@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})

    for n in [3, 1, 2]:
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"N": n}})
        assert resp.status_code == 201

    asc = (await client.get(f"/api/tables/{table['id']}/rows", params={"sort": _sort_param([{"field": "N", "direction": "asc"}])})).json()
    assert [r["values"]["N"] for r in asc["rows"]] == [1, 2, 3]

    desc = (await client.get(f"/api/tables/{table['id']}/rows", params={"sort": _sort_param([{"field": "N", "direction": "desc"}])})).json()
    assert [r["values"]["N"] for r in desc["rows"]] == [3, 2, 1]


async def test_sort_paginates_without_duplicates_or_gaps(client):
    await register_user(client, email="sortpager@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})

    for n in reversed(range(7)):
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"N": n}})
        assert resp.status_code == 201

    seen = []
    cursor = None
    for _ in range(10):
        params = {"sort": _sort_param([{"field": "N", "direction": "asc"}]), "limit": 3}
        if cursor is not None:
            params["cursor"] = cursor
        page = (await client.get(f"/api/tables/{table['id']}/rows", params=params)).json()
        seen.extend(r["values"]["N"] for r in page["rows"])
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]

    assert seen == list(range(7))


async def test_sort_with_nulls_last(client):
    await register_user(client, email="sortnulls@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})

    for n in [None, 2, None, 1]:
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"N": n} if n is not None else {}})
        assert resp.status_code == 201

    page = (await client.get(f"/api/tables/{table['id']}/rows", params={"sort": _sort_param([{"field": "N", "direction": "asc"}])})).json()
    values = [r["values"].get("N") for r in page["rows"]]
    assert values == [1, 2, None, None]


async def test_sort_unknown_field_rejected(client):
    await register_user(client, email="sortunknown@example.com")
    ws, base, table = await create_workspace_base_table(client)

    resp = await client.get(f"/api/tables/{table['id']}/rows", params={"sort": _sort_param([{"field": "NotAField", "direction": "asc"}])})
    assert resp.status_code == 422


async def test_multi_column_sort(client):
    await register_user(client, email="multisort@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Group", "field_type": "text", "options": {}})
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})

    rows = [
        {"Group": "B", "N": 2},
        {"Group": "A", "N": 3},
        {"Group": "B", "N": 1},
        {"Group": "A", "N": 1},
    ]
    for values in rows:
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": values})
        assert resp.status_code == 201

    # Group asc, then N desc within each group
    sort = _sort_param([{"field": "Group", "direction": "asc"}, {"field": "N", "direction": "desc"}])
    page = (await client.get(f"/api/tables/{table['id']}/rows", params={"sort": sort})).json()
    ordered = [(r["values"]["Group"], r["values"]["N"]) for r in page["rows"]]
    assert ordered == [("A", 3), ("A", 1), ("B", 2), ("B", 1)]


async def test_multi_column_sort_paginates_without_duplicates_or_gaps(client):
    await register_user(client, email="multisortpager@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Group", "field_type": "text", "options": {}})
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})

    expected = []
    for group in ["A", "B", "C"]:
        for n in reversed(range(4)):
            resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Group": group, "N": n}})
            assert resp.status_code == 201
            expected.append((group, n))
    expected.sort(key=lambda gn: (gn[0], gn[1]))

    seen = []
    cursor = None
    sort = _sort_param([{"field": "Group", "direction": "asc"}, {"field": "N", "direction": "asc"}])
    for _ in range(20):
        params = {"sort": sort, "limit": 5}
        if cursor is not None:
            params["cursor"] = cursor
        page = (await client.get(f"/api/tables/{table['id']}/rows", params=params)).json()
        seen.extend((r["values"]["Group"], r["values"]["N"]) for r in page["rows"])
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]

    assert seen == expected


async def test_view_config_persists_list_of_sorts(client):
    await register_user(client, email="sortviewlist@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})
    view_id = table["views"][0]["id"]

    sort_config = [{"field": "Name", "direction": "asc"}, {"field": "N", "direction": "desc"}]
    resp = await client.patch(f"/api/tables/{table['id']}/views/{view_id}", json={"config": {"sort": sort_config}})
    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["sort"] == sort_config
