"""Standalone demo stand-in for the external "Missing Terms" lookup API.

Not part of the dataforge app itself -- simulates a real third-party term
lookup service so the Missing Terms Check feature can be demoed end to end
without a real integration. Run it in its own terminal/screen session:

    python3 backend/scripts/demo_missing_terms_api.py [port] [delay_seconds]

Then point a workspace at it via the "External API" section on its
Prerequest list page (Owner/Admin only) -- or directly:
    PUT /api/workspaces/{workspace_id}/missing-terms-api-config
    {"api_url": "http://127.0.0.1:8899/lookup"}
Takes effect immediately, no restart needed (it's a DB-backed per-workspace
setting, not an env var).

Contract (matches submit_and_await_result() in app/core/webhook_client.py,
used by app/worker/tasks/missing_terms_tasks.py) -- async by job_id, since
a real lookup API can take minutes rather than seconds:
  1. POST /lookup {"job_id": "...", "rows": [{"sub_domain", "term_name",
     "page", "pdf_image", "pdf_name", "keywords"}, ...]}
     -> 202 Accepted immediately (this demo always goes the slow-path route,
        to exercise polling -- a real API fast enough to answer inline could
        return 200 here instead, with the same body as step 2, and skip
        polling entirely).
  2. GET /lookup?job_id=... , repeated every ~10s by the caller:
     -> 202 Accepted while still "processing" (simulated here by delay_seconds,
        default 20, elapsed since the POST)
     -> 200 [{"sub_domain", "term_name", "candidates": [{...}, {...}]}, ...]
        once ready
  Candidate keys are free-form -- the demo returns SubDomain/TermName/Page/
  PdfImage/Keywords/Confidence, matching the demo table's field names set up
  by seed_missing_terms_demo.py (no response_field_mapping needed for the
  demo; it still works correctly if you rename a field and add a mapping).
"""

import hashlib
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
DELAY_SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 20.0

# job_id -> {"rows": [...], "ready_at": epoch_seconds} -- in-memory only,
# fine for a throwaway demo process; a real API would persist this.
_jobs: dict[str, dict] = {}


def _seeded_variant(term_name: str, sub_domain: str, index: int) -> dict:
    """Deterministic-but-varied fake candidate so reruns of the demo are
    reproducible, without just echoing identical data for every candidate."""
    h = int(hashlib.sha256(f"{sub_domain}|{term_name}|{index}".encode()).hexdigest(), 16)
    page = 1 + (h % 240)
    confidence = round(0.95 - index * 0.22 - (h % 10) / 100, 2)
    return {
        "SubDomain": sub_domain,
        "TermName": term_name,
        "Page": str(page),
        "PdfImage": f"doc-{(h % 9000) + 1000}.pdf#page={page}",
        "Keywords": ", ".join(sorted({term_name.lower().split()[0], sub_domain.lower(), "spec", "drawing"})),
        "Confidence": confidence,
    }


def _build_results(rows: list[dict]) -> list[dict]:
    results = []
    for row in rows:
        sub_domain = str(row.get("sub_domain", ""))
        term_name = str(row.get("term_name", ""))
        if not sub_domain or not term_name:
            continue
        # 2 candidates for most terms, 3 for ones whose name hashes "long"
        # -- just enough variety to make the review/import screen feel real.
        count = 3 if len(term_name) % 2 == 0 else 2
        results.append({"sub_domain": sub_domain, "term_name": term_name, "candidates": [_seeded_variant(term_name, sub_domain, i) for i in range(count)]})
    return results


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, status: int, body_obj) -> None:
        body = json.dumps(body_obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw or b"{}")
            job_id = str(payload.get("job_id", ""))
            rows = payload.get("rows", [])
        except json.JSONDecodeError:
            job_id, rows = "", []

        if not job_id:
            self._send_json(400, {"error": "job_id is required"})
            return

        # Always take the slow path here to exercise polling -- a real API
        # fast enough to answer inline could return 200 with the results
        # directly instead of 202, and the caller would skip polling.
        _jobs[job_id] = {"rows": rows, "ready_at": time.monotonic() + DELAY_SECONDS}
        self.send_response(202)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        job_id = (query.get("job_id") or [""])[0]
        job = _jobs.get(job_id)
        if job is None:
            self._send_json(404, {"error": "unknown job_id"})
            return

        if time.monotonic() < job["ready_at"]:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        self._send_json(200, _build_results(job["rows"]))
        del _jobs[job_id]

    def log_message(self, fmt, *args):
        print(f"[demo-missing-terms-api] {self.address_string()} {fmt % args}")


if __name__ == "__main__":
    print(f"Demo Missing Terms API listening on http://127.0.0.1:{PORT}/lookup (simulated delay: {DELAY_SECONDS:.0f}s)")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
