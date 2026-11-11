from httpx import AsyncClient

from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import create_workspace_base_table, register_user


async def _add_attachment_field(client: AsyncClient, table_id: str) -> str:
    resp = await client.post(f"/api/tables/{table_id}/fields", json={"name": "Files", "field_type": "attachment", "options": {}})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_upload_appends_descriptor_to_row(client):
    await register_user(client, email="att1@example.com")
    ws, base, table = await create_workspace_base_table(client)
    field_id = await _add_attachment_field(client, table["id"])
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {}})).json()

    upload = await client.post(
        f"/api/tables/{table['id']}/rows/{row['row_id']}/fields/{field_id}/attachments",
        files={"file": ("hello.txt", b"hello world", "text/plain")},
    )
    assert upload.status_code == 201, upload.text
    files = upload.json()["values"]["Files"]
    assert len(files) == 1
    assert files[0]["filename"] == "hello.txt"
    assert files[0]["size"] == len(b"hello world")
    assert files[0]["content_type"] == "text/plain"
    assert "id" in files[0]
    assert "storage_key" not in files[0]  # internal storage path never echoed back to the client


async def test_download_returns_original_bytes(client):
    await register_user(client, email="att2@example.com")
    ws, base, table = await create_workspace_base_table(client)
    field_id = await _add_attachment_field(client, table["id"])
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {}})).json()

    upload = await client.post(
        f"/api/tables/{table['id']}/rows/{row['row_id']}/fields/{field_id}/attachments",
        files={"file": ("report.csv", b"a,b,c\n1,2,3", "text/csv")},
    )
    attachment_id = upload.json()["values"]["Files"][0]["id"]

    download = await client.get(
        f"/api/tables/{table['id']}/rows/{row['row_id']}/fields/{field_id}/attachments/{attachment_id}/download"
    )
    assert download.status_code == 200
    assert download.content == b"a,b,c\n1,2,3"
    assert 'filename="report.csv"' in download.headers["content-disposition"]


async def test_multiple_uploads_accumulate_and_delete_removes_one(client):
    await register_user(client, email="att3@example.com")
    ws, base, table = await create_workspace_base_table(client)
    field_id = await _add_attachment_field(client, table["id"])
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {}})).json()

    upload_url = f"/api/tables/{table['id']}/rows/{row['row_id']}/fields/{field_id}/attachments"
    r1 = await client.post(upload_url, files={"file": ("one.txt", b"1", "text/plain")})
    r2 = await client.post(upload_url, files={"file": ("two.txt", b"22", "text/plain")})
    files_after_two = r2.json()["values"]["Files"]
    assert len(files_after_two) == 2
    assert sorted(f["filename"] for f in files_after_two) == ["one.txt", "two.txt"]

    first_id = r1.json()["values"]["Files"][0]["id"]
    delete_resp = await client.delete(f"{upload_url}/{first_id}")
    assert delete_resp.status_code == 200
    remaining = delete_resp.json()["values"]["Files"]
    assert len(remaining) == 1
    assert remaining[0]["filename"] == "two.txt"

    # The deleted attachment's bytes are actually gone from storage, not just
    # unlinked from the row -- downloading it should now 404.
    redownload = await client.get(f"{upload_url}/{first_id}/download")
    assert redownload.status_code == 404


async def test_upload_bumps_row_version(client):
    await register_user(client, email="att4@example.com")
    ws, base, table = await create_workspace_base_table(client)
    field_id = await _add_attachment_field(client, table["id"])
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {}})).json()
    assert row["version"] == 1

    upload = await client.post(
        f"/api/tables/{table['id']}/rows/{row['row_id']}/fields/{field_id}/attachments",
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    assert upload.json()["version"] == 2


async def test_upload_rejects_non_attachment_field(client):
    await register_user(client, email="att5@example.com")
    ws, base, table = await create_workspace_base_table(client)
    text_field = (await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Title", "field_type": "text", "options": {}})).json()
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {}})).json()

    resp = await client.post(
        f"/api/tables/{table['id']}/rows/{row['row_id']}/fields/{text_field['id']}/attachments",
        files={"file": ("x.txt", b"x", "text/plain")},
    )
    assert resp.status_code == 422


async def test_viewer_can_download_but_not_upload(client, make_client):
    await register_user(client, email="att6@example.com")
    ws, base, table = await create_workspace_base_table(client)
    field_id = await _add_attachment_field(client, table["id"])
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {}})).json()
    upload_url = f"/api/tables/{table['id']}/rows/{row['row_id']}/fields/{field_id}/attachments"
    uploaded = await client.post(upload_url, files={"file": ("shared.txt", b"shared", "text/plain")})
    attachment_id = uploaded.json()["values"]["Files"][0]["id"]

    viewer = await make_client()
    await register_user(viewer, email="att6-viewer@example.com")
    await client.post(f"/api/workspaces/{ws['id']}/members", json={"email": "att6-viewer@example.com", "role": WorkspaceRole.VIEWER})

    download = await viewer.get(f"{upload_url}/{attachment_id}/download")
    assert download.status_code == 200
    assert download.content == b"shared"

    blocked_upload = await viewer.post(upload_url, files={"file": ("nope.txt", b"nope", "text/plain")})
    assert blocked_upload.status_code == 403
