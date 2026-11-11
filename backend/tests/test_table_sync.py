"""Two-way sync, Stage 1 (DataForge -> source push only).

Exercises the real connector write path against two genuine external
databases rather than mocks:
  - Postgres: a disposable schema inside the same dataforge_test database
    stands in for "the external database" -- zero new infrastructure, real
    asyncpg writes.
  - MySQL: the dataforge-mysql container (mysql:8.0, database
    external_test_db, host networking so it's reachable at 127.0.0.1:3316
    with no port-publish step needed) already exists on this machine for
    exactly this purpose.

Following test_bulk_ops.py's pattern: push_record_to_source is an arq task,
and there's no worker process running in tests, so it's imported and awaited
directly with ctx={}, the same way the real worker would call it.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from elasticsearch import AsyncElasticsearch, ConflictError as ESConflictError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.modules.connectors.base import ConnectorError, ConnectorRowNotFoundError, TableRef
from app.modules.connectors.types.es_connector import ID_COLUMN, ElasticsearchConnector
from app.modules.connectors.types.mysql_connector import MySQLConnector
from app.modules.connectors.types.postgres_connector import PostgresConnector
from app.modules.connectors.types.sql_common import stringify_external_pk
from app.worker.tasks.automation_tasks import run_automation
from app.worker.tasks.sync_tasks import check_table_sync_deletions, poll_table_sync, push_record_to_source
from tests.conftest import create_workspace_base_table, register_user

PG_CONFIG = {"host": "localhost", "port": 5544, "database": "dataforge_test", "username": "dataforge", "password": "dataforge"}
MYSQL_CONFIG = {"host": "127.0.0.1", "port": 3316, "database": "external_test_db", "username": "dataforge", "password": "dataforge"}

CONNECTORS = [
    pytest.param(PostgresConnector, PG_CONFIG, "ext_orders_pg", id="postgres"),
    pytest.param(MySQLConnector, MYSQL_CONFIG, "ext_orders_mysql", id="mysql"),
]


def _dialect_of(connector_cls) -> str:
    return "postgres" if connector_cls is PostgresConnector else "mysql"


async def _reset_external_table(config: dict, table_name: str, *, dialect: str) -> None:
    """Drops and recreates a plain (id, name, amount) table standing in for
    "the external table" -- Postgres uses its own disposable schema (ext_test)
    since dataforge_test is shared with the app's own metadata; MySQL already
    has a dedicated database (external_test_db) with nothing else in it."""
    if dialect == "postgres":
        url = f"postgresql+asyncpg://{config['username']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}"
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.execute(text("CREATE SCHEMA IF NOT EXISTS ext_test"))
            await conn.execute(text(f"DROP TABLE IF EXISTS ext_test.{table_name}"))
            await conn.execute(text(f"CREATE TABLE ext_test.{table_name} (id SERIAL PRIMARY KEY, name TEXT, amount NUMERIC)"))
        await engine.dispose()
    else:
        url = f"mysql+asyncmy://{config['username']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}"
        engine = create_async_engine(url)
        async with engine.begin() as conn:
            await conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))
            await conn.execute(
                text(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY AUTO_INCREMENT, name VARCHAR(255), amount DECIMAL(10,2))")
            )
        await engine.dispose()


def _table_ref(table_name: str, *, dialect: str) -> TableRef:
    return TableRef(name=table_name, schema="ext_test" if dialect == "postgres" else None)


@pytest.mark.parametrize("connector_cls,config,table_name", CONNECTORS)
async def test_introspect_columns_flags_primary_key(connector_cls, config, table_name):
    dialect = _dialect_of(connector_cls)
    await _reset_external_table(config, table_name, dialect=dialect)
    connector = connector_cls(config)
    try:
        columns = await connector.introspect_columns(_table_ref(table_name, dialect=dialect))
    finally:
        await connector.close()

    by_name = {c.name: c for c in columns}
    assert by_name["id"].is_primary_key is True
    assert by_name["name"].is_primary_key is False
    assert by_name["amount"].is_primary_key is False


@pytest.mark.parametrize("connector_cls,config,table_name", CONNECTORS)
async def test_insert_update_delete_row(connector_cls, config, table_name):
    dialect = _dialect_of(connector_cls)
    await _reset_external_table(config, table_name, dialect=dialect)
    connector = connector_cls(config)
    ref = _table_ref(table_name, dialect=dialect)
    try:
        pk = await connector.insert_row(ref, {"name": "Widget", "amount": 9.99})
        assert pk is not None

        await connector.update_row(ref, "id", pk, {"name": "Widget v2", "amount": 12.5})
        rows = [r async for batch in connector.stream_rows(ref) for r in batch]
        assert len(rows) == 1
        assert rows[0]["name"] == "Widget v2"

        with pytest.raises(ConnectorRowNotFoundError):
            await connector.update_row(ref, "id", pk + 999, {"name": "ghost"})

        await connector.delete_row(ref, "id", pk)
        rows_after = [r async for batch in connector.stream_rows(ref) for r in batch]
        assert rows_after == []

        # Deleting an already-gone row is success, not an error.
        await connector.delete_row(ref, "id", pk)
    finally:
        await connector.close()


async def _current_user_id(client) -> str:
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


@pytest_asyncio.fixture
async def synced_table(client):
    """Registers a user, creates a workspace/base, connects to a Postgres
    external table as a data source, and imports it with sync_enabled=True --
    the full "enable sync" path exercised through the real API, not a
    shortcut into the service layer."""
    await _reset_external_table(PG_CONFIG, "ext_synced", dialect="postgres")
    await register_user(client, email=f"sync_{uuid.uuid4().hex[:8]}@example.com")
    user_id = await _current_user_id(client)
    ws, base, _ = await create_workspace_base_table(client)

    ds_resp = await client.post(
        f"/api/workspaces/{ws['id']}/data-sources",
        data={"name": "ExtPG", "source_type": "postgres", "config": json.dumps(PG_CONFIG)},
    )
    assert ds_resp.status_code == 201, ds_resp.text
    data_source_id = ds_resp.json()["id"]

    import_resp = await client.post(
        f"/api/bases/{base['id']}/import-from-source/{data_source_id}",
        json={"table_name": "ext_synced", "table_schema": "ext_test", "new_table_name": "Synced", "sync_enabled": True},
    )
    assert import_resp.status_code == 201, import_resp.text
    table = import_resp.json()
    return client, table, data_source_id, user_id


async def test_deleting_workspace_with_synced_table_succeeds(synced_table):
    """Regression: table_sync_configs.data_source_id was originally
    ON DELETE RESTRICT, which made workspace deletion 500 the instant any
    table had sync enabled -- Postgres hit the RESTRICT constraint while
    cascading through data_sources, independent of the (also cascading)
    tables path. Must be CASCADE at the DB level; the "don't orphan a live
    sync" guard belongs in DataSourceService.delete() instead."""
    client, table, _, _ = synced_table
    ws_resp = await client.get(f"/api/bases/{table['base_id']}")
    ws_id = ws_resp.json()["workspace_id"]

    delete_resp = await client.delete(f"/api/workspaces/{ws_id}")
    assert delete_resp.status_code == 204, delete_resp.text


async def test_deleting_synced_data_source_directly_is_blocked(synced_table):
    client, table, data_source_id, _ = synced_table
    resp = await client.delete(f"/api/data-sources/{data_source_id}")
    assert resp.status_code == 422
    assert "unlink" in resp.json()["detail"].lower()

    # Unlinking first makes the delete succeed.
    await client.delete(f"/api/tables/{table['id']}/sync")
    resp2 = await client.delete(f"/api/data-sources/{data_source_id}")
    assert resp2.status_code == 204


async def test_import_with_sync_enabled_creates_config(synced_table):
    client, table, data_source_id, _ = synced_table
    sync_resp = await client.get(f"/api/tables/{table['id']}/sync")
    assert sync_resp.status_code == 200
    body = sync_resp.json()
    assert body["sync_enabled"] is True
    assert body["data_source_id"] == data_source_id
    assert body["consecutive_failures"] == 0


async def test_create_record_pushes_insert_to_source(synced_table):
    client, table, _, user_id = synced_table
    field_names = {f["name"] for f in table["fields"]}
    assert {"name", "amount"} <= field_names

    resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "New Order", "amount": "42"}})
    assert resp.status_code == 201
    row = resp.json()

    await push_record_to_source({}, table["id"], row["row_id"], "insert", row["values"], user_id)

    connector = PostgresConnector(PG_CONFIG)
    try:
        rows = [r async for batch in connector.stream_rows(TableRef(name="ext_synced", schema="ext_test")) for r in batch]
    finally:
        await connector.close()
    assert any(r["name"] == "New Order" for r in rows)


async def test_update_and_delete_push_to_source(synced_table):
    client, table, _, user_id = synced_table

    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Order A", "amount": "10"}})
    row = create_resp.json()
    await push_record_to_source({}, table["id"], row["row_id"], "insert", row["values"], user_id)

    update_resp = await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}", json={"values": {"name": "Order A (updated)"}, "expected_version": row["version"]}
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    await push_record_to_source({}, table["id"], row["row_id"], "update", updated["values"], user_id)

    connector = PostgresConnector(PG_CONFIG)
    try:
        rows = [r async for batch in connector.stream_rows(TableRef(name="ext_synced", schema="ext_test")) for r in batch]
        assert any(r["name"] == "Order A (updated)" for r in rows)
        external_pk = next(r["id"] for r in rows if r["name"] == "Order A (updated)")
    finally:
        await connector.close()

    delete_resp = await client.delete(f"/api/tables/{table['id']}/rows/{row['row_id']}")
    assert delete_resp.status_code == 204
    await push_record_to_source({}, table["id"], row["row_id"], "delete", None, user_id, external_pk=str(external_pk))

    connector = PostgresConnector(PG_CONFIG)
    try:
        rows_after = [r async for batch in connector.stream_rows(TableRef(name="ext_synced", schema="ext_test")) for r in batch]
    finally:
        await connector.close()
    assert rows_after == []


async def test_delete_field_backing_sync_pk_is_blocked(synced_table):
    """§1's bundled fix: deleting the field that backs external_pk_column
    doesn't break sync mechanics (the connector reads the raw external
    value independent of the Field row), but the column silently stops
    being visible/updated locally, which looks like a bug -- especially
    now that seeing the sync key (_id for ES, id here for Postgres) is
    sold as a feature. A different field must still be deletable."""
    client, table, _, _ = synced_table
    pk_field = next(f for f in table["fields"] if f["name"] == "id")
    other_field = next(f for f in table["fields"] if f["name"] == "amount")

    resp = await client.delete(f"/api/tables/{table['id']}/fields/{pk_field['id']}")
    assert resp.status_code == 422
    assert "sync" in resp.json()["detail"].lower()

    resp2 = await client.delete(f"/api/tables/{table['id']}/fields/{other_field['id']}")
    assert resp2.status_code == 204


async def test_repeated_failures_notify_and_auto_disable(synced_table):
    """Drops the external table out from under a working sync config, then
    drives 5 consecutive pushes (the auto-disable threshold) directly --
    asserts sync turns itself off with a distinct final notification instead
    of failing (and notifying) forever."""
    client, table, _, user_id = synced_table

    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Doomed", "amount": "1"}})
    row = create_resp.json()

    url = f"postgresql+asyncpg://{PG_CONFIG['username']}:{PG_CONFIG['password']}@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['database']}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("DROP TABLE ext_test.ext_synced"))
    await engine.dispose()

    for _ in range(5):
        await push_record_to_source({}, table["id"], row["row_id"], "insert", row["values"], user_id)

    sync_resp = await client.get(f"/api/tables/{table['id']}/sync")
    body = sync_resp.json()
    assert body["sync_enabled"] is False
    assert body["consecutive_failures"] >= 5
    assert body["last_error"]

    notifications = (await client.get("/api/notifications")).json()["notifications"]
    assert any("paused" in n["title"].lower() for n in notifications)


# ============================================================================
# Stage 2: pulling external changes
# ============================================================================


@pytest.mark.parametrize("connector_cls,config,table_name", CONNECTORS)
async def test_get_server_time_is_timezone_aware(connector_cls, config, table_name):
    """Regression: MySQL/asyncmy returns a naive datetime for any
    TIMESTAMP-family value -- get_server_time() must attach tzinfo itself
    (via UTC_TIMESTAMP, never the server's own configured timezone) or a
    naive watermark silently corrupts every downstream comparison against
    DataForge's own tz-aware _last_synced_at/_updated_at columns."""
    dialect = _dialect_of(connector_cls)
    await _reset_external_table(config, table_name, dialect=dialect)
    connector = connector_cls(config)
    try:
        server_time = await connector.get_server_time()
    finally:
        await connector.close()
    assert server_time.tzinfo is not None


def test_stringify_external_pk_decimal_canonicalization():
    """The exact bug class flagged in design review: a Decimal's str() is
    scale-sensitive, and different call sites (import, push, pull) must
    never produce different strings for what's really the same key."""
    assert stringify_external_pk(Decimal("5")) == stringify_external_pk(Decimal("5.00"))
    assert stringify_external_pk(Decimal("5.00")) == "5"
    assert stringify_external_pk(42) == "42"
    assert stringify_external_pk("already-a-string") == "already-a-string"


async def _reset_external_table_with_ts(table_name: str) -> None:
    """Postgres-only, adds an updated_at timestamp column for Stage 2's
    change-detection tests."""
    url = f"postgresql+asyncpg://{PG_CONFIG['username']}:{PG_CONFIG['password']}@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['database']}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS ext_test"))
        await conn.execute(text(f"DROP TABLE IF EXISTS ext_test.{table_name}"))
        await conn.execute(
            text(
                f"CREATE TABLE ext_test.{table_name} "
                "(id SERIAL PRIMARY KEY, name TEXT, amount NUMERIC, updated_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
        )
    await engine.dispose()


async def _external_execute(sql: str) -> None:
    url = f"postgresql+asyncpg://{PG_CONFIG['username']}:{PG_CONFIG['password']}@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['database']}"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.execute(text(sql))
    await engine.dispose()


@pytest_asyncio.fixture
async def pollable_table(client):
    """Like synced_table, but also configures Stage 2 pull (a designated
    updated_at column, fast intervals) via the real PATCH .../sync/pull
    endpoint."""
    await _reset_external_table_with_ts("ext_pollable")
    await register_user(client, email=f"poll_{uuid.uuid4().hex[:8]}@example.com")
    user_id = await _current_user_id(client)
    ws, base, _ = await create_workspace_base_table(client)

    ds_resp = await client.post(
        f"/api/workspaces/{ws['id']}/data-sources",
        data={"name": "ExtPGPoll", "source_type": "postgres", "config": json.dumps(PG_CONFIG)},
    )
    assert ds_resp.status_code == 201, ds_resp.text
    data_source_id = ds_resp.json()["id"]

    import_resp = await client.post(
        f"/api/bases/{base['id']}/import-from-source/{data_source_id}",
        json={"table_name": "ext_pollable", "table_schema": "ext_test", "new_table_name": "Pollable", "sync_enabled": True},
    )
    assert import_resp.status_code == 201, import_resp.text
    table = import_resp.json()

    pull_resp = await client.patch(
        f"/api/tables/{table['id']}/sync/pull",
        json={"external_updated_at_column": "updated_at", "poll_interval_seconds": 60, "deletion_check_interval_seconds": 300},
    )
    assert pull_resp.status_code == 200, pull_resp.text
    return client, table, data_source_id, user_id


async def test_configure_pull_rejects_plain_date_column(client):
    """A plain DATE column (daily granularity) must be rejected even though
    it maps to the same coarse inferred_field_type ("date") as a real
    timestamp column -- see sql_common.py's _map_sa_type_to_field_type."""
    await _reset_external_table_with_ts("ext_date_reject")
    await _external_execute("ALTER TABLE ext_test.ext_date_reject ADD COLUMN just_a_date DATE NOT NULL DEFAULT CURRENT_DATE")

    await register_user(client, email=f"daterej_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, _ = await create_workspace_base_table(client)
    ds_resp = await client.post(
        f"/api/workspaces/{ws['id']}/data-sources",
        data={"name": "ExtPGDate", "source_type": "postgres", "config": json.dumps(PG_CONFIG)},
    )
    data_source_id = ds_resp.json()["id"]
    import_resp = await client.post(
        f"/api/bases/{base['id']}/import-from-source/{data_source_id}",
        json={"table_name": "ext_date_reject", "table_schema": "ext_test", "new_table_name": "DateReject", "sync_enabled": True},
    )
    table = import_resp.json()

    resp = await client.patch(
        f"/api/tables/{table['id']}/sync/pull",
        json={"external_updated_at_column": "just_a_date", "poll_interval_seconds": 60},
    )
    assert resp.status_code == 422
    assert "date" in resp.json()["detail"].lower()


async def test_poll_table_sync_inserts_new_external_row(pollable_table):
    client, table, _, _ = pollable_table
    await _external_execute("INSERT INTO ext_test.ext_pollable (name, amount) VALUES ('Inserted Externally', 7.5)")

    await poll_table_sync({}, table["id"])

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert any(r["values"].get("name") == "Inserted Externally" for r in rows)

    sync_status = (await client.get(f"/api/tables/{table['id']}/sync")).json()
    assert sync_status["poll_paused"] is False
    assert sync_status["poll_consecutive_failures"] == 0


async def test_poll_table_sync_updates_existing_row_without_conflict(pollable_table):
    client, table, _, user_id = pollable_table

    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Original", "amount": "1"}})
    row = create_resp.json()
    await push_record_to_source({}, table["id"], row["row_id"], "insert", row["values"], user_id)

    await _external_execute("UPDATE ext_test.ext_pollable SET name = 'Changed Externally', updated_at = now()")
    await poll_table_sync({}, table["id"])

    updated = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert updated["values"]["name"] == "Changed Externally"

    notifications = (await client.get("/api/notifications")).json()["notifications"]
    assert not any("overwritten" in n["title"].lower() for n in notifications)


async def test_poll_table_sync_detects_and_resolves_conflict(pollable_table):
    """A row edited locally *after* its last successful sync, which also
    changed at the source, is a genuine conflict -- the external value wins
    (per the design review's rejection of cross-server timestamp tie-breaks)
    and it's surfaced via a distinct notification, never silently dropped."""
    client, table, _, user_id = pollable_table

    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Original", "amount": "1"}})
    row = create_resp.json()
    # Simulates the worker's push completing -- stamps _last_synced_at.
    await push_record_to_source({}, table["id"], row["row_id"], "insert", row["values"], user_id)

    # A local edit AFTER that stamp, with no push simulated for it this time
    # -- _updated_at is now newer than _last_synced_at.
    update_resp = await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}",
        json={"values": {"name": "Local Edit"}, "expected_version": row["version"]},
    )
    assert update_resp.status_code == 200

    # The source ALSO changed the same row.
    await _external_execute("UPDATE ext_test.ext_pollable SET name = 'External Edit', updated_at = now()")

    await poll_table_sync({}, table["id"])

    resolved = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert resolved["values"]["name"] == "External Edit"  # external wins

    notifications = (await client.get("/api/notifications")).json()["notifications"]
    assert any("overwritten" in n["title"].lower() for n in notifications)


async def test_check_table_sync_deletions_removes_local_row(pollable_table):
    client, table, _, user_id = pollable_table

    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Doomed", "amount": "1"}})
    row = create_resp.json()
    await push_record_to_source({}, table["id"], row["row_id"], "insert", row["values"], user_id)

    await _external_execute("DELETE FROM ext_test.ext_pollable")
    await check_table_sync_deletions({}, table["id"])

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert rows == []


async def test_check_table_sync_deletions_ignores_unpushed_rows(pollable_table):
    """A row created locally but whose insert-push hasn't landed yet has
    _external_pk = NULL -- it must never be treated as "deleted externally"
    just because it isn't in the external key set yet."""
    client, table, _, _ = pollable_table
    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Pending Push", "amount": "1"}})
    row = create_resp.json()

    await check_table_sync_deletions({}, table["id"])

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert any(r["row_id"] == row["row_id"] for r in rows)


class _FakeArqPool:
    """Captures enqueue_job calls instead of touching real Redis -- the
    manual-trigger endpoint's job is to enqueue the right jobs with the
    right args; whether arq itself dequeues and runs them is already
    covered by calling poll_table_sync/check_table_sync_deletions directly
    in the other tests above."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def enqueue_job(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))


async def test_run_pull_now_enqueues_immediate_poll(pollable_table, monkeypatch):
    client, table, _, _ = pollable_table
    fake_pool = _FakeArqPool()

    async def fake_get_arq_pool():
        return fake_pool

    monkeypatch.setattr("app.modules.connectors.api.get_arq_pool", fake_get_arq_pool)

    resp = await client.post(f"/api/tables/{table['id']}/sync/pull/run-now")
    assert resp.status_code == 200, resp.text
    assert [name for name, _, _ in fake_pool.calls] == ["poll_table_sync", "check_table_sync_deletions"]
    assert all(args == (table["id"],) for _, args, _ in fake_pool.calls)


async def test_run_pull_now_requires_pull_configured(synced_table, monkeypatch):
    """synced_table has push enabled but never called PATCH .../sync/pull --
    there's no updated_at column to poll on, so manual "sync now" must
    reject with a clear message rather than enqueueing a poll that would
    just no-op forever (poll_table_sync returns early when
    external_updated_at_column is None)."""
    client, table, _, _ = synced_table
    fake_pool = _FakeArqPool()

    async def fake_get_arq_pool():
        return fake_pool

    monkeypatch.setattr("app.modules.connectors.api.get_arq_pool", fake_get_arq_pool)

    resp = await client.post(f"/api/tables/{table['id']}/sync/pull/run-now")
    assert resp.status_code == 422
    assert "pull" in resp.json()["detail"].lower()
    assert fake_pool.calls == []


async def test_run_pull_now_resumes_from_paused(pollable_table, monkeypatch):
    """A manual "sync now" click is also the only way today to recover from
    poll_paused (see prepare_manual_poll's docstring) -- it must clear the
    pause and reset the failure counter so the next poll gets a clean
    attempt, not an instant no-op."""
    client, table, _, _ = pollable_table

    await _external_execute("DROP TABLE ext_test.ext_pollable")
    for _ in range(5):
        await poll_table_sync({}, table["id"])
    paused_status = (await client.get(f"/api/tables/{table['id']}/sync")).json()
    assert paused_status["poll_paused"] is True
    assert paused_status["poll_consecutive_failures"] >= 5

    fake_pool = _FakeArqPool()

    async def fake_get_arq_pool():
        return fake_pool

    monkeypatch.setattr("app.modules.connectors.api.get_arq_pool", fake_get_arq_pool)

    resp = await client.post(f"/api/tables/{table['id']}/sync/pull/run-now")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["poll_paused"] is False
    assert body["poll_consecutive_failures"] == 0
    assert len(fake_pool.calls) == 2


async def test_poll_and_push_health_are_independent(pollable_table):
    """Regression for the design review's point 4: a broken poll must never
    disable push (or vice versa) -- they're different axes on the same
    config row."""
    client, table, _, user_id = pollable_table

    await _external_execute("DROP TABLE ext_test.ext_pollable")

    for _ in range(5):
        await poll_table_sync({}, table["id"])

    status = (await client.get(f"/api/tables/{table['id']}/sync")).json()
    assert status["poll_paused"] is True
    assert status["poll_consecutive_failures"] >= 5
    assert status["sync_enabled"] is True  # push untouched by poll failures

    create_resp = await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"name": "Still Pushable", "amount": "1"}})
    row = create_resp.json()
    for _ in range(5):
        await push_record_to_source({}, table["id"], row["row_id"], "insert", row["values"], user_id)

    status_after_push_failures = (await client.get(f"/api/tables/{table['id']}/sync")).json()
    assert status_after_push_failures["sync_enabled"] is False
    assert status_after_push_failures["poll_paused"] is True  # unchanged, still true from before


async def test_automation_update_record_bumps_updated_at(client):
    """Regression for the Stage 2 prerequisite fix: automation_tasks.py's
    update_record action must bump _updated_at, or a real conflict is
    invisible to poll_table_sync's conflict detection (it would look like
    "only the external side changed")."""
    await register_user(client, email=f"automd_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, table = await create_workspace_base_table(client)
    await client.post(f"/api/tables/{table['id']}/fields", json={"name": "Status", "field_type": "text", "options": {}})
    row = (await client.post(f"/api/tables/{table['id']}/rows", json={"values": {"Status": "Old"}})).json()

    automation_resp = await client.post(
        f"/api/tables/{table['id']}/automations",
        json={"name": "bump test", "trigger_type": "record_updated", "trigger_config": {}},
    )
    automation_id = automation_resp.json()["id"]
    await client.post(
        f"/api/automations/{automation_id}/actions",
        json={"action_type": "update_record", "config": {"values": {"Status": "New"}}},
    )

    await run_automation({}, automation_id, row["row_id"], {"Status": "Old"})

    after = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert after["values"]["Status"] == "New"
    assert after["updated_at"] > after["created_at"]


# ============================================================================
# Elasticsearch two-way sync
# ============================================================================
#
# Elasticsearch has no relational schema/PK, so it doesn't fit the
# CONNECTORS/_reset_external_table parametrization above (SERIAL id,
# CREATE TABLE, integer pk + 999 to get a guaranteed-missing key) --
# separate index-based fixtures/helpers instead, exercised against the real
# dataforge-elasticsearch container (127.0.0.1:9250, security disabled) the
# same way Postgres/MySQL are exercised against real databases rather than
# mocks.

ES_CONFIG = {"url": "http://127.0.0.1:9250"}


async def _reset_es_index(index_name: str, *, with_ts: bool = False) -> None:
    """Deletes and recreates an ES index standing in for "the external
    index" -- an explicit mapping (not dynamic) so a date field really is
    an ES `date` type, matching what introspect_columns and the §5 "DATE"
    bypass need to see."""
    properties: dict = {"name": {"type": "text"}, "amount": {"type": "double"}}
    if with_ts:
        properties["updated_at"] = {"type": "date"}
    client = AsyncElasticsearch(ES_CONFIG["url"])
    try:
        await client.indices.delete(index=index_name, ignore_unavailable=True)
        await client.indices.create(index=index_name, mappings={"properties": properties})
    finally:
        await client.close()


async def _es_refresh(index_name: str) -> None:
    """The connector's own write methods don't force a refresh (mirroring
    real usage -- forcing one on every write would be a real perf cost in
    production), so tests that write via the connector and then immediately
    read back must refresh explicitly, or ES's default ~1s refresh_interval
    makes the read racy/flaky."""
    client = AsyncElasticsearch(ES_CONFIG["url"])
    try:
        await client.indices.refresh(index=index_name)
    finally:
        await client.close()


async def _es_index_doc(index_name: str, doc: dict, *, doc_id: str | None = None) -> str:
    """Indexes a document directly (bypassing the connector) to simulate an
    external write, refreshing synchronously so it's immediately visible."""
    client = AsyncElasticsearch(ES_CONFIG["url"])
    try:
        resp = await client.index(index=index_name, document=doc, id=doc_id, refresh="wait_for")
        return resp["_id"]
    finally:
        await client.close()


async def _es_update_doc(index_name: str, doc_id: str, doc: dict) -> None:
    client = AsyncElasticsearch(ES_CONFIG["url"])
    try:
        await client.update(index=index_name, id=doc_id, doc=doc, refresh="wait_for")
    finally:
        await client.close()


async def _es_delete_all(index_name: str) -> None:
    client = AsyncElasticsearch(ES_CONFIG["url"])
    try:
        await client.delete_by_query(index=index_name, query={"match_all": {}}, refresh=True)
    finally:
        await client.close()


def _es_ref(index_name: str) -> TableRef:
    return TableRef(name=index_name)


async def test_es_introspect_columns_synthesizes_id():
    await _reset_es_index("ext_es_orders")
    connector = ElasticsearchConnector(ES_CONFIG)
    try:
        columns = await connector.introspect_columns(_es_ref("ext_es_orders"))
    finally:
        await connector.close()

    by_name = {c.name: c for c in columns}
    assert by_name[ID_COLUMN].is_primary_key is True
    assert by_name["name"].is_primary_key is False
    assert by_name["amount"].is_primary_key is False
    assert by_name["amount"].inferred_field_type == "number"


async def test_es_insert_update_delete_row():
    index_name = "ext_es_widgets"
    await _reset_es_index(index_name)
    connector = ElasticsearchConnector(ES_CONFIG)
    ref = _es_ref(index_name)
    try:
        doc_id = await connector.insert_row(ref, {"name": "Widget", "amount": 9.99})
        assert doc_id is not None
        await _es_refresh(index_name)

        await connector.update_row(ref, ID_COLUMN, doc_id, {"name": "Widget v2", "amount": 12.5})
        await _es_refresh(index_name)
        rows = [r async for batch in connector.stream_rows(ref) for r in batch]
        assert len(rows) == 1
        assert rows[0]["name"] == "Widget v2"
        assert rows[0][ID_COLUMN] == doc_id

        with pytest.raises(ConnectorRowNotFoundError):
            await connector.update_row(ref, ID_COLUMN, "definitely-nonexistent-id", {"name": "ghost"})

        await connector.delete_row(ref, ID_COLUMN, doc_id)
        await _es_refresh(index_name)
        rows_after = [r async for batch in connector.stream_rows(ref) for r in batch]
        assert rows_after == []

        # Deleting an already-gone document is success, not an error.
        await connector.delete_row(ref, ID_COLUMN, doc_id)
    finally:
        await connector.close()


async def test_es_update_row_maps_conflict_error_as_retryable(monkeypatch):
    """Exact design-review requirement: a genuine version conflict must
    surface as a plain (retryable) ConnectorError, never miscategorized as
    ConnectorRowNotFoundError -- getting the except-clause order/specificity
    wrong here would silently break push's retry/notify contract."""
    connector = ElasticsearchConnector(ES_CONFIG)
    try:
        client = connector._client_instance()

        async def _raise_conflict(*args, **kwargs):
            meta = MagicMock()
            meta.status = 409
            raise ESConflictError("Conflict", meta, {"error": {"reason": "version conflict"}})

        monkeypatch.setattr(client, "update", _raise_conflict)

        with pytest.raises(ConnectorError) as exc_info:
            await connector.update_row(_es_ref("irrelevant"), ID_COLUMN, "some-id", {"name": "x"})
        assert not isinstance(exc_info.value, ConnectorRowNotFoundError)
    finally:
        await connector.close()


async def test_es_stream_changed_rows_and_fetch_primary_keys():
    index_name = "ext_es_changes"
    await _reset_es_index(index_name, with_ts=True)
    now = datetime.now(timezone.utc)
    old_id = await _es_index_doc(index_name, {"name": "Old", "amount": 1, "updated_at": (now - timedelta(hours=2)).isoformat()})
    new_id = await _es_index_doc(index_name, {"name": "New", "amount": 2, "updated_at": now.isoformat()})

    connector = ElasticsearchConnector(ES_CONFIG)
    ref = _es_ref(index_name)
    try:
        changed = [
            r
            async for batch in connector.stream_changed_rows(ref, updated_at_column="updated_at", since=now - timedelta(hours=1))
            for r in batch
        ]
        assert {r[ID_COLUMN] for r in changed} == {new_id}

        all_pks = await connector.fetch_primary_keys(ref, ID_COLUMN)
        assert all_pks == {old_id, new_id}
    finally:
        await connector.close()


async def test_es_configure_pull_accepts_date_field(client):
    """Regression for §5: Elasticsearch's own native type string for a
    `date` mapping is literally "date" (not a SQL dialect name) -- the
    existing plain-SQL-DATE-column rejection would otherwise reject this,
    the only case ES ever presents, making pull configuration for ES
    entirely unusable without the bypass."""
    index_name = "ext_es_date_ok"
    await _reset_es_index(index_name, with_ts=True)

    await register_user(client, email=f"esdate_{uuid.uuid4().hex[:8]}@example.com")
    ws, base, _ = await create_workspace_base_table(client)
    ds_resp = await client.post(
        f"/api/workspaces/{ws['id']}/data-sources",
        data={"name": "ExtESDate", "source_type": "elasticsearch", "config": json.dumps(ES_CONFIG)},
    )
    assert ds_resp.status_code == 201, ds_resp.text
    data_source_id = ds_resp.json()["id"]

    import_resp = await client.post(
        f"/api/bases/{base['id']}/import-from-source/{data_source_id}",
        json={"table_name": index_name, "new_table_name": "ESDateOK", "sync_enabled": True},
    )
    assert import_resp.status_code == 201, import_resp.text
    table = import_resp.json()

    pull_resp = await client.patch(
        f"/api/tables/{table['id']}/sync/pull",
        json={"external_updated_at_column": "updated_at", "poll_interval_seconds": 60},
    )
    assert pull_resp.status_code == 200, pull_resp.text


@pytest_asyncio.fixture
async def es_pollable_table(client):
    """Like pollable_table, but backed by a real Elasticsearch index instead
    of a Postgres table -- imports with sync enabled, then configures Stage
    2 pull via the real PATCH .../sync/pull endpoint."""
    index_name = f"ext_es_pollable_{uuid.uuid4().hex[:8]}"
    await _reset_es_index(index_name, with_ts=True)
    await register_user(client, email=f"espoll_{uuid.uuid4().hex[:8]}@example.com")
    user_id = await _current_user_id(client)
    ws, base, _ = await create_workspace_base_table(client)

    ds_resp = await client.post(
        f"/api/workspaces/{ws['id']}/data-sources",
        data={"name": "ExtES", "source_type": "elasticsearch", "config": json.dumps(ES_CONFIG)},
    )
    assert ds_resp.status_code == 201, ds_resp.text
    data_source_id = ds_resp.json()["id"]

    import_resp = await client.post(
        f"/api/bases/{base['id']}/import-from-source/{data_source_id}",
        json={"table_name": index_name, "new_table_name": "ESPollable", "sync_enabled": True},
    )
    assert import_resp.status_code == 201, import_resp.text
    table = import_resp.json()

    pull_resp = await client.patch(
        f"/api/tables/{table['id']}/sync/pull",
        json={"external_updated_at_column": "updated_at", "poll_interval_seconds": 60, "deletion_check_interval_seconds": 300},
    )
    assert pull_resp.status_code == 200, pull_resp.text
    return client, table, data_source_id, user_id, index_name


async def test_es_poll_table_sync_inserts_new_external_row(es_pollable_table):
    client, table, _, _, index_name = es_pollable_table
    await _es_index_doc(index_name, {"name": "Inserted Externally", "amount": 7.5, "updated_at": datetime.now(timezone.utc).isoformat()})

    await poll_table_sync({}, table["id"])

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert any(r["values"].get("name") == "Inserted Externally" for r in rows)
    # _id is a normal, visible, always-imported field for ES sources.
    assert any(r["values"].get(ID_COLUMN) for r in rows)

    sync_status = (await client.get(f"/api/tables/{table['id']}/sync")).json()
    assert sync_status["poll_paused"] is False
    assert sync_status["poll_consecutive_failures"] == 0


async def test_es_poll_table_sync_updates_existing_row_without_conflict(es_pollable_table):
    client, table, _, user_id, index_name = es_pollable_table

    doc_id = await _es_index_doc(index_name, {"name": "Original", "amount": 1, "updated_at": datetime.now(timezone.utc).isoformat()})
    await poll_table_sync({}, table["id"])  # pulls it in, establishes _external_pk/_last_synced_at

    await _es_update_doc(index_name, doc_id, {"name": "Changed Externally", "updated_at": datetime.now(timezone.utc).isoformat()})
    await poll_table_sync({}, table["id"])

    updated = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert updated["values"]["name"] == "Changed Externally"

    notifications = (await client.get("/api/notifications")).json()["notifications"]
    assert not any("overwritten" in n["title"].lower() for n in notifications)


async def test_es_poll_table_sync_detects_and_resolves_conflict(es_pollable_table):
    client, table, _, user_id, index_name = es_pollable_table

    doc_id = await _es_index_doc(index_name, {"name": "Original", "amount": 1, "updated_at": datetime.now(timezone.utc).isoformat()})
    await poll_table_sync({}, table["id"])
    row = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]

    # A local edit AFTER that pull, with no further poll yet -- _updated_at
    # is now newer than _last_synced_at.
    update_resp = await client.patch(
        f"/api/tables/{table['id']}/rows/{row['row_id']}",
        json={"values": {"name": "Local Edit"}, "expected_version": row["version"]},
    )
    assert update_resp.status_code == 200

    # The source ALSO changed the same document.
    await _es_update_doc(index_name, doc_id, {"name": "External Edit", "updated_at": datetime.now(timezone.utc).isoformat()})

    await poll_table_sync({}, table["id"])

    resolved = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"][0]
    assert resolved["values"]["name"] == "External Edit"  # external wins

    notifications = (await client.get("/api/notifications")).json()["notifications"]
    assert any("overwritten" in n["title"].lower() for n in notifications)


async def test_es_check_table_sync_deletions_removes_local_row(es_pollable_table):
    client, table, _, _, index_name = es_pollable_table

    await _es_index_doc(index_name, {"name": "Doomed", "amount": 1, "updated_at": datetime.now(timezone.utc).isoformat()})
    await poll_table_sync({}, table["id"])
    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert len(rows) == 1

    await _es_delete_all(index_name)
    await check_table_sync_deletions({}, table["id"])

    rows_after = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert rows_after == []


async def test_es_ingestion_lag_regression(es_pollable_table):
    """The exact scenario the rejected DataForge-clock watermark design
    (§3) would have lost permanently: Document A's own `updated_at` is
    stamped before it's actually indexed/searchable, so by the time a poll
    picks it up, wall-clock time has already moved past that timestamp. If
    the watermark advances to "now" (wall-clock, at poll time) rather than
    to Document A's own timestamp, a second document (B) whose own
    timestamp sits between the two -- itself perfectly ordinary, not late
    by any real amount -- would already be excluded by the time it's
    indexed, permanently. The data-derived watermark (this poll's max
    *observed* row timestamp, not wall-clock time) does not have this
    problem: it only ever advances to what was actually seen, so Document B
    is still >= it and gets picked up."""
    client, table, _, _, index_name = es_pollable_table

    doc_a_ts = datetime.now(timezone.utc) + timedelta(seconds=3)
    await _es_index_doc(index_name, {"name": "Document A", "amount": 1, "updated_at": doc_a_ts.isoformat()})
    await poll_table_sync({}, table["id"])

    rows = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert any(r["values"].get("name") == "Document A" for r in rows)

    sync_after_a = (await client.get(f"/api/tables/{table['id']}/sync")).json()
    last_polled_at = datetime.fromisoformat(sync_after_a["last_polled_at"])
    # The watermark must equal Document A's own timestamp (the coerced row
    # value), not the wall clock at the moment it was polled -- which, by
    # the time this assertion runs, is necessarily later than doc_a_ts.
    assert last_polled_at <= doc_a_ts + timedelta(seconds=1)

    # Document B's own timestamp is only 1 second after Document A's -- an
    # entirely ordinary gap, not a late arrival itself. A wall-clock
    # watermark (pinned to "now" when A was polled, already later than
    # doc_a_ts) could easily have already passed doc_b_ts, excluding it
    # forever. The data-derived watermark (<= doc_a_ts) has not.
    doc_b_ts = doc_a_ts + timedelta(seconds=1)
    await _es_index_doc(index_name, {"name": "Document B", "amount": 2, "updated_at": doc_b_ts.isoformat()})
    await poll_table_sync({}, table["id"])

    rows_after = (await client.get(f"/api/tables/{table['id']}/rows")).json()["rows"]
    assert any(r["values"].get("name") == "Document B" for r in rows_after)
