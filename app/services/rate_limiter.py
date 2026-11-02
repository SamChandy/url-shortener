"""Fixed-window rate limiting.

Redis is the shared counter (so every worker/container sees the same numbers).
If Redis is down we fall back to a per-process in-memory counter instead of
failing open: protection gets weaker across several workers, but never disappears.
"""
import logging
import math
import threading
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import current_app, make_response, request
from redis import Redis
from redis.exceptions import RedisError

from app.errors import ApiError

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])
RETRY_REDIS_AFTER_SECONDS = 30.0
MAX_LOCAL_KEYS = 10_000


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int  # seconds until the window resets
    enforced: bool = True  # False when limiting is switched off

    def headers(self) -> dict[str, str]:
        if not self.enforced:
            return {}
        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(self.remaining),
        }
        if not self.allowed:
            headers["Retry-After"] = str(self.retry_after)
        return headers


class _LocalWindow:
    """Thread-safe in-memory fixed-window counter (the Redis fallback)."""

    def __init__(self, window_seconds: int) -> None:
        self._window = window_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, list[float]] = {}  # key -> [count, window_end]

    def hit(self, key: str) -> tuple[int, int]:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry[1] <= now:
                entry = [0, now + self._window]
                self._entries[key] = entry
            entry[0] += 1
            if len(self._entries) > MAX_LOCAL_KEYS:  # drop expired windows
                self._entries = {k: v for k, v in self._entries.items() if v[1] > now}
            return int(entry[0]), max(1, math.ceil(entry[1] - now))


class RateLimiter:
    def __init__(
        self, client: Redis | None, limit: int, window_seconds: int, enabled: bool = True
    ) -> None:
        self._client = client
        self._limit = limit
        self._window = window_seconds
        self._enabled = enabled
        self._local = _LocalWindow(window_seconds)
        self._retry_redis_at = 0.0

    def _redis_hit(self, key: str) -> tuple[int, int] | None:
        """Count one hit in Redis -> (count, seconds_left); None if Redis is unusable."""
        if self._client is None or time.monotonic() < self._retry_redis_at:
            return None
        try:
            pipe = self._client.pipeline(transaction=True)
            pipe.incr(key)
            pipe.ttl(key)
            count, ttl = pipe.execute()
            if ttl < 0:  # first hit, or a key left without expiry by a crash: (re)start the window
                self._client.expire(key, self._window)
                ttl = self._window
            return int(count), int(ttl)
        except (RedisError, OSError) as exc:
            self._retry_redis_at = time.monotonic() + RETRY_REDIS_AFTER_SECONDS
            logger.warning(
                "Redis unavailable for rate limiting (%s); using in-memory counters for %d seconds.",
                type(exc).__name__,
                int(RETRY_REDIS_AFTER_SECONDS),
            )
            return None

    def check(self, scope: str, identity: str) -> RateLimitResult:
        if not self._enabled:
            return RateLimitResult(True, self._limit, self._limit, 0, enforced=False)
        key = f"rl:{scope}:{identity}"
        count, seconds_left = self._redis_hit(key) or self._local.hit(key)
        return RateLimitResult(
            allowed=count <= self._limit,
            limit=self._limit,
            remaining=max(0, self._limit - count),
            retry_after=max(1, seconds_left),
        )


def rate_limit(scope: str) -> Callable[[F], F]:
    """Limit a route per client IP. Put it BELOW @bp.route and ABOVE @login_required."""

    def decorator(view: F) -> F:
        @wraps(view)
        def wrapper(*args: Any, **kwargs: Any):
            limiter: RateLimiter = current_app.extensions["rate_limiter"]
            result = limiter.check(scope, request.remote_addr or "unknown")
            if not result.allowed:
                raise ApiError(
                    429,
                    f"Too many requests. Try again in {result.retry_after} seconds.",
                    headers=result.headers(),
                )
            response = make_response(view(*args, **kwargs))
            response.headers.update(result.headers())
            return response

        return cast(F, wrapper)

    return decorator
