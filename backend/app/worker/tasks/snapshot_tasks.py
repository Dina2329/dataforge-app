"""Daily automatic base snapshots -- one per Base, every day, retained for
AUTO_SNAPSHOT_RETENTION_DAYS (manual snapshots are never auto-deleted, only
these are). Mirrors scripts/backup.sh's cadence/retention shape, one level
up: that script protects the whole database from infrastructure-level loss;
this protects one Base's data from a bad edit, through the app's own actual
restore path (SnapshotService.restore_snapshot), not a DBA operation.

Deliberately not run_at_startup, unlike the per-minute cron jobs elsewhere in
this worker -- a once-daily job firing on every worker restart during dev
would create a fresh "automatic" snapshot far more often than once a day.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.core.db import SessionLocal
from app.modules.bases import schema_service
from app.modules.bases.repository import BaseRepository

AUTO_SNAPSHOT_RETENTION_DAYS = 7


async def tick_daily_snapshots(ctx: dict) -> None:
    # Deferred: SnapshotService -> RecordService -> AutomationService ->
    # app.worker.arq_app.get_arq_pool, and arq_app.py is what imports this
    # module (to register the cron job) -- a module-level import here would
    # be circular. By the time this function actually runs, arq_app has long
    # since finished initializing.
    from app.modules.snapshots.service import SnapshotService

    async with SessionLocal() as db:
        service = SnapshotService(db)
        for base in await BaseRepository(db).list_all():
            if not base.auto_snapshots_enabled:
                continue
            try:
                await service.create_snapshot_unchecked(base_id=base.id, created_by=base.created_by, is_automatic=True)
                await _prune_old_automatic_snapshots(service, base.id)
            except Exception:
                # One base's snapshot failing (e.g. a physical table gone
                # missing underneath it) must never block every other base's
                # daily snapshot from happening.
                await db.rollback()
                continue


async def _prune_old_automatic_snapshots(service: "SnapshotService", base_id: uuid.UUID) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=AUTO_SNAPSHOT_RETENTION_DAYS)
    for snapshot in await service.repo.list_automatic_for_base(base_id):
        if snapshot.created_at < cutoff:
            for snap_table in await service.repo.list_tables(snapshot.id):
                await schema_service.drop_snapshot_copy(service.db, snap_table.physical_snapshot_table)
            await service.repo.delete(snapshot)
    await service.db.commit()
