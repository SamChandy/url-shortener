"""Business logic for creating short links (no Flask request objects in here)."""
import re
import secrets
import string
from datetime import datetime, timezone
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ApiError
from app.models import Link, User
from app.schemas import LinkCreate

ALPHABET = string.ascii_letters + string.digits  # base62
ALIAS_RE = re.compile(r"^[A-Za-z0-9_-]{3,32}$")
RESERVED_ALIASES = {"api", "health", "docs", "static", "admin", "login", "signup", "favicon.ico"}
ALWAYS_BLOCKED_HOSTS = {"0.0.0.0", "::1"}
MAX_CODE_ATTEMPTS = 5


def generate_code(length: int) -> str:
    """Cryptographically random base62 code (62^7 ≈ 3.5 trillion combinations)."""
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def validate_long_url(raw: str, settings: Settings) -> str:
    """Return a cleaned URL or raise a 422 ApiError."""
    url = raw.strip()
    if not url or len(url) > 2048 or any(ch.isspace() for ch in url):
        raise ApiError(422, "Invalid URL")

    try:
        parts = urlsplit(url)
        _ = parts.port  # raises ValueError on a bad port
        host = parts.hostname
    except ValueError:
        raise ApiError(422, "Invalid URL") from None

    if parts.scheme.lower() not in {"http", "https"}:
        raise ApiError(422, "URL must start with http:// or https://")
    if not host:
        raise ApiError(422, "URL must include a hostname")
    if parts.username or parts.password:
        raise ApiError(422, "URL must not contain credentials")

    host = host.lower().rstrip(".")

    # Self-reference first: "localhost" has no dot, and it should get the helpful message.
    own_hosts = set(settings.blocked_host_list) | ALWAYS_BLOCKED_HOSTS
    base_host = urlsplit(settings.base_url).hostname
    if base_host:
        own_hosts.add(base_host.lower())
    if host in own_hosts:
        raise ApiError(422, "URL points back to this service")

    if "." not in host and ":" not in host:  # filters junk like http://hello
        raise ApiError(422, "URL hostname is not valid")
    return url


def validate_alias(alias: str) -> str:
    if not ALIAS_RE.fullmatch(alias):
        raise ApiError(422, "Alias must be 3-32 characters: letters, digits, '-' or '_'")
    if alias.lower() in RESERVED_ALIASES:
        raise ApiError(422, "That alias is reserved")
    return alias


def create_link(db: Session, user: User, payload: LinkCreate, settings: Settings) -> Link:
    long_url = validate_long_url(payload.long_url, settings)
    alias = validate_alias(payload.custom_alias) if payload.custom_alias else None

    if payload.expires_at is not None and payload.expires_at <= datetime.now(timezone.utc):
        raise ApiError(422, "expires_at must be in the future")

    # Random codes can (rarely) collide, so retry. The DB unique constraint is the
    # source of truth: it is race-free, unlike a "check then insert".
    for _ in range(1 if alias else MAX_CODE_ATTEMPTS):
        link = Link(
            code=alias or generate_code(settings.short_code_length),
            long_url=long_url,
            user_id=user.id,
            expires_at=payload.expires_at,
        )
        db.add(link)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if alias:
                raise ApiError(409, "That alias is already taken") from None
            continue
        db.refresh(link)
        return link

    raise ApiError(500, "Could not generate a unique code, please retry")
