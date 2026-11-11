"""arq job queue setup (architecture plan, section 5) — async-native so
connector/DB I/O runs natively in the worker's event loop, and Redis is
already required elsewhere so this adds no new infra dependency.
"""

from arq import cron, create_pool, func
from arq.connections import ArqRedis, RedisSettings

import app.all_models  # noqa: F401  (registers every ORM model before any DB op runs)
from app.config import settings
from app.worker.tasks.audit_tasks import write_audit_log_entry
from app.worker.tasks.automation_tasks import run_automation, tick_scheduled_automations
from app.worker.tasks.batch_submit_tasks import run_batch_submit_job
from app.worker.tasks.bulk_ops_tasks import run_bulk_update, undo_bulk_update
from app.worker.tasks.missing_terms_tasks import run_missing_terms_job
from app.worker.tasks.snapshot_tasks import tick_daily_snapshots
from app.worker.tasks.sync_tasks import check_table_sync_deletions, poll_table_sync, push_record_to_source, tick_table_sync_polls

_pool: ArqRedis | None = None


def redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def get_arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(redis_settings())
    return _pool


class WorkerSettings:
    functions = [
        run_bulk_update,
        undo_bulk_update,
        run_automation,
        write_audit_log_entry,
        push_record_to_source,
        poll_table_sync,
        check_table_sync_deletions,
        # Default job_timeout (5 min) is too tight: the external lookup this
        # task waits on can itself take minutes (see submit_and_await_result
        # in webhook_client.py), so this one task gets a longer allowance.
        func(run_missing_terms_job, timeout=900),
        # Same reasoning -- potentially many batches, each with its own
        # retry-with-backoff on a slow/flaky endpoint, can add up well past
        # the default 5 min for a large marked set.
        func(run_batch_submit_job, timeout=1800),
    ]
    cron_jobs = [
        cron(tick_scheduled_automations, minute=set(range(60)), run_at_startup=True),
        cron(tick_table_sync_polls, minute=set(range(60)), run_at_startup=True),
        # 3:00 AM, once a day -- offset from scripts/backup.sh's 2:30 AM DB
        # backup so the two don't compete for the same minute. Deliberately
        # not run_at_startup (see snapshot_tasks.py's module docstring).
        cron(tick_daily_snapshots, hour={3}, minute={0}),
    ]
    redis_settings = redis_settings()
