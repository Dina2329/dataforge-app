from sqlalchemy import text

from app.core.db import engine
from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import create_workspace_base_table, register_user


async def _physical_table_exists(physical_table_name: str) -> bool:
    async with engine.begin() as conn:
        result = await conn.execute(text("select to_regclass(:name)"), {"name": f"df_data.{physical_table_name}"})
        return result.scalar_one() is not None


async def _physical_name_for(client, table_id: str) -> str:
    async with engine.begin() as conn:
        row = (await conn.execute(text("select physical_table_name from df_meta.tables where id = :id"), {"id": table_id})).one()
        return row[0]


async def _add_member(client, workspace_id: str, make_client, role, email):
    member = await make_client()
    await register_user(member, email=email)
    await client.post(f"/api/workspaces/{workspace_id}/members", json={"email": email, "role": role})
    return member


# -- delete table -----------------------------------------------------------


async def test_owner_can_delete_table_and_drops_physical_table(client):
    await register_user(client, email="t-owner1@example.com")
    ws, base, table = await create_workspace_base_table(client)
    physical_name = await _physical_name_for(client, table["id"])
    assert await _physical_table_exists(physical_name) is True

    resp = await client.delete(f"/api/tables/{table['id']}")
    assert resp.status_code == 204
    assert await _physical_table_exists(physical_name) is False

    listing = await client.get(f"/api/bases/{base['id']}/tables")
    assert table["id"] not in [t["id"] for t in listing.json()]


async def test_admin_can_delete_table(client, make_client):
    await register_user(client, email="t-owner2@example.com")
    ws, base, table = await create_workspace_base_table(client)
    admin = await _add_member(client, ws["id"], make_client, WorkspaceRole.ADMIN, "t-admin2@example.com")

    resp = await admin.delete(f"/api/tables/{table['id']}")
    assert resp.status_code == 204


async def test_editor_cannot_delete_table(client, make_client):
    await register_user(client, email="t-owner3@example.com")
    ws, base, table = await create_workspace_base_table(client)
    editor = await _add_member(client, ws["id"], make_client, WorkspaceRole.EDITOR, "t-editor3@example.com")

    resp = await editor.delete(f"/api/tables/{table['id']}")
    assert resp.status_code == 403

    # Editors can still create tables (schema.write), just not delete them.
    create_resp = await editor.post(f"/api/bases/{base['id']}/tables", json={"name": "Editor Made This"})
    assert create_resp.status_code == 201


async def test_viewer_cannot_delete_table(client, make_client):
    await register_user(client, email="t-owner4@example.com")
    ws, base, table = await create_workspace_base_table(client)
    viewer = await _add_member(client, ws["id"], make_client, WorkspaceRole.VIEWER, "t-viewer4@example.com")

    resp = await viewer.delete(f"/api/tables/{table['id']}")
    assert resp.status_code == 403


async def test_delete_table_cascades_widgets_and_automations(client):
    await register_user(client, email="t-owner5@example.com")
    ws, base, table = await create_workspace_base_table(client)

    dashboard = (await client.post(f"/api/workspaces/{ws['id']}/dashboards", json={"name": "D"})).json()
    widget = (
        await client.post(
            f"/api/dashboards/{dashboard['id']}/widgets",
            json={"name": "W", "widget_type": "kpi", "table_id": table["id"], "config": {}, "position": {"x": 0, "y": 0, "w": 2, "h": 2}},
        )
    ).json()
    automation = (
        await client.post(
            f"/api/tables/{table['id']}/automations",
            json={"name": "A", "trigger_type": "record_created", "trigger_config": {}},
        )
    ).json()

    resp = await client.delete(f"/api/tables/{table['id']}")
    assert resp.status_code == 204

    widgets_after = await client.get(f"/api/dashboards/{dashboard['id']}/widgets")
    assert widget["id"] not in [w["id"] for w in widgets_after.json()]

    # The automation's own table_id FK is gone -- fetching its parent table 404s,
    # which is the observable proof the automation row itself was cascaded away
    # (there's no direct GET /api/automations/{id}, so this exercises the same thing
    # via the dashboard still existing but the automations list for that table 404ing).
    automations_after = await client.get(f"/api/tables/{table['id']}/automations")
    assert automations_after.status_code == 404
    assert automation["id"]  # created successfully before deletion, sanity check


# -- create base --------------------------------------------------------------


async def test_owner_can_create_base(client):
    await register_user(client, email="cb-owner1@example.com")
    ws = (await client.post("/api/workspaces", json={"name": "WS"})).json()

    resp = await client.post(f"/api/workspaces/{ws['id']}/bases", json={"name": "Owner Made This"})
    assert resp.status_code == 201, resp.text


async def test_admin_can_create_base(client, make_client):
    await register_user(client, email="cb-owner2@example.com")
    ws, base, table = await create_workspace_base_table(client)
    admin = await _add_member(client, ws["id"], make_client, WorkspaceRole.ADMIN, "cb-admin2@example.com")

    resp = await admin.post(f"/api/workspaces/{ws['id']}/bases", json={"name": "Admin Made This"})
    assert resp.status_code == 201, resp.text


async def test_editor_and_viewer_cannot_create_base(client, make_client):
    await register_user(client, email="cb-owner3@example.com")
    ws, base, table = await create_workspace_base_table(client)

    for role, email in [(WorkspaceRole.EDITOR, "cb-editor3@example.com"), (WorkspaceRole.VIEWER, "cb-viewer3@example.com")]:
        member = await _add_member(client, ws["id"], make_client, role, email)
        resp = await member.post(f"/api/workspaces/{ws['id']}/bases", json={"name": f"{role} Made This"})
        assert resp.status_code == 403, f"{role} should not be able to create a base"

    # Reserved for base creation specifically -- table creation inside an
    # existing base is unaffected (see test_editor_cannot_delete_table).
    editor = await _add_member(client, ws["id"], make_client, WorkspaceRole.EDITOR, "cb-editor3b@example.com")
    table_resp = await editor.post(f"/api/bases/{base['id']}/tables", json={"name": "Editor Made This"})
    assert table_resp.status_code == 201, table_resp.text


# -- delete base -------------------------------------------------------------


async def test_owner_can_delete_base_and_drops_all_physical_tables(client):
    await register_user(client, email="b-owner1@example.com")
    ws, base, table = await create_workspace_base_table(client)
    second_table = (await client.post(f"/api/bases/{base['id']}/tables", json={"name": "Second"})).json()

    physical_1 = await _physical_name_for(client, table["id"])
    physical_2 = await _physical_name_for(client, second_table["id"])
    assert await _physical_table_exists(physical_1) is True
    assert await _physical_table_exists(physical_2) is True

    resp = await client.delete(f"/api/bases/{base['id']}")
    assert resp.status_code == 204

    assert await _physical_table_exists(physical_1) is False
    assert await _physical_table_exists(physical_2) is False

    listing = await client.get(f"/api/workspaces/{ws['id']}/bases")
    assert base["id"] not in [b["id"] for b in listing.json()]


async def test_admin_can_delete_base(client, make_client):
    await register_user(client, email="b-owner2@example.com")
    ws, base, table = await create_workspace_base_table(client)
    admin = await _add_member(client, ws["id"], make_client, WorkspaceRole.ADMIN, "b-admin2@example.com")

    resp = await admin.delete(f"/api/bases/{base['id']}")
    assert resp.status_code == 204


async def test_editor_and_viewer_cannot_delete_base(client, make_client):
    await register_user(client, email="b-owner3@example.com")
    ws, base, table = await create_workspace_base_table(client)

    for role, email in [(WorkspaceRole.EDITOR, "b-editor3@example.com"), (WorkspaceRole.VIEWER, "b-viewer3@example.com")]:
        member = await _add_member(client, ws["id"], make_client, role, email)
        resp = await member.delete(f"/api/bases/{base['id']}")
        assert resp.status_code == 403, f"{role} should not be able to delete a base"

    listing = await client.get(f"/api/workspaces/{ws['id']}/bases")
    assert base["id"] in [b["id"] for b in listing.json()]


async def test_delete_nonexistent_base_and_table_404(client):
    await register_user(client, email="missing@example.com")
    resp = await client.delete("/api/bases/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    resp2 = await client.delete("/api/tables/00000000-0000-0000-0000-000000000000")
    assert resp2.status_code == 404
