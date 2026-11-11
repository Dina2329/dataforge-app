from datetime import datetime, timedelta, timezone

from jose import jwt

from app.config import settings
from tests.conftest import register_user


async def test_register_returns_tokens(client):
    tokens = await register_user(client, email="alice@example.com")
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"


async def test_register_duplicate_email_rejected(client, make_client):
    await register_user(client, email="dupe@example.com")
    other = await make_client()
    resp = await other.post(
        "/api/auth/register", json={"email": "dupe@example.com", "name": "Someone Else", "password": "testpass123"}
    )
    assert resp.status_code in (400, 409)


async def test_login_with_correct_password(client, make_client):
    await register_user(client, email="bob@example.com", password="correcthorse123")
    anon = await make_client()
    resp = await anon.post("/api/auth/login", json={"email": "bob@example.com", "password": "correcthorse123"})
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_login_with_wrong_password_rejected(client, make_client):
    await register_user(client, email="carol@example.com", password="correcthorse123")
    anon = await make_client()
    resp = await anon.post("/api/auth/login", json={"email": "carol@example.com", "password": "wrongpassword"})
    # This app deliberately raises ForbiddenError (403) rather than 401 for bad
    # credentials -- see AuthService.authenticate.
    assert resp.status_code == 403


async def test_me_requires_auth(make_client):
    anon = await make_client()
    resp = await anon.get("/api/auth/me")
    assert resp.status_code == 403  # HTTPBearer with no credentials -> 403, not 401


async def test_expired_access_token_is_401_not_403(make_client):
    """Regression test: an expired (or otherwise malformed) *access* token must
    come back as 401, never 403. apiClient's frontend interceptor only
    attempts a silent refresh-and-retry on 401 -- a real incident showed that
    when this path returned 403, an expired session surfaced as a permanent
    "Forbidden" on every request (e.g. "create workspace") until the user
    manually logged out and back in, because the interceptor never saw the
    401 it was watching for."""
    anon = await make_client()
    now = datetime.now(timezone.utc)
    expired_token = jwt.encode(
        {"sub": "11111111-1111-1111-1111-111111111111", "type": "access", "iat": now - timedelta(minutes=60), "exp": now - timedelta(minutes=30)},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    anon.headers["Authorization"] = f"Bearer {expired_token}"
    resp = await anon.get("/api/auth/me")
    assert resp.status_code == 401


async def test_garbage_access_token_is_401_not_403(make_client):
    anon = await make_client()
    anon.headers["Authorization"] = "Bearer not-a-real-token"
    resp = await anon.get("/api/auth/me")
    assert resp.status_code == 401


async def test_me_returns_current_user(client):
    tokens = await register_user(client, email="dana@example.com", name="Dana")
    resp = await client.get("/api/auth/me")
    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "dana@example.com"
    assert body["name"] == "Dana"


async def test_refresh_issues_new_access_token(client, make_client):
    tokens = await register_user(client, email="erin@example.com")
    anon = await make_client()
    resp = await anon.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()
    assert new_tokens["access_token"]

    anon.headers["Authorization"] = f"Bearer {new_tokens['access_token']}"
    me = await anon.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "erin@example.com"


async def test_refresh_with_garbage_token_rejected(make_client):
    anon = await make_client()
    resp = await anon.post("/api/auth/refresh", json={"refresh_token": "not-a-real-token"})
    assert resp.status_code == 403
