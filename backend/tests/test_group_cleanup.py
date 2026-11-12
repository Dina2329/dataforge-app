"""Group cleanup ("Move to missing term"): a table's rows are grouped by one
field (e.g. a component code); a group is deleted only when EVERY row
sharing that group value has an empty value field AND a zero score field.
A group with even one populated row, or one non-zero score, is left
completely untouched -- no partial deletes within a group."""

from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import create_workspace_base_table, register_user


async def _setup(client, *, email: str):
    await register_user(client, email=email)
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Code", "field_type": "text", "options": {}})
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Value", "field_type": "text", "options": {}})
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Score", "field_type": "number", "options": {}})
    return ws, base, table


async def _add_row(client, table_id, *, code, value, score):
    resp = await client.post(f"/api/tables/{table_id}/rows", json={"values": {"Code": code, "Value": value, "Score": score}})
    assert resp.status_code == 201, resp.text


async def test_group_fully_empty_and_zero_qualifies_group_with_any_match_does_not(client):
    ws, base, table = await _setup(client, email="cleanup1@example.com")

    # Group A: every row empty value + score 0 -- fully unmatched, qualifies.
    await _add_row(client, table["id"], code="A", value=None, score=0)
    await _add_row(client, table["id"], code="A", value="", score=0)

    # Group B: one row has a real value/score -- the whole group is spared.
    await _add_row(client, table["id"], code="B", value=None, score=0)
    await _add_row(client, table["id"], code="B", value="Crawford", score=1)

    preview = await client.get(
        f"/api/tables/{table['id']}/group-cleanup-preview",
        params={"group_field": "Code", "value_field": "Value", "score_field": "Score"},
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["qualifying_groups"] == 1
    assert body["rows_to_delete"] == 2
    assert body["sample_group_values"] == ["A"]

    execute = await client.post(
        f"/api/tables/{table['id']}/group-cleanup",
        json={"group_field": "Code", "value_field": "Value", "score_field": "Score"},
    )
    assert execute.status_code == 200, execute.text
    assert execute.json() == {"groups_deleted": 1, "rows_deleted": 2}

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    codes = sorted(r["values"]["Code"] for r in rows)
    assert codes == ["B", "B"]


async def test_preview_does_not_delete_anything(client):
    ws, base, table = await _setup(client, email="cleanup2@example.com")
    await _add_row(client, table["id"], code="A", value=None, score=0)

    await client.get(
        f"/api/tables/{table['id']}/group-cleanup-preview",
        params={"group_field": "Code", "value_field": "Value", "score_field": "Score"},
    )
    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert len(rows) == 1


async def test_nonzero_score_alone_spares_the_group(client):
    ws, base, table = await _setup(client, email="cleanup3@example.com")
    await _add_row(client, table["id"], code="A", value=None, score=0)
    await _add_row(client, table["id"], code="A", value=None, score=1)

    preview = await client.get(
        f"/api/tables/{table['id']}/group-cleanup-preview",
        params={"group_field": "Code", "value_field": "Value", "score_field": "Score"},
    )
    assert preview.json()["qualifying_groups"] == 0


async def test_unknown_field_name_rejected(client):
    ws, base, table = await _setup(client, email="cleanup4@example.com")
    resp = await client.get(
        f"/api/tables/{table['id']}/group-cleanup-preview",
        params={"group_field": "Code", "value_field": "NotAField", "score_field": "Score"},
    )
    assert resp.status_code == 422, resp.text


async def test_no_qualifying_groups_deletes_nothing(client):
    ws, base, table = await _setup(client, email="cleanup5@example.com")
    await _add_row(client, table["id"], code="A", value="x", score=1)

    execute = await client.post(
        f"/api/tables/{table['id']}/group-cleanup",
        json={"group_field": "Code", "value_field": "Value", "score_field": "Score"},
    )
    assert execute.json() == {"groups_deleted": 0, "rows_deleted": 0}
    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert len(rows) == 1


async def test_viewer_cannot_execute_cleanup(client, make_client):
    ws, base, table = await _setup(client, email="cleanup6@example.com")
    await _add_row(client, table["id"], code="A", value=None, score=0)

    viewer = await make_client()
    await register_user(viewer, email="cleanup6-viewer@example.com")
    await client.post(f"/api/workspaces/{ws['id']}/members", json={"email": "cleanup6-viewer@example.com", "role": WorkspaceRole.VIEWER})

    resp = await viewer.post(
        f"/api/tables/{table['id']}/group-cleanup",
        json={"group_field": "Code", "value_field": "Value", "score_field": "Score"},
    )
    assert resp.status_code == 403
