"""Batch Submit: config validation (a valid filter condition is required,
URL/batch size bounds), idempotent-active-job lock (one batch send per
table at a time), the worker's chunking into batch_size-sized POSTs with
per-batch results (success, keep-going-on-failure, total failure), and
permissions (SCHEMA_WRITE for config, RECORD_WRITE for triggering a send).

No real arq worker runs in tests -- enqueue_job itself still goes to a real
Redis (tests/conftest.py's REDIS_URL), same as every other job-creating
endpoint; nothing ever drains that queue in tests, so the worker task is
imported and awaited directly instead (see test_bulk_ops.py's docstring for
the same reasoning applied to bulk_ops)."""

from unittest.mock import AsyncMock

import httpx

from app.modules.workspaces.models import WorkspaceRole
from app.worker.tasks.batch_submit_tasks import run_batch_submit_job
from tests.conftest import create_workspace_base_table, register_user


async def _add_member(client, workspace_id: str, make_client, role, email):
    member = await make_client()
    await register_user(member, email=email)
    await client.post(f"/api/workspaces/{workspace_id}/members", json={"email": email, "role": role})
    return member


READY_FILTER = {"kind": "condition", "field": "Ready", "operator": "eq", "value": True}


async def _setup(client, *, email: str):
    await register_user(client, email=email)
    ws, base, table = await create_workspace_base_table(client)
    marker_field = (
        await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Ready", "field_type": "boolean", "options": {}})
    ).json()
    text_field = (
        await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Label", "field_type": "text", "options": {}})
    ).json()

    config = await client.put(
        f"/api/tables/{table['id']}/batch-submit-config",
        json={"url": "https://example.com/batch", "filter": READY_FILTER, "batch_size": 10},
    )
    assert config.status_code == 200, config.text
    return ws, base, table, marker_field, text_field


async def _mark_rows(client, table_id: str, count: int) -> list[int]:
    row_ids = []
    for i in range(count):
        resp = await client.post(f"/api/tables/{table_id}/rows", json={"values": {"Ready": True, "Label": f"row{i}"}})
        row_ids.append(resp.json()["row_id"])
    return row_ids


async def test_config_rejects_unknown_filter_field_bad_url_and_bad_batch_size(client):
    await register_user(client, email="batch1@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Ready", "field_type": "boolean", "options": {}})

    unknown_field = await client.put(
        f"/api/tables/{table['id']}/batch-submit-config",
        json={"url": "https://example.com/batch", "filter": {"kind": "condition", "field": "NotAField", "operator": "eq", "value": True}, "batch_size": 10},
    )
    assert unknown_field.status_code == 422, unknown_field.text

    bad_url = await client.put(
        f"/api/tables/{table['id']}/batch-submit-config",
        json={"url": "not-a-url", "filter": READY_FILTER, "batch_size": 10},
    )
    assert bad_url.status_code == 422, bad_url.text

    bad_batch_size = await client.put(
        f"/api/tables/{table['id']}/batch-submit-config",
        json={"url": "https://example.com/batch", "filter": READY_FILTER, "batch_size": 0},
    )
    assert bad_batch_size.status_code == 422, bad_batch_size.text


async def test_create_job_rejects_when_nothing_marked(client):
    ws, base, table, marker_field, text_field = await _setup(client, email="batch2@example.com")
    resp = await client.post(f"/api/tables/{table['id']}/batch-submit-jobs")
    assert resp.status_code == 422, resp.text


async def test_create_job_blocks_second_active_job_for_same_table(client):
    ws, base, table, marker_field, text_field = await _setup(client, email="batch3@example.com")
    await _mark_rows(client, table["id"], 3)

    first = await client.post(f"/api/tables/{table['id']}/batch-submit-jobs")
    assert first.status_code == 202, first.text
    assert first.json()["status"] == "queued"

    second = await client.post(f"/api/tables/{table['id']}/batch-submit-jobs")
    assert second.status_code == 409, second.text


async def test_worker_sends_all_rows_in_batches_of_configured_size(client, monkeypatch):
    ws, base, table, marker_field, text_field = await _setup(client, email="batch4@example.com")
    row_ids = await _mark_rows(client, table["id"], 25)  # batch_size=10 -> 3 batches: 10, 10, 5

    job = (await client.post(f"/api/tables/{table['id']}/batch-submit-jobs")).json()
    assert job["total_rows"] == 25
    assert job["total_batches"] == 3

    mock_post = AsyncMock(return_value=None)
    monkeypatch.setattr("app.worker.tasks.batch_submit_tasks.post_json", mock_post)
    await run_batch_submit_job({}, job["id"])

    refetched = (await client.get(f"/api/batch-submit-jobs/{job['id']}")).json()
    assert refetched["status"] == "completed"
    assert refetched["sent_batches"] == 3
    assert refetched["failed_batches"] == 0
    assert mock_post.call_count == 3
    assert [len(b["row_ids"]) for b in refetched["batch_results"]] == [10, 10, 5]
    all_sent_row_ids = {rid for b in refetched["batch_results"] for rid in b["row_ids"]}
    assert all_sent_row_ids == set(row_ids)
    assert all(b["status"] == "sent" for b in refetched["batch_results"])

    # Payload shape sent to the external API.
    first_call_payload = mock_post.call_args_list[0].args[2]
    assert first_call_payload["table_id"] == table["id"]
    assert first_call_payload["batch_index"] == 0
    assert len(first_call_payload["rows"]) == 10
    assert "row_id" in first_call_payload["rows"][0]
    assert first_call_payload["rows"][0]["values"]["Label"] in {f"row{i}" for i in range(25)}

    # By design, rows are NOT auto-cleared after a successful send.
    rows_after = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert all(r["values"]["Ready"] is True for r in rows_after)


async def test_worker_keeps_going_after_one_batch_fails(client, monkeypatch):
    ws, base, table, marker_field, text_field = await _setup(client, email="batch5@example.com")
    await _mark_rows(client, table["id"], 20)  # 2 batches of 10

    job = (await client.post(f"/api/tables/{table['id']}/batch-submit-jobs")).json()

    calls = []

    async def _flaky_post(url, headers, payload):
        calls.append(payload["batch_index"])
        if payload["batch_index"] == 0:
            raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.worker.tasks.batch_submit_tasks.post_json", _flaky_post)
    await run_batch_submit_job({}, job["id"])

    refetched = (await client.get(f"/api/batch-submit-jobs/{job['id']}")).json()
    assert refetched["status"] == "partially_failed"
    assert refetched["sent_batches"] == 1
    assert refetched["failed_batches"] == 1
    # Both batches were attempted -- the first batch's failure did not stop the second.
    assert calls == [0, 1]
    results_by_index = {b["batch_index"]: b for b in refetched["batch_results"]}
    assert results_by_index[0]["status"] == "failed"
    assert "boom" in results_by_index[0]["error"]
    assert results_by_index[1]["status"] == "sent"


async def test_worker_marks_failed_when_every_batch_fails(client, monkeypatch):
    ws, base, table, marker_field, text_field = await _setup(client, email="batch6@example.com")
    await _mark_rows(client, table["id"], 5)

    job = (await client.post(f"/api/tables/{table['id']}/batch-submit-jobs")).json()
    mock_post = AsyncMock(side_effect=httpx.ConnectError("down"))
    monkeypatch.setattr("app.worker.tasks.batch_submit_tasks.post_json", mock_post)
    await run_batch_submit_job({}, job["id"])

    refetched = (await client.get(f"/api/batch-submit-jobs/{job['id']}")).json()
    assert refetched["status"] == "failed"
    assert refetched["sent_batches"] == 0
    assert refetched["failed_batches"] == 1

    # A terminal job unblocks creating a new one for the same table.
    retry = await client.post(f"/api/tables/{table['id']}/batch-submit-jobs")
    assert retry.status_code == 202, retry.text


async def test_viewer_cannot_configure_or_trigger_but_editor_can(client, make_client):
    ws, base, table, marker_field, text_field = await _setup(client, email="batch7@example.com")
    viewer = await _add_member(client, ws["id"], make_client, WorkspaceRole.VIEWER, "batch7-viewer@example.com")
    editor = await _add_member(client, ws["id"], make_client, WorkspaceRole.EDITOR, "batch7-editor@example.com")

    viewer_config = await viewer.put(
        f"/api/tables/{table['id']}/batch-submit-config",
        json={"url": "https://example.com/batch", "filter": READY_FILTER, "batch_size": 10},
    )
    assert viewer_config.status_code == 403

    await _mark_rows(client, table["id"], 2)
    viewer_job = await viewer.post(f"/api/tables/{table['id']}/batch-submit-jobs")
    assert viewer_job.status_code == 403

    editor_job = await editor.post(f"/api/tables/{table['id']}/batch-submit-jobs")
    assert editor_job.status_code == 202, editor_job.text


async def test_dismiss_only_allowed_once_terminal(client, monkeypatch):
    ws, base, table, marker_field, text_field = await _setup(client, email="batch8@example.com")
    await _mark_rows(client, table["id"], 2)
    job = (await client.post(f"/api/tables/{table['id']}/batch-submit-jobs")).json()

    still_queued = await client.post(f"/api/batch-submit-jobs/{job['id']}/dismiss")
    assert still_queued.status_code == 422, still_queued.text

    monkeypatch.setattr("app.worker.tasks.batch_submit_tasks.post_json", AsyncMock(return_value=None))
    await run_batch_submit_job({}, job["id"])

    now_terminal = await client.post(f"/api/batch-submit-jobs/{job['id']}/dismiss")
    assert now_terminal.status_code == 204, now_terminal.text


async def test_preview_counts_marked_rows_without_creating_a_job(client):
    ws, base, table, marker_field, text_field = await _setup(client, email="batch9@example.com")
    await _mark_rows(client, table["id"], 23)  # batch_size=10 -> 3 batches

    preview = (await client.get(f"/api/tables/{table['id']}/batch-submit-preview")).json()
    assert preview == {"matched_count": 23, "batch_size": 10, "total_batches": 3}

    # Purely read-only -- no job was created by calling preview.
    jobs = (await client.get(f"/api/tables/{table['id']}/batch-submit-jobs")).json()
    assert jobs == []


async def test_worker_real_connection_failure_still_records_batch_results(client):
    # Regression: post_json retries transient failures itself (tenacity) and
    # raises RetryError (wrapping the real httpx exception) once exhausted,
    # not that exception directly -- a narrower except that only catches
    # httpx.* would let this escape the per-batch try/except, fail the WHOLE
    # job, and leave batch_results empty, losing every batch's outcome, not
    # just the failed one. Deliberately NOT mocking post_json here, unlike
    # the other worker tests above, so the real tenacity retry/RetryError
    # path actually runs.
    ws, base, table, marker_field, text_field = await _setup(client, email="batch10@example.com")
    await client.put(
        f"/api/tables/{table['id']}/batch-submit-config",
        json={"url": "http://127.0.0.1:1/unreachable", "filter": READY_FILTER, "batch_size": 10},
    )
    await _mark_rows(client, table["id"], 5)

    job = (await client.post(f"/api/tables/{table['id']}/batch-submit-jobs")).json()
    await run_batch_submit_job({}, job["id"])

    refetched = (await client.get(f"/api/batch-submit-jobs/{job['id']}")).json()
    assert refetched["status"] == "failed"
    assert refetched["sent_batches"] == 0
    assert refetched["failed_batches"] == 1
    assert len(refetched["batch_results"]) == 1
    assert refetched["batch_results"][0]["status"] == "failed"
