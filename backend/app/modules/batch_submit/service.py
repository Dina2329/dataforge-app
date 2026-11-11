import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.query.filter_dsl import compile_filter, parse_filter_expr
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.service import BasesService
from app.modules.batch_submit.models import BatchSubmitConfig, BatchSubmitJob
from app.modules.batch_submit.repository import BatchSubmitConfigRepository, BatchSubmitJobRepository
from app.modules.workspaces.permissions import Permission
from app.worker.arq_app import get_arq_pool

MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 1000


class BatchSubmitService:
    """Per-table "send every row matching a filter condition to an external
    API, in chunks" config + job lifecycle. Deliberately separate from
    RecordSubmitService (the per-row Submit button): different config, own
    URL, and a manual batch trigger rather than a per-row action."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.bases = BasesService(db)
        self.config_repo = BatchSubmitConfigRepository(db)
        self.job_repo = BatchSubmitJobRepository(db)

    # -- Config -----------------------------------------------------------------

    async def get_config(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> BatchSubmitConfig | None:
        await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        return await self.config_repo.get_for_table(table_id)

    async def upsert_config(
        self,
        *,
        table_id: uuid.UUID,
        user_id: uuid.UUID,
        url: str,
        headers: dict[str, Any] | None,
        filter_dict: dict[str, Any],
        batch_size: int,
    ) -> BatchSubmitConfig:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)

        if not url.strip() or not url.strip().lower().startswith(("http://", "https://")):
            raise ValidationError("url must be a non-empty http(s):// URL")
        if not (MIN_BATCH_SIZE <= batch_size <= MAX_BATCH_SIZE):
            raise ValidationError(f"batch_size must be between {MIN_BATCH_SIZE} and {MAX_BATCH_SIZE}")

        await self._compile_table_filter(table_id=table_id, filter_dict=filter_dict)

        config = await self.config_repo.upsert(
            table_id=table_id, url=url.strip(), headers=headers, filter_dict=filter_dict, batch_size=batch_size, created_by=user_id
        )
        await self.db.commit()
        return config

    async def _compile_table_filter(self, *, table_id: uuid.UUID, filter_dict: dict[str, Any]):
        """Validates filter_dict against this table's real (non-virtual)
        fields and returns the compiled WHERE clause -- same columns_map
        pattern dashboards/bulk_ops already use (architecture plan, section
        2: one filter language, every call site)."""
        table = await self.bases.tables.get(table_id)
        fields = await self.bases.fields.list_for_table(table_id)
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        columns_map = {f.name: sa_table.c[f.db_column_name] for f in fields if not get_field_type(f.field_type).is_virtual}
        return sa_table, compile_filter(parse_filter_expr(filter_dict), columns_map)

    async def _require_ready_config(self, *, table_id: uuid.UUID) -> BatchSubmitConfig:
        config = await self.config_repo.get_for_table(table_id)
        if config is None or not config.filter_json:
            raise ValidationError("Batch Submit isn't configured for this table yet (set a URL and a condition)")
        return config

    async def _count_matching(self, *, table_id: uuid.UUID, config: BatchSubmitConfig) -> int:
        sa_table, where_clause = await self._compile_table_filter(table_id=table_id, filter_dict=config.filter_json)
        return (await self.db.execute(select(func.count()).select_from(sa_table).where(where_clause))).scalar_one()

    async def preview(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> dict[str, int]:
        """Read-only: how many rows currently match the configured condition,
        and how many batches that'll take -- for the Send dialog to show
        before the user commits to actually sending anything."""
        await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        config = await self._require_ready_config(table_id=table_id)
        matched_count = await self._count_matching(table_id=table_id, config=config)
        total_batches = (matched_count + config.batch_size - 1) // config.batch_size if matched_count else 0
        return {"matched_count": matched_count, "batch_size": config.batch_size, "total_batches": total_batches}

    # -- Jobs -----------------------------------------------------------------

    async def create_job(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> BatchSubmitJob:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.RECORD_WRITE)
        config = await self._require_ready_config(table_id=table_id)

        matched_count = await self._count_matching(table_id=table_id, config=config)
        if matched_count == 0:
            raise ValidationError("No rows currently match the configured condition")

        total_batches = (matched_count + config.batch_size - 1) // config.batch_size

        try:
            job = await self.job_repo.create(
                table_id=table_id, batch_size=config.batch_size, total_rows=matched_count, total_batches=total_batches, created_by=user_id
            )
        except IntegrityError as exc:
            await self.db.rollback()
            constraint = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
            if constraint == "uq_batch_submit_job_active_per_table":
                raise ConflictError("A batch send for this table is already in progress") from exc
            raise

        await self.db.commit()
        pool = await get_arq_pool()
        await pool.enqueue_job("run_batch_submit_job", str(job.id))
        return job

    async def get_job(self, *, job_id: uuid.UUID, user_id: uuid.UUID) -> BatchSubmitJob:
        job = await self.job_repo.get(job_id)
        if job is None:
            raise NotFoundError("Job not found")
        await self.bases.check_table_access(table_id=job.table_id, user_id=user_id)
        if job.created_by != user_id:
            raise NotFoundError("Job not found")
        return job

    async def list_jobs(self, *, table_id: uuid.UUID, user_id: uuid.UUID, include_dismissed: bool) -> list[BatchSubmitJob]:
        await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        return await self.job_repo.list_for_table(table_id=table_id, created_by=user_id, include_dismissed=include_dismissed)

    async def dismiss_job(self, *, job_id: uuid.UUID, user_id: uuid.UUID) -> None:
        job = await self.get_job(job_id=job_id, user_id=user_id)
        if job.status in ("queued", "running"):
            raise ValidationError("Can't dismiss a job that's still queued or running")
        job.dismissed = True
        await self.db.commit()
