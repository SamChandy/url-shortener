"""Password hashing, JWT creation/verification and the @login_required decorator."""
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, TypeVar, cast

from flask import g, request
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.database import get_db
from app.deps import current_settings
from app.errors import ApiError
from app.models import User

F = TypeVar("F", bound=Callable[..., Any])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Verified against when the email is unknown, so login takes the same time either way.
_DUMMY_HASH = pwd_context.hash("not-a-real-password")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str | None) -> bool:
    return pwd_context.verify(plain, hashed or _DUMMY_HASH) and hashed is not None


def create_access_token(user_id: int) -> tuple[str, int]:
    """Return (jwt, lifetime_in_seconds)."""
    settings = current_settings()
    lifetime = timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    claims = {"sub": str(user_id), "iat": now, "exp": now + lifetime}
    token = jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, int(lifetime.total_seconds())


def _unauthorized(message: str) -> ApiError:
    return ApiError(401, message, headers={"WWW-Authenticate": "Bearer"})


def get_current_user() -> User:
    """Resolve the user from the `Authorization: Bearer <token>` header."""
    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("Missing or malformed Authorization header")

    settings = current_settings()
    try:
        payload = jwt.decode(token.strip(), settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise _unauthorized("Invalid or expired token") from None

    user = get_db().get(User, user_id)
    if user is None:
        raise _unauthorized("Invalid or expired token")
    return user


def login_required(view: F) -> F:
    """Protect a route; the authenticated user is available as `g.current_user`."""

    @wraps(view)
    def wrapper(*args: Any, **kwargs: Any):
        g.current_user = get_current_user()
        return view(*args, **kwargs)

    return cast(F, wrapper)
