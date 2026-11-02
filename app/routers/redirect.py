"""GET /<code>: the hot path. Redis first, PostgreSQL on a miss, click logged in the background."""
from datetime import datetime, timezone

from flask import Blueprint, redirect, request
from sqlalchemy import select

from app.database import get_db
from app.deps import current_cache, current_settings
from app.errors import ApiError
from app.models import Link
from app.schemas import ensure_utc
from app.services.cache import CachedLink
from app.services.tracker import ClickEvent, enqueue_click

bp = Blueprint("redirect", __name__)


@bp.get("/<code>", strict_slashes=False)  # /abc and /abc/ both work
def follow(code: str):
    now = datetime.now(timezone.utc)
    cache = current_cache()
    settings = current_settings()

    entry = cache.get(code)
    if entry is not None:
        cache_status = "HIT"
    else:
        row = get_db().execute(
            select(Link.id, Link.long_url, Link.expires_at).where(Link.code == code)
        ).first()
        if row is None:
            raise ApiError(404, "Link not found or expired")
        entry = CachedLink(link_id=row.id, long_url=row.long_url, expires_at=ensure_utc(row.expires_at))
        if not entry.is_expired(now):
            cache.set(code, entry, now)
        # MISS = Redis is working but did not have it; BYPASS = Redis disabled or down.
        cache_status = "MISS" if cache.available else "BYPASS"

    if entry.is_expired(now):
        cache.delete(code)
        raise ApiError(404, "Link not found or expired")

    # HEAD requests (link previews, uptime checks) should not count as clicks.
    if request.method == "GET" and settings.click_tracking_enabled:
        enqueue_click(
            ClickEvent(
                link_id=entry.link_id,
                clicked_at=now,
                ip=request.remote_addr,
                user_agent=request.headers.get("User-Agent", ""),
                geoip_db_path=settings.geoip_db_path,
            )
        )

    # 307 keeps every click flowing through us (a 301 would be cached by browsers).
    response = redirect(entry.long_url, code=307)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Cache"] = cache_status
    return response
