"""Bulk update: preview -> execute -> undo.

execute_bulk_update only enqueues an arq job (app/modules/bulk_ops/service.py
calls pool.enqueue_job(...)); there's no worker process running in tests, so
these drive the actual CASE-WHEN update/undo logic directly by importing and
awaiting the task functions from app/worker/tasks/bulk_ops_tasks.py the same
way the arq worker would, instead of standing up a whole worker loop.
"""

from app.worker.tasks.bulk_ops_tasks import run_bulk_update, undo_bulk_update
from tests.conftest import create_workspace_base_table, register_user


async def _seed_rows(client, table_id, statuses):
    for status in statuses:
        resp = await client.post(f"/api/tables/{table_id}/rows", json={"values": {"Status": status}})
        assert resp.status_code == 201


async def test_bulk_update_preview_does_not_change_data(client):
    await register_user(client, email="bulk1@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Status", "field_type": "text", "options": {}})
    await _seed_rows(client, table["id"], ["pending", "pending", "done"])

    preview = await client.post(
        f"/api/tables/{table['id']}/bulk-update/preview",
        json={"filter": {"kind": "condition", "field": "Status", "operator": "eq", "value": "pending"}, "values": {"Status": "done"}},
    )
    assert preview.status_code == 200
    body = preview.json()
    assert body["matched_count"] == 2
    assert len(body["sample_rows"]) == 2

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    statuses = sorted(r["values"]["Status"] for r in rows)
    assert statuses == ["done", "pending", "pending"]


async def test_bulk_update_requires_confirm(client):
    await register_user(client, email="bulk2@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Status", "field_type": "text", "options": {}})
    await _seed_rows(client, table["id"], ["pending"])

    resp = await client.post(
        f"/api/tables/{table['id']}/bulk-update/execute",
        json={
            "filter": {"kind": "condition", "field": "Status", "operator": "eq", "value": "pending"},
            "values": {"Status": "done"},
            "confirm": False,
        },
    )
    assert resp.status_code == 422


async def test_bulk_update_execute_and_undo(client):
    await register_user(client, email="bulk3@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Status", "field_type": "text", "options": {}})
    await _seed_rows(client, table["id"], ["pending", "pending", "done", "pending"])

    execute_resp = await client.post(
        f"/api/tables/{table['id']}/bulk-update/execute",
        json={
            "filter": {"kind": "condition", "field": "Status", "operator": "eq", "value": "pending"},
            "values": {"Status": "done"},
            "confirm": True,
        },
    )
    assert execute_resp.status_code == 202
    operation = execute_resp.json()
    assert operation["status"] == "pending"

    # Run what the arq worker would run, synchronously.
    await run_bulk_update({}, operation["id"])

    status_resp = await client.get(f"/api/bulk-operations/{operation['id']}")
    assert status_resp.status_code == 200
    completed = status_resp.json()
    assert completed["status"] == "completed"
    assert completed["matched_count"] == 3
    assert completed["affected_count"] == 3

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    statuses = sorted(r["values"]["Status"] for r in rows)
    assert statuses == ["done", "done", "done", "done"]

    # Undo should restore each row's own prior value (3x "pending", 1x untouched "done").
    undo_resp = await client.post(f"/api/bulk-operations/{operation['id']}/undo")
    assert undo_resp.status_code == 202

    await undo_bulk_update({}, operation["id"])

    undone_status = (await client.get(f"/api/bulk-operations/{operation['id']}")).json()
    assert undone_status["undone_at"] is not None

    rows_after_undo = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    statuses_after_undo = sorted(r["values"]["Status"] for r in rows_after_undo)
    assert statuses_after_undo == ["done", "pending", "pending", "pending"]


async def test_bulk_update_cannot_touch_primary_field(client):
    await register_user(client, email="bulk4@example.com")
    ws, base, table = await create_workspace_base_table(client)
    # The table's auto-created "Name" field is primary (see BasesService.create_table).
    resp = await client.post(
        f"/api/tables/{table['id']}/bulk-update/preview",
        json={"filter": {"kind": "condition", "field": "Name", "operator": "eq", "value": "x"}, "values": {"Name": "y"}},
    )
    assert resp.status_code == 422


async def test_viewer_cannot_execute_bulk_update(client, make_client):
    from app.modules.workspaces.models import WorkspaceRole

    await register_user(client, email="bulk5@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Status", "field_type": "text", "options": {}})

    viewer = await make_client()
    await register_user(viewer, email="bulk5-viewer@example.com")
    await client.post(f"/api/workspaces/{ws['id']}/members", json={"email": "bulk5-viewer@example.com", "role": WorkspaceRole.VIEWER})

    resp = await viewer.post(
        f"/api/tables/{table['id']}/bulk-update/preview",
        json={"filter": {"kind": "condition", "field": "Status", "operator": "eq", "value": "x"}, "values": {"Status": "y"}},
    )
    assert resp.status_code == 403
