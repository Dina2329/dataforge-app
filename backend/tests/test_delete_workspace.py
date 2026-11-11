from sqlalchemy import text

from app.core.db import engine
from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import create_workspace_base_table, register_user


async def _physical_table_exists(physical_table_name: str) -> bool:
    async with engine.begin() as conn:
        result = await conn.execute(text("select to_regclass(:name)"), {"name": f"df_data.{physical_table_name}"})
        return result.scalar_one() is not None


async def test_owner_can_delete_workspace_and_it_disappears(client):
    await register_user(client, email="owner1@example.com")
    ws, base, table = await create_workspace_base_table(client)

    resp = await client.delete(f"/api/workspaces/{ws['id']}")
    assert resp.status_code == 204

    listing = await client.get("/api/workspaces")
    assert ws["id"] not in [w["id"] for w in listing.json()]

    members_resp = await client.get(f"/api/workspaces/{ws['id']}/members")
    assert members_resp.status_code == 404


async def test_delete_workspace_drops_physical_table(client):
    await register_user(client, email="owner2@example.com")
    ws, base, table = await create_workspace_base_table(client)

    # Prove the table isn't just metadata -- give it a real column and row.
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Title", "field_type": "text", "options": {}})
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Title": "hello"}})

    # physical_table_name isn't exposed over the API -- read it directly from df_meta instead.
    async with engine.begin() as conn:
        row = (await conn.execute(text("select physical_table_name from df_meta.tables where id = :id"), {"id": table["id"]})).one()
        physical_name = row[0]

    assert await _physical_table_exists(physical_name) is True

    resp = await client.delete(f"/api/workspaces/{ws['id']}")
    assert resp.status_code == 204

    assert await _physical_table_exists(physical_name) is False


async def test_admin_can_delete_workspace(client, make_client):
    await register_user(client, email="owner3a@example.com")
    ws, base, table = await create_workspace_base_table(client)

    admin = await make_client()
    await register_user(admin, email="admin3a@example.com")
    await client.post(f"/api/workspaces/{ws['id']}/members", json={"email": "admin3a@example.com", "role": WorkspaceRole.ADMIN})

    resp = await admin.delete(f"/api/workspaces/{ws['id']}")
    assert resp.status_code == 204


async def test_editor_and_viewer_cannot_delete_workspace(client, make_client):
    await register_user(client, email="owner3@example.com")
    ws, base, table = await create_workspace_base_table(client)

    for role, email in [(WorkspaceRole.EDITOR, "editor3@example.com"), (WorkspaceRole.VIEWER, "viewer3@example.com")]:
        member = await make_client()
        await register_user(member, email=email)
        await client.post(f"/api/workspaces/{ws['id']}/members", json={"email": email, "role": role})

        resp = await member.delete(f"/api/workspaces/{ws['id']}")
        assert resp.status_code == 403, f"{role} should not be able to delete the workspace"

    # Still there afterwards.
    listing = await client.get("/api/workspaces")
    assert ws["id"] in [w["id"] for w in listing.json()]


async def test_non_member_cannot_delete_workspace(client, make_client):
    await register_user(client, email="owner4@example.com")
    ws, base, table = await create_workspace_base_table(client)

    stranger = await make_client()
    await register_user(stranger, email="stranger4@example.com")
    resp = await stranger.delete(f"/api/workspaces/{ws['id']}")
    assert resp.status_code in (403, 404)


async def test_delete_nonexistent_workspace_404s(client):
    await register_user(client, email="owner5@example.com")
    resp = await client.delete("/api/workspaces/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
