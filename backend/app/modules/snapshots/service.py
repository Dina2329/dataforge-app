"""Base snapshots -- a point-in-time checkpoint of an entire Base (every
Table's schema + data at that instant), and the ability to restore one.

Storage: each Table in the Base gets a raw CREATE TABLE ... AS SELECT copy
(schema_service.create_snapshot_copy) into the df_snapshots schema -- fast
even for a large table, and a real Postgres table rather than a JSON blob,
so restore can read it with plain SQL.

Restore is deliberately implemented as a diff against current data, replayed
through RecordService.create_record/update_record/delete_record -- not a raw
table swap. That's what makes a restored row's push-to-source (or its
approval-gate queueing, if push_requires_approval is on) automatically
behave exactly like any other edit: no special-cased sync interaction to
get wrong, because it IS an ordinary edit as far as the rest of the system
is concerned.

Known, deliberate v1 limitations (not oversights):
- Only non-virtual fields are captured/restored -- link_to_record's actual
  state lives in a separate join table this doesn't touch at all, and
  lookup/rollup/formula are always computed, never stored. Restoring a
  base does not restore link relationships.
- A row that has to be re-created (existed in the snapshot, was deleted
  since) gets a brand-new row id -- internal ids were never meant to be
  stable identifiers across a restore, only the field values are restored.
- A field deleted since the snapshot can't be restored (nothing to restore
  it into); a field that still exists is matched by its stable id, not its
  current name, so a rename since the snapshot doesn't break restore.
- A whole Table created after the snapshot is left untouched by a restore
  (not deleted) -- restoring only brings back what the snapshot actually
  captured.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SNAPSHOT_SCHEMA
from app.core.errors import NotFoundError
from app.modules.audit.service import AuditService
from app.modules.bases import schema_service
from app.modules.bases.field_types import get_field_type
from app.modules.bases.models import Base, Table
from app.modules.bases.service import BasesService
from app.modules.records.service import RecordService
from app.modules.snapshots.models import BaseSnapshot, BaseSnapshotTable
from app.modules.snapshots.repository import SnapshotRepository
from app.modules.workspaces.permissions import Permission


class SnapshotService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = SnapshotRepository(db)
        self.bases = BasesService(db)
        self.audit = AuditService(db)

    async def create_snapshot(
        self, *, base_id: uuid.UUID, user_id: uuid.UUID, label: str | None = None
    ) -> tuple[BaseSnapshot, int]:
        """API-facing: permission-checked against the acting user. The daily
        automatic snapshot (snapshot_tasks.py) has no acting user -- see
        create_snapshot_unchecked, which this delegates to once the check
        passes."""
        base = await self.bases._get_base_or_404(base_id)
        await self.bases.workspaces.require_permission(workspace_id=base.workspace_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        return await self.create_snapshot_unchecked(base_id=base_id, created_by=user_id, label=label, is_automatic=False)

    async def create_snapshot_unchecked(
        self, *, base_id: uuid.UUID, created_by: uuid.UUID, label: str | None = None, is_automatic: bool = False
    ) -> tuple[BaseSnapshot, int]:
        """No permission check -- for internal callers only (the daily
        automatic-snapshot cron task, which already picked created_by itself
        rather than acting on behalf of an authenticated request). API
        endpoints must use create_snapshot instead."""
        base = await self.bases._get_base_or_404(base_id)
        snapshot_label = label or f"Snapshot — {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}"
        snapshot = await self.repo.create_snapshot(base_id=base_id, label=snapshot_label, is_automatic=is_automatic, created_by=created_by)

        table_count = 0
        for table in await self.bases.tables.list_for_base(base_id):
            fields = await self.bases.fields.list_for_table(table.id)
            non_virtual = [f for f in fields if not get_field_type(f.field_type).is_virtual]
            field_defs = [
                {"id": str(f.id), "name": f.name, "db_column_name": f.db_column_name, "field_type": f.field_type, "options": f.options}
                for f in non_virtual
            ]
            physical_snapshot_table = schema_service.generate_snapshot_table_name()
            await schema_service.create_snapshot_copy(self.db, physical_snapshot_table, table.physical_table_name)
            row_count = (
                await self.db.execute(text(f'SELECT count(*) FROM "{SNAPSHOT_SCHEMA}"."{physical_snapshot_table}"'))
            ).scalar_one()
            await self.repo.add_snapshot_table(
                snapshot_id=snapshot.id, table_id=table.id, table_name=table.name,
                physical_snapshot_table=physical_snapshot_table, field_defs=field_defs, row_count=row_count,
            )
            table_count += 1

        await self.audit.log(
            workspace_id=base.workspace_id, user_id=created_by, action="base_snapshot.created", resource_type="base",
            resource_id=str(base_id), resource_label=snapshot_label,
        )
        await self.db.commit()
        return snapshot, table_count

    async def list_for_base(self, *, base_id: uuid.UUID, user_id: uuid.UUID) -> list[tuple[BaseSnapshot, int]]:
        base = await self.bases._get_base_or_404(base_id)
        await self.bases.workspaces.require_member(workspace_id=base.workspace_id, user_id=user_id)
        snapshots = await self.repo.list_for_base(base_id)
        return [(s, len(await self.repo.list_tables(s.id))) for s in snapshots]

    async def set_auto_snapshots_enabled(self, *, base_id: uuid.UUID, user_id: uuid.UUID, enabled: bool) -> Base:
        """The off switch for the unattended nightly snapshot only -- manual
        snapshots (create_snapshot above) are never gated by this. Same
        permission tier as taking a manual snapshot (SCHEMA_WRITE), since
        this isn't a destructive action the way restore/delete are."""
        base = await self.bases._get_base_or_404(base_id)
        await self.bases.workspaces.require_permission(workspace_id=base.workspace_id, user_id=user_id, permission=Permission.SCHEMA_WRITE)
        base.auto_snapshots_enabled = enabled
        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id,
            action="base_snapshot.auto_enabled" if enabled else "base_snapshot.auto_disabled",
            resource_type="base", resource_id=str(base_id),
        )
        await self.db.commit()
        return base

    async def _get_checked(self, *, snapshot_id: uuid.UUID, user_id: uuid.UUID) -> tuple[BaseSnapshot, Base]:
        snapshot = await self.repo.get(snapshot_id)
        if snapshot is None:
            raise NotFoundError("Snapshot not found")
        base = await self.bases._get_base_or_404(snapshot.base_id)
        await self.bases.workspaces.require_member(workspace_id=base.workspace_id, user_id=user_id)
        return snapshot, base

    async def delete_snapshot(self, *, snapshot_id: uuid.UUID, user_id: uuid.UUID) -> None:
        snapshot, base = await self._get_checked(snapshot_id=snapshot_id, user_id=user_id)
        # Same tier as deleting a base/table -- see WorkspaceService.require_owner_or_admin.
        await self.bases.workspaces.require_owner_or_admin(workspace_id=base.workspace_id, user_id=user_id)
        for snap_table in await self.repo.list_tables(snapshot.id):
            await schema_service.drop_snapshot_copy(self.db, snap_table.physical_snapshot_table)
        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="base_snapshot.deleted", resource_type="base",
            resource_id=str(base.id), resource_label=snapshot.label,
        )
        await self.repo.delete(snapshot)
        await self.db.commit()

    async def _resolve_snapshot_table(self, snap_table: BaseSnapshotTable) -> tuple[Table | None, dict[str, Any] | None]:
        """Shared by preview_restore and restore_snapshot -- exactly one of
        the two return values is non-None. A missing table_id (or a table_id
        that no longer resolves) means the table was deleted since the
        snapshot was taken; both callers skip it identically."""
        table = await self.bases.tables.get(snap_table.table_id) if snap_table.table_id is not None else None
        if table is not None:
            return table, None
        return None, {"table_name": snap_table.table_name, "skipped": True, "skip_reason": "This table was deleted since the snapshot was taken"}

    async def _diff_table(self, *, table: Table, snap_table: BaseSnapshotTable) -> dict[str, Any]:
        """What restoring `table` from its snapshot copy would do, computed
        but not applied -- shared by preview_restore (which stops here) and
        restore_snapshot (which applies exactly what this returns), so the
        preview a user sees and the restore that actually runs can never
        drift apart into two different code paths."""
        current_fields = await self.bases.fields.list_for_table(table.id)
        current_fields_by_id = {str(f.id): f for f in current_fields}
        # (snapshot field def, live Field) pairs -- only fields that still
        # exist and are still non-virtual now. Matched by stable field id,
        # not name, so a rename since the snapshot doesn't break this.
        restorable = [
            (fd, current_fields_by_id[fd["id"]])
            for fd in snap_table.field_defs
            if fd["id"] in current_fields_by_id and not get_field_type(current_fields_by_id[fd["id"]].field_type).is_virtual
        ]

        snap_rows_raw = (
            await self.db.execute(text(f'SELECT * FROM "{SNAPSHOT_SCHEMA}"."{snap_table.physical_snapshot_table}"'))
        ).mappings().all()
        snap_rows = {row["_row_id"]: dict(row) for row in snap_rows_raw}

        sa_table = schema_service.build_data_table(table.physical_table_name, current_fields)
        current_rows_raw = (await self.db.execute(select(sa_table))).all()
        current_rows = {row._mapping["_row_id"]: dict(row._mapping) for row in current_rows_raw}

        to_create: list[tuple[int, dict[str, Any]]] = []
        to_update: list[tuple[int, dict[str, Any]]] = []
        to_delete: list[int] = []
        unchanged = 0

        for row_id in sorted(set(snap_rows) | set(current_rows)):
            snap_row = snap_rows.get(row_id)
            current_row = current_rows.get(row_id)
            if snap_row is not None and current_row is None:
                values = {cf.name: snap_row[fd["db_column_name"]] for fd, cf in restorable if fd["db_column_name"] in snap_row}
                to_create.append((row_id, values))
            elif snap_row is None and current_row is not None:
                to_delete.append(row_id)
            else:
                changed_values = {
                    cf.name: snap_row[fd["db_column_name"]]
                    for fd, cf in restorable
                    if fd["db_column_name"] in snap_row and snap_row[fd["db_column_name"]] != current_row.get(cf.db_column_name)
                }
                if changed_values:
                    to_update.append((row_id, changed_values))
                else:
                    unchanged += 1

        return {"to_create": to_create, "to_update": to_update, "to_delete": to_delete, "unchanged": unchanged}

    async def preview_restore(self, *, snapshot_id: uuid.UUID, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Read-only -- computes exactly what restore_snapshot would do,
        without writing anything, so a user can see which tables/how many
        rows would be created/updated/deleted before committing to it."""
        snapshot, base = await self._get_checked(snapshot_id=snapshot_id, user_id=user_id)
        await self.bases.workspaces.require_owner_or_admin(workspace_id=base.workspace_id, user_id=user_id)

        results: list[dict[str, Any]] = []
        for snap_table in await self.repo.list_tables(snapshot.id):
            table, skip_result = await self._resolve_snapshot_table(snap_table)
            if skip_result is not None:
                results.append(skip_result)
                continue
            diff = await self._diff_table(table=table, snap_table=snap_table)
            results.append({
                "table_name": table.name, "created": len(diff["to_create"]), "updated": len(diff["to_update"]),
                "deleted": len(diff["to_delete"]), "unchanged": diff["unchanged"], "failed": 0, "failures": [],
            })
        return results

    async def restore_snapshot(self, *, snapshot_id: uuid.UUID, user_id: uuid.UUID) -> list[dict[str, Any]]:
        snapshot, base = await self._get_checked(snapshot_id=snapshot_id, user_id=user_id)
        await self.bases.workspaces.require_owner_or_admin(workspace_id=base.workspace_id, user_id=user_id)

        records = RecordService(self.db)
        results: list[dict[str, Any]] = []

        for snap_table in await self.repo.list_tables(snapshot.id):
            table, skip_result = await self._resolve_snapshot_table(snap_table)
            if skip_result is not None:
                results.append(skip_result)
                continue

            diff = await self._diff_table(table=table, snap_table=snap_table)
            created = updated = deleted = 0
            failures: list[dict[str, Any]] = []

            for row_id, values in diff["to_create"]:
                try:
                    await records.create_record(table_id=table.id, user_id=user_id, values=values)
                    created += 1
                except Exception as exc:
                    failures.append({"row_id": row_id, "error": str(exc)})
            for row_id, values in diff["to_update"]:
                try:
                    await records.update_record(table_id=table.id, row_id=row_id, user_id=user_id, values=values, expected_version=None)
                    updated += 1
                except Exception as exc:
                    failures.append({"row_id": row_id, "error": str(exc)})
            for row_id in diff["to_delete"]:
                try:
                    await records.delete_record(table_id=table.id, row_id=row_id, user_id=user_id)
                    deleted += 1
                except Exception as exc:
                    failures.append({"row_id": row_id, "error": str(exc)})

            results.append({
                "table_name": table.name, "created": created, "updated": updated, "deleted": deleted,
                "unchanged": diff["unchanged"], "failed": len(failures), "failures": failures,
            })

        await self.audit.log(
            workspace_id=base.workspace_id, user_id=user_id, action="base_snapshot.restored", resource_type="base",
            resource_id=str(base.id), resource_label=snapshot.label, details={"tables": results},
        )
        await self.db.commit()
        return results
