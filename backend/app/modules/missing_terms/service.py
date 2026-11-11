import csv
import hashlib
import io
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.modules.bases import schema_service
from app.modules.bases.service import BasesService
from app.modules.missing_terms.models import (
    MissingTermsApiConfig,
    MissingTermsConfig,
    MissingTermsIgnoredTerm,
    MissingTermsJob,
    MissingTermsJobRow,
    PrerequestTerm,
    PrerequestUpload,
)
from app.modules.missing_terms.repository import (
    MissingTermsApiConfigRepository,
    MissingTermsConfigRepository,
    MissingTermsIgnoredRepository,
    MissingTermsJobRepository,
    PrerequestRepository,
)
from app.modules.records.schemas import RecordResponse
from app.modules.records.service import RecordService
from app.modules.workspaces.permissions import Permission
from app.modules.workspaces.service import WorkspaceService
from app.worker.arq_app import get_arq_pool

_REQUIRED_PREREQUEST_HEADERS = {"subdomain": "sub_domain", "termname": "term_name"}
_OPTIONAL_PREREQUEST_HEADERS = {"estate": "estate", "building": "building", "unit": "unit"}


def _normalize_header(header: str) -> str:
    """Spaces, hyphens, and underscores are all the same separator to a CSV
    author -- "Sub-Domain", "Sub Domain", and "sub_domain" must all match
    the same canonical column, not just the one literal spelling."""
    return re.sub(r"[\s_-]+", "", header.strip().lower())


def normalize(value: str | None) -> str:
    """trim + case-insensitive + collapse whitespace, exactly as spec'd."""
    if value is None:
        return ""
    return " ".join(value.strip().split()).lower()


def _idempotency_key(rows: list[dict[str, Any]]) -> str:
    """Order-independent -- the same batch submitted with its rows in a
    different order must still collide, so sort by the natural key first."""
    canonical_rows = sorted(
        ({"sub_domain": normalize(r.get("sub_domain")), "term_name": normalize(r.get("term_name")),
          "page": r.get("page"), "pdf_image": r.get("pdf_image"), "pdf_name": r.get("pdf_name"), "keywords": r.get("keywords")} for r in rows),
        key=lambda r: (r["sub_domain"], r["term_name"]),
    )
    canonical = json.dumps(canonical_rows, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _parse_prerequest_csv(csv_text: str) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(csv_text))
    headers = reader.fieldnames or []
    header_map: dict[str, str] = {}
    headers_normalized = {_normalize_header(h): h for h in headers}
    missing = []
    for canonical_lower, slot in _REQUIRED_PREREQUEST_HEADERS.items():
        if canonical_lower not in headers_normalized:
            missing.append(slot)
        else:
            header_map[slot] = headers_normalized[canonical_lower]
    if missing:
        raise ValidationError(f"Prerequest CSV is missing required column(s): {', '.join(missing)}")
    for canonical_lower, slot in _OPTIONAL_PREREQUEST_HEADERS.items():
        if canonical_lower in headers_normalized:
            header_map[slot] = headers_normalized[canonical_lower]

    rows = []
    for row in reader:
        sub_domain = (row.get(header_map["sub_domain"]) or "").strip()
        term_name = (row.get(header_map["term_name"]) or "").strip()
        if not sub_domain or not term_name:
            continue
        rows.append(
            {
                "estate": (row.get(header_map["estate"]) or "").strip() if "estate" in header_map else None,
                "building": (row.get(header_map["building"]) or "").strip() if "building" in header_map else None,
                "unit": (row.get(header_map["unit"]) or "").strip() if "unit" in header_map else None,
                "sub_domain": sub_domain,
                "term_name": term_name,
            }
        )
    return rows


class MissingTermsService:
    """Shared-prerequest gap detection + async "ask an external API for
    candidate rows" job lifecycle + reviewed import, generalizing the
    CSV-comparison feature built/deleted/rebuilt/deleted earlier this
    session. Field-name mapping and "unrecognized response keys are dropped,
    never block an insert" are both first-class from the start this time."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.bases = BasesService(db)
        self.workspaces = WorkspaceService(db)
        self.prerequest_repo = PrerequestRepository(db)
        self.api_config_repo = MissingTermsApiConfigRepository(db)
        self.config_repo = MissingTermsConfigRepository(db)
        self.job_repo = MissingTermsJobRepository(db)
        self.ignored_repo = MissingTermsIgnoredRepository(db)

    # -- Prerequest (workspace-scoped, admin-only) --------------------------

    async def get_prerequest(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> PrerequestUpload | None:
        await self.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.PREREQUEST_MANAGE)
        return await self.prerequest_repo.get_upload(workspace_id)

    async def replace_prerequest(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, filename: str, csv_text: str
    ) -> PrerequestUpload:
        await self.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.PREREQUEST_MANAGE)
        rows = _parse_prerequest_csv(csv_text)
        if not rows:
            raise ValidationError("Prerequest CSV has no valid rows (Sub-Domain and Term Name are both required per row)")
        upload = await self.prerequest_repo.replace(workspace_id=workspace_id, original_filename=filename, rows=rows, uploaded_by=user_id)
        await self.db.commit()
        return upload

    async def delete_prerequest(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> None:
        await self.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.PREREQUEST_MANAGE)
        deleted = await self.prerequest_repo.delete(workspace_id)
        if not deleted:
            raise NotFoundError("No prerequest list to delete")
        await self.db.commit()

    # -- External API config (workspace-scoped, admin-only, live --------------
    # no app restart needed to change it, unlike an env var) -----------------

    async def get_api_config(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> MissingTermsApiConfig | None:
        await self.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.PREREQUEST_MANAGE)
        return await self.api_config_repo.get_for_workspace(workspace_id)

    async def upsert_api_config(
        self, *, workspace_id: uuid.UUID, user_id: uuid.UUID, api_url: str, headers: dict[str, Any] | None
    ) -> MissingTermsApiConfig:
        await self.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.PREREQUEST_MANAGE)
        if not api_url.strip() or not api_url.strip().lower().startswith(("http://", "https://")):
            raise ValidationError("api_url must be a non-empty http(s):// URL")
        config = await self.api_config_repo.upsert(workspace_id=workspace_id, api_url=api_url.strip(), headers=headers, updated_by=user_id)
        await self.db.commit()
        return config

    # -- Per-table config ----------------------------------------------------

    async def get_config(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> MissingTermsConfig | None:
        await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        return await self.config_repo.get_for_table(table_id)

    async def upsert_config(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, estate: str | None, building: str | None, unit: str | None, field_mapping: dict[str, str]
    ) -> MissingTermsConfig:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        if field_mapping:
            field_ids = {f.id for f in await self.bases.fields.list_for_table(table_id)}
            unknown = {v for v in field_mapping.values() if uuid.UUID(v) not in field_ids}
            if unknown:
                raise ValidationError(f"field_mapping points at unknown field id(s): {', '.join(sorted(unknown))}")
        config = await self.config_repo.upsert(
            table_id=table_id, estate=estate, building=building, unit=unit, field_mapping=field_mapping, created_by=user_id
        )
        await self.db.commit()
        return config

    async def _require_ready_config(self, *, table_id: uuid.UUID) -> MissingTermsConfig:
        config = await self.config_repo.get_for_table(table_id)
        if config is None or "sub_domain" not in config.field_mapping or "term_name" not in config.field_mapping:
            raise ValidationError("Missing Terms Check isn't configured for this table yet (map Sub-Domain and Term Name first)")
        return config

    async def _mapped_field(self, *, table_id: uuid.UUID, config: MissingTermsConfig, slot: str):
        field_id = config.field_mapping.get(slot)
        if field_id is None:
            return None
        fields = await self.bases.fields.list_for_table(table_id)
        return next((f for f in fields if str(f.id) == field_id), None)

    # -- Gap detection --------------------------------------------------------

    async def get_missing_terms(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, cursor: int, limit: int
    ) -> tuple[dict[str, int], list[dict[str, Any]], bool]:
        table = await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        workspace_id = await self.bases.get_workspace_id_for_table(table_id)
        config = await self._require_ready_config(table_id=table_id)

        fields = await self.bases.fields.list_for_table(table_id)
        sub_domain_field = await self._mapped_field(table_id=table_id, config=config, slot="sub_domain")
        term_name_field = await self._mapped_field(table_id=table_id, config=config, slot="term_name")
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        sub_col = sa_table.c[sub_domain_field.db_column_name]
        term_col = sa_table.c[term_name_field.db_column_name]

        # A prerequest row that doesn't carry a given scope field at all (null
        # or blank -- common when the shared CSV never had an Estate/Building/
        # Unit column) is treated as applying to every table regardless of its
        # configured scope; only a row that specifies a DIFFERENT value for
        # that field gets excluded. This also means the scope value doubles as
        # a fallback tag for display/submission (see the row-merging below)
        # when the prerequest itself has nothing more specific to offer.
        base_filter = [PrerequestTerm.workspace_id == workspace_id]
        for scope_value, column in ((config.estate, PrerequestTerm.estate), (config.building, PrerequestTerm.building), (config.unit, PrerequestTerm.unit)):
            if scope_value is not None:
                base_filter.append(or_(column.is_(None), func.trim(column) == "", func.lower(func.trim(column)) == normalize(scope_value)))

        already_in_table = exists(
            select(1).where(
                func.lower(func.trim(sub_col)) == func.lower(func.trim(PrerequestTerm.sub_domain)),
                func.lower(func.trim(term_col)) == func.lower(func.trim(PrerequestTerm.term_name)),
            )
        )
        in_active_job = exists(
            select(1)
            .select_from(MissingTermsJobRow)
            .join(MissingTermsJob, MissingTermsJobRow.job_id == MissingTermsJob.id)
            .where(
                MissingTermsJob.table_id == table_id,
                MissingTermsJob.status.in_(("queued", "running")),
                func.lower(func.trim(MissingTermsJobRow.sub_domain_norm)) == func.lower(func.trim(PrerequestTerm.sub_domain)),
                func.lower(func.trim(MissingTermsJobRow.term_name_norm)) == func.lower(func.trim(PrerequestTerm.term_name)),
            )
        )
        is_ignored = exists(
            select(1)
            .select_from(MissingTermsIgnoredTerm)
            .where(
                MissingTermsIgnoredTerm.table_id == table_id,
                func.lower(func.trim(MissingTermsIgnoredTerm.sub_domain_norm)) == func.lower(func.trim(PrerequestTerm.sub_domain)),
                func.lower(func.trim(MissingTermsIgnoredTerm.term_name_norm)) == func.lower(func.trim(PrerequestTerm.term_name)),
            )
        )

        total = (await self.db.execute(select(func.count()).select_from(PrerequestTerm).where(*base_filter))).scalar_one()
        matched = (await self.db.execute(select(func.count()).select_from(PrerequestTerm).where(*base_filter, already_in_table))).scalar_one()
        in_progress = (
            await self.db.execute(select(func.count()).select_from(PrerequestTerm).where(*base_filter, ~already_in_table, in_active_job))
        ).scalar_one()
        ignored = (
            await self.db.execute(
                select(func.count()).select_from(PrerequestTerm).where(*base_filter, ~already_in_table, ~in_active_job, is_ignored)
            )
        ).scalar_one()
        missing = total - matched - in_progress - ignored

        rows_stmt = (
            select(PrerequestTerm)
            .where(*base_filter, ~already_in_table, ~in_active_job, ~is_ignored)
            .order_by(PrerequestTerm.sub_domain, PrerequestTerm.term_name)
            .offset(cursor)
            .limit(limit + 1)
        )
        rows = list((await self.db.execute(rows_stmt)).scalars().all())
        has_more = len(rows) > limit
        rows = rows[:limit]

        # Fall back to the table's own configured scope wherever the
        # prerequest row itself didn't specify one -- never overrides a real
        # per-row value, only fills in what the shared list left blank.
        merged_rows = [
            {
                "estate": r.estate or config.estate,
                "building": r.building or config.building,
                "unit": r.unit or config.unit,
                "sub_domain": r.sub_domain,
                "term_name": r.term_name,
            }
            for r in rows
        ]

        return {"total": total, "matched": matched, "missing": missing, "in_progress": in_progress, "ignored": ignored}, merged_rows, has_more

    # -- Ignored terms ----------------------------------------------------------

    async def ignore_term(self, *, table_id: uuid.UUID, user_id: uuid.UUID, sub_domain: str, term_name: str) -> None:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.RECORD_WRITE)
        await self.ignored_repo.add(table_id=table_id, sub_domain=sub_domain, term_name=term_name, created_by=user_id)
        await self.db.commit()

    async def unignore_term(self, *, table_id: uuid.UUID, user_id: uuid.UUID, sub_domain: str, term_name: str) -> None:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.RECORD_WRITE)
        await self.ignored_repo.remove(table_id=table_id, sub_domain=sub_domain, term_name=term_name)
        await self.db.commit()

    async def list_ignored(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> list[MissingTermsIgnoredTerm]:
        await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        return await self.ignored_repo.list_for_table(table_id)

    # -- Jobs -----------------------------------------------------------------

    async def create_job(self, *, table_id: uuid.UUID, user_id: uuid.UUID, rows: list[dict[str, Any]]) -> MissingTermsJob:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.RECORD_WRITE)
        await self._require_ready_config(table_id=table_id)

        submittable = [r for r in rows if (r.get("page") or r.get("pdf_image") or r.get("pdf_name") or r.get("keywords"))]
        if not submittable:
            raise ValidationError("Fill in at least one of page / PDF-Image / PDF Name / keywords on at least one row before submitting")

        idempotency_key = _idempotency_key(submittable)
        normalized_pairs = [(normalize(r["sub_domain"]), normalize(r["term_name"])) for r in submittable]
        try:
            job = await self.job_repo.create(
                table_id=table_id, idempotency_key=idempotency_key, submitted_rows=submittable, normalized_pairs=normalized_pairs, created_by=user_id
            )
        except IntegrityError as exc:
            await self.db.rollback()
            constraint = getattr(getattr(exc.orig, "__cause__", None), "constraint_name", None)
            if constraint == "uq_missing_terms_job_active_idempotency":
                raise ConflictError("A job for this exact set of rows is already queued or running on this table") from exc
            raise

        await self.db.commit()
        pool = await get_arq_pool()
        await pool.enqueue_job("run_missing_terms_job", str(job.id))
        return job

    async def get_job(self, *, job_id: uuid.UUID, user_id: uuid.UUID) -> MissingTermsJob:
        job = await self.job_repo.get(job_id)
        if job is None:
            raise NotFoundError("Job not found")
        await self.bases.check_table_access(table_id=job.table_id, user_id=user_id)
        if job.created_by != user_id:
            raise NotFoundError("Job not found")
        return job

    async def list_jobs(self, *, table_id: uuid.UUID, user_id: uuid.UUID, include_dismissed: bool) -> list[MissingTermsJob]:
        await self.bases.check_table_access(table_id=table_id, user_id=user_id)
        return await self.job_repo.list_for_table(table_id=table_id, created_by=user_id, include_dismissed=include_dismissed)

    async def retry_job(self, *, job_id: uuid.UUID, user_id: uuid.UUID) -> MissingTermsJob:
        job = await self.get_job(job_id=job_id, user_id=user_id)
        await self.bases.check_table_permission(table_id=job.table_id, user_id=user_id, permission=Permission.RECORD_WRITE)
        if job.status not in ("failed", "partially_failed"):
            raise ValidationError(f"Job is '{job.status}', only a failed job can be retried")
        job.status = "queued"
        job.error = None
        await self.db.commit()
        pool = await get_arq_pool()
        await pool.enqueue_job("run_missing_terms_job", str(job.id))
        return job

    async def dismiss_job(self, *, job_id: uuid.UUID, user_id: uuid.UUID) -> None:
        job = await self.get_job(job_id=job_id, user_id=user_id)
        if job.status in ("queued", "running"):
            raise ValidationError("Can't dismiss a job that's still queued or running")
        job.dismissed = True
        await self.db.commit()

    # -- Import -----------------------------------------------------------------

    async def _find_duplicate_row_id(
        self, *, sa_table, sub_col_name: str, term_col_name: str, sub_domain: str, term_name: str, extra_col_name: str | None = None, extra_value: Any = None
    ) -> int | None:
        sub_col = sa_table.c[sub_col_name]
        term_col = sa_table.c[term_col_name]
        conditions = [func.lower(func.trim(sub_col)) == normalize(sub_domain), func.lower(func.trim(term_col)) == normalize(term_name)]
        if extra_col_name is not None:
            # Some tables are long/EAV-shaped -- one row per extracted FIELD
            # of a term, not one row per term -- so sub_domain + term_name
            # alone isn't a unique key there; the candidate's own "field"
            # value (e.g. "component_name" vs "model_name") disambiguates
            # which of that term's many rows this selection actually matches.
            conditions.append(func.lower(func.trim(sa_table.c[extra_col_name])) == normalize(str(extra_value)))
        stmt = select(sa_table.c["_row_id"]).where(*conditions)
        result = await self.db.execute(stmt)
        row = result.first()
        return row[0] if row else None

    async def import_results(self, *, job_id: uuid.UUID, user_id: uuid.UUID, selections: list[dict[str, Any]]) -> list[dict[str, Any]]:
        job = await self.get_job(job_id=job_id, user_id=user_id)
        await self.bases.check_table_permission(table_id=job.table_id, user_id=user_id, permission=Permission.RECORD_WRITE)
        if job.response_rows is None:
            raise ValidationError("This job has no results to import yet")

        config = await self._require_ready_config(table_id=job.table_id)
        fields = await self.bases.fields.list_for_table(job.table_id)
        fields_by_id = {str(f.id): f for f in fields}
        field_names = {f.name for f in fields}
        sub_domain_field = fields_by_id[config.field_mapping["sub_domain"]]
        term_name_field = fields_by_id[config.field_mapping["term_name"]]

        record_service = RecordService(self.db)
        imported_keys = set(job.imported_keys or [])
        results: list[dict[str, Any]] = []

        # No duplicate check against the main table here, by design -- every
        # ticked selection always becomes its own new row. The only thing
        # still prevented is re-importing the exact same (job, candidate)
        # a second time, via imported_keys below; a genuinely new selection
        # is never compared against what's already in the table.
        for sel in selections:
            response_group = next(
                (g for g in job.response_rows if normalize(g.get("sub_domain")) == normalize(sel["sub_domain"]) and normalize(g.get("term_name")) == normalize(sel["term_name"])),
                None,
            )
            if response_group is None or not (0 <= sel["candidate_index"] < len(response_group.get("candidates", []))):
                results.append({"sub_domain": sel["sub_domain"], "term_name": sel["term_name"], "status": "skipped", "row_id": None})
                continue

            import_key = f"{normalize(sel['sub_domain'])}|{normalize(sel['term_name'])}|{sel['candidate_index']}"
            if import_key in imported_keys:
                results.append({"sub_domain": sel["sub_domain"], "term_name": sel["term_name"], "status": "skipped", "row_id": None})
                continue

            candidate = {**response_group["candidates"][sel["candidate_index"]], **(sel.get("overrides") or {})}
            ticked_columns = set(sel.get("columns") or candidate.keys())
            values: dict[str, Any] = {}
            for key, value in candidate.items():
                if key not in ticked_columns:
                    continue
                target_field_id = config.field_mapping.get(key)
                target_field = fields_by_id.get(target_field_id) if target_field_id else None
                target_name = target_field.name if target_field else key
                if target_name in field_names:
                    values[target_name] = value
            values.setdefault(sub_domain_field.name, sel["sub_domain"])
            values.setdefault(term_name_field.name, sel["term_name"])

            response = await record_service.create_record(table_id=job.table_id, user_id=user_id, values=values)
            results.append({"sub_domain": sel["sub_domain"], "term_name": sel["term_name"], "status": "inserted", "row_id": response.row_id})
            imported_keys.add(import_key)

        job.imported_keys = sorted(imported_keys)
        await self.db.commit()
        return results

    # -- Manual entry -----------------------------------------------------------

    async def manual_insert(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, sub_domain: str, term_name: str, values: dict[str, Any], on_conflict: str
    ) -> RecordResponse:
        await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=Permission.RECORD_WRITE)
        config = await self._require_ready_config(table_id=table_id)
        fields = await self.bases.fields.list_for_table(table_id)
        fields_by_id = {str(f.id): f for f in fields}
        sub_domain_field = fields_by_id[config.field_mapping["sub_domain"]]
        term_name_field = fields_by_id[config.field_mapping["term_name"]]
        table = await self.bases.tables.get(table_id)
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)

        record_service = RecordService(self.db)
        duplicate_row_id = await self._find_duplicate_row_id(
            sa_table=sa_table, sub_col_name=sub_domain_field.db_column_name, term_col_name=term_name_field.db_column_name,
            sub_domain=sub_domain, term_name=term_name,
        )
        if duplicate_row_id is not None and on_conflict == "skip":
            raise ConflictError(f"A row for '{sub_domain}' / '{term_name}' already exists (row #{duplicate_row_id})")

        full_values = {**values, sub_domain_field.name: sub_domain, term_name_field.name: term_name}
        if duplicate_row_id is not None:
            existing = await record_service.get_record(table_id=table_id, row_id=duplicate_row_id, user_id=user_id)
            return await record_service.update_record(
                table_id=table_id, row_id=duplicate_row_id, user_id=user_id, values=full_values, expected_version=existing.version
            )
        return await record_service.create_record(table_id=table_id, user_id=user_id, values=full_values)
