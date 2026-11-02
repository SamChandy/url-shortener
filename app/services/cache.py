"""Redis cache for link lookups.

Redis is an optimisation, never a dependency: if it is down the redirect still
works by reading PostgreSQL. After one failure we skip Redis for a short while
(a tiny circuit breaker) so a dead Redis does not slow down every request.
"""
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime

from redis import Redis
from redis.exceptions import RedisError

from app.schemas import ensure_utc

logger = logging.getLogger(__name__)

KEY_PREFIX = "link:"
RETRY_AFTER_SECONDS = 30.0


@dataclass(frozen=True)
class CachedLink:
    """The minimum needed to redirect and to record a click."""

    link_id: int
    long_url: str
    expires_at: datetime | None

    def is_expired(self, now: datetime) -> bool:
        return self.expires_at is not None and self.expires_at <= now

    def to_json(self) -> str:
        return json.dumps(
            {
                "link_id": self.link_id,
                "long_url": self.long_url,
                "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "CachedLink":
        data = json.loads(raw)
        expires = data["expires_at"]
        return cls(
            link_id=int(data["link_id"]),
            long_url=str(data["long_url"]),
            expires_at=ensure_utc(datetime.fromisoformat(expires)) if expires else None,
        )


class LinkCache:
    def __init__(self, client: Redis | None, ttl_seconds: int) -> None:
        self._client = client
        self._ttl = ttl_seconds
        self._retry_at = 0.0  # monotonic time before which Redis is skipped

    @property
    def available(self) -> bool:
        return self._client is not None and time.monotonic() >= self._retry_at

    def _trip(self, exc: Exception) -> None:
        self._retry_at = time.monotonic() + RETRY_AFTER_SECONDS
        logger.warning(
            "Redis unavailable (%s). Using the database only for the next %d seconds.",
            type(exc).__name__,
            int(RETRY_AFTER_SECONDS),
        )

    def get(self, code: str) -> CachedLink | None:
        if not self.available:
            return None
        try:
            raw = self._client.get(KEY_PREFIX + code)  # type: ignore[union-attr]
        except (RedisError, OSError) as exc:
            self._trip(exc)
            return None
        if raw is None:
            return None
        try:
            return CachedLink.from_json(raw.decode() if isinstance(raw, bytes) else raw)
        except (ValueError, KeyError, TypeError):
            logger.warning("Discarding corrupt cache entry for %s", code)
            self.delete(code)
            return None

    def set(self, code: str, entry: CachedLink, now: datetime) -> None:
        """Cache for CACHE_TTL_SECONDS, but never beyond the link's own expiry."""
        ttl = self._ttl
        if entry.expires_at is not None:
            ttl = min(ttl, int((entry.expires_at - now).total_seconds()))
        if ttl <= 0 or not self.available:
            return
        try:
            self._client.set(KEY_PREFIX + code, entry.to_json(), ex=ttl)  # type: ignore[union-attr]
        except (RedisError, OSError) as exc:
            self._trip(exc)

    def delete(self, code: str) -> None:
        if not self.available:
            return
        try:
            self._client.delete(KEY_PREFIX + code)  # type: ignore[union-attr]
        except (RedisError, OSError) as exc:
            self._trip(exc)
