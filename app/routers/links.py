"""Authenticated link management: POST /api/links and GET /api/links."""
from flask import Blueprint, g, jsonify, request
from sqlalchemy import select

from app.auth import login_required
from app.database import get_db
from app.deps import current_settings
from app.models import Link
from app.schemas import LinkCreate, LinkOut, parse_json
from app.services.rate_limiter import rate_limit
from app.services.shortener import create_link

bp = Blueprint("links", __name__, url_prefix="/api/links")


@bp.post("")
@rate_limit("create")  # 20 requests/minute per IP, checked before authentication
@login_required
def create():
    payload = parse_json(LinkCreate)
    settings = current_settings()
    link = create_link(get_db(), g.current_user, payload, settings)
    return jsonify(LinkOut.from_link(link, settings.base_url).to_json()), 201


@bp.get("")
@login_required
def list_my_links():
    limit = min(max(request.args.get("limit", 50, type=int), 1), 100)
    offset = max(request.args.get("offset", 0, type=int), 0)
    rows = get_db().scalars(
        select(Link)
        .where(Link.user_id == g.current_user.id)
        .order_by(Link.created_at.desc(), Link.id.desc())
        .limit(limit)
        .offset(offset)
    )
    base_url = current_settings().base_url
    return jsonify([LinkOut.from_link(link, base_url).to_json() for link in rows])
