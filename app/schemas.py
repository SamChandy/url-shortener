"""Pydantic schemas: request validation and response shapes."""
from datetime import datetime, timezone
from typing import Any, TypeVar

from flask import request
from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, field_validator

from app.errors import ApiError
from app.models import Link, User

T = TypeVar("T", bound=BaseModel)


def ensure_utc(value: datetime | None) -> datetime | None:
    """Treat naive datetimes as UTC (SQLite drops tzinfo) and convert aware ones to UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def parse_json(model: type[T]) -> T:
    """Validate the JSON request body against `model`, or raise a 4xx ApiError."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "Request body must be a JSON object")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        details = [
            {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]}
            for e in exc.errors(include_url=False, include_context=False, include_input=False)
        ]
        raise ApiError(422, "Validation failed", details=details) from None


# ---------- auth ----------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, v: str) -> str:
        if len(v.encode("utf-8")) > 72:  # bcrypt silently truncates beyond 72 bytes
            raise ValueError("password must be at most 72 bytes")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower_email(cls, v: str) -> str:
        return v.lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return ensure_utc(v)  # type: ignore[return-value]

    @classmethod
    def from_user(cls, user: User) -> "UserOut":
        return cls.model_validate(user)


# ---------- links ----------
class LinkCreate(BaseModel):
    long_url: str = Field(min_length=1, max_length=2048)
    custom_alias: str | None = None
    expires_at: datetime | None = None

    @field_validator("custom_alias")
    @classmethod
    def _blank_alias_is_none(cls, v: str | None) -> str | None:
        return v.strip() or None if v is not None else None

    @field_validator("expires_at")
    @classmethod
    def _utc(cls, v: datetime | None) -> datetime | None:
        return ensure_utc(v)


class LinkOut(BaseModel):
    id: int
    code: str
    short_url: str
    long_url: str
    created_at: datetime
    expires_at: datetime | None

    @classmethod
    def from_link(cls, link: Link, base_url: str) -> "LinkOut":
        return cls(
            id=link.id,
            code=link.code,
            short_url=f"{base_url.rstrip('/')}/{link.code}",
            long_url=link.long_url,
            created_at=ensure_utc(link.created_at),  # type: ignore[arg-type]
            expires_at=ensure_utc(link.expires_at),
        )

    def to_json(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


# ---------- analytics ----------
class TotalClicksOut(BaseModel):
    code: str
    total_clicks: int


class CountryClicks(BaseModel):
    country: str
    clicks: int


class DeviceClicks(BaseModel):
    device: str
    clicks: int


class DailyClicks(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    clicks: int


class TopLinkOut(BaseModel):
    code: str
    short_url: str
    long_url: str
    clicks: int
