"""Dashboards pivot widget: rows x columns x aggregate cross-tab (e.g.
Reviewed By x Date -> count), including date-field bucketing by day/week/month
and the row_field/column_field validation errors. Also covers widgets sourced
from the Audit Log instead of a real table (pivot/kpi/table widget types over
action/resource_type/actor_email/created_at), including that only an
owner/admin (Permission.AUDIT_LOG_READ) can create or view one."""

from app.modules.workspaces.models import WorkspaceRole
from tests.conftest import create_workspace_base_table, register_user


async def _add_member(client, workspace_id: str, make_client, role, email):
    member = await make_client()
    await register_user(member, email=email)
    await client.post(f"/api/workspaces/{workspace_id}/members", json={"email": email, "role": role})
    return member


async def _add_field(client, table_id: str, name: str, field_type: str = "text") -> dict:
    resp = await client.post(f"/api/tables/{table_id}/fields", json={"name": name, "field_type": field_type, "options": {}})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _setup_qc_table(client, *, email: str):
    await register_user(client, email=email)
    ws, base, table = await create_workspace_base_table(client)
    await _add_field(client, table["id"], "Reviewed By")
    await _add_field(client, table["id"], "Reviewed Date", field_type="date")
    await _add_field(client, table["id"], "Status")

    rows = [
        ("Alice", "2026-11-01", "Pass"),
        ("Alice", "2026-11-01", "Fail"),
        ("Alice", "2026-11-02", "Pass"),
        ("Bob", "2026-11-01", "Pass"),
        ("Bob", "2026-11-03", "Fail"),
    ]
    for reviewer, reviewed_date, status in rows:
        resp = await client.post(
            f"/api/tables/{table['id']}/rows",
            json={"values": {"Reviewed By": reviewer, "Reviewed Date": reviewed_date, "Status": status}},
        )
        assert resp.status_code == 201, resp.text

    dashboard = (await client.post(f"/api/workspaces/{ws['id']}/dashboards", json={"name": "QC Dashboard"})).json()
    return ws, base, table, dashboard


async def test_kpi_widget_count_with_no_filter_counts_all_rows(client):
    # Regression: a bare count() with no y_field and no filter has no column
    # of its own for SQLAlchemy to infer a FROM clause from -- without an
    # explicit select_from(sa_table), this silently compiled to a FROM-less
    # "SELECT count(*)" and always returned 1, no matter how many rows
    # actually existed.
    ws, base, table, dashboard = await _setup_qc_table(client, email="kpi1@example.com")

    widget = (
        await client.post(
            f"/api/dashboards/{dashboard['id']}/widgets",
            json={"name": "Total", "widget_type": "kpi", "table_id": table["id"], "config": {"aggregate": "count"}, "position": {"x": 0, "y": 0, "w": 4, "h": 2}},
        )
    ).json()

    data = (await client.get(f"/api/dashboards/{dashboard['id']}/widgets/{widget['id']}/data")).json()
    assert data["value"] == 5


async def test_pivot_widget_counts_by_person_and_day(client):
    ws, base, table, dashboard = await _setup_qc_table(client, email="pivot1@example.com")

    widget = (
        await client.post(
            f"/api/dashboards/{dashboard['id']}/widgets",
            json={
                "name": "QC work by person/day",
                "widget_type": "pivot",
                "table_id": table["id"],
                "config": {"row_field": "Reviewed By", "column_field": "Reviewed Date", "aggregate": "count"},
                "position": {"x": 0, "y": 0, "w": 4, "h": 4},
            },
        )
    ).json()

    data = (await client.get(f"/api/dashboards/{dashboard['id']}/widgets/{widget['id']}/data")).json()
    pivot = data["pivot"]

    assert pivot["rows"] == ["Alice", "Bob"]
    assert pivot["columns"] == ["2026-11-01", "2026-11-02", "2026-11-03"]
    # Alice: 2 on 11-01, 1 on 11-02, 0 on 11-03. Bob: 1 on 11-01, 0, 1 on 11-03.
    assert pivot["cells"] == [[2, 1, 0], [1, 0, 1]]
    assert pivot["row_totals"] == [3, 2]
    assert pivot["column_totals"] == [3, 1, 1]
    assert pivot["grand_total"] == 5


async def test_pivot_widget_buckets_dates_by_month(client):
    ws, base, table, dashboard = await _setup_qc_table(client, email="pivot2@example.com")

    widget = (
        await client.post(
            f"/api/dashboards/{dashboard['id']}/widgets",
            json={
                "name": "QC work by person/month",
                "widget_type": "pivot",
                "table_id": table["id"],
                "config": {"row_field": "Reviewed By", "column_field": "Reviewed Date", "aggregate": "count", "date_granularity": "month"},
                "position": {"x": 0, "y": 0, "w": 4, "h": 4},
            },
        )
    ).json()

    data = (await client.get(f"/api/dashboards/{dashboard['id']}/widgets/{widget['id']}/data")).json()
    pivot = data["pivot"]

    # All 3 distinct days collapse into the one November column once bucketed by month.
    assert pivot["columns"] == ["2026-11"]
    assert pivot["cells"] == [[3], [2]]
    assert pivot["grand_total"] == 5


async def test_pivot_widget_requires_row_and_column_field(client):
    ws, base, table, dashboard = await _setup_qc_table(client, email="pivot3@example.com")

    missing_row = await client.post(
        f"/api/dashboards/{dashboard['id']}/widgets",
        json={"name": "bad", "widget_type": "pivot", "table_id": table["id"], "config": {"column_field": "Reviewed Date"}, "position": {"x": 0, "y": 0, "w": 4, "h": 4}},
    )
    widget = missing_row.json()
    resp = await client.get(f"/api/dashboards/{dashboard['id']}/widgets/{widget['id']}/data")
    assert resp.status_code == 422, resp.text

    missing_col = await client.post(
        f"/api/dashboards/{dashboard['id']}/widgets",
        json={"name": "bad2", "widget_type": "pivot", "table_id": table["id"], "config": {"row_field": "Reviewed By"}, "position": {"x": 0, "y": 0, "w": 4, "h": 4}},
    )
    widget2 = missing_col.json()
    resp2 = await client.get(f"/api/dashboards/{dashboard['id']}/widgets/{widget2['id']}/data")
    assert resp2.status_code == 422, resp2.text


async def test_audit_log_widget_pivot_counts_by_person_and_action(client, make_client):
    await register_user(client, email="auditw1@example.com")
    ws, base, table = await create_workspace_base_table(client)
    editor = await _add_member(client, ws["id"], make_client, WorkspaceRole.EDITOR, "auditw1-editor@example.com")

    # Both of these go through AuditService.log() (same-transaction, not the
    # arq queue) -- dashboard.created is logged inline, so no worker-task
    # patching is needed to see it show up immediately.
    dashboard = (await client.post(f"/api/workspaces/{ws['id']}/dashboards", json={"name": "Dash A"})).json()
    await editor.post(f"/api/workspaces/{ws['id']}/dashboards", json={"name": "Dash B"})
    await editor.post(f"/api/workspaces/{ws['id']}/dashboards", json={"name": "Dash C"})

    widget = (
        await client.post(
            f"/api/dashboards/{dashboard['id']}/widgets",
            json={
                "name": "Dashboards created by person",
                "widget_type": "pivot",
                "source_type": "audit_log",
                "config": {
                    "row_field": "actor_email",
                    "column_field": "action",
                    "aggregate": "count",
                    "filter": {"kind": "condition", "field": "action", "operator": "eq", "value": "dashboard.created"},
                },
                "position": {"x": 0, "y": 0, "w": 4, "h": 4},
            },
        )
    ).json()
    assert widget["source_type"] == "audit_log"
    assert widget["table_id"] is None

    data = (await client.get(f"/api/dashboards/{dashboard['id']}/widgets/{widget['id']}/data")).json()
    pivot = data["pivot"]
    # Scoped by the filter above to just "dashboard.created" -- workspace
    # setup (create_workspace_base_table, _add_member) logs its own
    # base.created/table.created/member.invited entries too, which this
    # filter deliberately excludes so the test isn't coupled to that noise.
    assert pivot["columns"] == ["dashboard.created"]
    rows_by_person = dict(zip(pivot["rows"], [c[0] for c in pivot["cells"]]))
    assert rows_by_person["auditw1-editor@example.com"] == 2
    assert rows_by_person["auditw1@example.com"] == 1


async def test_audit_log_widget_kpi_respects_filter_and_workspace_scope(client):
    await register_user(client, email="auditw2@example.com")
    ws, base, table = await create_workspace_base_table(client)
    other_ws = (await client.post("/api/workspaces", json={"name": "Other WS"})).json()

    dashboard = (await client.post(f"/api/workspaces/{ws['id']}/dashboards", json={"name": "Dash"})).json()
    await client.post(f"/api/workspaces/{ws['id']}/dashboards", json={"name": "Dash2"})  # a second dashboard.created in the SAME workspace
    await client.post(f"/api/workspaces/{other_ws['id']}/dashboards", json={"name": "Other WS Dash"})  # must not be counted

    widget = (
        await client.post(
            f"/api/dashboards/{dashboard['id']}/widgets",
            json={
                "name": "Total dashboards created",
                "widget_type": "kpi",
                "source_type": "audit_log",
                "config": {"aggregate": "count", "filter": {"kind": "condition", "field": "action", "operator": "eq", "value": "dashboard.created"}},
                "position": {"x": 0, "y": 0, "w": 4, "h": 2},
            },
        )
    ).json()

    data = (await client.get(f"/api/dashboards/{dashboard['id']}/widgets/{widget['id']}/data")).json()
    # 2 in this workspace (the dashboard itself + Dash2) -- the other
    # workspace's dashboard.created entry must not leak in.
    assert data["value"] == 2


async def test_audit_log_widget_requires_audit_permission(client, make_client):
    await register_user(client, email="auditw3@example.com")
    ws, base, table = await create_workspace_base_table(client)
    editor = await _add_member(client, ws["id"], make_client, WorkspaceRole.EDITOR, "auditw3-editor@example.com")

    dashboard = (await client.post(f"/api/workspaces/{ws['id']}/dashboards", json={"name": "Dash"})).json()

    forbidden = await editor.post(
        f"/api/dashboards/{dashboard['id']}/widgets",
        json={
            "name": "Not allowed",
            "widget_type": "kpi",
            "source_type": "audit_log",
            "config": {"aggregate": "count"},
            "position": {"x": 0, "y": 0, "w": 4, "h": 2},
        },
    )
    assert forbidden.status_code == 403, forbidden.text

    allowed = await client.post(
        f"/api/dashboards/{dashboard['id']}/widgets",
        json={
            "name": "Allowed",
            "widget_type": "kpi",
            "source_type": "audit_log",
            "config": {"aggregate": "count"},
            "position": {"x": 0, "y": 0, "w": 4, "h": 2},
        },
    )
    assert allowed.status_code == 201, allowed.text


async def test_audit_log_widget_filters_to_one_table(client, monkeypatch):
    from app.worker.tasks.audit_tasks import write_audit_log_entry

    class _ImmediateArqPool:
        async def enqueue_job(self, name, **kwargs):
            await write_audit_log_entry({}, **kwargs)

    async def _fake_get_arq_pool():
        return _ImmediateArqPool()

    monkeypatch.setattr("app.worker.arq_app.get_arq_pool", _fake_get_arq_pool)

    await register_user(client, email="auditw4@example.com")
    ws, base, table_a = await create_workspace_base_table(client, table_name="Table A")
    table_b = (await client.post(f"/api/bases/{base['id']}/tables", json={"name": "Table B"})).json()

    # Two rows in Table A, one in Table B -- record.created audit entries
    # for each, each carrying its own table_id in details.
    await client.post(f"/api/tables/{table_a['id']}/rows", json={"values": {}})
    await client.post(f"/api/tables/{table_a['id']}/rows", json={"values": {}})
    await client.post(f"/api/tables/{table_b['id']}/rows", json={"values": {}})

    dashboard = (await client.post(f"/api/workspaces/{ws['id']}/dashboards", json={"name": "Dash"})).json()
    widget = (
        await client.post(
            f"/api/dashboards/{dashboard['id']}/widgets",
            json={
                "name": "Table A activity only",
                "widget_type": "kpi",
                "source_type": "audit_log",
                "config": {
                    "aggregate": "count",
                    "filter": {"kind": "condition", "field": "table_id", "operator": "eq", "value": table_a["id"]},
                },
                "position": {"x": 0, "y": 0, "w": 4, "h": 2},
            },
        )
    ).json()

    data = (await client.get(f"/api/dashboards/{dashboard['id']}/widgets/{widget['id']}/data")).json()
    assert data["value"] == 2
