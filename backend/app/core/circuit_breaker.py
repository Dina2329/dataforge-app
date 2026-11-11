"""Generic Redis-backed circuit breaker (architecture plan, section 9: "top
risks" calls for per-connector circuit breakers so a flaky external source
can't be hammered by repeated test/import attempts).

Deliberately generic on `key` -- callers namespace it themselves (e.g.
f"data_source:{id}") -- this is a reusable primitive, not connector-specific
machinery. State lives in Redis (already running for arq) rather than
in-process memory, so the breaker is shared correctly across the API process
and any future horizontally-scaled replicas.

Three Redis keys per breaker `key`, no separate "state" field -- state is
inferred from which keys exist:
  cb:open:{key}      TTL'd marker; present => circuit OPEN, reject immediately.
  cb:failures:{key}  counter with a sliding window; hitting the threshold trips cb:open.
A success clears both, so the first successful call after the open TTL lapses
(the implicit half-open trial) fully resets the breaker.
"""

from redis.asyncio import Redis

from app.config import settings
from app.core.errors import DataForgeError

FAILURE_THRESHOLD = 3
WINDOW_SECONDS = 120
COOLDOWN_SECONDS = 60

_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url)
    return _redis


class CircuitOpenError(DataForgeError):
    status_code = 503

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Too many recent connection failures — temporarily disabled, retry in {retry_after_seconds}s"
        )


async def check_circuit(key: str) -> None:
    """Raises CircuitOpenError without attempting any connection if `key`'s
    breaker is currently open. Call this BEFORE the real connector call."""
    ttl = await _client().ttl(f"cb:open:{key}")
    if ttl and ttl > 0:
        raise CircuitOpenError(ttl)


async def record_success(key: str) -> None:
    await _client().delete(f"cb:failures:{key}", f"cb:open:{key}")


async def record_failure(key: str) -> None:
    client = _client()
    failures_key = f"cb:failures:{key}"
    count = await client.incr(failures_key)
    if count == 1:
        await client.expire(failures_key, WINDOW_SECONDS)
    if count >= FAILURE_THRESHOLD:
        await client.set(f"cb:open:{key}", "1", ex=COOLDOWN_SECONDS)
        await client.delete(failures_key)
