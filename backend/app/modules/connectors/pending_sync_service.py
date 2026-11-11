"""Push approval gate: when a TableSyncConfig has push_requires_approval set,
RecordService._enqueue_sync_push calls into this instead of enqueueing
push_record_to_source directly. Owns pending_sync_changes/sync_change_batches
-- a gate in front of the existing push pipeline, not a parallel one;
approving a batch just enqueues the exact same push_record_to_source job the
direct-push path would have for each row in it, so every existing
retry/circuit-breaker/failure-notification behavior applies unchanged once
something is approved.

Two-step editor flow, not "every edit is instantly in the owner's queue":
an edit on a gated table first lands as a *draft* (request(), status="draft")
-- visible only to the editor who made it, collapsing repeated edits to the
same row exactly like before. The editor then explicitly calls submit() once
they're done, bundling every one of their current drafts (however many rows,
across however many gated tables) into one SyncChangeBatch that an
owner/admin reviews and approves/rejects as a single action.
"""

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.core.json_safe import json_safe
from app.modules.audit.service import AuditService
from app.modules.auth.repository import UserRepository
from app.modules.bases import schema_service
from app.modules.bases.models import Table
from app.modules.bases.service import BasesService
from app.modules.connectors.models import PendingSyncChange, SyncChangeBatch
from app.modules.connectors.repository import PendingSyncChangeRepository, SyncChangeBatchRepository
from app.modules.notifications.service import NotificationService
from app.modules.workspaces.permissions import Permission
from app.worker.arq_app import get_arq_pool


class PendingSyncChangeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = PendingSyncChangeRepository(db)
        self.batches = SyncChangeBatchRepository(db)
        self.bases = BasesService(db)
        self.audit = AuditService(db)
        self.notifications = NotificationService(db)
        self.users = UserRepository(db)

    async def _current_external_pk(self, table: Table, row_id: int) -> str | None:
        sync_table = schema_service.build_sync_columns_table(table.physical_table_name)
        result = await self.db.execute(select(sync_table.c._external_pk).where(sync_table.c._row_id == row_id))
        return result.scalar_one_or_none()

    async def request(
        self,
        *,
        table: Table,
        row_id: int,
        operation: str,
        values: dict[str, Any] | None,
        external_pk: str | None,
        user_id: uuid.UUID,
        previous_values: dict[str, Any] | None = None,
    ) -> None:
        """Called instead of enqueueing push_record_to_source directly, once
        for every local insert/update/delete on a table gated behind
        approval. Always creates/refreshes a *draft* -- visible only to this
        editor until they call submit() -- collapsing to at most one
        unresolved row per (table_id, row_id) -- a second local edit before
        submission just refreshes this row's stored values, so submitting
        always bundles the latest state, never a stale intermediate
        snapshot.

        previous_values is only ever stored on a brand-new draft row (the
        row's state before the *first* unreviewed edit) and is never
        overwritten by a later collapsed edit -- a reject's restore
        (PendingSyncChangeService.reject_batch) must be able to undo back to
        before everything that piled up while this sat unreviewed, not just
        the most recent edit."""
        # A date-typed field's coerced value is a real Python date/datetime
        # object here (see DateFieldType.to_storage), not a string -- fine
        # for the FastAPI response this dict was built for, but plain
        # json.dumps (what the JSON column below goes through) can't
        # serialize either on its own. Sanitize once, up front, rather than
        # at each of this method's several store sites below.
        values = json_safe(values)
        previous_values = json_safe(previous_values)
        existing = await self.repo.get_pending_for_row(table_id=table.id, row_id=row_id)

        if operation == "delete":
            if existing is not None and existing.operation == "insert":
                # Never reached the external side in the first place (still
                # only a draft/pending insert) -- nothing to delete there
                # either. Cancel outright rather than leave a dangling
                # "delete" with nothing behind it to remove.
                await self.repo.delete(existing)
                await self.db.commit()
                return
            if external_pk is None:
                # No prior successful push (no draft/pending insert, and the
                # row itself carries no _external_pk) -- again, nothing to do.
                return
            if existing is not None:
                existing.operation = "delete"
                existing.values = None
                existing.external_pk = external_pk
                existing.requested_by = user_id
                existing.requested_at = datetime.now(timezone.utc)
            else:
                await self.repo.create(
                    table_id=table.id, row_id=row_id, operation="delete", values=None, external_pk=external_pk,
                    requested_by=user_id, previous_values=previous_values,
                )
            await self.db.commit()
            return

        # insert/update: the operation actually owed to the external system
        # is always re-derived from whether the row already has a real
        # external_pk, never just trusted from the caller's local operation
        # label -- a row's first-ever edit under approval mode is still an
        # "insert" externally no matter what the local caller calls it (e.g.
        # a pre-existing, never-synced row edited for the first time after
        # push_requires_approval was turned on).
        if existing is not None:
            existing.values = values
            existing.requested_by = user_id
            existing.requested_at = datetime.now(timezone.utc)
        else:
            real_external_pk = await self._current_external_pk(table, row_id)
            derived_operation = "update" if real_external_pk is not None else "insert"
            await self.repo.create(
                table_id=table.id, row_id=row_id, operation=derived_operation, values=values, external_pk=None,
                requested_by=user_id,
                # None for a derived "insert" -- there is no external "before" to
                # restore to; a rejected insert is undone by deleting instead (see
                # reject_batch).
                previous_values=previous_values if derived_operation == "update" else None,
            )
        await self.db.commit()

    async def list_drafts(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> list[tuple[PendingSyncChange, str]]:
        """One editor's own not-yet-submitted edits -- just membership, no
        approval permission needed, since these are only ever the caller's
        own drafts (scoped by requested_by in the query itself)."""
        await self.bases.workspaces.require_member(workspace_id=workspace_id, user_id=user_id)
        return await self.repo.list_drafts_for_user(workspace_id=workspace_id, requested_by=user_id)

    async def submit(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> tuple[SyncChangeBatch, int]:
        """Bundles every one of this user's current drafts in this workspace
        (however many rows, across however many gated tables) into one new
        batch, and notifies approvers exactly once for the whole thing --
        the entire point of this two-step flow is that an owner/admin no
        longer gets pinged, or has to click through, once per edit."""
        await self.bases.workspaces.require_member(workspace_id=workspace_id, user_id=user_id)
        batch = await self.batches.create(workspace_id=workspace_id, requested_by=user_id)
        moved = await self.repo.mark_all_draft_as_submitted(workspace_id=workspace_id, requested_by=user_id, batch_id=batch.id)
        if moved == 0:
            await self.db.rollback()
            raise ValidationError("You don't have any pending edits to submit")
        await self.db.commit()

        rows = await self.repo.list_for_batch(batch.id)
        table_names = sorted({table_name for _, table_name in rows})
        approver_ids = await self.bases.workspaces.list_member_ids_with_permission(
            workspace_id=workspace_id, permission=Permission.SYNC_APPROVAL_MANAGE
        )
        change_word = "change" if moved == 1 else "changes"
        for approver_id in approver_ids:
            await self.notifications.create(
                user_id=approver_id,
                title="Changes awaiting approval",
                message=f"{moved} {change_word} on {', '.join(table_names)} are waiting to be pushed to their synced source.",
                link=f"/workspaces/{workspace_id}/pending-sync-changes",
            )
        return batch, moved

    async def list_batches_for_workspace(self, *, workspace_id: uuid.UUID, user_id: uuid.UUID) -> list[dict[str, Any]]:
        """Open batches an owner/admin still needs to act on, each with its
        underlying row-level changes nested in so the reviewer can still see
        exactly what's in it before approving/rejecting the whole thing."""
        await self.bases.workspaces.require_permission(workspace_id=workspace_id, user_id=user_id, permission=Permission.SYNC_APPROVAL_MANAGE)
        batches = await self.batches.list_pending_for_workspace(workspace_id)
        result = []
        for batch, requester_name in batches:
            rows = await self.repo.list_for_batch(batch.id)
            result.append({
                "batch": batch,
                "requester_name": requester_name,
                "changes": [{"change": change, "table_name": table_name} for change, table_name in rows],
            })
        return result

    async def _get_batch_checked(self, *, batch_id: uuid.UUID, user_id: uuid.UUID) -> tuple[SyncChangeBatch, uuid.UUID]:
        batch = await self.batches.get(batch_id)
        if batch is None or batch.status != "pending":
            raise NotFoundError("Batch not found")
        await self.bases.workspaces.require_permission(
            workspace_id=batch.workspace_id, user_id=user_id, permission=Permission.SYNC_APPROVAL_MANAGE
        )
        return batch, batch.workspace_id

    async def _requester_name(self, user_id: uuid.UUID) -> str:
        user = await self.users.get_by_id(user_id)
        return user.name if user is not None else "Unknown"

    async def approve_batch(self, *, batch_id: uuid.UUID, user_id: uuid.UUID) -> tuple[SyncChangeBatch, str]:
        batch, workspace_id = await self._get_batch_checked(batch_id=batch_id, user_id=user_id)
        requester_name = await self._requester_name(batch.requested_by)
        rows = await self.repo.list_for_batch(batch.id)

        pool = await get_arq_pool()
        for change, _table_name in rows:
            change.status = "approved"
            change.reviewed_by = user_id
            change.reviewed_at = datetime.now(timezone.utc)
            await self.audit.log(
                workspace_id=workspace_id, user_id=user_id, action="sync_change.approved", resource_type="record",
                resource_id=str(change.row_id), details={"table_id": str(change.table_id), "operation": change.operation},
            )
            await pool.enqueue_job(
                "push_record_to_source", str(change.table_id), change.row_id, change.operation, change.values,
                str(change.requested_by), external_pk=change.external_pk,
            )

        batch.status = "approved"
        batch.reviewed_by = user_id
        batch.reviewed_at = datetime.now(timezone.utc)
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="sync_change_batch.approved", resource_type="sync_change_batch",
            resource_id=str(batch.id), details={"change_count": len(rows)},
        )
        await self.db.commit()

        change_word = "change" if len(rows) == 1 else "changes"
        await self.notifications.create(
            user_id=batch.requested_by, title="Changes approved",
            message=f"Your batch of {len(rows)} {change_word} was approved and is being pushed to its source.",
        )
        return batch, requester_name

    async def reject_batch(
        self, *, batch_id: uuid.UUID, user_id: uuid.UUID, reason: str | None, restore: bool = False
    ) -> tuple[SyncChangeBatch, str]:
        batch, workspace_id = await self._get_batch_checked(batch_id=batch_id, user_id=user_id)
        if reason is not None and not reason.strip():
            raise ValidationError("Rejection reason can't be blank if provided")
        rows = await self.repo.list_for_batch(batch.id)
        if restore and any(change.operation in ("update", "delete") and change.previous_values is None for change, _ in rows):
            # Only possible for a row created before previous_values existed
            # (a pre-upgrade row still sitting unresolved) -- nothing was
            # captured to restore it to.
            raise ValidationError("Can't restore this batch: no prior state was recorded for one or more of its changes")
        requester_name = await self._requester_name(batch.requested_by)

        tables_by_id: dict[uuid.UUID, Table] = {}
        for change, _table_name in rows:
            change.status = "rejected"
            change.reviewed_by = user_id
            change.reviewed_at = datetime.now(timezone.utc)
            change.rejection_reason = reason
            await self.audit.log(
                workspace_id=workspace_id, user_id=user_id, action="sync_change.rejected", resource_type="record",
                resource_id=str(change.row_id),
                details={"table_id": str(change.table_id), "operation": change.operation, "reason": reason, "restored": restore},
            )
            if change.table_id not in tables_by_id:
                tables_by_id[change.table_id] = await self.db.get(Table, change.table_id)

        batch.status = "rejected"
        batch.reviewed_by = user_id
        batch.reviewed_at = datetime.now(timezone.utc)
        batch.rejection_reason = reason
        await self.audit.log(
            workspace_id=workspace_id, user_id=user_id, action="sync_change_batch.rejected", resource_type="sync_change_batch",
            resource_id=str(batch.id), details={"change_count": len(rows), "reason": reason, "restored": restore},
        )
        await self.db.commit()

        if restore:
            for change, _table_name in rows:
                await self._restore_local_row(change=change, table=tables_by_id[change.table_id], user_id=user_id)

        change_word = "change" if len(rows) == 1 else "changes"
        await self.notifications.create(
            user_id=batch.requested_by, title="Changes rejected",
            message=f"Your batch of {len(rows)} {change_word} was rejected"
            + (f": {reason}" if reason else " and will not be pushed to its source.")
            + (" The local changes have been reverted." if restore else ""),
        )
        return batch, requester_name

    async def _restore_local_row(self, *, change: PendingSyncChange, table: Table, user_id: uuid.UUID) -> None:
        """Undoes the local effect of a just-rejected pending change. Never
        pushes anything externally (skip_sync_push=True throughout) --
        nothing reached the external system for this change in the first
        place, which is exactly why rejecting it is safe to undo locally.
        Uses the approver's own user_id: reaching this method already
        required SYNC_APPROVAL_MANAGE, which only owners/admins hold, and
        every role with that permission also holds RECORD_WRITE/RECORD_DELETE
        (see ROLE_PERMISSIONS), so the record-service permission checks below
        are never the blocker."""
        # Local import: RecordService imports this module, so importing it at
        # module level here would be circular.
        from app.modules.records.service import RecordService

        records = RecordService(self.db)
        try:
            if change.operation == "insert":
                # Never reached the external side -- restoring means undoing
                # its local creation entirely.
                await records.delete_record(table_id=table.id, row_id=change.row_id, user_id=user_id, skip_sync_push=True)
            elif change.operation == "update":
                await records.update_record(
                    table_id=table.id, row_id=change.row_id, user_id=user_id, values=change.previous_values,
                    expected_version=None, skip_sync_push=True,
                )
            else:  # "delete"
                # The row is already gone locally -- restoring means
                # recreating it, then re-linking it to the external record it
                # already matches (never pushed, so the external side is
                # untouched) so the next real edit produces an UPDATE, not a
                # duplicate INSERT.
                response = await records.create_record(
                    table_id=table.id, user_id=user_id, values=change.previous_values, skip_sync_push=True
                )
                sync_table = schema_service.build_sync_columns_table(table.physical_table_name)
                await self.db.execute(
                    update(sync_table).where(sync_table.c._row_id == response.row_id).values(_external_pk=change.external_pk)
                )
            await self.db.commit()
        except NotFoundError:
            # Already consistent with what restoring would have produced
            # (e.g. the row was separately deleted since) -- nothing to do.
            await self.db.rollback()
