import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.missing_terms.models import (
    MissingTermsApiConfig,
    MissingTermsConfig,
    MissingTermsIgnoredTerm,
    MissingTermsJob,
    MissingTermsJobRow,
    PrerequestTerm,
    PrerequestUpload,
)


def _normalize(value: str) -> str:
    """Same rule as missing_terms/service.py's normalize() -- duplicated
    (not imported) to avoid a circular import, since service.py imports
    this module's repository classes."""
    return " ".join(value.strip().split()).lower()


class PrerequestRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_upload(self, workspace_id: uuid.UUID) -> PrerequestUpload | None:
        result = await self.db.execute(select(PrerequestUpload).where(PrerequestUpload.workspace_id == workspace_id))
        return result.scalar_one_or_none()

    async def replace(
        self, *, workspace_id: uuid.UUID, original_filename: str, rows: list[dict[str, Any]], uploaded_by: uuid.UUID
    ) -> PrerequestUpload:
        """Full replace -- delete every existing term for this workspace,
        insert the new set, in the same transaction (the caller commits)."""
        await self.db.execute(delete(PrerequestTerm).where(PrerequestTerm.workspace_id == workspace_id))

        existing = await self.get_upload(workspace_id)
        if existing is not None:
            existing.original_filename = original_filename
            existing.row_count = len(rows)
            existing.uploaded_by = uploaded_by
            upload = existing
        else:
            upload = PrerequestUpload(
                workspace_id=workspace_id, original_filename=original_filename, row_count=len(rows), uploaded_by=uploaded_by
            )
            self.db.add(upload)

        self.db.add_all(
            [
                PrerequestTerm(
                    workspace_id=workspace_id,
                    estate=row.get("estate") or None,
                    building=row.get("building") or None,
                    unit=row.get("unit") or None,
                    sub_domain=row["sub_domain"],
                    term_name=row["term_name"],
                )
                for row in rows
            ]
        )
        await self.db.flush()
        return upload

    async def delete(self, workspace_id: uuid.UUID) -> bool:
        """Removes the prerequest list entirely (not a replace) -- every
        table's gap detection then has nothing to compare against until a
        new list is uploaded. Returns False if there was nothing to delete."""
        upload = await self.get_upload(workspace_id)
        if upload is None:
            return False
        await self.db.execute(delete(PrerequestTerm).where(PrerequestTerm.workspace_id == workspace_id))
        await self.db.delete(upload)
        await self.db.flush()
        return True


class MissingTermsApiConfigRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for_workspace(self, workspace_id: uuid.UUID) -> MissingTermsApiConfig | None:
        result = await self.db.execute(select(MissingTermsApiConfig).where(MissingTermsApiConfig.workspace_id == workspace_id))
        return result.scalar_one_or_none()

    async def upsert(
        self, *, workspace_id: uuid.UUID, api_url: str, headers: dict[str, Any] | None, updated_by: uuid.UUID
    ) -> MissingTermsApiConfig:
        existing = await self.get_for_workspace(workspace_id)
        if existing is not None:
            existing.api_url = api_url
            existing.headers = headers
            existing.updated_by = updated_by
            await self.db.flush()
            return existing

        config = MissingTermsApiConfig(workspace_id=workspace_id, api_url=api_url, headers=headers, updated_by=updated_by)
        self.db.add(config)
        await self.db.flush()
        return config


class MissingTermsConfigRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_for_table(self, table_id: uuid.UUID) -> MissingTermsConfig | None:
        result = await self.db.execute(select(MissingTermsConfig).where(MissingTermsConfig.table_id == table_id))
        return result.scalar_one_or_none()

    async def upsert(
        self,
        *,
        table_id: uuid.UUID,
        estate: str | None,
        building: str | None,
        unit: str | None,
        field_mapping: dict[str, str],
        created_by: uuid.UUID,
    ) -> MissingTermsConfig:
        existing = await self.get_for_table(table_id)
        if existing is not None:
            existing.estate = estate
            existing.building = building
            existing.unit = unit
            existing.field_mapping = field_mapping
            await self.db.flush()
            return existing

        config = MissingTermsConfig(
            table_id=table_id, estate=estate, building=building, unit=unit, field_mapping=field_mapping, created_by=created_by
        )
        self.db.add(config)
        await self.db.flush()
        return config


class MissingTermsJobRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        table_id: uuid.UUID,
        idempotency_key: str,
        submitted_rows: list[dict[str, Any]],
        normalized_pairs: list[tuple[str, str]],
        created_by: uuid.UUID,
    ) -> MissingTermsJob:
        job = MissingTermsJob(
            table_id=table_id, idempotency_key=idempotency_key, submitted_rows=submitted_rows, created_by=created_by
        )
        self.db.add(job)
        # flush (not commit) -- lets the partial unique index's IntegrityError
        # surface at the earliest point, while the caller still holds the
        # transaction and can catch/convert it cleanly.
        await self.db.flush()
        self.db.add_all(
            [MissingTermsJobRow(job_id=job.id, sub_domain_norm=sd, term_name_norm=tn) for sd, tn in normalized_pairs]
        )
        await self.db.flush()
        return job

    async def get(self, job_id: uuid.UUID) -> MissingTermsJob | None:
        return await self.db.get(MissingTermsJob, job_id)

    async def list_for_table(self, *, table_id: uuid.UUID, created_by: uuid.UUID, include_dismissed: bool) -> list[MissingTermsJob]:
        stmt = select(MissingTermsJob).where(MissingTermsJob.table_id == table_id, MissingTermsJob.created_by == created_by)
        if not include_dismissed:
            stmt = stmt.where(MissingTermsJob.dismissed.is_(False))
        stmt = stmt.order_by(MissingTermsJob.created_at.desc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


class MissingTermsIgnoredRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def add(self, *, table_id: uuid.UUID, sub_domain: str, term_name: str, created_by: uuid.UUID) -> MissingTermsIgnoredTerm:
        """Idempotent -- ignoring an already-ignored term just returns the
        existing row rather than erroring, so the UI never needs to check
        first."""
        sub_norm, term_norm = _normalize(sub_domain), _normalize(term_name)
        existing = await self._get(table_id=table_id, sub_domain_norm=sub_norm, term_name_norm=term_norm)
        if existing is not None:
            return existing

        row = MissingTermsIgnoredTerm(
            table_id=table_id, sub_domain=sub_domain.strip(), term_name=term_name.strip(), sub_domain_norm=sub_norm, term_name_norm=term_norm, created_by=created_by
        )
        self.db.add(row)
        try:
            await self.db.flush()
        except IntegrityError:
            # Lost a race with a concurrent identical ignore -- fine, the
            # end state is the same either way.
            await self.db.rollback()
            existing = await self._get(table_id=table_id, sub_domain_norm=sub_norm, term_name_norm=term_norm)
            if existing is not None:
                return existing
            raise
        return row

    async def remove(self, *, table_id: uuid.UUID, sub_domain: str, term_name: str) -> bool:
        existing = await self._get(table_id=table_id, sub_domain_norm=_normalize(sub_domain), term_name_norm=_normalize(term_name))
        if existing is None:
            return False
        await self.db.delete(existing)
        await self.db.flush()
        return True

    async def list_for_table(self, table_id: uuid.UUID) -> list[MissingTermsIgnoredTerm]:
        result = await self.db.execute(
            select(MissingTermsIgnoredTerm).where(MissingTermsIgnoredTerm.table_id == table_id).order_by(MissingTermsIgnoredTerm.created_at.desc())
        )
        return list(result.scalars().all())

    async def _get(self, *, table_id: uuid.UUID, sub_domain_norm: str, term_name_norm: str) -> MissingTermsIgnoredTerm | None:
        result = await self.db.execute(
            select(MissingTermsIgnoredTerm).where(
                MissingTermsIgnoredTerm.table_id == table_id,
                MissingTermsIgnoredTerm.sub_domain_norm == sub_domain_norm,
                MissingTermsIgnoredTerm.term_name_norm == term_name_norm,
            )
        )
        return result.scalar_one_or_none()
