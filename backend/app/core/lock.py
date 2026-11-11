"""Generic Redis-backed advisory lock -- same "generic primitive, callers
namespace the key themselves" spirit as app.core.circuit_breaker. Used to
stop a slow poll/deletion-check for one table piling up concurrent runs
against the same external source if it's still in flight when the next tick
fires.

The TTL is a crash-safety fallback ONLY, not the normal release path --
callers must explicitly `release` in a `finally` block once their run
finishes. A poll that fails fast (a dropped table, bad credentials) but
holds the lock for its full TTL would otherwise be unable to retry again
until the TTL lapses, even if the user configured a much shorter poll
interval expecting failures to count against the auto-pause threshold at
that cadence."""

from redis.asyncio import Redis

from app.config import settings

_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url)
    return _redis


async def try_acquire(key: str, *, ttl_seconds: int) -> bool:
    """Returns True if the lock was acquired, False if it's already held."""
    return bool(await _client().set(f"lock:{key}", "1", nx=True, ex=ttl_seconds))


async def release(key: str) -> None:
    await _client().delete(f"lock:{key}")
