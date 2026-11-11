"""Missing Terms Check: prerequest admin gating, gap detection (normalization,
scope, duplicate-prerequest-row, active-job exclusion), idempotent job
creation, the worker task's success/partial/failure paths (including the
notification each terminal state posts), retry, import (column selection,
no main-table duplicate check at all -- only re-importing the identical
job+candidate twice is blocked), and the manual-insert bypass (which does
still duplicate-check, separately from import).
No real arq worker runs in tests -- enqueue_job itself still goes to a real
Redis (tests/conftest.py's REDIS_URL), same as every other job-creating
endpoint; nothing ever drains that queue in tests, so the worker task is
imported and awaited directly instead (see test_bulk_ops.py's docstring for
the same reasoning applied to bulk_ops).
"""

from unittest.mock import AsyncMock

import httpx

from app.modules.workspaces.models import WorkspaceRole
from app.worker.tasks.missing_terms_tasks import run_missing_terms_job
from tests.conftest import create_workspace_base_table, register_user

PREREQUEST_CSV = (
    "Estate,Building,Unit,Sub-Domain,Term Name\n"
    "E1,B1,U1,Alterations,Building Construction Date\n"
    "E1,B1,U1,Alterations,Last Refurbishment Date\n"
    "E1,B1,U1,Component,No. Loading Doors\n"
    "E1,B1,U1,Component,No. Loading Doors\n"  # duplicate prerequest row, on purpose
    ",,, ,  \n"  # blank sub_domain/term_name -- must be skipped, not kept as an empty row
)


async def _add_member(client, workspace_id: str, make_client, role, email):
    member = await make_client()
    await register_user(member, email=email)
    await client.post(f"/api/workspaces/{workspace_id}/members", json={"email": email, "role": role})
    return member


async def _add_text_field(client, table_id: str, name: str) -> dict:
    resp = await client.post(f"/api/tables/{table_id}/fields", json={"name": name, "field_type": "text", "options": {}})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _setup(client, *, email: str, upload_csv: str = PREREQUEST_CSV):
    await register_user(client, email=email)
    ws, base, table = await create_workspace_base_table(client)
    sub_field = await _add_text_field(client, table["id"], "SubDomain")
    term_field = await _add_text_field(client, table["id"], "TermName")
    page_field = await _add_text_field(client, table["id"], "Page")
    pdf_field = await _add_text_field(client, table["id"], "PdfImage")
    keywords_field = await _add_text_field(client, table["id"], "Keywords")

    upload = await client.put(f"/api/workspaces/{ws['id']}/prerequest", files={"file": ("prerequest.csv", upload_csv, "text/csv")})
    assert upload.status_code == 200, upload.text

    config = await client.put(
        f"/api/tables/{table['id']}/missing-terms-config",
        json={
            "field_mapping": {
                "sub_domain": sub_field["id"],
                "term_name": term_field["id"],
                "page": page_field["id"],
                "pdf_image": pdf_field["id"],
                "keywords": keywords_field["id"],
            }
        },
    )
    assert config.status_code == 200, config.text

    api_config = await client.put(f"/api/workspaces/{ws['id']}/missing-terms-api-config", json={"api_url": "https://example.com/missing-terms-lookup"})
    assert api_config.status_code == 200, api_config.text
    return ws, base, table


async def test_prerequest_replace_parses_and_dedupes_summary(client):
    ws, base, table = await _setup(client, email="mt1@example.com")
    get = await client.get(f"/api/workspaces/{ws['id']}/prerequest")
    assert get.status_code == 200
    assert get.json()["row_count"] == 4  # 4 valid rows, the blank row dropped

    resp = await client.get(f"/api/tables/{table['id']}/missing-terms")
    assert resp.status_code == 200, resp.text
    summary = resp.json()["summary"]
    assert summary["total"] == 4
    assert summary["missing"] == 4  # main table is empty -- nothing matched yet


async def test_prerequest_accepts_underscore_and_space_header_variants(client):
    await register_user(client, email="mt1b@example.com")
    ws, base, table = await create_workspace_base_table(client)
    csv_text = "sub_domain,term_name\nAlterations,Building Construction Date\n"
    upload = await client.put(f"/api/workspaces/{ws['id']}/prerequest", files={"file": ("p.csv", csv_text, "text/csv")})
    assert upload.status_code == 200, upload.text
    assert upload.json()["row_count"] == 1


async def test_viewer_cannot_manage_prerequest_but_editor_can_configure_table(client, make_client):
    ws, base, table = await _setup(client, email="mt2@example.com")
    viewer = await _add_member(client, ws["id"], make_client, WorkspaceRole.VIEWER, "mt2-viewer@example.com")
    editor = await _add_member(client, ws["id"], make_client, WorkspaceRole.EDITOR, "mt2-editor@example.com")

    viewer_upload = await viewer.put(f"/api/workspaces/{ws['id']}/prerequest", files={"file": ("p.csv", PREREQUEST_CSV, "text/csv")})
    assert viewer_upload.status_code == 403
    editor_upload = await editor.put(f"/api/workspaces/{ws['id']}/prerequest", files={"file": ("p.csv", PREREQUEST_CSV, "text/csv")})
    assert editor_upload.status_code == 403

    # Table-level config only needs SCHEMA_WRITE, which editor has.
    editor_config = await editor.get(f"/api/tables/{table['id']}/missing-terms-config")
    assert editor_config.status_code == 200


async def test_gap_detection_normalizes_and_respects_scope(client):
    ws, base, table = await _setup(client, email="mt3@example.com")

    # Main table already has one matching row -- different case/whitespace,
    # must still count as matched.
    await client.post(
        f"/api/tables/{table['id']}/rows", json={"values": {"SubDomain": "  alterations ", "TermName": "building construction date"}}
    )

    resp = await client.get(f"/api/tables/{table['id']}/missing-terms")
    body = resp.json()
    assert body["summary"]["matched"] == 1
    assert body["summary"]["missing"] == 3
    remaining = {(r["sub_domain"], r["term_name"]) for r in body["rows"]}
    assert ("Alterations", "Building Construction Date") not in remaining
    assert ("Alterations", "Last Refurbishment Date") in remaining

    # Now scope the table to a different Estate than the prerequest has --
    # nothing should match at all.
    await client.put(f"/api/tables/{table['id']}/missing-terms-config", json={"estate": "E2", "field_mapping": (await client.get(f"/api/tables/{table['id']}/missing-terms-config")).json()["field_mapping"]})
    scoped = (await client.get(f"/api/tables/{table['id']}/missing-terms")).json()
    assert scoped["summary"]["total"] == 0


async def test_scope_fallback_applies_when_prerequest_row_has_no_scope_of_its_own(client):
    # This prerequest CSV never had Estate/Building/Unit columns at all --
    # every row's scope fields are null. A table scoped to "Dagenham"/"5"
    # must still see these as missing (not zero them out), and the response
    # should carry the table's own scope as a fallback tag per row.
    csv_no_scope = "sub_domain,term_name\nAlterations,Building Construction Date\nAlterations,Last Refurbishment Date\n"
    ws, base, table = await _setup(client, email="mt3c@example.com", upload_csv=csv_no_scope)

    await client.put(
        f"/api/tables/{table['id']}/missing-terms-config",
        json={"estate": "Dagenham", "unit": "5", "field_mapping": (await client.get(f"/api/tables/{table['id']}/missing-terms-config")).json()["field_mapping"]},
    )

    scoped = (await client.get(f"/api/tables/{table['id']}/missing-terms")).json()
    assert scoped["summary"]["total"] == 2
    assert scoped["summary"]["missing"] == 2
    row = next(r for r in scoped["rows"] if r["term_name"] == "Last Refurbishment Date")
    assert row["estate"] == "Dagenham"
    assert row["unit"] == "5"
    assert row["building"] is None


async def test_ignore_term_removes_it_from_missing_list_and_unignore_reverts(client):
    ws, base, table = await _setup(client, email="mt3b@example.com")

    before = (await client.get(f"/api/tables/{table['id']}/missing-terms")).json()
    assert before["summary"]["ignored"] == 0
    assert before["summary"]["missing"] == 4
    assert ("Alterations", "Last Refurbishment Date") in {(r["sub_domain"], r["term_name"]) for r in before["rows"]}

    ignore = await client.post(
        f"/api/tables/{table['id']}/missing-terms/ignore", json={"sub_domain": "alterations", "term_name": "  last refurbishment date "}
    )
    assert ignore.status_code == 204, ignore.text

    # Idempotent -- ignoring the same (normalized) term again is a no-op, not an error.
    again = await client.post(
        f"/api/tables/{table['id']}/missing-terms/ignore", json={"sub_domain": "Alterations", "term_name": "Last Refurbishment Date"}
    )
    assert again.status_code == 204

    after = (await client.get(f"/api/tables/{table['id']}/missing-terms")).json()
    assert after["summary"]["ignored"] == 1
    assert after["summary"]["missing"] == 3
    remaining = {(r["sub_domain"], r["term_name"]) for r in after["rows"]}
    assert ("Alterations", "Last Refurbishment Date") not in remaining

    ignored_list = (await client.get(f"/api/tables/{table['id']}/missing-terms/ignored")).json()
    assert len(ignored_list) == 1
    assert ignored_list[0]["sub_domain"] == "alterations"
    assert ignored_list[0]["term_name"] == "last refurbishment date"

    unignore = await client.post(
        f"/api/tables/{table['id']}/missing-terms/unignore", json={"sub_domain": "Alterations", "term_name": "Last Refurbishment Date"}
    )
    assert unignore.status_code == 204

    reverted = (await client.get(f"/api/tables/{table['id']}/missing-terms")).json()
    assert reverted["summary"]["ignored"] == 0
    assert reverted["summary"]["missing"] == 4
    assert ("Alterations", "Last Refurbishment Date") in {(r["sub_domain"], r["term_name"]) for r in reverted["rows"]}
    assert (await client.get(f"/api/tables/{table['id']}/missing-terms/ignored")).json() == []


async def test_create_job_rejects_empty_submission_and_dedupes_active_but_allows_terminal_resubmit(client, monkeypatch):
    ws, base, table = await _setup(client, email="mt4@example.com")

    empty = await client.post(f"/api/tables/{table['id']}/missing-terms-jobs", json={"rows": [{"sub_domain": "Alterations", "term_name": "Last Refurbishment Date"}]})
    assert empty.status_code == 422

    payload = {"rows": [{"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "page": "12"}]}
    first = await client.post(f"/api/tables/{table['id']}/missing-terms-jobs", json=payload)
    assert first.status_code == 202, first.text

    duplicate = await client.post(f"/api/tables/{table['id']}/missing-terms-jobs", json=payload)
    assert duplicate.status_code == 409, duplicate.text

    # Excluded from the missing list while the job is active.
    missing = (await client.get(f"/api/tables/{table['id']}/missing-terms")).json()
    assert missing["summary"]["in_progress"] == 1
    assert not any(r["term_name"] == "Last Refurbishment Date" for r in missing["rows"])

    mock_post = AsyncMock(side_effect=httpx.ConnectError("boom"))
    monkeypatch.setattr("app.worker.tasks.missing_terms_tasks.submit_and_await_result", mock_post)
    await run_missing_terms_job({}, first.json()["id"])

    resubmit = await client.post(f"/api/tables/{table['id']}/missing-terms-jobs", json=payload)
    assert resubmit.status_code == 202, resubmit.text


async def test_import_each_field_pivot_candidate_becomes_its_own_row(client, monkeypatch):
    # Some tables are long/EAV-shaped -- one row per extracted FIELD of a
    # term (a literal "field" column names the attribute, "value" holds its
    # content), not one row per term. Ticking several field-candidates for
    # the same submitted term must create SEPARATE rows -- and since import
    # does no duplicate checking against the main table at all, even two
    # candidates extracting the SAME field ("component_name" twice) each
    # still get their own new row; only re-importing the identical (job,
    # candidate) a second time is blocked, via imported_keys.
    ws, base, table = await _setup(client, email="mt6d@example.com")
    await _add_text_field(client, table["id"], "field")
    await _add_text_field(client, table["id"], "value")

    job = (
        await client.post(
            f"/api/tables/{table['id']}/missing-terms-jobs",
            json={"rows": [{"sub_domain": "Component", "term_name": "No. Loading Doors", "page": "1"}]},
        )
    ).json()

    mock_post = AsyncMock(
        return_value=[
            {
                "sub_domain": "Component",
                "term_name": "No. Loading Doors",
                "candidates": [
                    {"sub_domain": "Component", "term_name": "No. Loading Doors", "field": "component_name", "value": "Reinforced door", "score": 1},
                    {"sub_domain": "Component", "term_name": "No. Loading Doors", "field": "model_name", "value": "LD-900", "score": 1},
                    {"sub_domain": "Component", "term_name": "No. Loading Doors", "field": "component_name", "value": "Different value", "score": 0.5},
                ],
            }
        ]
    )
    monkeypatch.setattr("app.worker.tasks.missing_terms_tasks.submit_and_await_result", mock_post)
    await run_missing_terms_job({}, job["id"])

    import_resp = await client.post(
        f"/api/missing-terms-jobs/{job['id']}/import",
        json={
            "selections": [
                {"sub_domain": "Component", "term_name": "No. Loading Doors", "candidate_index": 0, "columns": []},
                {"sub_domain": "Component", "term_name": "No. Loading Doors", "candidate_index": 1, "columns": []},
                {"sub_domain": "Component", "term_name": "No. Loading Doors", "candidate_index": 2, "columns": []},
            ]
        },
    )
    assert import_resp.status_code == 200, import_resp.text
    results = import_resp.json()["results"]
    assert [r["status"] for r in results] == ["inserted", "inserted", "inserted"]
    assert len({r["row_id"] for r in results}) == 3  # three distinct rows, even though two share the same "field" value

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    values_by_row = {r["row_id"]: r["values"] for r in rows}
    assert values_by_row[results[0]["row_id"]]["field"] == "component_name"
    assert values_by_row[results[0]["row_id"]]["value"] == "Reinforced door"
    assert values_by_row[results[1]["row_id"]]["field"] == "model_name"
    assert values_by_row[results[1]["row_id"]]["value"] == "LD-900"
    assert values_by_row[results[2]["row_id"]]["field"] == "component_name"
    assert values_by_row[results[2]["row_id"]]["value"] == "Different value"

    # Re-importing the exact same (job, candidate) a second time is still
    # the one thing that's blocked -- not a main-table duplicate check.
    reimport_resp = await client.post(
        f"/api/missing-terms-jobs/{job['id']}/import",
        json={"selections": [{"sub_domain": "Component", "term_name": "No. Loading Doors", "candidate_index": 0, "columns": []}]},
    )
    assert reimport_resp.json()["results"][0]["status"] == "skipped"


async def test_worker_success_partial_and_failure_notify(client, monkeypatch):
    ws, base, table = await _setup(client, email="mt5@example.com")
    payload = {
        "rows": [
            {"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "page": "1"},
            {"sub_domain": "Component", "term_name": "No. Loading Doors", "page": "2"},
        ]
    }
    job = (await client.post(f"/api/tables/{table['id']}/missing-terms-jobs", json=payload)).json()

    # Only one of the two submitted rows gets candidates back -> partially_failed.
    mock_post = AsyncMock(
        return_value=[{"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "candidates": [{"SubDomain": "Alterations", "TermName": "Last Refurbishment Date", "extra_meta": "x"}]}]
    )
    monkeypatch.setattr("app.worker.tasks.missing_terms_tasks.submit_and_await_result", mock_post)
    await run_missing_terms_job({}, job["id"])

    refetched = (await client.get(f"/api/missing-terms-jobs/{job['id']}")).json()
    assert refetched["status"] == "partially_failed"
    assert len(refetched["response_rows"]) == 1

    notifications = (await client.get("/api/notifications")).json()["notifications"]
    assert any(f"missingTermsJob={job['id']}" in (n["link"] or "") for n in notifications)

    # A second job that fails entirely.
    job2 = (await client.post(f"/api/tables/{table['id']}/missing-terms-jobs", json={"rows": [{"sub_domain": "Component", "term_name": "No. Loading Doors", "page": "3"}]})).json()
    mock_fail = AsyncMock(side_effect=httpx.ConnectError("boom"))
    monkeypatch.setattr("app.worker.tasks.missing_terms_tasks.submit_and_await_result", mock_fail)
    await run_missing_terms_job({}, job2["id"])
    refetched2 = (await client.get(f"/api/missing-terms-jobs/{job2['id']}")).json()
    assert refetched2["status"] == "failed"
    assert refetched2["error"]

    retry = await client.post(f"/api/missing-terms-jobs/{job2['id']}/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "queued"


async def test_import_writes_only_ticked_columns_and_prevents_double_import(client, monkeypatch):
    ws, base, table = await _setup(client, email="mt6@example.com")
    job = (
        await client.post(
            f"/api/tables/{table['id']}/missing-terms-jobs",
            json={"rows": [{"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "page": "1"}]},
        )
    ).json()
    mock_post = AsyncMock(
        return_value=[
            {
                "sub_domain": "Alterations",
                "term_name": "Last Refurbishment Date",
                "candidates": [{"SubDomain": "Alterations", "TermName": "Last Refurbishment Date", "Keywords": "roof, date", "score": 0.9}],
            }
        ]
    )
    monkeypatch.setattr("app.worker.tasks.missing_terms_tasks.submit_and_await_result", mock_post)
    await run_missing_terms_job({}, job["id"])

    # Only Keywords is ticked -- "score" has no field mapping and must be
    # dropped silently, and SubDomain/TermName are always set regardless.
    import_resp = await client.post(
        f"/api/missing-terms-jobs/{job['id']}/import",
        json={"selections": [{"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "candidate_index": 0, "columns": ["Keywords"]}]},
    )
    assert import_resp.status_code == 200, import_resp.text
    result = import_resp.json()["results"][0]
    assert result["status"] == "inserted"

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    inserted = next(r for r in rows if r["row_id"] == result["row_id"])
    assert inserted["values"]["Keywords"] == "roof, date"
    assert inserted["values"]["SubDomain"] == "Alterations"

    # Re-importing the same (job, candidate) must be a no-op skip, not a second row.
    reimport = await client.post(
        f"/api/missing-terms-jobs/{job['id']}/import",
        json={"selections": [{"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "candidate_index": 0, "columns": ["Keywords"]}]},
    )
    assert reimport.json()["results"][0]["status"] == "skipped"
    rows_after = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert len(rows_after) == 1


async def test_import_override_writes_edited_value_instead_of_candidate(client, monkeypatch):
    ws, base, table = await _setup(client, email="mt6b@example.com")
    job = (
        await client.post(
            f"/api/tables/{table['id']}/missing-terms-jobs",
            json={"rows": [{"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "page": "1"}]},
        )
    ).json()
    mock_post = AsyncMock(
        return_value=[
            {
                "sub_domain": "Alterations",
                "term_name": "Last Refurbishment Date",
                "candidates": [{"SubDomain": "Alterations", "TermName": "Last Refurbishment Date", "Keywords": "roof, date"}],
            }
        ]
    )
    monkeypatch.setattr("app.worker.tasks.missing_terms_tasks.submit_and_await_result", mock_post)
    await run_missing_terms_job({}, job["id"])

    # The user corrected "Keywords" on the review screen -- the override
    # must win over the API's own candidate value, without mutating the
    # job's stored response_rows (the raw API output).
    import_resp = await client.post(
        f"/api/missing-terms-jobs/{job['id']}/import",
        json={
            "selections": [
                {
                    "sub_domain": "Alterations",
                    "term_name": "Last Refurbishment Date",
                    "candidate_index": 0,
                    "columns": ["Keywords"],
                    "overrides": {"Keywords": "corrected, keywords"},
                }
            ]
        },
    )
    assert import_resp.status_code == 200, import_resp.text
    result = import_resp.json()["results"][0]
    assert result["status"] == "inserted"

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    inserted = next(r for r in rows if r["row_id"] == result["row_id"])
    assert inserted["values"]["Keywords"] == "corrected, keywords"

    refetched = (await client.get(f"/api/missing-terms-jobs/{job['id']}")).json()
    assert refetched["response_rows"][0]["candidates"][0]["Keywords"] == "roof, date"


async def test_submitted_rows_carry_estate_building_unit_to_external_api(client, monkeypatch):
    ws, base, table = await _setup(client, email="mt6c@example.com")
    job = (
        await client.post(
            f"/api/tables/{table['id']}/missing-terms-jobs",
            json={
                "rows": [
                    {
                        "sub_domain": "Alterations",
                        "term_name": "Last Refurbishment Date",
                        "estate": "E1",
                        "building": "B1",
                        "unit": "U1",
                        "page": "1",
                    }
                ]
            },
        )
    ).json()
    assert job["submitted_rows"][0]["estate"] == "E1"
    assert job["submitted_rows"][0]["building"] == "B1"
    assert job["submitted_rows"][0]["unit"] == "U1"

    mock_post = AsyncMock(return_value=[{"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "candidates": []}])
    monkeypatch.setattr("app.worker.tasks.missing_terms_tasks.submit_and_await_result", mock_post)
    await run_missing_terms_job({}, job["id"])

    payload = mock_post.call_args.args[2]
    assert payload["rows"][0]["estate"] == "E1"
    assert payload["rows"][0]["building"] == "B1"
    assert payload["rows"][0]["unit"] == "U1"


async def test_manual_insert_duplicate_checked(client):
    ws, base, table = await _setup(client, email="mt7@example.com")
    first = await client.post(
        f"/api/tables/{table['id']}/missing-terms/manual-insert",
        json={"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "values": {"Page": "5"}},
    )
    assert first.status_code == 200, first.text

    duplicate = await client.post(
        f"/api/tables/{table['id']}/missing-terms/manual-insert",
        json={"sub_domain": "alterations", "term_name": "last refurbishment date", "values": {"Page": "9"}},
    )
    assert duplicate.status_code == 409, duplicate.text

    overwrite = await client.post(
        f"/api/tables/{table['id']}/missing-terms/manual-insert",
        json={"sub_domain": "alterations", "term_name": "last refurbishment date", "values": {"Page": "9"}, "on_conflict": "overwrite"},
    )
    assert overwrite.status_code == 200, overwrite.text
    assert overwrite.json()["row_id"] == first.json()["row_id"]
    assert overwrite.json()["values"]["Page"] == "9"


async def test_api_config_round_trips_and_is_admin_only(client, make_client):
    ws, base, table = await _setup(client, email="mt8@example.com")
    viewer = await _add_member(client, ws["id"], make_client, WorkspaceRole.VIEWER, "mt8-viewer@example.com")

    forbidden = await viewer.put(f"/api/workspaces/{ws['id']}/missing-terms-api-config", json={"api_url": "https://evil.example/hook"})
    assert forbidden.status_code == 403

    get = await client.get(f"/api/workspaces/{ws['id']}/missing-terms-api-config")
    assert get.status_code == 200
    assert get.json()["api_url"] == "https://example.com/missing-terms-lookup"

    viewer_get = await viewer.get(f"/api/workspaces/{ws['id']}/missing-terms-api-config")
    assert viewer_get.status_code == 403

    bad = await client.put(f"/api/workspaces/{ws['id']}/missing-terms-api-config", json={"api_url": "not-a-url"})
    assert bad.status_code == 422

    updated = await client.put(
        f"/api/workspaces/{ws['id']}/missing-terms-api-config",
        json={"api_url": "https://new.example/lookup", "headers": {"X-Key": "abc"}},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["headers"] == {"X-Key": "abc"}


async def test_worker_uses_the_workspaces_own_api_config(client, monkeypatch):
    ws, base, table = await _setup(client, email="mt9@example.com")
    job = (
        await client.post(
            f"/api/tables/{table['id']}/missing-terms-jobs",
            json={"rows": [{"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "page": "1"}]},
        )
    ).json()

    mock_post = AsyncMock(return_value=[{"sub_domain": "Alterations", "term_name": "Last Refurbishment Date", "candidates": [{"SubDomain": "Alterations", "TermName": "Last Refurbishment Date"}]}])
    monkeypatch.setattr("app.worker.tasks.missing_terms_tasks.submit_and_await_result", mock_post)
    await run_missing_terms_job({}, job["id"])

    # The URL/headers actually used come from this workspace's own DB-backed
    # config, not an env var -- confirmed by checking what was passed in.
    call_args = mock_post.call_args
    assert call_args.args[0] == "https://example.com/missing-terms-lookup"

    refetched = (await client.get(f"/api/missing-terms-jobs/{job['id']}")).json()
    assert refetched["status"] == "completed"


async def test_worker_fails_clearly_when_workspace_has_no_api_config(client, monkeypatch):
    await register_user(client, email="mt10@example.com")
    ws, base, table = await create_workspace_base_table(client)
    sub_field = await _add_text_field(client, table["id"], "SubDomain")
    term_field = await _add_text_field(client, table["id"], "TermName")
    await client.put(
        f"/api/tables/{table['id']}/missing-terms-config",
        json={"field_mapping": {"sub_domain": sub_field["id"], "term_name": term_field["id"]}},
    )
    # Deliberately skip configuring an API for this workspace.
    job = (await client.post(f"/api/tables/{table['id']}/missing-terms-jobs", json={"rows": [{"sub_domain": "A", "term_name": "B", "page": "1"}]})).json()
    await run_missing_terms_job({}, job["id"])
    refetched = (await client.get(f"/api/missing-terms-jobs/{job['id']}")).json()
    assert refetched["status"] == "failed"
    assert "no external api" in refetched["error"].lower()


async def test_delete_prerequest_is_admin_only_and_idempotent_error(client, make_client):
    ws, base, table = await _setup(client, email="mt11@example.com")
    viewer = await _add_member(client, ws["id"], make_client, WorkspaceRole.VIEWER, "mt11-viewer@example.com")

    forbidden = await viewer.delete(f"/api/workspaces/{ws['id']}/prerequest")
    assert forbidden.status_code == 403

    deleted = await client.delete(f"/api/workspaces/{ws['id']}/prerequest")
    assert deleted.status_code == 204

    get = await client.get(f"/api/workspaces/{ws['id']}/prerequest")
    assert get.status_code == 200
    assert get.json() is None

    summary = (await client.get(f"/api/tables/{table['id']}/missing-terms")).json()["summary"]
    assert summary["total"] == 0

    double_delete = await client.delete(f"/api/workspaces/{ws['id']}/prerequest")
    assert double_delete.status_code == 404
