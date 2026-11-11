"""Audit log: record mutations carry a human-readable resource_label
("Row #<id> in <table name>") so "who changed which row" is answerable
straight from the audit feed, not just a bare row_id. record.created's
audit write goes through the real arq queue (log_deferred) -- nothing
drains that queue in tests, so this patches get_arq_pool to run the write
inline instead (same reasoning as every other *_tasks.py test in this
suite that awaits the worker function directly rather than via Redis)."""

from app.worker.tasks.audit_tasks import write_audit_log_entry
from tests.conftest import create_workspace_base_table, register_user


class _ImmediateArqPool:
    async def enqueue_job(self, name, **kwargs):
        assert name == "write_audit_log_entry"
        await write_audit_log_entry({}, **kwargs)


async def _use_immediate_arq(monkeypatch):
    async def _fake_get_arq_pool():
        return _ImmediateArqPool()

    monkeypatch.setattr("app.worker.arq_app.get_arq_pool", _fake_get_arq_pool)


async def test_record_mutations_log_resource_label_and_changed_fields(client, monkeypatch):
    await _use_immediate_arq(monkeypatch)
    await register_user(client, email="audit1@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Name2", "field_type": "text", "options": {}})

    created = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name2": "first"}})).json()
    row_id = created["row_id"]

    await client.patch(f"/api/tables/{table['id']}/rows/{row_id}", json={"values": {"Name2": "second"}, "expected_version": 1})
    await client.delete(f"/api/tables/{table['id']}/rows/{row_id}")

    entries = (await client.get(f"/api/workspaces/{ws['id']}/audit-log?resource_type=record")).json()
    by_action = {e["action"]: e for e in entries}

    assert by_action["record.created"]["resource_label"] == f"Row #{row_id} in {table['name']}"
    assert by_action["record.created"]["resource_id"] == str(row_id)

    assert by_action["record.updated"]["resource_label"] == f"Row #{row_id} in {table['name']}"
    assert by_action["record.updated"]["details"]["changed_fields"] == ["Name2"]

    assert by_action["record.deleted"]["resource_label"] == f"Row #{row_id} in {table['name']}"
