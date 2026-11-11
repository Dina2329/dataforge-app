"""Base snapshots -- point-in-time checkpoint + restore. Restore is
implemented as a diff replayed through the ordinary record create/update/
delete methods (see snapshots/service.py's module docstring), so these
tests lean on test_table_sync.py's real-Postgres fixtures to prove that
claim concretely: a restored row on a synced table actually pushes, and on
an approval-gated table actually queues for approval, exactly like a normal
edit would -- not a special-cased "restore" code path that happens to look
similar.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import update

from app.core.db import SessionLocal
from app.modules.connectors.base import TableRef
from app.modules.connectors.types.postgres_connector import PostgresConnector
from app.modules.snapshots.models import BaseSnapshot
from app.modules.workspaces.models import WorkspaceRole
from app.worker.tasks.snapshot_tasks import AUTO_SNAPSHOT_RETENTION_DAYS, tick_daily_snapshots
from app.worker.tasks.sync_tasks import push_record_to_source
from tests.conftest import create_workspace_base_table, register_user
from tests.test_table_sync import PG_CONFIG, _current_user_id, _reset_external_table


async def _invite(owner_client, workspace_id, email, role):
    resp = await owner_client.post(f"/api/workspaces/{workspace_id}/members", json={"email": email, "role": role})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_snapshot_captures_current_rows(client):
    await register_user(client, email=f"snap_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Amount", "field_type": "number", "options": {}})
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Row A", "Amount": "1"}})

    resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={"label": "checkpoint"})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["label"] == "checkpoint"
    assert body["table_count"] == 1

    list_resp = await client.get(f"/api/bases/{base['id']}/snapshots")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1


async def test_default_label_when_none_given(client):
    await register_user(client, email=f"snaplabel_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, _ = await create_workspace_base_table(client)
    resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={})
    assert resp.status_code == 201, resp.text
    assert "Snapshot" in resp.json()["label"]


async def test_restore_reverts_an_update(client):
    await register_user(client, email=f"snaprevert_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Original"}})).json()

    snap_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={"label": "before edit"})
    snapshot_id = snap_resp.json()["id"]

    await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}", json={"values": {"Name": "Changed"}, "expected_version": row["version"]}
    )
    changed = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert changed["values"]["Name"] == "Changed"

    restore_resp = await client.post(f"/api/snapshots/{snapshot_id}/restore")
    assert restore_resp.status_code == 200, restore_resp.text
    result = restore_resp.json()["tables"][0]
    assert result["updated"] == 1
    assert result["created"] == 0 and result["deleted"] == 0

    restored = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert restored["values"]["Name"] == "Original"


async def test_preview_shows_the_same_counts_as_restore_but_changes_nothing(client):
    await register_user(client, email=f"snappreview_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Original"}})).json()

    snap_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={"label": "before edit"})
    snapshot_id = snap_resp.json()["id"]

    await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}", json={"values": {"Name": "Changed"}, "expected_version": row["version"]}
    )

    preview_resp = await client.get(f"/api/snapshots/{snapshot_id}/preview")
    assert preview_resp.status_code == 200, preview_resp.text
    preview_result = preview_resp.json()["tables"][0]
    assert preview_result["updated"] == 1
    assert preview_result["created"] == 0 and preview_result["deleted"] == 0

    # Read-only -- the row must still show the edited value, not the
    # snapshot's, after only previewing.
    still_changed = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert still_changed["values"]["Name"] == "Changed"

    # The real restore now reports the exact same counts the preview did,
    # and this time actually applies them.
    restore_resp = await client.post(f"/api/snapshots/{snapshot_id}/restore")
    restore_result = restore_resp.json()["tables"][0]
    assert restore_result["updated"] == preview_result["updated"] == 1
    restored = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert restored["values"]["Name"] == "Original"


async def test_preview_requires_owner_or_admin(client, make_client):
    await register_user(client, email=f"snappreviewperm_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    snap_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={})
    snapshot_id = snap_resp.json()["id"]

    editor = await make_client()
    await register_user(editor, email=f"snappreviewperm2_{uuid.uuid4().hex[:8]}@example.com")
    editor_email = (await editor.get("/api/auth/me")).json()["email"]
    await _invite(client, ws["id"], editor_email, WorkspaceRole.EDITOR)

    resp = await editor.get(f"/api/snapshots/{snapshot_id}/preview")
    assert resp.status_code == 403


async def test_restore_recreates_a_deleted_row(client):
    await register_user(client, email=f"snaprecreate_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Will Be Deleted"}})).json()

    snap_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={})
    snapshot_id = snap_resp.json()["id"]

    await client.delete(f"/api/tables/{table['id']}/rows/{row['row_id']}")
    assert (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"] == []

    restore_resp = await client.post(f"/api/snapshots/{snapshot_id}/restore")
    result = restore_resp.json()["tables"][0]
    assert result["created"] == 1

    rows_after = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert len(rows_after) == 1
    assert rows_after[0]["values"]["Name"] == "Will Be Deleted"
    # A new row id -- restoring values, not the original internal identity.
    assert rows_after[0]["row_id"] != row["row_id"]


async def test_restore_deletes_a_row_added_after_the_snapshot(client):
    await register_user(client, email=f"snapdelnew_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Kept"}})

    snap_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={})
    snapshot_id = snap_resp.json()["id"]

    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Added After Snapshot"}})
    assert len((await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]) == 2

    restore_resp = await client.post(f"/api/snapshots/{snapshot_id}/restore")
    result = restore_resp.json()["tables"][0]
    assert result["deleted"] == 1

    rows_after = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert [r["values"]["Name"] for r in rows_after] == ["Kept"]


async def test_restore_matches_renamed_field_by_stable_id(client):
    await register_user(client, email=f"snaprename_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Original"}})).json()
    snap_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={})
    snapshot_id = snap_resp.json()["id"]

    fields = (await client.get(f"/api/tables/{table['id']}")).json()["fields"]
    name_field = next(f for f in fields if f["name"] == "Name")
    rename_resp = await client.patch(f"/api/tables/{table['id']}/fields/{name_field['id']}", json={"name": "Renamed"})
    assert rename_resp.status_code == 200, rename_resp.text

    await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}", json={"values": {"Renamed": "Changed"}, "expected_version": row["version"]}
    )

    restore_resp = await client.post(f"/api/snapshots/{snapshot_id}/restore")
    assert restore_resp.json()["tables"][0]["updated"] == 1
    restored = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert restored["values"]["Renamed"] == "Original"


async def test_editor_can_create_but_not_restore_or_delete_snapshot(client, make_client):
    await register_user(client, email=f"snapeditor_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    snap_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={})
    snapshot_id = snap_resp.json()["id"]

    editor = await make_client()
    await register_user(editor, email=f"snapeditor2_{uuid.uuid4().hex[:8]}@example.com")
    editor_email = (await editor.get("/api/auth/me")).json()["email"]
    await _invite(client, ws["id"], editor_email, WorkspaceRole.EDITOR)

    create_resp = await editor.post(f"/api/bases/{base['id']}/snapshots", json={"label": "editor's own"})
    assert create_resp.status_code == 201, create_resp.text

    restore_resp = await editor.post(f"/api/snapshots/{snapshot_id}/restore")
    assert restore_resp.status_code == 403

    delete_resp = await editor.delete(f"/api/snapshots/{snapshot_id}")
    assert delete_resp.status_code == 403


async def test_deleting_snapshot_drops_its_physical_copy(client):
    await register_user(client, email=f"snapdel_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    snap_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={})
    snapshot_id = snap_resp.json()["id"]

    delete_resp = await client.delete(f"/api/snapshots/{snapshot_id}")
    assert delete_resp.status_code == 204

    list_resp = await client.get(f"/api/bases/{base['id']}/snapshots")
    assert list_resp.json() == []
    # Deleted, not just "hidden" -- restoring it now 404s.
    restore_resp = await client.post(f"/api/snapshots/{snapshot_id}/restore")
    assert restore_resp.status_code == 404


class _FakeArqPool:
    def __init__(self):
        self.calls: list[tuple] = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))


async def test_restored_row_on_synced_table_actually_pushes(client, monkeypatch):
    """The whole point of implementing restore as ordinary record edits: a
    reverted row on a synced table goes through the exact same push pipeline
    any other edit would, with no special-cased sync-interaction logic --
    proven by capturing the enqueued job restore's update_record call
    produces and running it for real against the actual external database."""
    await _reset_external_table(PG_CONFIG, "ext_snapshot_sync", dialect="postgres")
    await register_user(client, email=f"snapsync_{uuid.uuid4().hex[:8]}@example.com")
    user_id = await _current_user_id(client)
    ws, base, _ = await create_workspace_base_table(client)

    ds_resp = await client.post(
        f"/api/workspaces/{ws['id']}/data-sources",
        data={"name": "ExtSnapshotSync", "source_type": "postgres", "config": json.dumps(PG_CONFIG)},
    )
    data_source_id = ds_resp.json()["id"]
    import_resp = await client.post(
        f"/api/bases/{base['id']}/import-from-source/{data_source_id}",
        json={"table_name": "ext_snapshot_sync", "table_schema": "ext_test", "new_table_name": "SnapshotSync", "sync_enabled": True},
    )
    table = import_resp.json()

    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Original", "amount": "1"}})
    row = create_resp.json()
    await push_record_to_source({}, table["id"], row["row_id"], "insert", row["values"], user_id)

    snap_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={})
    snapshot_id = snap_resp.json()["id"]

    await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}",
        json={"values": {"name": "Changed"}, "expected_version": row["version"]},
    )

    fake_pool = _FakeArqPool()

    async def fake_get_arq_pool():
        return fake_pool

    monkeypatch.setattr("app.modules.records.service.get_arq_pool", fake_get_arq_pool)

    restore_resp = await client.post(f"/api/snapshots/{snapshot_id}/restore")
    assert restore_resp.status_code == 200, restore_resp.text
    # Two tables in this base -- the default blank one from
    # create_workspace_base_table plus the imported "SnapshotSync" -- so
    # find the one that actually has the row, rather than assuming index 0.
    result = next(t for t in restore_resp.json()["tables"] if t["table_name"] == "SnapshotSync")
    assert result["updated"] == 1

    # The revert enqueued a real push_record_to_source job -- same call the
    # direct-push path already makes for any other edit, not a special case.
    push_calls = [c for c in fake_pool.calls if c[0] == "push_record_to_source"]
    assert len(push_calls) == 1
    _, args, kwargs = push_calls[0]
    await push_record_to_source({}, *args, **kwargs)

    connector = PostgresConnector(PG_CONFIG)
    try:
        rows = [r async for batch in connector.stream_rows(TableRef(name="ext_snapshot_sync", schema="ext_test")) for r in batch]
        assert any(r["name"] == "Original" for r in rows)
    finally:
        await connector.close()


async def test_daily_snapshot_cron_creates_one_per_base(client):
    await register_user(client, email=f"snapcron_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Row"}})

    await tick_daily_snapshots({})

    list_resp = await client.get(f"/api/bases/{base['id']}/snapshots")
    assert list_resp.status_code == 200
    snapshots = list_resp.json()
    assert len(snapshots) == 1
    assert snapshots[0]["is_automatic"] is True


async def test_daily_snapshot_cron_prunes_old_automatic_snapshots(client):
    await register_user(client, email=f"snapprune_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, _ = await create_workspace_base_table(client)

    await tick_daily_snapshots({})
    old_snapshot_id = (await client.get(f"/api/bases/{base['id']}/snapshots")).json()[0]["id"]

    # Backdate it past the retention window -- as if it had been sitting
    # there for AUTO_SNAPSHOT_RETENTION_DAYS + 1 days already.
    async with SessionLocal() as db:
        stale = datetime.now(timezone.utc) - timedelta(days=AUTO_SNAPSHOT_RETENTION_DAYS + 1)
        await db.execute(update(BaseSnapshot).where(BaseSnapshot.id == uuid.UUID(old_snapshot_id)).values(created_at=stale))
        await db.commit()

    await tick_daily_snapshots({})

    snapshots = (await client.get(f"/api/bases/{base['id']}/snapshots")).json()
    # The stale one got pruned; today's fresh automatic snapshot is kept.
    assert len(snapshots) == 1
    assert snapshots[0]["id"] != old_snapshot_id


async def test_manual_snapshot_is_never_pruned_by_the_cron(client):
    await register_user(client, email=f"snapkeep_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, _ = await create_workspace_base_table(client)

    manual_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={"label": "keep me forever"})
    manual_id = manual_resp.json()["id"]

    async with SessionLocal() as db:
        ancient = datetime.now(timezone.utc) - timedelta(days=365)
        await db.execute(update(BaseSnapshot).where(BaseSnapshot.id == uuid.UUID(manual_id)).values(created_at=ancient))
        await db.commit()

    await tick_daily_snapshots({})

    snapshots = (await client.get(f"/api/bases/{base['id']}/snapshots")).json()
    assert any(s["id"] == manual_id for s in snapshots)


async def test_new_base_has_auto_snapshots_enabled_by_default(client):
    await register_user(client, email=f"snapdefault_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, _ = await create_workspace_base_table(client)
    assert base["auto_snapshots_enabled"] is True


async def test_disabling_auto_snapshots_skips_that_base_in_the_cron(client):
    await register_user(client, email=f"snapdisable_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, _ = await create_workspace_base_table(client)

    toggle_resp = await client.patch(f"/api/bases/{base['id']}/snapshots/settings", json={"auto_snapshots_enabled": False})
    assert toggle_resp.status_code == 200, toggle_resp.text
    assert toggle_resp.json()["auto_snapshots_enabled"] is False

    await tick_daily_snapshots({})

    snapshots = (await client.get(f"/api/bases/{base['id']}/snapshots")).json()
    assert snapshots == []

    # Manual snapshots still work regardless of the automatic toggle.
    manual_resp = await client.post(f"/api/bases/{base['id']}/snapshots", json={"label": "still manual"})
    assert manual_resp.status_code == 201, manual_resp.text

    # Flip it back on -- the very next cron run picks the base up again.
    reenable_resp = await client.patch(f"/api/bases/{base['id']}/snapshots/settings", json={"auto_snapshots_enabled": True})
    assert reenable_resp.json()["auto_snapshots_enabled"] is True
    await tick_daily_snapshots({})
    snapshots_after = (await client.get(f"/api/bases/{base['id']}/snapshots")).json()
    assert any(s["is_automatic"] for s in snapshots_after)


async def test_viewer_cannot_toggle_auto_snapshots(client, make_client):
    await register_user(client, email=f"snaptoggleview_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, _ = await create_workspace_base_table(client)

    viewer = await make_client()
    await register_user(viewer, email=f"snaptoggleview2_{uuid.uuid4().hex[:8]}@example.com")
    viewer_email = (await viewer.get("/api/auth/me")).json()["email"]
    await _invite(client, ws["id"], viewer_email, WorkspaceRole.VIEWER)

    resp = await viewer.patch(f"/api/bases/{base['id']}/snapshots/settings", json={"auto_snapshots_enabled": False})
    assert resp.status_code == 403

