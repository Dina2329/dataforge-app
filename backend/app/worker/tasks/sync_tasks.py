"""Two-way table sync: Stage 1 pushes DataForge -> source (below,
push_record_to_source), Stage 2 pulls source -> DataForge (poll_table_sync,
check_table_sync_deletions, tick_table_sync_polls).

Enqueued from RecordService._enqueue_sync_push (push) or the per-minute
tick_table_sync_polls cron (pull) -- always on the arq worker, never inline
on a request path, for the same reason automations/audit do: an external
database's own latency or an outage on its end must never sit between a user
and their own edit landing (architecture plan, section 5).
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import Column, DateTime, Text, delete as sa_delete, insert, select, update
from tenacity import retry, retry_if_exception_type, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from app.core.circuit_breaker import CircuitOpenError, check_circuit, record_failure, record_success
from app.core.db import SessionLocal
from app.core.encryption import decrypt_json
from app.core.lock import release, try_acquire
from app.core.ws_manager import manager as ws_manager
from app.modules.audit.service import AuditService
from app.modules.bases import schema_service
from app.modules.bases.models import Table
from app.modules.connectors.base import ConnectorError, ConnectorRowNotFoundError, TableRef
from app.modules.connectors.import_service import coerce_external_row
from app.modules.connectors.models import DataSource, TableSyncConfig
from app.modules.connectors.registry import get_connector
from app.modules.connectors.repository import TableSyncConfigRepository
from app.modules.connectors.service import breaker_key
from app.modules.connectors.sync_service import TableSyncService
from app.modules.connectors.types.sql_common import stringify_external_pk
from app.modules.notifications.service import NotificationService

POLL_LOCK_TTL_SECONDS = 300
DELETION_CHECK_LOCK_TTL_SECONDS = 1800


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    # A vanished external row won't stop vanishing on a 2nd/3rd try -- burning
    # retries against it just delays surfacing the (real, non-transient)
    # failure. Every other ConnectorError (a dropped connection, a timeout)
    # is exactly the transient case retrying is for.
    retry=retry_if_exception_type(ConnectorError) & retry_if_not_exception_type(ConnectorRowNotFoundError),
    reraise=True,
)
async def _do_push(connector, table_ref: TableRef, pk_column: str, operation: str, values: dict[str, Any] | None, external_pk: str | None):
    if operation == "insert":
        return await connector.insert_row(table_ref, values)
    if operation == "update":
        await connector.update_row(table_ref, pk_column, external_pk, values)
        return None
    if operation == "delete":
        await connector.delete_row(table_ref, pk_column, external_pk)
        return None
    raise ValueError(f"Unknown sync operation: {operation}")


async def push_record_to_source(
    ctx: dict,
    table_id: str,
    row_id: int,
    operation: str,
    values: dict[str, Any] | None,
    user_id: str,
    *,
    external_pk: str | None = None,
) -> None:
    async with SessionLocal() as db:
        table_uuid = uuid.UUID(table_id)
        sync = TableSyncService(db)
        config = await sync.get_config_for_table(table_uuid)
        # Sync may have been disabled/unlinked between enqueue and now, or
        # the table itself deleted -- both harmless races, not errors.
        if config is None or not config.sync_enabled:
            return
        table = await db.get(Table, table_uuid)
        if table is None:
            return

        # update's external_pk isn't known by the request path (only the
        # worker, reading the still-existing row, can look it up) -- insert
        # has none yet by definition; delete's was captured by the caller
        # before the row disappeared.
        if operation == "update":
            sync_table = schema_service.build_sync_columns_table(table.physical_table_name)
            pk_row = await db.execute(select(sync_table.c._external_pk).where(sync_table.c._row_id == row_id))
            external_pk = pk_row.scalar_one_or_none()
            if external_pk is None:
                await _handle_failure(
                    db, sync, config, table_uuid, row_id, user_id,
                    "This row hasn't finished its initial sync to the source yet -- edit it again once that completes.",
                )
                return

        data_source = await db.get(DataSource, config.data_source_id)
        if data_source is None:
            await _handle_failure(db, sync, config, table_uuid, row_id, user_id, "The linked data source no longer exists.")
            return

        source_config = decrypt_json(data_source.config_encrypted)
        connector = get_connector(data_source.source_type, source_config)
        table_ref = TableRef(name=config.external_table_name, schema=config.external_schema)
        key = breaker_key(config.data_source_id)
        # The external PK column was imported as an ordinary DataForge field
        # too (so it's visible/readable), but it must never be pushed back as
        # a value: on insert the external side assigns its own new key, and
        # rewriting a row's own PK via update isn't a supported Stage 1 edit.
        push_values = {k: v for k, v in values.items() if k != config.external_pk_column} if values is not None else values
        if operation == "insert" and push_values is not None:
            # A freshly-created local row reports every field it didn't set
            # as None -- sending that through as an explicit NULL breaks any
            # external column that's NOT NULL (even one with its own
            # DEFAULT, e.g. a typical "updated_at" column), since an
            # explicit NULL overrides a column default. Omitting the key
            # entirely lets the external side's own default apply, matching
            # "we never set this" rather than "we set this to nothing."
            push_values = {k: v for k, v in push_values.items() if v is not None}

        try:
            await check_circuit(key)
            result = await _do_push(connector, table_ref, config.external_pk_column, operation, push_values, external_pk)
        except CircuitOpenError as exc:
            await _handle_failure(db, sync, config, table_uuid, row_id, user_id, str(exc))
            return
        except ConnectorRowNotFoundError as exc:
            # A real mismatch, not a connectivity problem -- don't trip the
            # breaker over it (Stage 2's reconciliation would be the actual
            # fix; for now this just fails loudly instead of silently).
            await _handle_failure(db, sync, config, table_uuid, row_id, user_id, str(exc))
            return
        except ConnectorError as exc:
            await record_failure(key)
            await _handle_failure(db, sync, config, table_uuid, row_id, user_id, str(exc))
            return
        finally:
            await connector.close()

        await record_success(key)
        await _stamp_sync_state(db, table, row_id, operation, result)
        await sync.record_success(config)
        await AuditService(db).log(
            workspace_id=await sync.bases.get_workspace_id_for_table(table_uuid),
            user_id=uuid.UUID(user_id),
            action="record.synced_to_source",
            resource_type="record",
            resource_id=str(row_id),
            details={"table_id": table_id, "operation": operation},
        )
        await db.commit()


async def _stamp_sync_state(db, table: Table, row_id: int, operation: str, insert_result: Any) -> None:
    if operation == "delete":
        return  # the row (and its sync columns) is already gone locally
    sync_table = schema_service.build_sync_columns_table(table.physical_table_name)
    values: dict[str, Any] = {"_last_synced_at": datetime.now(timezone.utc)}
    if operation == "insert":
        values["_external_pk"] = stringify_external_pk(insert_result)
    await db.execute(update(sync_table).where(sync_table.c._row_id == row_id).values(**values))


async def _handle_failure(
    db,
    sync: TableSyncService,
    config: TableSyncConfig,
    table_id: uuid.UUID,
    row_id: int,
    user_id: str,
    error: str,
) -> None:
    just_auto_disabled = await sync.record_failure(config, error)
    workspace_id = await sync.bases.get_workspace_id_for_table(table_id)
    await AuditService(db).log(
        workspace_id=workspace_id, user_id=uuid.UUID(user_id), action="record.sync_failed", resource_type="record",
        resource_id=str(row_id), details={"table_id": str(table_id), "error": error},
    )
    notifications = NotificationService(db)
    if just_auto_disabled:
        await notifications.create(
            user_id=uuid.UUID(user_id),
            title="Sync paused after repeated failures",
            message=f"Syncing this table to its data source failed {config.consecutive_failures} times in a row and has "
            f"been turned off. Last error: {error}",
            link=f"/tables/{table_id}",
        )
    else:
        await notifications.create(
            user_id=uuid.UUID(user_id),
            title="Couldn't sync a change to the data source",
            message=error,
            link=f"/tables/{table_id}",
        )
    await db.commit()


# -- Stage 2: pulling external changes ---------------------------------


async def _retrying(fn, *args, **kwargs):
    """Same retry discipline as push's _do_push (3 attempts, exponential
    backoff, only for ConnectorError) applied to a single connector call --
    a transient blip shouldn't cost a full strike against poll_consecutive_failures."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(ConnectorError),
        reraise=True,
    )
    async def _inner():
        return await fn(*args, **kwargs)

    return await _inner()


async def _handle_poll_failure(db, sync: TableSyncService, config: TableSyncConfig, table_id: uuid.UUID, error: str) -> None:
    just_auto_paused = await sync.record_poll_failure(config, error)
    workspace_id = await sync.bases.get_workspace_id_for_table(table_id)
    await AuditService(db).log(
        workspace_id=workspace_id, user_id=config.created_by, action="table_sync.poll_failed", resource_type="table",
        resource_id=str(table_id), details={"error": error},
    )
    notifications = NotificationService(db)
    if just_auto_paused:
        await notifications.create(
            user_id=config.created_by,
            title="Pulling changes paused after repeated failures",
            message=f"Checking the data source for changes failed {config.poll_consecutive_failures} times in a row "
            f"and has been turned off. Last error: {error}",
            link=f"/tables/{table_id}",
        )
    else:
        await notifications.create(
            user_id=config.created_by,
            title="Couldn't check the data source for changes",
            message=error,
            link=f"/tables/{table_id}",
        )
    await db.commit()


async def _load_connector(db, config: TableSyncConfig):
    """Returns (data_source, connector) or (None, None) if the data source
    was deleted out from under an active sync config."""
    data_source = await db.get(DataSource, config.data_source_id)
    if data_source is None:
        return None, None
    source_config = decrypt_json(data_source.config_encrypted)
    return data_source, get_connector(data_source.source_type, source_config)


async def poll_table_sync(ctx: dict, table_id: str) -> None:
    lock_key = f"poll_table_sync:{table_id}"
    if not await try_acquire(lock_key, ttl_seconds=POLL_LOCK_TTL_SECONDS):
        return  # a previous poll for this table hasn't finished yet
    try:
        await _poll_table_sync(table_id)
    finally:
        await release(lock_key)


async def _poll_table_sync(table_id: str) -> None:
    async with SessionLocal() as db:
        table_uuid = uuid.UUID(table_id)
        sync = TableSyncService(db)
        config = await sync.get_config_for_table(table_uuid)
        if config is None or not config.sync_enabled or config.poll_paused or not config.external_updated_at_column:
            return
        table = await db.get(Table, table_uuid)
        if table is None:
            return
        fields = await sync.bases.fields.list_for_table(table_uuid)
        fields_by_name = {f.name: f for f in fields}

        data_source, connector = await _load_connector(db, config)
        if data_source is None:
            await _handle_poll_failure(db, sync, config, table_uuid, "The linked data source no longer exists.")
            return
        table_ref = TableRef(name=config.external_table_name, schema=config.external_schema)
        key = breaker_key(config.data_source_id)
        updated_at_field = fields_by_name.get(config.external_updated_at_column)

        # The watermark for *this* poll's query, and the value the NEXT
        # poll's `since` will use, is derived entirely from the external
        # data actually observed (max db_column value across every row
        # processed) -- never from asking the connector "what time is it."
        # A connector's own clock (or DataForge's) isn't safe here: a
        # document can become visible to a query well after the instant its
        # own timestamp field records (ingestion/indexing lag is a known,
        # common pattern, not a hypothetical), and a wall-clock watermark
        # only ever advances forward, so a late-arriving row with an
        # earlier timestamp would be permanently excluded once the
        # watermark has passed it -- silent, permanent data loss. Data-
        # derived avoids the question entirely and applies uniformly to
        # every connector, not just Elasticsearch (which is what surfaced
        # this in the first place -- ES ingestion lag is common; get_server_time()
        # is kept only for configure_pull's one-time initial cutoff, see
        # ElasticsearchConnector.get_server_time's docstring).
        since = config.last_polled_at or datetime.min.replace(tzinfo=timezone.utc)
        max_seen: datetime | None = None
        # Stamped on every row touched this poll -- DataForge's own clock,
        # deliberately, not the connector's. _last_synced_at is only ever
        # compared against _updated_at (another DataForge-local column) for
        # conflict detection; keeping both sides of that comparison on the
        # same clock avoids a cross-clock drift risk that stamping this with
        # the *external* server's time would otherwise introduce.
        synced_at = datetime.now(timezone.utc)

        rows_updated = rows_inserted = conflicts = 0
        try:
            await check_circuit(key)

            sync_table = schema_service.build_sync_columns_table(table.physical_table_name)
            full_table = schema_service.build_data_table(table.physical_table_name, fields)
            full_table.append_column(Column("_external_pk", Text))
            full_table.append_column(Column("_last_synced_at", DateTime(timezone=True)))

            async for batch in connector.stream_changed_rows(
                table_ref, updated_at_column=config.external_updated_at_column, since=since
            ):
                pks = [stringify_external_pk(row[config.external_pk_column]) for row in batch]
                existing_result = await db.execute(
                    select(sync_table.c._external_pk, sync_table.c._row_id, sync_table.c._updated_at, sync_table.c._last_synced_at)
                    .where(sync_table.c._external_pk.in_(pks))
                )
                existing_by_pk = {r._external_pk: r for r in existing_result}

                for row in batch:
                    pk_str = stringify_external_pk(row[config.external_pk_column])
                    db_values = coerce_external_row(row, fields_by_name)

                    if updated_at_field is not None:
                        row_ts = db_values.get(updated_at_field.db_column_name)
                        if isinstance(row_ts, datetime):
                            if row_ts.tzinfo is None:
                                row_ts = row_ts.replace(tzinfo=timezone.utc)
                            if max_seen is None or row_ts > max_seen:
                                max_seen = row_ts

                    existing_row = existing_by_pk.get(pk_str)
                    if existing_row is not None:
                        is_conflict = (
                            existing_row._updated_at is not None
                            and existing_row._last_synced_at is not None
                            and existing_row._updated_at > existing_row._last_synced_at
                        )
                        await db.execute(
                            update(full_table)
                            .where(full_table.c._row_id == existing_row._row_id)
                            .values(**db_values, _last_synced_at=synced_at)
                        )
                        await ws_manager.broadcast(table_uuid, {"type": "record_change", "row_id": existing_row._row_id})
                        rows_updated += 1
                        if is_conflict:
                            conflicts += 1
                    else:
                        insert_result = await db.execute(
                            insert(full_table)
                            .values(**db_values, _external_pk=pk_str, _last_synced_at=synced_at, _created_by=config.created_by)
                            .returning(full_table.c._row_id)
                        )
                        new_row_id = insert_result.scalar_one()
                        await ws_manager.broadcast(table_uuid, {"type": "record_change", "row_id": new_row_id})
                        rows_inserted += 1
        except CircuitOpenError as exc:
            await _handle_poll_failure(db, sync, config, table_uuid, str(exc))
            return
        except ConnectorError as exc:
            await record_failure(key)
            await _handle_poll_failure(db, sync, config, table_uuid, str(exc))
            return
        finally:
            await connector.close()

        await record_success(key)
        if max_seen is not None:
            config.last_polled_at = max_seen
        await sync.record_poll_success(config)
        workspace_id = await sync.bases.get_workspace_id_for_table(table_uuid)
        await AuditService(db).log(
            workspace_id=workspace_id, user_id=config.created_by, action="table_sync.polled", resource_type="table",
            resource_id=str(table_uuid), details={"rows_updated": rows_updated, "rows_inserted": rows_inserted, "conflicts": conflicts},
        )
        if conflicts > 0:
            await NotificationService(db).create(
                user_id=config.created_by,
                title="Some edits were overwritten by the data source",
                message=f"{conflicts} row(s) in this table had a local edit made since the last sync, but the data "
                "source's value was applied anyway because it changed there too — review recent activity if that "
                "matters here.",
                link=f"/tables/{table_uuid}",
            )
        await db.commit()


async def check_table_sync_deletions(ctx: dict, table_id: str) -> None:
    """Separate cadence from poll_table_sync, deliberately -- a full
    primary-key-set fetch on both sides is cheap in isolation but must not
    run at whatever tight interval a user picks for upsert polling, and
    disabling it (deletion_check_interval_seconds = None) should not cost a
    table its fast upsert polling."""
    lock_key = f"check_table_sync_deletions:{table_id}"
    if not await try_acquire(lock_key, ttl_seconds=DELETION_CHECK_LOCK_TTL_SECONDS):
        return
    try:
        await _check_table_sync_deletions(table_id)
    finally:
        await release(lock_key)


async def _check_table_sync_deletions(table_id: str) -> None:
    async with SessionLocal() as db:
        table_uuid = uuid.UUID(table_id)
        sync = TableSyncService(db)
        config = await sync.get_config_for_table(table_uuid)
        if (
            config is None
            or not config.sync_enabled
            or config.poll_paused
            or not config.deletion_check_interval_seconds
        ):
            return
        table = await db.get(Table, table_uuid)
        if table is None:
            return

        data_source, connector = await _load_connector(db, config)
        if data_source is None:
            await _handle_poll_failure(db, sync, config, table_uuid, "The linked data source no longer exists.")
            return
        table_ref = TableRef(name=config.external_table_name, schema=config.external_schema)
        key = breaker_key(config.data_source_id)

        try:
            await check_circuit(key)
            external_pks = await _retrying(connector.fetch_primary_keys, table_ref, config.external_pk_column)
        except CircuitOpenError as exc:
            await _handle_poll_failure(db, sync, config, table_uuid, str(exc))
            return
        except ConnectorError as exc:
            await record_failure(key)
            await _handle_poll_failure(db, sync, config, table_uuid, str(exc))
            return
        finally:
            await connector.close()

        await record_success(key)
        sync_table = schema_service.build_sync_columns_table(table.physical_table_name)
        local_result = await db.execute(
            select(sync_table.c._row_id, sync_table.c._external_pk).where(sync_table.c._external_pk.isnot(None))
        )
        to_delete = [r._row_id for r in local_result if r._external_pk not in external_pks]
        if to_delete:
            await db.execute(sa_delete(sync_table).where(sync_table.c._row_id.in_(to_delete)))
            for row_id in to_delete:
                await ws_manager.broadcast(table_uuid, {"type": "record_change", "row_id": row_id})

        await sync.record_poll_success(config)
        workspace_id = await sync.bases.get_workspace_id_for_table(table_uuid)
        await AuditService(db).log(
            workspace_id=workspace_id, user_id=config.created_by, action="table_sync.deletions_applied", resource_type="table",
            resource_id=str(table_uuid), details={"count": len(to_delete)},
        )
        await db.commit()


async def tick_table_sync_polls(ctx: dict) -> None:
    """Runs every minute (arq cron), mirroring tick_scheduled_automations's
    shape exactly: find due work, enqueue it, advance the next-due
    timestamp, one commit. Two independent due-conditions (upsert polling,
    deletion checking) since each runs on its own configurable, per-table
    cadence."""
    from app.worker.arq_app import get_arq_pool

    async with SessionLocal() as db:
        repo = TableSyncConfigRepository(db)
        now = datetime.now(timezone.utc)
        due_poll = await repo.list_due_for_poll(now)
        due_deletion = await repo.list_due_for_deletion_check(now)
        if not due_poll and not due_deletion:
            return
        pool = await get_arq_pool()
        for config in due_poll:
            config.next_poll_at = now + timedelta(seconds=config.poll_interval_seconds)
            await pool.enqueue_job("poll_table_sync", str(config.table_id))
        for config in due_deletion:
            config.next_deletion_check_at = now + timedelta(seconds=config.deletion_check_interval_seconds)
            await pool.enqueue_job("check_table_sync_deletions", str(config.table_id))
        await db.commit()
