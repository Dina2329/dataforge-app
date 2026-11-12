"""Missing Terms job execution -- runs in the arq worker, never the request
thread, since the external API's candidate search can take minutes, not
just seconds. Mirrors bulk_ops_tasks.py's run_bulk_update shape: its own
session, status set to "running" and committed before any outbound call,
one broad except-Exception -> rollback/failed/commit. Posts to this app's
existing notifications inbox on either terminal status, since the Missing
Terms panel is meant to be closed and reopened later (a dedicated Jobs
panel is the richer per-job surface), not watched with a blocking spinner.

submit_and_await_result() (webhook_client.py) carries the job_id through so
a slow external API can ack with HTTP 202 and be polled by job_id instead
of holding one HTTP request open for the whole lookup -- see that
function's docstring for the exact contract. run_missing_terms_job is
registered in arq_app.py with an extended per-task timeout to match (the
worker's blanket default would otherwise kill a job still polling).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.webhook_client import submit_and_await_result
from app.modules.bases.models import Base, Table
from app.modules.missing_terms.models import MissingTermsApiConfig, MissingTermsJob
from app.modules.notifications.service import NotificationService


def _normalize(value: str | None) -> str:
    """Same rule as missing_terms/service.py's _normalize() -- duplicated
    (not imported) to avoid a circular import: that module imports
    get_arq_pool from this worker's own arq_app, which imports this task
    module to register it. Worker task modules only ever import models,
    never a sibling service.py, for exactly this reason (see every other
    *_tasks.py in this package)."""
    if value is None:
        return ""
    return " ".join(value.strip().split()).lower()


async def run_missing_terms_job(ctx, job_id: str) -> None:
    async with SessionLocal() as db:
        job = await db.get(MissingTermsJob, uuid.UUID(job_id))
        if job is None:
            return

        try:
            job.status = "running"
            await db.commit()

            table = await db.get(Table, job.table_id)
            base = await db.get(Base, table.base_id) if table else None
            api_config = (
                (await db.execute(select(MissingTermsApiConfig).where(MissingTermsApiConfig.workspace_id == base.workspace_id))).scalar_one_or_none()
                if base
                else None
            )
            if api_config is None:
                raise ValueError("No external API is configured for this workspace yet (Prerequest list page -> External API)")

            body = await submit_and_await_result(
                api_config.api_url,
                api_config.headers,
                {"job_id": str(job.id), "rows": job.submitted_rows},
                job_id=str(job.id),
            )
            if not isinstance(body, list):
                raise ValueError("External API did not return a list of {sub_domain, term_name, candidates} groups")

            submitted_keys = {(_normalize(r["sub_domain"]), _normalize(r["term_name"])) for r in job.submitted_rows}
            response_keys = set()
            response_rows = []
            for group in body:
                if not isinstance(group, dict) or "sub_domain" not in group or "term_name" not in group:
                    continue
                candidates = group.get("candidates")
                if not isinstance(candidates, list) or not all(isinstance(c, dict) for c in candidates):
                    continue
                response_rows.append(group)
                response_keys.add((_normalize(group["sub_domain"]), _normalize(group["term_name"])))

            if not response_rows:
                raise ValueError("External API did not return any usable {sub_domain, term_name, candidates} groups")

            job.response_rows = response_rows
            job.status = "completed" if response_keys >= submitted_keys else "partially_failed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await NotificationService(db).create(
                user_id=job.created_by,
                title="Missing Terms results ready" if job.status == "completed" else "Missing Terms partially completed",
                message=f"{len(response_rows)} of {len(job.submitted_rows)} submitted row(s) got candidates back.",
                link=f"/tables/{job.table_id}?missingTermsJob={job.id}",
            )
        except Exception as exc:
            await db.rollback()
            job.status = "failed"
            # Some exceptions (e.g. an httpx timeout raised internally with
            # no message) stringify to "" -- fall back to the exception's
            # type name so a failed job never ends up with a blank, useless
            # error message.
            job.error = (str(exc) or type(exc).__name__)[:1000]
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await NotificationService(db).create(
                user_id=job.created_by,
                title="Missing Terms job failed",
                message=job.error,
                link=f"/tables/{job.table_id}?missingTermsJob={job.id}",
            )
