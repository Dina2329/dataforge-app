"""Batch Submit execution -- runs in the arq worker, never the request
thread (architecture plan, section 4): sends every row currently matching
a table's configured filter condition (app.core.query.filter_dsl, the
same filter language records/bulk_ops/dashboards all already use) to an
external API, chunked into config.batch_size-sized POSTs (reusing
post_json -- same 3x-retry-with-backoff helper record_submit's single-row
path and automations' send_webhook already use).

A batch failing never stops the rest -- every remaining batch still gets
sent, and job.batch_results records which ones landed and which didn't
(committed after EACH batch, not once at the end, so polling mid-run shows
real progress). By explicit design, a successful send does not clear the
marker field on its rows -- re-clicking "Send batch" resends every
currently-checked row; batch_results is how a user finds out which rows to
re-tick for a retry.
"""

import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from tenacity import RetryError

from app.core.db import SessionLocal
from app.core.json_safe import json_safe
from app.core.query.filter_dsl import compile_filter, parse_filter_expr
from app.core.webhook_client import post_json
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.models import Field, Table
from app.modules.batch_submit.models import BatchSubmitConfig, BatchSubmitJob
from app.modules.notifications.service import NotificationService

_NOTIFICATION_TITLES = {
    "completed": "Batch send completed",
    "partially_failed": "Batch send partially completed",
    "failed": "Batch send failed",
}


async def run_batch_submit_job(ctx, job_id: str) -> None:
    async with SessionLocal() as db:
        job = await db.get(BatchSubmitJob, uuid.UUID(job_id))
        if job is None:
            return

        try:
            job.status = "running"
            await db.commit()

            table = await db.get(Table, job.table_id)
            fields = list((await db.execute(select(Field).where(Field.table_id == table.id))).scalars().all())
            config = (
                await db.execute(select(BatchSubmitConfig).where(BatchSubmitConfig.table_id == table.id))
            ).scalar_one_or_none()
            if config is None or not config.filter_json:
                raise ValueError("Batch Submit is no longer configured for this table")

            sa_table = schema_service.build_data_table(table.physical_table_name, fields)
            real_fields = [f for f in fields if not get_field_type(f.field_type).is_virtual]
            columns_map = {f.name: sa_table.c[f.db_column_name] for f in real_fields}
            where_clause = compile_filter(parse_filter_expr(config.filter_json), columns_map)

            rows = (
                await db.execute(select(sa_table).where(where_clause).order_by(sa_table.c._row_id))
            ).all()

            batch_size = job.batch_size
            batch_results: list[dict] = []
            sent_batches = 0
            failed_batches = 0

            for batch_index, start in enumerate(range(0, len(rows), batch_size)):
                chunk = rows[start : start + batch_size]
                row_payloads = []
                row_ids = []
                for row in chunk:
                    mapping = row._mapping
                    row_id = mapping["_row_id"]
                    row_ids.append(row_id)
                    values = {
                        f.name: json_safe(get_field_type(f.field_type).from_storage(mapping[f.db_column_name], f.options))
                        for f in real_fields
                    }
                    row_payloads.append({"row_id": row_id, "values": values})

                payload = {"table_id": str(table.id), "batch_index": batch_index, "rows": row_payloads}
                try:
                    await post_json(config.url, config.headers, payload)
                except (httpx.HTTPStatusError, httpx.RequestError, RetryError) as exc:
                    # post_json retries transient failures itself (tenacity);
                    # once its own retries are exhausted it raises
                    # RetryError wrapping the real httpx exception, not that
                    # exception directly -- without catching RetryError too,
                    # a genuine network failure here would escape this
                    # per-batch try/except entirely and fail the WHOLE job
                    # (losing every other batch's results), the opposite of
                    # "a batch failing never stops the rest."
                    failed_batches += 1
                    batch_results.append({"batch_index": batch_index, "row_ids": row_ids, "status": "failed", "error": str(exc)[:500]})
                else:
                    sent_batches += 1
                    batch_results.append({"batch_index": batch_index, "row_ids": row_ids, "status": "sent"})

                job.sent_batches = sent_batches
                job.failed_batches = failed_batches
                job.batch_results = batch_results
                # batch_results is mutated in place (the same list object
                # every iteration, just appended to) -- a plain JSON-mapped
                # column only detects a *reassignment to a different object*
                # as dirty, so without this, every commit after the first
                # silently drops back to whatever was written that first
                # time (SQLAlchemy sees "same object == no change" and
                # leaves it out of the UPDATE).
                flag_modified(job, "batch_results")
                await db.commit()

            if failed_batches == 0:
                job.status = "completed"
            elif sent_batches == 0:
                job.status = "failed"
                job.error = "Every batch failed to send"
            else:
                job.status = "partially_failed"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

            await NotificationService(db).create(
                user_id=job.created_by,
                title=_NOTIFICATION_TITLES[job.status],
                message=f"{sent_batches} of {sent_batches + failed_batches} batch(es) sent ({job.total_rows} row(s) marked).",
                link=f"/tables/{job.table_id}?batchSubmitJob={job.id}",
            )
        except Exception as exc:
            await db.rollback()
            job.status = "failed"
            job.error = str(exc)[:1000]
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            await NotificationService(db).create(
                user_id=job.created_by,
                title="Batch send failed",
                message=job.error,
                link=f"/tables/{job.table_id}?batchSubmitJob={job.id}",
            )
