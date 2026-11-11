from unittest.mock import AsyncMock

import httpx

from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import create_workspace_base_table, register_user


async def _add_member(client, workspace_id: str, make_client, role, email):
    member = await make_client()
    await register_user(member, email=email)
    await client.post(f"/api/workspaces/{workspace_id}/members", json={"email": email, "role": role})
    return member


async def _setup_table_with_status_field(client):
    ws, base, table = await create_workspace_base_table(client)
    status_field = (
        await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Submitted At", "field_type": "text", "options": {}})
    ).json()
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Row 1"}})).json()
    return ws, base, table, status_field, row


async def test_submit_config_round_trips(client):
    await register_user(client, email="submit1@example.com")
    ws, base, table, status_field, row = await _setup_table_with_status_field(client)

    put = await client.put(
        f"/api/tables/{table['id']}/submit-config",
        json={"url": "https://example.com/hook", "headers": {"X-Key": "abc"}, "status_field_id": status_field["id"]},
    )
    assert put.status_code == 200, put.text
    assert put.json()["url"] == "https://example.com/hook"

    get = await client.get(f"/api/tables/{table['id']}/submit-config")
    assert get.status_code == 200
    assert get.json()["status_field_id"] == status_field["id"]


async def test_submit_config_rejects_status_field_from_another_table(client):
    await register_user(client, email="submit2@example.com")
    ws, base, table, status_field, row = await _setup_table_with_status_field(client)
    other_table = (await client.post(f"/api/bases/{base['id']}/tables", json={"name": "Other"})).json()
    other_field = (await client.post(f"/api/tables/{other_table['id']}/fields", json={"name": "F", "field_type": "text", "options": {}})).json()

    resp = await client.put(
        f"/api/tables/{table['id']}/submit-config",
        json={"url": "https://example.com/hook", "status_field_id": other_field["id"]},
    )
    assert resp.status_code == 422


async def test_submit_config_rejects_virtual_status_field(client):
    await register_user(client, email="submit3@example.com")
    ws, base, table, status_field, row = await _setup_table_with_status_field(client)
    link_field = (
        await client.post(
            f"/api/tables/{table['id']}/fields",
            json={"name": "Link", "field_type": "link_to_record", "options": {"target_table_id": table["id"]}},
        )
    ).json()

    resp = await client.put(
        f"/api/tables/{table['id']}/submit-config",
        json={"url": "https://example.com/hook", "status_field_id": link_field["id"]},
    )
    assert resp.status_code == 422


async def test_submit_row_posts_full_values_and_stamps_status_field(client, monkeypatch):
    await register_user(client, email="submit4@example.com")
    ws, base, table, status_field, row = await _setup_table_with_status_field(client)
    await client.put(
        f"/api/tables/{table['id']}/submit-config",
        json={"url": "https://example.com/hook", "status_field_id": status_field["id"]},
    )

    mock_post = AsyncMock(return_value=None)
    monkeypatch.setattr("app.modules.record_submit.service.post_json", mock_post)

    resp = await client.post(f"/api/tables/{table['id']}/rows/{row['row_id']}/submit")
    assert resp.status_code == 200, resp.text

    mock_post.assert_awaited_once()
    call_args = mock_post.call_args
    assert call_args.args[0] == "https://example.com/hook"
    assert call_args.args[2]["values"]["Name"] == "Row 1"

    body = resp.json()
    assert body["values"]["Submitted At"]  # stamped, non-empty

    refetched = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert refetched["values"]["Submitted At"] == body["values"]["Submitted At"]


async def test_submit_row_failure_does_not_stamp_status_field(client, monkeypatch):
    await register_user(client, email="submit5@example.com")
    ws, base, table, status_field, row = await _setup_table_with_status_field(client)
    await client.put(
        f"/api/tables/{table['id']}/submit-config",
        json={"url": "https://example.com/hook", "status_field_id": status_field["id"]},
    )

    mock_post = AsyncMock(side_effect=httpx.ConnectError("boom"))
    monkeypatch.setattr("app.modules.record_submit.service.post_json", mock_post)

    resp = await client.post(f"/api/tables/{table['id']}/rows/{row['row_id']}/submit")
    assert resp.status_code == 502

    refetched = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert refetched["values"]["Submitted At"] in (None, "")


async def test_submit_row_without_config_is_rejected(client):
    await register_user(client, email="submit6@example.com")
    ws, base, table = await create_workspace_base_table(client)
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Name": "Row 1"}})).json()

    resp = await client.post(f"/api/tables/{table['id']}/rows/{row['row_id']}/submit")
    assert resp.status_code == 422


async def test_viewer_cannot_submit_row_only_editor_or_above_can_set_config(client, make_client):
    await register_user(client, email="submit7@example.com")
    ws, base, table, status_field, row = await _setup_table_with_status_field(client)
    viewer = await _add_member(client, ws["id"], make_client, WorkspaceRole.VIEWER, "submit7-viewer@example.com")

    config_resp = await viewer.put(
        f"/api/tables/{table['id']}/submit-config",
        json={"url": "https://example.com/hook", "status_field_id": status_field["id"]},
    )
    assert config_resp.status_code == 403

    await client.put(
        f"/api/tables/{table['id']}/submit-config",
        json={"url": "https://example.com/hook", "status_field_id": status_field["id"]},
    )
    submit_resp = await viewer.post(f"/api/tables/{table['id']}/rows/{row['row_id']}/submit")
    assert submit_resp.status_code == 403


async def test_submit_row_real_connection_failure_returns_502_not_an_unhandled_error(client):
    # Regression: post_json retries transient failures itself (tenacity) and
    # raises RetryError (wrapping the real httpx exception) once exhausted,
    # not that exception directly -- a narrower except that only catches
    # httpx.* would let this escape unhandled instead of as a clean 502.
    # Deliberately NOT mocking post_json here, unlike the test above, so the
    # real tenacity retry/RetryError path actually runs.
    await register_user(client, email="submit6@example.com")
    ws, base, table, status_field, row = await _setup_table_with_status_field(client)
    await client.put(
        f"/api/tables/{table['id']}/submit-config",
        json={"url": "http://127.0.0.1:1/unreachable", "status_field_id": status_field["id"]},
    )

    resp = await client.post(f"/api/tables/{table['id']}/rows/{row['row_id']}/submit")
    assert resp.status_code == 502, resp.text
