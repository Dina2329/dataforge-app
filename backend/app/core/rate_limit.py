"""Redis-backed rate limiter (architecture plan, section 9: "top risks" calls
for rate limiting alongside per-connector circuit breakers). A fixed-window
counter per key -- simple and sufficient at this scale; a proper sliding-log
limiter isn't worth the complexity here.

Applied as a FastAPI dependency so each route picks its own key/threshold:
    @router.post("/login", dependencies=[Depends(rate_limit(key_prefix="login", max_requests=10, window_seconds=300))])
"""

from collections.abc import Callable

from fastapi import Request
from redis.asyncio import Redis

from app.config import settings
from app.core.errors import DataForgeError

_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.redis_url)
    return _redis


class RateLimitedError(DataForgeError):
    status_code = 429

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Too many requests — try again in {retry_after_seconds}s")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def rate_limit(
    *, key_prefix: str, max_requests: int, window_seconds: int, key_func: Callable[[Request], str] = _client_ip
):
    """Returns a FastAPI dependency enforcing at most `max_requests` per
    `window_seconds` per key (default key: client IP). Raises RateLimitedError
    (429) once the window's count is exceeded."""

    async def dependency(request: Request) -> None:
        key = f"rl:{key_prefix}:{key_func(request)}"
        client = _client()
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, window_seconds)
        if count > max_requests:
            ttl = await client.ttl(key)
            raise RateLimitedError(max(ttl, 1))

    return dependency
