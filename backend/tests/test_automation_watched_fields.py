"""watched_fields: an automation's record_updated trigger can be scoped to
only fire when specific columns were part of the write -- distinct from the
existing `filter` config (which checks the row's resulting values, not which
columns a given write touched). No real arq worker runs in tests, so these
patch AutomationService's own `get_arq_pool` with a fake that just records
every enqueue_job call, to assert on the dispatch DECISION itself rather than
running the automation end-to-end (see test_bulk_ops.py's docstring for the
same reasoning applied to a different module)."""

from unittest.mock import AsyncMock

from tests.conftest import create_workspace_base_table, register_user


class _FakePool:
    def __init__(self):
        self.enqueued = []

    async def enqueue_job(self, job_name, *args, **kwargs):
        self.enqueued.append((job_name, args, kwargs))


def _patch_pool(monkeypatch):
    pool = _FakePool()
    monkeypatch.setattr("app.modules.automations.service.get_arq_pool", AsyncMock(return_value=pool))
    return pool


async def test_watched_fields_only_fires_on_matching_column(client, monkeypatch):
    await register_user(client, email="watch1@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Status", "field_type": "text", "options": {}})
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Notes", "field_type": "text", "options": {}})
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Row 1"}})).json()

    automation_resp = await client.post(
        f"/api/tables/{table['id']}/automations",
        json={
            "name": "Status watcher",
            "trigger_type": "record_updated",
            "trigger_config": {"watched_fields": ["Status"]},
        },
    )
    assert automation_resp.status_code == 201, automation_resp.text

    pool = _patch_pool(monkeypatch)

    await client.patch(f"/api/tables/{table['id']}/rows/{row['row_id']}", json={"values": {"Notes": "irrelevant"}, "expected_version": row["version"]})
    assert pool.enqueued == []  # Notes isn't watched -- must not fire

    row = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    await client.patch(f"/api/tables/{table['id']}/rows/{row['row_id']}", json={"values": {"Status": "done"}, "expected_version": row["version"]})
    assert len(pool.enqueued) == 1  # Status is watched -- must fire
    assert pool.enqueued[0][0] == "run_automation"


async def test_no_watched_fields_fires_on_any_change(client, monkeypatch):
    await register_user(client, email="watch2@example.com")
    ws, base, table = await create_workspace_base_table(client)
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Row 1"}})).json()

    await client.post(
        f"/api/tables/{table['id']}/automations",
        json={"name": "Any change", "trigger_type": "record_updated", "trigger_config": {}},
    )

    pool = _patch_pool(monkeypatch)
    await client.patch(f"/api/tables/{table['id']}/rows/{row['row_id']}", json={"values": {"Name": "Row 1 renamed"}, "expected_version": row["version"]})
    assert len(pool.enqueued) == 1


async def test_no_op_write_does_not_fire_automation_even_without_watched_fields(client, monkeypatch):
    # A write that round-trips a field back to its own existing value (e.g. a
    # grid cell clicked into and blurred without being edited) must not count
    # as a "record updated" -- regardless of whether watched_fields is even
    # configured. This is the general case watched_fields' own change
    # detection is built on top of.
    await register_user(client, email="watch7@example.com")
    ws, base, table = await create_workspace_base_table(client)
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Row 1"}})).json()

    await client.post(
        f"/api/tables/{table['id']}/automations",
        json={"name": "Any change", "trigger_type": "record_updated", "trigger_config": {}},
    )

    pool = _patch_pool(monkeypatch)
    resp = await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}", json={"values": {"Name": "Row 1"}, "expected_version": row["version"]}
    )
    assert resp.status_code == 200
    assert pool.enqueued == []  # same value written back -- nothing actually changed


async def test_watched_fields_rejected_for_non_record_updated_trigger(client):
    await register_user(client, email="watch3@example.com")
    ws, base, table = await create_workspace_base_table(client)

    resp = await client.post(
        f"/api/tables/{table['id']}/automations",
        json={"name": "Bad", "trigger_type": "record_created", "trigger_config": {"watched_fields": ["Name"]}},
    )
    assert resp.status_code == 422


async def test_watched_fields_rejected_for_unknown_field(client):
    await register_user(client, email="watch4@example.com")
    ws, base, table = await create_workspace_base_table(client)

    resp = await client.post(
        f"/api/tables/{table['id']}/automations",
        json={"name": "Bad", "trigger_type": "record_updated", "trigger_config": {"watched_fields": ["Nonexistent"]}},
    )
    assert resp.status_code == 422


async def test_watched_fields_rejected_for_virtual_field(client):
    await register_user(client, email="watch5@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Price", "field_type": "number", "options": {}})
    formula_resp = await client.post(
        f"/api/tables/{table['id']}/fields",
        json={"name": "Total", "field_type": "formula", "options": {"expression": "{Price}"}},
    )
    assert formula_resp.status_code == 201, formula_resp.text

    resp = await client.post(
        f"/api/tables/{table['id']}/automations",
        json={"name": "Bad", "trigger_type": "record_updated", "trigger_config": {"watched_fields": ["Total"]}},
    )
    assert resp.status_code == 422


async def test_watched_fields_editable_via_update(client, monkeypatch):
    await register_user(client, email="watch6@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Status", "field_type": "text", "options": {}})
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Row 1"}})).json()

    automation = (
        await client.post(
            f"/api/tables/{table['id']}/automations",
            json={"name": "Watcher", "trigger_type": "record_updated", "trigger_config": {}},
        )
    ).json()

    patch = await client.patch(f"/api/automations/{automation['id']}", json={"trigger_config": {"watched_fields": ["Status"]}})
    assert patch.status_code == 200, patch.text
    assert patch.json()["trigger_config"]["watched_fields"] == ["Status"]

    pool = _patch_pool(monkeypatch)
    await client.patch(f"/api/tables/{table['id']}/rows/{row['row_id']}", json={"values": {"Name": "renamed"}, "expected_version": row["version"]})
    assert pool.enqueued == []  # Name isn't watched anymore
