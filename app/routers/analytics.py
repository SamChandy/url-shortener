"""Owner-only analytics. 401 = not logged in, 403 = not your link, 404 = no such link."""
from collections.abc import Iterable

from flask import Blueprint, g, jsonify, request
from pydantic import BaseModel

from app.auth import login_required
from app.database import get_db
from app.deps import current_settings
from app.errors import ApiError
from app.models import Click
from app.schemas import (
    CountryClicks,
    DailyClicks,
    DeviceClicks,
    TopLinkOut,
    TotalClicksOut,
)
from app.services import analytics

bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


def _int_arg(name: str, default: int, low: int, high: int) -> int:
    raw = request.args.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ApiError(422, f"'{name}' must be an integer") from None
    if not low <= value <= high:
        raise ApiError(422, f"'{name}' must be between {low} and {high}")
    return value


def _json_list(items: Iterable[BaseModel]):
    return jsonify([item.model_dump(mode="json") for item in items])


@bp.get("/links/<code>/total")
@login_required
def total(code: str):
    db = get_db()
    link = analytics.get_owned_link(db, code, g.current_user)
    body = TotalClicksOut(code=link.code, total_clicks=analytics.total_clicks(db, link.id))
    return jsonify(body.model_dump())


@bp.get("/links/<code>/by-country")
@login_required
def by_country(code: str):
    db = get_db()
    link = analytics.get_owned_link(db, code, g.current_user)
    rows = analytics.clicks_by(db, link.id, Click.country)
    return _json_list(CountryClicks(country=value, clicks=n) for value, n in rows)


@bp.get("/links/<code>/by-device")
@login_required
def by_device(code: str):
    db = get_db()
    link = analytics.get_owned_link(db, code, g.current_user)
    rows = analytics.clicks_by(db, link.id, Click.device)
    return _json_list(DeviceClicks(device=value, clicks=n) for value, n in rows)


@bp.get("/links/<code>/per-day")
@login_required
def per_day(code: str):
    days = _int_arg("days", default=30, low=1, high=365)
    db = get_db()
    link = analytics.get_owned_link(db, code, g.current_user)
    rows = analytics.clicks_per_day(db, link.id, days)
    return _json_list(DailyClicks(date=day, clicks=n) for day, n in rows)


@bp.get("/top-links")
@login_required
def top_links():
    limit = _int_arg("limit", default=10, low=1, high=100)
    base_url = current_settings().base_url.rstrip("/")
    rows = analytics.top_links(get_db(), g.current_user.id, limit)
    return _json_list(
        TopLinkOut(code=code, short_url=f"{base_url}/{code}", long_url=long_url, clicks=n)
        for code, long_url, n in rows
    )
