import base64
import csv
import io
import json
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, delete, func, insert, nullslast, or_, select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.json_safe import json_safe
from app.core.query.filter_dsl import compile_filter, evaluate_filter, parse_filter_expr
from app.core.ws_manager import manager as ws_manager
from app.modules.audit.service import AuditService
from app.modules.automations.service import AutomationService
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.formula_engine import evaluate_formula
from app.modules.bases.models import Field, Table
from app.modules.bases.service import BasesService
from app.modules.connectors.pending_sync_service import PendingSyncChangeService
from app.modules.connectors.sync_service import TableSyncService
from app.modules.records.schemas import RecordListResponse, RecordResponse
from app.modules.row_policies.service import RowPolicyService
from app.modules.workspaces.models import WorkspaceRole
from app.modules.workspaces.permissions import Permission
from app.worker.arq_app import get_arq_pool

DEFAULT_PAGE_SIZE = 200
MAX_PAGE_SIZE = 1000


def _encode_cursor(row_id: int, sort_values: list[Any]) -> str:
    """Opaque pagination token: the client only ever passes back what the
    server handed it, so this can encode whatever the keyset needs -- here,
    the tiebreaker _row_id plus (when sorting) each sort column's value on
    that row, in priority order, since resuming a multi-column sorted keyset
    scan needs all of them."""
    payload = json.dumps({"r": row_id, "s": [json_safe(v) for v in sort_values]})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[int, list[Any]]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return int(payload["r"]), list(payload.get("s") or [])
    except Exception as exc:
        raise ValidationError("Invalid cursor") from exc


def _keyset_clause(sort_specs: list[tuple[Any, str]], last_values: list[Any], row_id_col: Any, last_row_id: int) -> Any:
    """WHERE clause for resuming a keyset scan ordered by sort_specs (each
    NULLS LAST, in its own asc/desc direction) then row_id ascending.

    For each sort column in priority order, a candidate "this row sorts after
    the cursor" branch is: every higher-priority column tied to the cursor's
    value, AND this column strictly further along (or NULL, since NULLS LAST
    makes NULL maximal regardless of direction). If the cursor's value at a
    position is itself NULL, every remaining row already ties on NULL there
    too (nothing sorts "more NULL"), so that position contributes no branch
    of its own -- only extends the equality prefix for later columns. The
    final branch is "every column tied, row_id greater" -- the pure tiebreak."""
    branches = []
    equal_so_far = []
    for (col, direction), last_value in zip(sort_specs, last_values):
        if last_value is None:
            equal_so_far.append(col.is_(None))
            continue
        further = col < last_value if direction == "desc" else col > last_value
        branches.append(and_(*equal_so_far, or_(col.is_(None), further)))
        equal_so_far.append(col == last_value)
    branches.append(and_(*equal_so_far, row_id_col > last_row_id))
    return or_(*branches)


def _csv_cell(value: Any) -> str:
    """Flattens a record value into one CSV cell -- link_to_record/attachment
    values are lists of dicts (display name / filename), everything else is
    already a plain scalar by the time it reaches here (RecordResponse.values
    ran every field through field_type.from_storage())."""
    if value is None:
        return ""
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                parts.append(str(item.get("display") or item.get("filename") or item.get("row_id") or item))
            else:
                parts.append(str(item))
        return ", ".join(parts)
    return str(value)


def _plain_values_for_filter(mapping: Any, fields: list[Field]) -> dict[str, Any]:
    """{field.name: value} for real (non-virtual) fields only -- a row-level
    policy's filter can only ever reference these (RowPolicyService validates
    that at policy-creation time), so this never needs the virtual-field
    machinery _row_to_response does."""
    return {
        f.name: get_field_type(f.field_type).from_storage(mapping[f.db_column_name], f.options)
        for f in fields
        if not get_field_type(f.field_type).is_virtual
    }


def _aggregate(values: list[Any], aggregate: str) -> Any:
    if aggregate == "count":
        return len(values)
    numeric = [v for v in values if isinstance(v, (int, float))]
    if not numeric:
        return None
    if aggregate == "sum":
        return sum(numeric)
    if aggregate == "avg":
        return sum(numeric) / len(numeric)
    if aggregate == "min":
        return min(numeric)
    if aggregate == "max":
        return max(numeric)
    return None


class RecordService:
    """Grid CRUD against a Table's dynamic physical data table.

    Pagination is keyset-based on the immutable, monotonically increasing
    `_row_id` — cost stays O(log n) via the primary key index regardless of
    scroll depth, unlike OFFSET pagination (architecture plan, section 1).
    Custom per-view sort/filter is a Phase 1 concern; Phase 0 always orders
    by _row_id ascending.

    link_to_record/lookup/rollup/formula fields have no real column (see
    field_types.registry.BaseFieldType.is_virtual) — their values are
    computed separately per page/row in _compute_virtual_values rather than
    read out of the row mapping like every other field type.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.bases = BasesService(db)
        self.automations = AutomationService(db)
        self.audit = AuditService(db)
        self.row_policies = RowPolicyService(db)
        self.table_sync = TableSyncService(db)
        self.pending_sync_changes = PendingSyncChangeService(db)

    async def _load_table(self, *, table_id: uuid.UUID, user_id: uuid.UUID, permission: Permission | None = None):
        if permission is not None:
            table = await self.bases.check_table_permission(table_id=table_id, user_id=user_id, permission=permission)
            fields = await self.bases.fields.list_for_table(table_id)
        else:
            table, fields, _ = await self.bases.get_table_detail(table_id=table_id, user_id=user_id)
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        fields_by_name = {f.name: f for f in fields}
        return table, fields, sa_table, fields_by_name

    async def _load_table_for_write(self, *, table_id: uuid.UUID, user_id: uuid.UUID, permission: Permission):
        """Same shape as _load_table's permission branch, but also returns the
        workspace_id and role the permission check already fetched -- used by
        create/update/delete_record so they don't each separately re-fetch
        the same table+base (for the audit log's workspace_id) and
        table+base+membership (for row-policy's owner/admin bypass) a second
        and third time right after. See check_table_permission_with_context's
        docstring for the load-test numbers that motivated this."""
        table, workspace_id, membership = await self.bases.check_table_permission_with_context(
            table_id=table_id, user_id=user_id, permission=permission
        )
        fields = await self.bases.fields.list_for_table(table_id)
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        role = WorkspaceRole(membership.role)
        return table, fields, sa_table, workspace_id, role

    # -- Virtual field computation ---------------------------------------

    async def _link_targets_for_rows(self, link_field: Field, row_ids: list[int]) -> dict[int, list[int]]:
        """{row_id: [target_row_id, ...]} via a link_to_record field's join table."""
        targets: dict[int, list[int]] = {rid: [] for rid in row_ids}
        if not row_ids:
            return targets
        link_table = schema_service.build_link_table(link_field.options["link_table_name"])
        stmt = select(link_table.c.left_row_id, link_table.c.right_row_id).where(link_table.c.left_row_id.in_(row_ids))
        result = await self.db.execute(stmt)
        for left_row_id, right_row_id in result.all():
            targets[left_row_id].append(right_row_id)
        return targets

    async def _fetch_field_values(self, table_id: uuid.UUID, field: Field, row_ids: list[int]) -> dict[int, Any]:
        """{row_id: value} for one real (non-virtual) field on any table —
        used to pull a link's display value and a lookup/rollup's target
        value. field_type_obj.is_virtual is enforced false at field-creation
        time (BasesService._prepare_field_options), so field.db_column_name
        always names a real column here."""
        if not row_ids:
            return {}
        table = await self.bases.tables.get(table_id)
        fields = await self.bases.fields.list_for_table(table_id)
        sa_table = schema_service.build_data_table(table.physical_table_name, fields)
        stmt = select(sa_table.c._row_id, sa_table.c[field.db_column_name]).where(sa_table.c._row_id.in_(row_ids))
        result = await self.db.execute(stmt)
        field_type = get_field_type(field.field_type)
        return {row_id: field_type.from_storage(raw, field.options) for row_id, raw in result.all()}

    async def _compute_virtual_values(self, fields: list[Field], row_ids: list[int]) -> dict[str, dict[int, Any]]:
        """{field.name: {row_id: value}} for every link_to_record/lookup/rollup
        field among `fields`. formula is deliberately excluded — it's computed
        in _row_to_response, after every other field's value (including these)
        is already assembled into that row's `values` dict."""
        result: dict[str, dict[int, Any]] = {}
        if not row_ids:
            return result

        for field in fields:
            if field.field_type == "link_to_record":
                targets = await self._link_targets_for_rows(field, row_ids)
                all_target_ids = sorted({tid for ids in targets.values() for tid in ids})
                target_table_id = uuid.UUID(field.options["target_table_id"])
                target_fields = await self.bases.fields.list_for_table(target_table_id)
                primary_field = next((f for f in target_fields if f.is_primary), None) or (target_fields[0] if target_fields else None)
                display_map = await self._fetch_field_values(target_table_id, primary_field, all_target_ids) if primary_field else {}
                result[field.name] = {
                    rid: [{"row_id": tid, "display": display_map.get(tid)} for tid in tids] for rid, tids in targets.items()
                }

            elif field.field_type in ("lookup", "rollup"):
                link_field = await self.bases.fields.get(uuid.UUID(field.options["link_field_id"]))
                target_field = await self.bases.fields.get(uuid.UUID(field.options["target_field_id"]))
                if link_field is None or target_field is None:
                    result[field.name] = {rid: None for rid in row_ids}
                    continue
                targets = await self._link_targets_for_rows(link_field, row_ids)
                all_target_ids = sorted({tid for ids in targets.values() for tid in ids})
                target_table_id = uuid.UUID(link_field.options["target_table_id"])
                value_map = await self._fetch_field_values(target_table_id, target_field, all_target_ids)

                if field.field_type == "lookup":
                    result[field.name] = {rid: [value_map.get(tid) for tid in tids] for rid, tids in targets.items()}
                else:
                    aggregate = field.options.get("aggregate", "count")
                    result[field.name] = {rid: _aggregate([value_map.get(tid) for tid in tids], aggregate) for rid, tids in targets.items()}

        return result

    async def _sync_link_fields(self, fields: list[Field], row_id: int, values: dict[str, Any]) -> None:
        """Sets a link_to_record field's linked rows for one row, if that
        field's name is present in `values` — a full replace, not a merge, so
        `[]`/omitting the key both leave-or-clear intuitively."""
        for field in fields:
            if field.field_type != "link_to_record" or field.name not in values:
                continue
            raw = values[field.name] or []
            if not isinstance(raw, list):
                raise ValidationError(f"'{field.name}' expects a list of row ids")
            try:
                target_row_ids = [int(x) for x in raw]
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"'{field.name}' expects a list of integer row ids") from exc

            link_table = schema_service.build_link_table(field.options["link_table_name"])
            await self.db.execute(delete(link_table).where(link_table.c.left_row_id == row_id))
            if target_row_ids:
                await self.db.execute(insert(link_table).values([{"left_row_id": row_id, "right_row_id": rid} for rid in target_row_ids]))

    def _row_to_response(self, row: Row, fields: list[Field], virtual_values: dict[str, dict[int, Any]]) -> RecordResponse:
        mapping = row._mapping
        row_id = mapping["_row_id"]
        values: dict[str, Any] = {}
        formula_fields = []
        for field in fields:
            field_type = get_field_type(field.field_type)
            if field.field_type == "formula":
                formula_fields.append(field)
            elif field_type.is_virtual:
                values[field.name] = virtual_values.get(field.name, {}).get(row_id)
            else:
                values[field.name] = field_type.from_storage(mapping[field.db_column_name], field.options)
        for field in formula_fields:
            values[field.name] = evaluate_formula(field.options.get("expression", ""), values)
        return RecordResponse(
            row_id=row_id,
            version=mapping["_version"],
            created_at=mapping["_created_at"],
            updated_at=mapping["_updated_at"],
            values=values,
        )

    async def list_records(
        self,
        *,
        table_id: uuid.UUID,
        user_id: uuid.UUID,
        cursor: str | None,
        limit: int,
        sort: list[dict] | None = None,
        view_filter: dict | None = None,
    ) -> RecordListResponse:
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        _, fields, sa_table, fields_by_name = await self._load_table(table_id=table_id, user_id=user_id)

        # sort_specs: [(column, direction, db_column_name), ...] in priority
        # order -- db_column_name is carried alongside so the next-page cursor
        # can read each sort column's raw value back off the last emitted row.
        sort_specs: list[tuple[Any, str]] = []
        sort_db_columns: list[str] = []
        for spec in sort or []:
            field_name = spec.get("field")
            direction = spec.get("direction", "asc")
            target = fields_by_name.get(field_name)
            if target is None or get_field_type(target.field_type).is_virtual:
                raise ValidationError(f"Field '{field_name}' cannot be sorted")
            if direction not in ("asc", "desc"):
                raise ValidationError("sort direction must be 'asc' or 'desc'")
            column = sa_table.c[target.db_column_name]
            sort_specs.append((column, direction))
            sort_db_columns.append(target.db_column_name)

        order_cols = [nullslast(col.desc() if direction == "desc" else col.asc()) for col, direction in sort_specs]
        order_cols.append(sa_table.c._row_id.asc())
        stmt = select(sa_table).order_by(*order_cols).limit(limit + 1)

        if cursor is not None:
            last_row_id, last_values = _decode_cursor(cursor)
            if not sort_specs:
                stmt = stmt.where(sa_table.c._row_id > last_row_id)
            else:
                stmt = stmt.where(_keyset_clause(sort_specs, last_values, sa_table.c._row_id, last_row_id))

        effective_filter = await self.row_policies.get_effective_filter(table_id=table_id, user_id=user_id)
        columns_map = {f.name: sa_table.c[f.db_column_name] for f in fields if not get_field_type(f.field_type).is_virtual}
        if effective_filter is not None:
            stmt = stmt.where(compile_filter(effective_filter, columns_map))
        if view_filter is not None:
            stmt = stmt.where(compile_filter(parse_filter_expr(view_filter), columns_map))

        result = await self.db.execute(stmt)
        rows = result.all()

        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = None
        if has_more and page:
            last_mapping = page[-1]._mapping
            sort_values = [last_mapping[db_col] for db_col in sort_db_columns]
            next_cursor = _encode_cursor(last_mapping["_row_id"], sort_values)

        row_ids = [r._mapping["_row_id"] for r in page]
        virtual_values = await self._compute_virtual_values(fields, row_ids)

        return RecordListResponse(
            rows=[self._row_to_response(row, fields, virtual_values) for row in page],
            next_cursor=next_cursor,
            has_more=has_more,
        )

    async def get_record(self, *, table_id: uuid.UUID, row_id: int, user_id: uuid.UUID) -> RecordResponse:
        """Single-row equivalent of list_records -- used by record_submit so the
        external payload gets the exact same virtual-field-resolved values the
        grid itself shows, and respects the same row-level-policy scoping
        update_record enforces (a row a viewer can't see can't be submitted
        either)."""
        table, fields, sa_table, fields_by_name = await self._load_table(table_id=table_id, user_id=user_id)
        result = await self.db.execute(select(sa_table).where(sa_table.c._row_id == row_id))
        row = result.one_or_none()
        if row is None:
            raise NotFoundError("Row not found")

        effective_filter = await self.row_policies.get_effective_filter(table_id=table_id, user_id=user_id)
        if effective_filter is not None:
            plain_values = _plain_values_for_filter(row._mapping, fields)
            if not evaluate_filter(effective_filter, plain_values):
                raise NotFoundError("Row not found")  # scoped out -- same as update_record

        virtual_values = await self._compute_virtual_values(fields, [row_id])
        return self._row_to_response(row, fields, virtual_values)

    async def distinct_field_values(
        self,
        *,
        field_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int = 500,
        apply_exclusion: bool = True,
        other_filter: dict[str, Any] | None = None,
    ) -> list[Any]:
        """Values already present in `field_id`'s own table, for an easy
        "pick an existing value" filter picker -- suggests fewer/better filter
        OPTIONS, never hides rows (that stays entirely inside filter_dsl,
        untouched). If the field has exclude_values_from configured (see
        BasesService._validate_exclude_mapping), values already present in the
        mapped field are additionally left out, same as before this handled
        the plain case too -- unless `apply_exclusion=False`, used by the
        column-header AutoFilter checklist, which always wants this column's
        own complete set of values regardless of an unrelated reconciliation
        mapping someone may have configured on it.

        `other_filter` is that same checklist's cascading behavior (Excel's
        own AutoFilter does this too): once a different column is already
        filtered, opening a second column's checklist should only offer
        values that actually occur among rows matching the FIRST column's
        filter, not every value in the whole table -- otherwise checking a
        value here could produce zero rows with no indication why. The
        caller is expected to have already stripped this field's own
        condition out of it (see frontend's filterExcludingField), since
        re-applying it here would be a no-op at best and a self-contradiction
        at worst."""
        field = await self.bases.fields.get(field_id)
        if field is None:
            raise NotFoundError("Field not found")
        await self.bases.check_table_access(table_id=field.table_id, user_id=user_id)

        own_table = await self.bases.tables.get(field.table_id)
        own_fields = await self.bases.fields.list_for_table(field.table_id)
        own_sa_table = schema_service.build_data_table(own_table.physical_table_name, own_fields)
        own_col = own_sa_table.c[field.db_column_name]
        stmt = select(own_col).where(own_col.isnot(None))

        if other_filter:
            columns_map = {f.name: own_sa_table.c[f.db_column_name] for f in own_fields if not get_field_type(f.field_type).is_virtual}
            stmt = stmt.where(compile_filter(parse_filter_expr(other_filter), columns_map))

        mapping = field.options.get("exclude_values_from") if apply_exclusion else None
        if mapping:
            target_table_id = uuid.UUID(mapping["table_id"])
            target_field_id = uuid.UUID(mapping["field_id"])
            await self.bases.check_table_access(table_id=target_table_id, user_id=user_id)
            target_table = await self.bases.tables.get(target_table_id)
            target_field = await self.bases.fields.get(target_field_id)
            if target_table is None or target_field is None:
                raise ValidationError("Exclusion mapping points at a table/field that no longer exists")
            target_fields = await self.bases.fields.list_for_table(target_table_id)
            target_sa_table = schema_service.build_data_table(target_table.physical_table_name, target_fields)
            target_col = target_sa_table.c[target_field.db_column_name]
            # target_col.isnot(None) inside the subquery is load-bearing:
            # Postgres's NOT IN against a subquery containing any NULL
            # returns zero rows for every candidate, silently -- dropping
            # this filter would make every call here return an empty list the
            # moment the target column has one unset value anywhere.
            subq = select(target_col).where(target_col.isnot(None)).distinct().scalar_subquery()
            stmt = stmt.where(own_col.notin_(subq))

        stmt = stmt.distinct().order_by(own_col).limit(limit)
        result = await self.db.execute(stmt)
        field_type = get_field_type(field.field_type)
        return [field_type.from_storage(v, field.options) for (v,) in result.all()]

    async def get_table_name_checked(self, *, table_id: uuid.UUID, user_id: uuid.UUID) -> str:
        """Runs the same permission check _load_table does, eagerly rather
        than on first iteration of the export generator -- StreamingResponse
        sends a 200 and its headers as soon as the first chunk is pulled, so a
        permission error raised lazily inside the generator would arrive as a
        broken stream instead of a clean 403/404."""
        table, _, _ = await self.bases.get_table_detail(table_id=table_id, user_id=user_id)
        return table.name

    async def export_csv_rows(
        self,
        *,
        table_id: uuid.UUID,
        user_id: uuid.UUID,
        sort: list[dict] | None = None,
        view_filter: dict | None = None,
    ):
        """Streams the table as CSV text in page-sized chunks. Reuses
        list_records for every page rather than re-deriving the cursor/filter/
        sort/row-policy logic -- from the exporter's perspective, a full
        export is just "every page, concatenated".

        Opens its own DB session rather than using self.db: FastAPI tears down
        a `Depends`-injected session as soon as the route handler returns, but
        StreamingResponse only iterates this generator afterward, while the
        body is being sent -- reusing self.db here would mean querying
        through an already-closed session/connection."""
        from app.core.db import SessionLocal

        async with SessionLocal() as db:
            service = RecordService(db)
            _, fields, _, _ = await service._load_table(table_id=table_id, user_id=user_id)
            ordered_fields = sorted(fields, key=lambda f: f.position)

            buffer = io.StringIO()
            writer = csv.writer(buffer)
            writer.writerow([f.name for f in ordered_fields])
            yield buffer.getvalue()

            cursor = None
            while True:
                page = await service.list_records(
                    table_id=table_id,
                    user_id=user_id,
                    cursor=cursor,
                    limit=MAX_PAGE_SIZE,
                    sort=sort,
                    view_filter=view_filter,
                )
                buffer.seek(0)
                buffer.truncate(0)
                for row in page.rows:
                    writer.writerow([_csv_cell(row.values.get(f.name)) for f in ordered_fields])
                yield buffer.getvalue()
                if not page.has_more:
                    break
                cursor = page.next_cursor

    def _coerce_values(self, values: dict[str, Any], fields: list[Field], *, for_create: bool) -> dict[str, Any]:
        fields_by_name = {f.name: f for f in fields}
        unknown = set(values) - set(fields_by_name)
        if unknown:
            raise ValidationError(f"Unknown field(s): {', '.join(sorted(unknown))}")

        db_values: dict[str, Any] = {}
        for field in fields:
            field_type = get_field_type(field.field_type)
            if field_type.is_virtual:
                # link_to_record is written via _sync_link_fields; lookup/rollup/formula are computed, never written.
                continue
            if field.name in values:
                db_values[field.db_column_name] = field_type.to_storage(values[field.name], field.options)
            elif for_create and field.required:
                raise ValidationError(f"Field '{field.name}' is required")
        return db_values

    async def _enqueue_sync_push(
        self,
        *,
        table: Table,
        row_id: int,
        operation: str,
        values: dict[str, Any] | None,
        user_id: uuid.UUID,
        external_pk: str | None = None,
        previous_values: dict[str, Any] | None = None,
        skip_sync_push: bool = False,
    ) -> None:
        """If this table is linked for sync (Stage 1: push only, see
        connectors.sync_service), queue the external write on the arq worker
        rather than doing it inline -- an external DB's latency/availability
        must never sit in the path of a user's own edit landing. A no-op,
        cheap lookup for the (much more common) unsynced case.

        external_pk is only meaningful for "delete": the row (and its
        _external_pk column) is gone by the time the worker runs, so the
        caller must capture it beforehand. insert/update leave it None and
        the worker looks it up itself from the still-existing row.

        If the table's sync is gated behind approval, this diverts to a
        pending_sync_changes row instead of enqueueing the push directly --
        the local edit itself still lands immediately either way; only the
        *external* write waits. See PendingSyncChangeService.request.

        skip_sync_push short-circuits all of the above -- used by
        PendingSyncChangeService.reject's restore path, which undoes a
        rejected local edit via this same create/update/delete machinery but
        must never itself re-enter the approval gate or push anything
        externally (nothing reached the external system in the first place,
        which is exactly why a reject is safe to restore without a push)."""
        if skip_sync_push:
            return
        config = await self.table_sync.get_config_for_table(table.id)
        if config is None or not config.sync_enabled:
            return
        if config.push_requires_approval:
            await self.pending_sync_changes.request(
                table=table, row_id=row_id, operation=operation, values=values, external_pk=external_pk,
                previous_values=previous_values, user_id=user_id,
            )
            return
        if operation == "delete" and external_pk is None:
            # Never reached the external side in the first place (no prior
            # successful push ever set _external_pk) -- nothing to delete
            # there either.
            return
        pool = await get_arq_pool()
        await pool.enqueue_job(
            "push_record_to_source", str(table.id), row_id, operation, values, str(user_id), external_pk=external_pk
        )

    async def create_record(
        self, *, table_id: uuid.UUID, user_id: uuid.UUID, values: dict[str, Any], skip_sync_push: bool = False
    ) -> RecordResponse:
        table, fields, sa_table, workspace_id, _ = await self._load_table_for_write(
            table_id=table_id, user_id=user_id, permission=Permission.RECORD_WRITE
        )
        db_values = self._coerce_values(values, fields, for_create=True)
        db_values["_created_by"] = user_id

        stmt = insert(sa_table).values(**db_values).returning(sa_table)
        result = await self.db.execute(stmt)
        row = result.one()
        row_id = row._mapping["_row_id"]
        await self._sync_link_fields(fields, row_id, values)
        await self.db.commit()
        await self.audit.log_deferred(
            workspace_id=workspace_id, user_id=user_id, action="record.created", resource_type="record",
            resource_id=str(row_id), resource_label=f"Row #{row_id} in {table.name}", details={"table_id": str(table_id)},
        )
        await ws_manager.broadcast(table_id, {"type": "record_change", "row_id": row_id})

        virtual_values = await self._compute_virtual_values(fields, [row_id])
        response = self._row_to_response(row, fields, virtual_values)
        await self.automations.dispatch_record_event(
            table_id=table_id, trigger_type="record_created", row_values=response.values, row_id=response.row_id
        )
        await self._enqueue_sync_push(
            table=table, row_id=row_id, operation="insert", values=response.values, user_id=user_id, skip_sync_push=skip_sync_push
        )
        return response

    async def create_record_via_form(self, *, view_token: str, values: dict[str, Any]) -> RecordResponse:
        """No auth, no permission check -- the share token is the
        authorization (same trust model as a dashboard share link). Only
        fields the form was explicitly configured to collect can ever be
        written; anything else in `values` is silently dropped rather than
        erroring, so a tampered request body can't reach other columns."""
        table, view, form_fields = await self.bases.get_public_form(token=view_token)
        allowed_names = {f.name for f in form_fields}
        filtered_values = {name: value for name, value in values.items() if name in allowed_names}

        all_fields = await self.bases.fields.list_for_table(table.id)
        sa_table = schema_service.build_data_table(table.physical_table_name, all_fields)
        db_values = self._coerce_values(filtered_values, form_fields, for_create=True)
        db_values["_created_by"] = None

        stmt = insert(sa_table).values(**db_values).returning(sa_table)
        result = await self.db.execute(stmt)
        row = result.one()
        row_id = row._mapping["_row_id"]
        await self._sync_link_fields(all_fields, row_id, filtered_values)
        workspace_id = await self.bases.get_workspace_id_for_table(table.id)
        await self.audit.log(
            workspace_id=workspace_id, user_id=None, action="record.created", resource_type="record",
            resource_id=str(row_id), resource_label=f"Row #{row_id} in {table.name}",
            details={"table_id": str(table.id), "via": "public_form", "view_id": str(view.id)},
        )
        await self.db.commit()
        await ws_manager.broadcast(table.id, {"type": "record_change", "row_id": row_id})

        virtual_values = await self._compute_virtual_values(all_fields, [row_id])
        response = self._row_to_response(row, all_fields, virtual_values)
        await self.automations.dispatch_record_event(
            table_id=table.id, trigger_type="record_created", row_values=response.values, row_id=response.row_id
        )
        return response

    async def update_record(
        self,
        *,
        table_id: uuid.UUID,
        row_id: int,
        user_id: uuid.UUID,
        values: dict[str, Any],
        expected_version: int | None,
        skip_sync_push: bool = False,
    ) -> RecordResponse:
        table, fields, sa_table, workspace_id, role = await self._load_table_for_write(
            table_id=table_id, user_id=user_id, permission=Permission.RECORD_WRITE
        )

        existing = await self.db.execute(select(sa_table).where(sa_table.c._row_id == row_id))
        current = existing.one_or_none()
        if current is None:
            raise NotFoundError("Row not found")
        if expected_version is not None and current._mapping["_version"] != expected_version:
            raise ConflictError("This row was modified by someone else — reload and try again")

        effective_filter = await self.row_policies.get_effective_filter(table_id=table_id, user_id=user_id, role=role)
        previous_values = _plain_values_for_filter(current._mapping, fields)
        if effective_filter is not None and not evaluate_filter(effective_filter, previous_values):
            raise NotFoundError("Row not found")  # scoped out -- looks identical to a nonexistent row, not a 403

        db_values = self._coerce_values(values, fields, for_create=False)
        stmt = (
            update(sa_table)
            .where(sa_table.c._row_id == row_id)
            .values(**db_values, _version=sa_table.c._version + 1, _updated_at=func.now())
            .returning(sa_table)
        )
        result = await self.db.execute(stmt)
        row = result.one()
        await self._sync_link_fields(fields, row_id, values)
        await self.db.commit()
        await self.audit.log_deferred(
            workspace_id=workspace_id, user_id=user_id, action="record.updated", resource_type="record",
            resource_id=str(row_id), resource_label=f"Row #{row_id} in {table.name}",
            details={"table_id": str(table_id), "changed_fields": sorted(values.keys())},
        )
        await ws_manager.broadcast(table_id, {"type": "record_change", "row_id": row_id})

        virtual_values = await self._compute_virtual_values(fields, [row_id])
        response = self._row_to_response(row, fields, virtual_values)
        # watched_fields means "this column's value actually changed," not
        # "this column was present in the write" -- a cell committed back to
        # its own existing value (click into a cell, blur without typing
        # anything; a checkbox is the one exception, since toggling it always
        # is a real change) would otherwise count as a change to every
        # automation watching that column. previous_values and
        # response.values are both already run through from_storage, so
        # they're directly comparable here.
        actually_changed_fields = {name for name in values if name in previous_values and previous_values[name] != response.values.get(name)}
        await self.automations.dispatch_record_event(
            table_id=table_id, trigger_type="record_updated", row_values=response.values, row_id=response.row_id,
            changed_fields=actually_changed_fields,
        )
        await self._enqueue_sync_push(
            table=table, row_id=row_id, operation="update", values=response.values, user_id=user_id,
            previous_values=previous_values, skip_sync_push=skip_sync_push,
        )
        return response

    async def delete_record(
        self, *, table_id: uuid.UUID, row_id: int, user_id: uuid.UUID, skip_sync_push: bool = False
    ) -> None:
        table, fields, sa_table, workspace_id, role = await self._load_table_for_write(
            table_id=table_id, user_id=user_id, permission=Permission.RECORD_DELETE
        )

        # Always fetched (not just under a row-level policy) -- a reject's
        # restore path (PendingSyncChangeService.reject) needs this row's
        # last values to recreate it, and there's no other point after this
        # where they're still readable.
        existing = await self.db.execute(select(sa_table).where(sa_table.c._row_id == row_id))
        current = existing.one_or_none()
        previous_values = _plain_values_for_filter(current._mapping, fields) if current is not None else None
        effective_filter = await self.row_policies.get_effective_filter(table_id=table_id, user_id=user_id, role=role)
        if effective_filter is not None:
            if current is None or not evaluate_filter(effective_filter, previous_values):
                raise NotFoundError("Row not found")

        # The row (and its _external_pk) is gone the instant the delete
        # below commits -- captured now, before it's too late, same
        # discipline as capturing ORM scalars before a session rollback.
        sync_config = await self.table_sync.get_config_for_table(table_id)
        external_pk: str | None = None
        if sync_config is not None and sync_config.sync_enabled:
            # build_data_table()'s sa_table doesn't know about the reserved
            # sync columns (they're not Field-derived) -- the narrow
            # sync-columns table is what exposes _external_pk.
            sync_table = schema_service.build_sync_columns_table(table.physical_table_name)
            pk_row = await self.db.execute(select(sync_table.c._external_pk).where(sync_table.c._row_id == row_id))
            external_pk = pk_row.scalar_one_or_none()

        stmt = delete(sa_table).where(sa_table.c._row_id == row_id)
        result = await self.db.execute(stmt)
        if result.rowcount == 0:
            raise NotFoundError("Row not found")

        await self.db.commit()
        await self.audit.log_deferred(
            workspace_id=workspace_id, user_id=user_id, action="record.deleted", resource_type="record",
            resource_id=str(row_id), resource_label=f"Row #{row_id} in {table.name}", details={"table_id": str(table_id)},
        )
        await ws_manager.broadcast(table_id, {"type": "record_change", "row_id": row_id})
        # Not gated on external_pk is not None anymore -- a row can be
        # deleted while its *insert* is still awaiting approval (external_pk
        # never set), and _enqueue_sync_push still needs a chance to cancel
        # that pending insert. It's the direct-push branch (not this call
        # site) that now skips actually pushing when there's truly nothing
        # external to remove.
        if sync_config is not None and sync_config.sync_enabled:
            await self._enqueue_sync_push(
                table=table, row_id=row_id, operation="delete", values=None, user_id=user_id, external_pk=external_pk,
                previous_values=previous_values, skip_sync_push=skip_sync_push,
            )
