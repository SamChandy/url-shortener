"""Click tracking that runs OFF the request path.

Flask has no BackgroundTasks, so clicks are handed to a small thread pool after
the redirect decision is made. Rules that keep this safe:
  * the request thread only captures plain values (ip, user agent, time);
  * the worker opens its OWN database session (never the request's session);
  * a worker never raises into the request, errors are logged;
  * the queue is bounded, so a slow database cannot exhaust memory.
"""
import ipaddress
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import geoip2.database
import geoip2.errors
from user_agents import parse as parse_user_agent_string

from app.database import SessionLocal
from app.models import Click

logger = logging.getLogger(__name__)

MAX_WORKERS = 4
MAX_PENDING = 10_000
UNKNOWN = "Unknown"

_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="click-tracker")
_cond = threading.Condition()
_pending = 0


@dataclass(frozen=True)
class ClickEvent:
    link_id: int
    clicked_at: datetime
    ip: str | None
    user_agent: str
    geoip_db_path: str


def parse_user_agent(user_agent: str) -> tuple[str, str, str]:
    """Return (device, browser, os). Device is Mobile / Tablet / PC / Other."""
    ua = parse_user_agent_string(user_agent or "")
    if ua.is_tablet:
        device = "Tablet"
    elif ua.is_mobile:
        device = "Mobile"
    elif ua.is_pc:
        device = "PC"
    else:
        device = "Other"
    return device, (ua.browser.family or "Other")[:64], (ua.os.family or "Other")[:64]


@lru_cache(maxsize=1)
def _geo_reader(path: str) -> geoip2.database.Reader | None:
    if not Path(path).is_file():
        logger.info("GeoIP database not found at %s; country will be 'Unknown'", path)
        return None
    return geoip2.database.Reader(path)


def lookup_country(ip: str | None, db_path: str) -> str:
    if not ip:
        return UNKNOWN
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return UNKNOWN
    if addr.is_private or addr.is_loopback or addr.is_reserved:
        return UNKNOWN
    reader = _geo_reader(db_path)
    if reader is None:
        return UNKNOWN
    try:
        return reader.country(ip).country.name or UNKNOWN
    except (geoip2.errors.AddressNotFoundError, ValueError):
        return UNKNOWN


def record_click(event: ClickEvent) -> None:
    """Write one click row (synchronous; the pool calls this)."""
    device, browser, os_name = parse_user_agent(event.user_agent)
    country = lookup_country(event.ip, event.geoip_db_path)
    with SessionLocal.session_factory() as session:  # a fresh session, not the request's
        session.add(
            Click(
                link_id=event.link_id,
                clicked_at=event.clicked_at,
                country=country[:64],
                device=device,
                browser=browser,
                os=os_name,
            )
        )
        session.commit()


def _worker(event: ClickEvent) -> None:
    global _pending
    try:
        record_click(event)
    except Exception:  # noqa: BLE001 - tracking must never break anything
        logger.exception("Failed to record click for link %s", event.link_id)
    finally:
        with _cond:
            _pending -= 1
            _cond.notify_all()


def enqueue_click(event: ClickEvent) -> None:
    """Schedule a click to be stored; returns immediately."""
    global _pending
    with _cond:
        if _pending >= MAX_PENDING:
            logger.warning("Click queue full; dropping a click for link %s", event.link_id)
            return
        _pending += 1
    try:
        _executor.submit(_worker, event)
    except RuntimeError:  # interpreter is shutting down
        with _cond:
            _pending -= 1


def wait_until_idle(timeout: float = 5.0) -> bool:
    """Block until queued clicks are written (used by tests)."""
    with _cond:
        return _cond.wait_for(lambda: _pending == 0, timeout)
