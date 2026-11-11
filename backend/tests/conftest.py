"""Test infra.

Runs against a REAL Postgres database (dataforge_test) rather than sqlite —
this app leans on asyncpg-specific behavior and per-table dynamic DDL
(app/modules/bases/schema_service.py), so a lighter-weight substitute would
test a different code path than production actually runs. The env vars
below must be set before `app.config`/`app.main` are ever imported (pydantic
Settings reads the environment once, at class instantiation), which is why
they're set at module scope here — conftest.py is always imported before any
test module, so this runs first.

Bring the test DB up once with:
    createdb -h localhost -p 5544 -U dataforge dataforge_test
    DATABASE_URL=postgresql+asyncpg://dataforge:dataforge@localhost:5544/dataforge_test alembic upgrade head
"""

import asyncio
import os
import uuid

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://dataforge:dataforge@localhost:5544/dataforge_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6390/15")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.db import DATA_SCHEMA, META_SCHEMA, SNAPSHOT_SCHEMA
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped so the SQLAlchemy async engine and the rate-limiter's
    Redis client -- both process-wide singletons created lazily on first use
    -- get bound once and stay valid for the whole run. pytest-asyncio's
    default per-function loop would tear down and recreate the loop between
    every test, orphaning both singletons' connections (asyncpg/redis-py
    connections are loop-bound) and surfacing as "Event loop is closed"."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _truncate_all_sync() -> None:
    """Plain psycopg2 (sync, no event loop involved) so this can run both
    outside any test's event loop (session start) and after each test without
    touching the asyncpg engine's loop-bound connection pool."""
    import psycopg2

    sync_dsn = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for schema in (DATA_SCHEMA, META_SCHEMA):
                cur.execute(
                    "select tablename from pg_tables where schemaname = %s and tablename != 'alembic_version'",
                    (schema,),
                )
                tables = [f'"{schema}"."{name}"' for (name,) in cur.fetchall()]
                if tables:
                    cur.execute(f"TRUNCATE TABLE {', '.join(tables)} RESTART IDENTITY CASCADE")
            # df_snapshots holds base-snapshot copy tables (modules/snapshots)
            # -- transient artifacts with no fixed structure of their own,
            # unlike DATA_SCHEMA/META_SCHEMA above. Truncating META_SCHEMA
            # already wipes the base_snapshots/base_snapshot_tables rows that
            # point at these, so a leftover copy table here is pure orphaned
            # cruft every test run -- drop each one outright rather than
            # truncate it.
            cur.execute("select tablename from pg_tables where schemaname = %s", (SNAPSHOT_SCHEMA,))
            snapshot_tables = [f'"{SNAPSHOT_SCHEMA}"."{name}"' for (name,) in cur.fetchall()]
            if snapshot_tables:
                cur.execute(f"DROP TABLE IF EXISTS {', '.join(snapshot_tables)}")
    finally:
        conn.close()


@pytest.fixture(autouse=True, scope="session")
def _clean_db_at_session_start():
    """A prior crashed run (interpreter killed mid-test, etc.) can skip the
    per-test teardown below and leave stale rows behind, which then makes an
    unrelated later run flaky (e.g. a "duplicate email" surprise). Belt and
    suspenders: also wipe once at the start of the whole session."""
    _truncate_all_sync()


@pytest.fixture(autouse=True)
def _clean_db():
    """Truncate every df_meta/df_data table between tests so each test starts
    from an empty database without paying for a schema rebuild each time."""
    yield
    _truncate_all_sync()


def _make_client() -> AsyncClient:
    # A fresh fake client IP per fixture instance keeps per-IP rate limits
    # (login/register) from bleeding between tests that request their own client.
    fake_ip = f"10.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}.{uuid.uuid4().int % 255}"
    transport = ASGITransport(app=app, client=(fake_ip, 123))
    return AsyncClient(transport=transport, base_url="http://test")


@pytest_asyncio.fixture
async def client():
    async with _make_client() as c:
        yield c


@pytest_asyncio.fixture
async def make_client():
    """For tests that need more than one logged-in identity at once (RBAC
    tests) -- each call gets its own fake IP so rate limits don't collide."""
    clients = []

    async def _factory() -> AsyncClient:
        c = _make_client()
        await c.__aenter__()
        clients.append(c)
        return c

    yield _factory
    for c in clients:
        await c.__aexit__(None, None, None)


async def register_user(client: AsyncClient, *, email: str | None = None, name: str = "Test User", password: str = "testpass123"):
    email = email or f"{uuid.uuid4().hex[:12]}@example.com"
    resp = await client.post("/api/auth/register", json={"email": email, "name": name, "password": password})
    assert resp.status_code == 201, resp.text
    tokens = resp.json()
    client.headers["Authorization"] = f"Bearer {tokens['access_token']}"
    return tokens


async def create_workspace_base_table(client: AsyncClient, *, workspace_name="WS", base_name="Base", table_name="Table"):
    ws = (await client.post("/api/workspaces", json={"name": workspace_name})).json()
    base = (await client.post(f"/api/workspaces/{ws['id']}/bases", json={"name": base_name})).json()
    table = (await client.post(f"/api/bases/{base['id']}/tables", json={"name": table_name})).json()
    return ws, base, table
