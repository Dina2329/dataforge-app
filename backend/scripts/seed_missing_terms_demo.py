"""Seeds a self-contained demo for the Missing Terms Check feature, against
the REAL running backend (exercises the exact same API a user would) --
not a direct DB write. Safe to re-run: each run creates a fresh demo
workspace (named "Missing Terms Demo <date>") rather than mutating a
previous one, so old demo runs are simply left behind for you to delete
from the UI whenever you like.

Usage:
    cd backend && source .venv/bin/activate
    python3 scripts/seed_missing_terms_demo.py [base_url]

Requires: the backend API running (default http://localhost:8000), and
MISSING_TERMS_API_URL pointing at demo_missing_terms_api.py (see that
script's own docstring) if you want "Submit to API" to actually resolve.
"""

import sys
from datetime import date

import httpx

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
DEMO_EMAIL = "demo.missingterms@example.com"
DEMO_PASSWORD = "DemoPass123!"

PREREQUEST_CSV = """Estate,Building,Unit,Sub-Domain,Term Name
Riverside,Block A,101,Alterations,Roof Construction Date
Riverside,Block A,101,Alterations,Last Refurbishment Date
Riverside,Block A,101,Component,Loading Dock Count
,,,Alterations,Facade Material
,,,Alterations,Window Replacement Date
,,,Component,Fire Exit Count
,,,Compliance,Asbestos Survey Date
,,,Compliance,Fire Risk Assessment Date
"""
# The first three rows deliberately match the three rows seeded into the
# main table below (case/whitespace varied, to prove normalization) -- the
# rest are left genuinely missing, so the gap-detection summary shows a mix
# of matched/missing instead of everything in one bucket.
EXISTING_ROWS = [
    {"SubDomain": "  alterations", "TermName": "roof construction date", "Page": "12", "Keywords": "roof, original"},
    {"SubDomain": "Alterations", "TermName": "Last Refurbishment Date ", "Page": "14", "Keywords": "refurb, 2019"},
    {"SubDomain": "component", "TermName": "LOADING DOCK COUNT", "Page": "8", "Keywords": "loading, dock"},
]


def main() -> None:
    client = httpx.Client(base_url=BASE_URL, timeout=15.0)

    resp = client.post("/api/auth/register", json={"email": DEMO_EMAIL, "name": "Missing Terms Demo", "password": DEMO_PASSWORD})
    if resp.status_code == 201:
        token = resp.json()["access_token"]
        print(f"Created demo user {DEMO_EMAIL}")
    else:
        resp = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        resp.raise_for_status()
        token = resp.json()["access_token"]
        print(f"Demo user {DEMO_EMAIL} already existed -- logged in")

    client.headers["Authorization"] = f"Bearer {token}"

    ws_name = f"Missing Terms Demo {date.today().isoformat()}"
    ws = client.post("/api/workspaces", json={"name": ws_name}).json()
    base = client.post(f"/api/workspaces/{ws['id']}/bases", json={"name": "Asset Register"}).json()
    table = client.post(f"/api/bases/{base['id']}/tables", json={"name": "Components"}).json()
    table_id = table["id"]
    print(f"Created workspace '{ws_name}' / base 'Asset Register' / table 'Components'")

    field_ids = {}
    for name in ["SubDomain", "TermName", "Page", "PdfImage", "Keywords"]:
        resp = client.post(f"/api/tables/{table_id}/fields", json={"name": name, "field_type": "text", "options": {}})
        resp.raise_for_status()
        field_ids[name] = resp.json()["id"]

    # The table already has a default "Name" field from table creation --
    # leave it alone, it's harmless and not part of the Missing Terms mapping.

    for row in EXISTING_ROWS:
        client.post(f"/api/tables/{table_id}/rows", json={"values": row}).raise_for_status()
    print(f"Inserted {len(EXISTING_ROWS)} existing rows (these will show as 'matched')")

    upload = client.put(
        f"/api/workspaces/{ws['id']}/prerequest",
        files={"file": ("prerequest.csv", PREREQUEST_CSV, "text/csv")},
    )
    upload.raise_for_status()
    print(f"Uploaded prerequest list: {upload.json()['row_count']} rows")

    config = client.put(
        f"/api/tables/{table_id}/missing-terms-config",
        json={
            "field_mapping": {
                "sub_domain": field_ids["SubDomain"],
                "term_name": field_ids["TermName"],
                "page": field_ids["Page"],
                "pdf_image": field_ids["PdfImage"],
                "keywords": field_ids["Keywords"],
            }
        },
    )
    config.raise_for_status()
    print("Configured Missing Terms Check field mapping")

    summary = client.get(f"/api/tables/{table_id}/missing-terms").json()["summary"]
    print(f"Gap detection summary: {summary}")

    print()
    print("=" * 70)
    print("Demo ready.")
    print(f"  Login:     {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"  Workspace: {ws_name}")
    print(f"  Table URL: http://localhost:5173/tables/{table_id}")
    print(f"  Prerequest admin page: http://localhost:5173/workspaces/{ws['id']}/prerequest")
    print("=" * 70)


if __name__ == "__main__":
    main()
