from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import create_workspace_base_table, register_user


async def _invite(owner_client, workspace_id, email, role):
    resp = await owner_client.post(f"/api/workspaces/{workspace_id}/members", json={"email": email, "role": role})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_owner_can_create_table_and_records(client):
    await register_user(client, email="owner@example.com")
    ws, base, table = await create_workspace_base_table(client)

    field_resp = await client.post(
        f"/api/tables/{table['id']}/fields", json={"name": "Title", "field_type": "text", "options": {}, "required": False}
    )
    assert field_resp.status_code == 201, field_resp.text

    row_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Title": "Hello"}})
    assert row_resp.status_code == 201, row_resp.text
    assert row_resp.json()["values"]["Title"] == "Hello"


async def test_records_cursor_pagination(client):
    await register_user(client, email="pager@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "N", "field_type": "number", "options": {}})

    for i in range(5):
        resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"N": i}})
        assert resp.status_code == 201

    page1 = (await client.get(f"/api/tables/{table['id']}/rows", params={"limit": 2})).json()
    assert len(page1["rows"]) == 2
    assert page1["has_more"] is True
    assert page1["next_cursor"] is not None

    page2 = (await client.get(f"/api/tables/{table['id']}/rows", params={"limit": 2, "cursor": page1["next_cursor"]})).json()
    assert len(page2["rows"]) == 2
    # No overlap between pages.
    page1_ids = {r["row_id"] for r in page1["rows"]}
    page2_ids = {r["row_id"] for r in page2["rows"]}
    assert page1_ids.isdisjoint(page2_ids)

    page3 = (await client.get(f"/api/tables/{table['id']}/rows", params={"limit": 2, "cursor": page2["next_cursor"]})).json()
    assert len(page3["rows"]) == 1
    assert page3["has_more"] is False
    assert page3["next_cursor"] is None


async def test_optimistic_concurrency_conflict_on_stale_version(client):
    await register_user(client, email="version@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Title", "field_type": "text", "options": {}})
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Title": "v1"}})).json()

    ok = await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}",
        json={"values": {"Title": "v2"}, "expected_version": row["version"]},
    )
    assert ok.status_code == 200
    assert ok.json()["version"] == row["version"] + 1

    stale = await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}",
        json={"values": {"Title": "v3-stale"}, "expected_version": row["version"]},
    )
    assert stale.status_code == 409


async def test_viewer_cannot_write_but_can_read(client, make_client):
    await register_user(client, email="owner2@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Title", "field_type": "text", "options": {}})
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Title": "seed"}})

    viewer = await make_client()
    await register_user(viewer, email="viewer@example.com")
    await _invite(client, ws["id"], "viewer@example.com", WorkspaceRole.VIEWER)

    # Viewer can read...
    read_resp = await viewer.get(f"/api/tables/{table['id']}/rows")
    assert read_resp.status_code == 200
    assert len(read_resp.json()["rows"]) == 1

    # ...but cannot create a row, create a field, or create a table.
    write_resp = await viewer.post(f"/api/tables/{table['id']}/rows", json={"values": {"Title": "nope"}})
    assert write_resp.status_code == 403

    field_resp = await viewer.post(
        f"/api/tables/{table['id']}/fields", json={"name": "New", "field_type": "text", "options": {}}
    )
    assert field_resp.status_code == 403

    table_resp = await viewer.post(f"/api/bases/{base['id']}/tables", json={"name": "Nope"})
    assert table_resp.status_code == 403


async def test_editor_can_write_records_but_not_manage_members(client, make_client):
    await register_user(client, email="owner3@example.com")
    ws, base, table = await create_workspace_base_table(client)

    editor = await make_client()
    await register_user(editor, email="editor@example.com")
    await _invite(client, ws["id"], "editor@example.com", WorkspaceRole.EDITOR)

    row_resp = await editor.post(f"/api/tables/{table['id']}/rows", json={"values": {}})
    assert row_resp.status_code == 201

    invite_resp = await editor.post(
        f"/api/workspaces/{ws['id']}/members", json={"email": "someone@example.com", "role": WorkspaceRole.VIEWER}
    )
    assert invite_resp.status_code == 403


async def test_non_member_cannot_see_workspace_resources(client, make_client):
    await register_user(client, email="owner4@example.com")
    ws, base, table = await create_workspace_base_table(client)

    stranger = await make_client()
    await register_user(stranger, email="stranger@example.com")

    resp = await stranger.get(f"/api/tables/{table['id']}/rows")
    assert resp.status_code in (403, 404)
