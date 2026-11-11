"""Push approval gate (pending_sync_changes / sync_change_batches) -- a
review step in front of the existing push pipeline tested in
test_table_sync.py. Reuses that file's real-Postgres fixtures (same external
database, same push_record_to_source task) since approval doesn't change the
push mechanism at all, only whether it fires immediately or waits for an
owner/admin to say so.

Two-step flow under test: an edit on a gated table first lands as a private
*draft* (only its own editor can see it, via .../pending-sync-change-drafts);
the editor then explicitly submits, bundling every current draft into one
SyncChangeBatch that an owner/admin approves or rejects as a single action
(.../sync-change-batches).
"""

import json
import uuid

import pytest_asyncio

from app.modules.connectors.base import TableRef
from app.modules.connectors.types.postgres_connector import PostgresConnector
from app.modules.workspaces.models import WorkspaceRole
from app.worker.tasks.sync_tasks import push_record_to_source
from tests.conftest import create_workspace_base_table, register_user
from tests.test_table_sync import PG_CONFIG, _current_user_id, _reset_external_table, _reset_external_table_with_ts


class _FakeArqPool:
    """Same pattern as test_table_sync.py's manual-poll tests: captures the
    enqueue_job call(s) instead of touching real Redis, so the test can run
    the exact jobs that were enqueued directly (no worker process during
    tests). A batch approval enqueues one job per row in the batch."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))


async def _invite(owner_client, workspace_id, email, role):
    resp = await owner_client.post(f"/api/workspaces/{workspace_id}/members", json={"email": email, "role": role})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _external_rows():
    connector = PostgresConnector(PG_CONFIG)
    try:
        return [r async for batch in connector.stream_rows(TableRef(name="ext_approval", schema="ext_test")) for r in batch]
    finally:
        await connector.close()


async def _submit(client, workspace_id):
    resp = await client.post(f"/api/workspaces/{workspace_id}/pending-sync-changes/submit")
    assert resp.status_code == 200, resp.text
    return resp.json()  # {"batch_id": ..., "change_count": ...}


async def _get_batch(client, workspace_id, batch_id):
    batches = (await client.get(f"/api/workspaces/{workspace_id}/sync-change-batches")).json()
    return next(b for b in batches if b["id"] == batch_id)


async def _approve_batch(client, batch_id, monkeypatch, *, run: bool = True):
    fake_pool = _FakeArqPool()

    async def fake_get_arq_pool():
        return fake_pool

    monkeypatch.setattr("app.modules.connectors.pending_sync_service.get_arq_pool", fake_get_arq_pool)
    resp = await client.post(f"/api/sync-change-batches/{batch_id}/approve")
    assert resp.status_code == 200, resp.text
    if run:
        for name, args, kwargs in fake_pool.calls:
            assert name == "push_record_to_source"
            await push_record_to_source({}, *args, **kwargs)
    return resp.json()


@pytest_asyncio.fixture
async def approval_table(client):
    """Owner-created, push-enabled, push_requires_approval=True table backed
    by a real Postgres table. The registering user becomes workspace OWNER
    (has SYNC_APPROVAL_MANAGE via role_has_permission's _ALL_PERMISSIONS),
    so `client` alone can exercise the submit/approve/reject endpoints;
    editor-role tests invite a second user separately."""
    await _reset_external_table(PG_CONFIG, "ext_approval", dialect="postgres")
    await register_user(client, email=f"appr_{uuid.uuid4().hex[:8]}@example.com")
    user_id = await _current_user_id(client)
    ws, base, _ = await create_workspace_base_table(client)

    ds_resp = await client.post(
        f"/api/workspaces/{ws['id']}/data-sources",
        data={"name": "ExtApproval", "source_type": "postgres", "config": json.dumps(PG_CONFIG)},
    )
    assert ds_resp.status_code == 201, ds_resp.text
    data_source_id = ds_resp.json()["id"]

    import_resp = await client.post(
        f"/api/bases/{base['id']}/import-from-source/{data_source_id}",
        json={"table_name": "ext_approval", "table_schema": "ext_test", "new_table_name": "Approval", "sync_enabled": True},
    )
    assert import_resp.status_code == 201, import_resp.text
    table = import_resp.json()

    gate_resp = await client.patch(f"/api/tables/{table['id']}/sync", json={"sync_enabled": True, "push_requires_approval": True})
    assert gate_resp.status_code == 200, gate_resp.text
    assert gate_resp.json()["push_requires_approval"] is True

    return client, table, ws, user_id


async def test_toggle_requires_approval_needs_admin_permission(client, make_client):
    await _reset_external_table(PG_CONFIG, "ext_approval_toggle", dialect="postgres")
    await register_user(client, email=f"apprtog_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, _ = await create_workspace_base_table(client)
    ds_resp = await client.post(
        f"/api/workspaces/{ws['id']}/data-sources",
        data={"name": "ExtApprovalToggle", "source_type": "postgres", "config": json.dumps(PG_CONFIG)},
    )
    data_source_id = ds_resp.json()["id"]
    import_resp = await client.post(
        f"/api/bases/{base['id']}/import-from-source/{data_source_id}",
        json={"table_name": "ext_approval_toggle", "table_schema": "ext_test", "new_table_name": "ApprovalToggle", "sync_enabled": True},
    )
    table = import_resp.json()

    editor = await make_client()
    await register_user(editor, email=f"editor_{uuid.uuid4().hex[:8]}@example.com")
    editor_email = (await editor.get("/api/auth/me")).json()["email"]
    await _invite(client, ws["id"], editor_email, WorkspaceRole.EDITOR)

    # An editor can still toggle plain sync_enabled (DATA_SOURCE_WRITE)...
    editor_resp = await editor.patch(f"/api/tables/{table['id']}/sync", json={"sync_enabled": True})
    assert editor_resp.status_code == 200, editor_resp.text
    # ...but not the approval gate -- letting an editor turn this back off
    # themselves would defeat the entire feature.
    editor_gate_resp = await editor.patch(f"/api/tables/{table['id']}/sync", json={"sync_enabled": True, "push_requires_approval": True})
    assert editor_gate_resp.status_code == 403

    owner_resp = await client.patch(f"/api/tables/{table['id']}/sync", json={"sync_enabled": True, "push_requires_approval": True})
    assert owner_resp.status_code == 200, owner_resp.text
    assert owner_resp.json()["push_requires_approval"] is True


async def test_gated_insert_creates_a_draft_not_a_push(approval_table):
    client, table, ws, _ = approval_table
    resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Widget", "amount": "9.99"}})
    assert resp.status_code == 201

    assert await _external_rows() == []

    drafts = (await client.get(f"/api/workspaces/{ws['id']}/pending-sync-change-drafts")).json()
    assert len(drafts) == 1
    assert drafts[0]["operation"] == "insert"
    assert drafts[0]["values"]["name"] == "Widget"
    assert drafts[0]["status"] == "draft"
    assert drafts[0]["table_name"] == "Approval"

    # Not visible to an approver at all until it's submitted.
    batches = (await client.get(f"/api/workspaces/{ws['id']}/sync-change-batches")).json()
    assert batches == []


async def test_submitting_and_approving_a_batch_pushes_it(approval_table, monkeypatch):
    client, table, ws, _ = approval_table
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Widget", "amount": "9.99"}})

    submitted = await _submit(client, ws["id"])
    assert submitted["change_count"] == 1
    batch = await _get_batch(client, ws["id"], submitted["batch_id"])
    assert len(batch["changes"]) == 1
    assert batch["changes"][0]["status"] == "pending"

    approved = await _approve_batch(client, batch["id"], monkeypatch)
    assert approved["status"] == "approved"
    assert approved["changes"][0]["status"] == "approved"

    rows = await _external_rows()
    assert any(r["name"] == "Widget" for r in rows)

    # Resolved -- no longer an open batch.
    still_open = (await client.get(f"/api/workspaces/{ws['id']}/sync-change-batches")).json()
    assert still_open == []


async def test_rejecting_a_batch_does_not_push(approval_table):
    client, table, ws, _ = approval_table
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Rejected Widget", "amount": "1"}})
    submitted = await _submit(client, ws["id"])

    reject_resp = await client.post(f"/api/sync-change-batches/{submitted['batch_id']}/reject", json={"reason": "wrong price"})
    assert reject_resp.status_code == 200, reject_resp.text
    assert reject_resp.json()["status"] == "rejected"
    assert reject_resp.json()["rejection_reason"] == "wrong price"

    assert await _external_rows() == []
    still_open = (await client.get(f"/api/workspaces/{ws['id']}/sync-change-batches")).json()
    assert still_open == []

    notifications = (await client.get("/api/notifications")).json()["notifications"]
    assert any("rejected" in n["title"].lower() for n in notifications)


async def test_second_edit_before_submit_collapses_to_latest_values(approval_table):
    client, table, ws, _ = approval_table
    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Original", "amount": "1"}})
    row = create_resp.json()

    update_resp = await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}",
        json={"values": {"name": "Edited Before Submit"}, "expected_version": row["version"]},
    )
    assert update_resp.status_code == 200

    drafts = (await client.get(f"/api/workspaces/{ws['id']}/pending-sync-change-drafts")).json()
    # Still exactly one draft, not two -- and still "insert" (nothing was
    # ever pushed, so that's still what's owed externally), carrying the
    # *latest* values, not the original ones.
    assert len(drafts) == 1
    assert drafts[0]["operation"] == "insert"
    assert drafts[0]["values"]["name"] == "Edited Before Submit"


async def test_edit_after_submit_but_before_review_collapses_into_the_open_batch(approval_table):
    client, table, ws, _ = approval_table
    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Original", "amount": "1"}})
    row = create_resp.json()
    submitted = await _submit(client, ws["id"])

    update_resp = await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}",
        json={"values": {"name": "Edited After Submit"}, "expected_version": row["version"]},
    )
    assert update_resp.status_code == 200

    batches = (await client.get(f"/api/workspaces/{ws['id']}/sync-change-batches")).json()
    assert len(batches) == 1  # not a second batch
    assert batches[0]["id"] == submitted["batch_id"]
    assert len(batches[0]["changes"]) == 1
    assert batches[0]["changes"][0]["values"]["name"] == "Edited After Submit"


async def test_delete_before_insert_submitted_cancels_the_draft(approval_table):
    client, table, ws, _ = approval_table
    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Doomed", "amount": "1"}})
    row = create_resp.json()

    drafts_before = (await client.get(f"/api/workspaces/{ws['id']}/pending-sync-change-drafts")).json()
    assert len(drafts_before) == 1

    delete_resp = await client.delete(f"/api/tables/{table['id']}/rows/{row['row_id']}")
    assert delete_resp.status_code == 204

    drafts_after = (await client.get(f"/api/workspaces/{ws['id']}/pending-sync-change-drafts")).json()
    assert drafts_after == []
    assert await _external_rows() == []  # never reached the external side at all


async def test_delete_after_approved_insert_creates_a_new_draft_delete(approval_table, monkeypatch):
    client, table, ws, _ = approval_table
    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Will Be Deleted", "amount": "1"}})
    row = create_resp.json()
    submitted = await _submit(client, ws["id"])
    batch = await _get_batch(client, ws["id"], submitted["batch_id"])
    await _approve_batch(client, batch["id"], monkeypatch)
    assert any(r["name"] == "Will Be Deleted" for r in await _external_rows())

    delete_resp = await client.delete(f"/api/tables/{table['id']}/rows/{row['row_id']}")
    assert delete_resp.status_code == 204

    drafts = (await client.get(f"/api/workspaces/{ws['id']}/pending-sync-change-drafts")).json()
    assert len(drafts) == 1
    assert drafts[0]["operation"] == "delete"
    assert drafts[0]["external_pk"] is not None
    # Local row is already gone even though the external delete is still
    # only a draft -- local writes are never held back, only the external push is.
    rows_after_local_delete = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert rows_after_local_delete == []
    assert any(r["name"] == "Will Be Deleted" for r in await _external_rows())  # still there externally

    submitted2 = await _submit(client, ws["id"])
    batch2 = await _get_batch(client, ws["id"], submitted2["batch_id"])
    await _approve_batch(client, batch2["id"], monkeypatch)
    assert await _external_rows() == []  # now actually removed


async def test_submit_bundles_multiple_rows_into_one_batch(approval_table, monkeypatch):
    client, table, ws, _ = approval_table
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Row A", "amount": "1"}})
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Row B", "amount": "2"}})
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Row C", "amount": "3"}})

    drafts = (await client.get(f"/api/workspaces/{ws['id']}/pending-sync-change-drafts")).json()
    assert len(drafts) == 3

    submitted = await _submit(client, ws["id"])
    assert submitted["change_count"] == 3

    batches = (await client.get(f"/api/workspaces/{ws['id']}/sync-change-batches")).json()
    assert len(batches) == 1
    assert len(batches[0]["changes"]) == 3

    # Drafts are gone -- everything moved into the one batch.
    drafts_after = (await client.get(f"/api/workspaces/{ws['id']}/pending-sync-change-drafts")).json()
    assert drafts_after == []

    await _approve_batch(client, batches[0]["id"], monkeypatch)
    names = {r["name"] for r in await _external_rows()}
    assert names == {"Row A", "Row B", "Row C"}


async def test_submit_with_no_drafts_is_rejected(approval_table):
    client, table, ws, _ = approval_table
    resp = await client.post(f"/api/workspaces/{ws['id']}/pending-sync-changes/submit")
    assert resp.status_code == 422


async def test_editor_cannot_see_batches_but_can_submit_own_drafts(approval_table, make_client):
    client, table, ws, _ = approval_table

    editor = await make_client()
    await register_user(editor, email=f"appreditor_{uuid.uuid4().hex[:8]}@example.com")
    editor_email = (await editor.get("/api/auth/me")).json()["email"]
    await _invite(client, ws["id"], editor_email, WorkspaceRole.EDITOR)

    create_resp = await editor.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Contested", "amount": "1"}})
    assert create_resp.status_code == 201

    list_resp = await editor.get(f"/api/workspaces/{ws['id']}/sync-change-batches")
    assert list_resp.status_code == 403

    # An editor CAN see and submit their own drafts -- only reviewing what's
    # submitted is admin/owner-only.
    drafts_resp = await editor.get(f"/api/workspaces/{ws['id']}/pending-sync-change-drafts")
    assert drafts_resp.status_code == 200
    assert len(drafts_resp.json()) == 1

    submit_resp = await editor.post(f"/api/workspaces/{ws['id']}/pending-sync-changes/submit")
    assert submit_resp.status_code == 200, submit_resp.text
    batch_id = submit_resp.json()["batch_id"]

    approve_resp = await editor.post(f"/api/sync-change-batches/{batch_id}/approve")
    assert approve_resp.status_code == 403

    reject_resp = await editor.post(f"/api/sync-change-batches/{batch_id}/reject", json={})
    assert reject_resp.status_code == 403


async def test_pending_change_with_a_date_field_does_not_crash(client):
    """Regression: a date/timestamp-typed field's coerced value is a real
    Python date/datetime object (see DateFieldType.to_storage), not a
    string. pending_sync_changes.values is a JSON column -- storing that
    object directly used to blow up with "Object of type date/datetime is
    not JSON serializable" the moment any approval-gated table had a synced
    date column (exactly what every Stage 2 pull-enabled table has, since
    external_updated_at_column is always one)."""
    await _reset_external_table_with_ts("ext_approval_date")
    await register_user(client, email=f"appdate_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, _ = await create_workspace_base_table(client)

    ds_resp = await client.post(
        f"/api/workspaces/{ws['id']}/data-sources",
        data={"name": "ExtApprovalDate", "source_type": "postgres", "config": json.dumps(PG_CONFIG)},
    )
    data_source_id = ds_resp.json()["id"]
    import_resp = await client.post(
        f"/api/bases/{base['id']}/import-from-source/{data_source_id}",
        json={"table_name": "ext_approval_date", "table_schema": "ext_test", "new_table_name": "ApprovalDate", "sync_enabled": True},
    )
    table = import_resp.json()

    gate_resp = await client.patch(f"/api/tables/{table['id']}/sync", json={"sync_enabled": True, "push_requires_approval": True})
    assert gate_resp.status_code == 200, gate_resp.text

    create_resp = await client.post(
        f"/api/tables/{table['id']}/rows", json={"values": {"name": "Has A Date", "amount": "1", "updated_at": "2026-01-01T00:00:00Z"}}
    )
    assert create_resp.status_code == 201, create_resp.text

    drafts = (await client.get(f"/api/workspaces/{ws['id']}/pending-sync-change-drafts")).json()
    assert len(drafts) == 1
    assert drafts[0]["values"]["updated_at"] is not None


async def test_reject_with_restore_on_pending_insert_deletes_the_local_row(approval_table):
    client, table, ws, _ = approval_table
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Never Approved", "amount": "1"}})
    submitted = await _submit(client, ws["id"])
    batch = await _get_batch(client, ws["id"], submitted["batch_id"])
    assert batch["changes"][0]["operation"] == "insert"
    assert batch["changes"][0]["previous_values"] is None  # nothing "before" an insert

    reject_resp = await client.post(f"/api/sync-change-batches/{batch['id']}/reject", json={"restore": True})
    assert reject_resp.status_code == 200, reject_resp.text

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert rows == []  # local creation itself was undone, not just the push


async def test_reject_with_restore_on_pending_update_reverts_local_value(approval_table, monkeypatch):
    client, table, ws, _ = approval_table
    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Original Name", "amount": "1"}})
    row = create_resp.json()
    submitted = await _submit(client, ws["id"])
    batch = await _get_batch(client, ws["id"], submitted["batch_id"])
    await _approve_batch(client, batch["id"], monkeypatch)  # now has a real external_pk

    update_resp = await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}",
        json={"values": {"name": "Edited Name"}, "expected_version": row["version"]},
    )
    assert update_resp.status_code == 200

    submitted2 = await _submit(client, ws["id"])
    batch2 = await _get_batch(client, ws["id"], submitted2["batch_id"])
    assert batch2["changes"][0]["operation"] == "update"
    assert batch2["changes"][0]["previous_values"]["name"] == "Original Name"

    reject_resp = await client.post(f"/api/sync-change-batches/{batch2['id']}/reject", json={"restore": True})
    assert reject_resp.status_code == 200, reject_resp.text

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    current = next(r for r in rows if r["row_id"] == row["row_id"])
    assert current["values"]["name"] == "Original Name"
    # Never pushed externally -- the external record still has whatever the
    # approved insert put there, untouched by either the rejected edit or the restore.
    assert any(r["name"] == "Original Name" for r in await _external_rows())


async def test_reject_with_restore_on_pending_delete_recreates_row_and_relinks(approval_table, monkeypatch):
    client, table, ws, _ = approval_table
    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Almost Deleted", "amount": "1"}})
    row = create_resp.json()
    submitted = await _submit(client, ws["id"])
    batch = await _get_batch(client, ws["id"], submitted["batch_id"])
    await _approve_batch(client, batch["id"], monkeypatch)

    delete_resp = await client.delete(f"/api/tables/{table['id']}/rows/{row['row_id']}")
    assert delete_resp.status_code == 204
    assert (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"] == []

    submitted2 = await _submit(client, ws["id"])
    batch2 = await _get_batch(client, ws["id"], submitted2["batch_id"])
    assert batch2["changes"][0]["operation"] == "delete"
    assert batch2["changes"][0]["previous_values"]["name"] == "Almost Deleted"

    reject_resp = await client.post(f"/api/sync-change-batches/{batch2['id']}/reject", json={"restore": True})
    assert reject_resp.status_code == 200, reject_resp.text

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert len(rows) == 1
    assert rows[0]["values"]["name"] == "Almost Deleted"
    new_row_id = rows[0]["row_id"]

    # Re-linked to the external record it already matches -- a further edit
    # must produce an "update", not a duplicate "insert".
    edit_resp = await client.patch(
        f"/api/tables/{table['id']}/rows/{new_row_id}",
        json={"values": {"name": "Edited After Restore"}, "expected_version": rows[0]["version"]},
    )
    assert edit_resp.status_code == 200
    submitted3 = await _submit(client, ws["id"])
    batch3 = await _get_batch(client, ws["id"], submitted3["batch_id"])
    # "update", not "insert" -- request() only derives "update" when the row's
    # _external_pk column already holds a real value (_current_external_pk),
    # which proves the restore's re-link actually took.
    assert batch3["changes"][0]["operation"] == "update"

    await _approve_batch(client, batch3["id"], monkeypatch)
    external_rows = await _external_rows()
    assert len(external_rows) == 1  # updated in place, not duplicated
    assert external_rows[0]["name"] == "Edited After Restore"


async def test_reject_without_restore_leaves_local_row_untouched(approval_table):
    client, table, ws, _ = approval_table
    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Untouched", "amount": "1"}})
    row = create_resp.json()
    submitted = await _submit(client, ws["id"])

    reject_resp = await client.post(f"/api/sync-change-batches/{submitted['batch_id']}/reject", json={"reason": "no restore wanted"})
    assert reject_resp.status_code == 200, reject_resp.text

    # Default (restore omitted) never touches the local row -- only today's
    # existing behavior (block the push) applies.
    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    current = next(r for r in rows if r["row_id"] == row["row_id"])
    assert current["values"]["name"] == "Untouched"
