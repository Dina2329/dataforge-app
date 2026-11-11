"""Seeds a self-contained demo for the new Dashboards "Pivot table" widget,
against the REAL running backend (exercises the exact same API a user
would) -- not a direct DB write. Reuses the existing Missing Terms demo
account rather than creating a new one, per request. Safe to re-run: each
run creates a fresh demo workspace (named "Pivot Dashboard Demo <date>")
rather than mutating a previous one, so old demo runs are simply left
behind for you to delete from the UI whenever you like.

Usage:
    cd backend && source .venv/bin/activate
    python3 scripts/seed_pivot_dashboard_demo.py [base_url]

Requires: the backend API running (default http://localhost:8000).
"""

import sys
from datetime import date, timedelta

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
DEMO_EMAIL = "demo.missingterms@example.com"
DEMO_PASSWORD = "DemoPass123!"

REVIEWERS = ["Alice", "Bob", "Charlie"]
STATUSES = ["pass", "pass", "fail", "pending"]  # weighted so "pass" is most common, like a real QC queue

# Every reviewer gets at least one row on every day in the window, plus a
# varying number of extras, so the pivot table has a real shape to show
# (not a flat uniform grid) -- deterministic (no randomness) so repeat runs
# produce an identical demo.
EXTRA_ROWS_PER_DAY = {0: [0, 1, 2], 1: [1, 0, 1], 2: [2, 1, 0], 3: [0, 2, 1], 4: [1, 1, 0]}


def build_rows() -> list[dict]:
    today = date.today()
    rows = []
    for day_offset, extras in EXTRA_ROWS_PER_DAY.items():
        the_date = (today - timedelta(days=4 - day_offset)).isoformat()
        for reviewer_idx, reviewer in enumerate(REVIEWERS):
            count = 1 + extras[reviewer_idx]
            for i in range(count):
                status = STATUSES[(day_offset + reviewer_idx + i) % len(STATUSES)]
                rows.append(
                    {
                        "Reviewed By": reviewer,
                        "Reviewed Date": the_date,
                        "Status": status,
                        "Notes": f"{reviewer}'s QC pass #{i + 1} on {the_date}",
                    }
                )
    return rows


def main() -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=15.0)

    resp = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    resp.raise_for_status()
    token = resp.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    print(f"Logged in as {DEMO_EMAIL}")

    ws_name = f"Pivot Dashboard Demo {date.today().isoformat()}"
    ws = client.post("/api/workspaces", json={"name": ws_name}).json()
    base = client.post(f"/api/workspaces/{ws['id']}/bases", json={"name": "QC Review"}).json()
    table = client.post(f"/api/bases/{base['id']}/tables", json={"name": "QC Tasks"}).json()
    table_id = table["id"]
    print(f"Created workspace '{ws_name}' / base 'QC Review' / table 'QC Tasks'")

    client.post(f"/api/tables/{table_id}/fields", json={"name": "Reviewed By", "field_type": "text", "options": {}}).raise_for_status()
    client.post(f"/api/tables/{table_id}/fields", json={"name": "Reviewed Date", "field_type": "date", "options": {}}).raise_for_status()
    client.post(
        f"/api/tables/{table_id}/fields",
        json={
            "name": "Status",
            "field_type": "single_select",
            "options": {"choices": [{"value": "pass", "label": "Pass"}, {"value": "fail", "label": "Fail"}, {"value": "pending", "label": "Pending"}]},
        },
    ).raise_for_status()
    client.post(f"/api/tables/{table_id}/fields", json={"name": "Notes", "field_type": "text", "options": {}}).raise_for_status()
    print("Added fields: Reviewed By, Reviewed Date, Status, Notes")

    rows = build_rows()
    for row in rows:
        client.post(f"/api/tables/{table_id}/rows", json={"values": row}).raise_for_status()
    print(f"Inserted {len(rows)} QC task rows across {len(REVIEWERS)} reviewers and {len(EXTRA_ROWS_PER_DAY)} days")

    dashboard = client.post(f"/api/workspaces/{ws['id']}/dashboards", json={"name": "QC Work Tracker"}).json()
    dashboard_id = dashboard["id"]
    print("Created dashboard 'QC Work Tracker'")

    client.post(
        f"/api/dashboards/{dashboard_id}/widgets",
        json={
            "name": "Reviews by person & day",
            "widget_type": "pivot",
            "table_id": table_id,
            "config": {"row_field": "Reviewed By", "column_field": "Reviewed Date", "aggregate": "count", "date_granularity": "day"},
            "position": {"x": 0, "y": 0, "w": 8, "h": 5},
        },
    ).raise_for_status()
    client.post(
        f"/api/dashboards/{dashboard_id}/widgets",
        json={
            "name": "Total reviews",
            "widget_type": "kpi",
            "table_id": table_id,
            "config": {"aggregate": "count"},
            "position": {"x": 8, "y": 0, "w": 4, "h": 2},
        },
    ).raise_for_status()
    client.post(
        f"/api/dashboards/{dashboard_id}/widgets",
        json={
            "name": "Reviews by status",
            "widget_type": "bar",
            "table_id": table_id,
            "config": {"x_field": "Status", "aggregate": "count"},
            "position": {"x": 8, "y": 2, "w": 4, "h": 3},
        },
    ).raise_for_status()
    print("Added widgets: pivot (person x day), KPI (total), bar chart (by status)")

    print()
    print("=" * 70)
    print("Demo ready.")
    print(f"  Login:         {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"  Workspace:     {ws_name}")
    print(f"  Table URL:     http://localhost:5173/tables/{table_id}")
    print(f"  Dashboard URL: http://localhost:5173/dashboards/{dashboard_id}")
    print("=" * 70)


if __name__ == "__main__":
    main()
