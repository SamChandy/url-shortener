"""Shared fixtures.

Every test gets a brand-new app with its own empty database and its own fake
Redis, so tests never touch your real .env, shortener.db or a real Redis.
Set TEST_DATABASE_URL to run the same suite against PostgreSQL (CI does this).
"""
import os

# Settings are read from the environment, so this must happen BEFORE the app is imported.
os.environ.update(
    DATABASE_URL="sqlite:///unused-placeholder.db",
    REDIS_URL="redis://localhost:6379/15",
    SECRET_KEY="test-secret-key-used-only-by-pytest",
    ACCESS_TOKEN_EXPIRE_MINUTES="60",
    BASE_URL="http://localhost:5000",
    BLOCKED_HOSTS="localhost,127.0.0.1",
    CACHE_ENABLED="true",
    CACHE_TTL_SECONDS="3600",
    RATE_LIMIT_REQUESTS="20",
    RATE_LIMIT_WINDOW_SECONDS="60",
    RATE_LIMIT_ENABLED="true",
    TRUSTED_PROXY_COUNT="0",
    GEOIP_DB_PATH="does-not-exist.mmdb",
)

from datetime import date, datetime, time, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402
from fakeredis import FakeRedis, FakeServer  # noqa: E402
from redis import Redis  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.auth import pwd_context  # noqa: E402
from app.database import Base, SessionLocal, get_engine  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Click, Link  # noqa: E402
from app.services import tracker  # noqa: E402

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# bcrypt's real cost (12 rounds) makes each signup/login take ~0.3 s; 4 rounds is plenty for tests.
pwd_context.update(bcrypt__rounds=4)


@pytest.fixture
def app(tmp_path, request):
    """A fresh app. Customise it with @pytest.mark.app_config(...)."""
    marker = request.node.get_closest_marker("app_config")
    overrides = dict(marker.kwargs) if marker else {}

    redis_client = FakeRedis(server=FakeServer(), decode_responses=True)
    if overrides.pop("redis", None) == "down":
        redis_client = Redis(
            host="127.0.0.1", port=1, decode_responses=True,
            socket_connect_timeout=0.2, socket_timeout=0.2,
        )

    settings = {
        "database_url": TEST_DATABASE_URL or f"sqlite:///{tmp_path / 'test.db'}",
        "rate_limit_requests": 1000,  # tests that care set their own limit
        **overrides,
    }
    flask_app = create_app(settings, redis_client=redis_client)
    flask_app.config.update(TESTING=True)
    Base.metadata.drop_all(get_engine())
    Base.metadata.create_all(get_engine())

    yield flask_app

    tracker.wait_until_idle(10)
    SessionLocal.remove()
    if TEST_DATABASE_URL:
        Base.metadata.drop_all(get_engine())
    get_engine().dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def redis(app):
    return app.extensions["redis"]


@pytest.fixture
def login_as(client):
    """login_as("a@b.com") -> Authorization headers (signs the user up first)."""

    def _login(email: str = "user@example.com", password: str = "password123") -> dict[str, str]:
        client.post("/api/auth/signup", json={"email": email, "password": password})
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.get_json()
        return {"Authorization": f"Bearer {r.get_json()['access_token']}"}

    return _login


@pytest.fixture
def auth(login_as):
    return login_as("user@example.com")


@pytest.fixture
def other_auth(login_as):
    return login_as("other@example.com")


@pytest.fixture
def new_link(client):
    """new_link(headers, long_url=..., custom_alias=..., expires_at=...) -> created link JSON."""

    def _new(headers, long_url: str = "https://example.com/page", **extra):
        r = client.post("/api/links", json={"long_url": long_url, **extra}, headers=headers)
        assert r.status_code == 201, r.get_json()
        return r.get_json()

    return _new


@pytest.fixture
def add_clicks():
    """Insert click rows directly: add_clicks(code, {"n": 3, "country": "India", "days_ago": 1}, ...)."""

    def _add(code: str, *specs: dict) -> None:
        today = datetime.now(timezone.utc).date()
        with SessionLocal.session_factory() as db:
            link_id = db.scalar(select(Link.id).where(Link.code == code))
            for spec in specs:
                day: date = today - timedelta(days=spec.get("days_ago", 0))
                when = datetime.combine(day, time(12, 0), tzinfo=timezone.utc)
                for _ in range(spec.get("n", 1)):
                    db.add(
                        Click(
                            link_id=link_id,
                            clicked_at=when,
                            country=spec.get("country", "Unknown"),
                            device=spec.get("device", "PC"),
                            browser="Chrome",
                            os="Windows",
                        )
                    )
            db.commit()

    return _add


@pytest.fixture
def clicks_for():
    """clicks_for(code) -> stored Click rows, after background tracking has finished."""

    def _clicks(code: str) -> list[Click]:
        tracker.wait_until_idle(10)
        with SessionLocal.session_factory() as db:
            stmt = select(Click).join(Link, Link.id == Click.link_id).where(Link.code == code)
            return list(db.scalars(stmt))

    return _clicks
