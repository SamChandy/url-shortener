import time
from datetime import datetime, timedelta, timezone

from app.database import SessionLocal
from app.models import Link
from app.services.cache import CachedLink


def iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


def test_link_that_expired_in_the_database_is_404(client):
    user_id = client.post(
        "/api/auth/signup", json={"email": "a@example.com", "password": "password123"}
    ).get_json()["id"]
    with SessionLocal.session_factory() as db:
        db.add(
            Link(
                code="expired1", long_url="https://example.com", user_id=user_id,
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
        )
        db.commit()
    r = client.get("/expired1")
    assert r.status_code == 404
    assert "error" in r.get_json()


def test_link_works_before_expiry_and_404s_after(client, auth, new_link):
    code = new_link(auth, expires_at=iso(timedelta(seconds=2)))["code"]
    assert client.get(f"/{code}").status_code == 307  # warms the cache
    assert client.get(f"/{code}").status_code == 307
    time.sleep(2.2)
    assert client.get(f"/{code}").status_code == 404


def test_cache_entry_never_outlives_the_link(client, redis, auth, new_link):
    code = new_link(auth, expires_at=iso(timedelta(seconds=100)))["code"]
    client.get(f"/{code}")
    assert 0 < redis.ttl(f"link:{code}") <= 100


def test_a_stale_cache_entry_is_not_served(client, redis, auth, new_link):
    code = new_link(auth)["code"]
    stale = CachedLink(
        link_id=1, long_url="https://stale.example.com",
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=5),
    )
    redis.set(f"link:{code}", stale.to_json(), ex=60)
    assert client.get(f"/{code}").status_code == 404
    assert redis.get(f"link:{code}") is None  # and it was evicted


def test_the_api_refuses_to_create_an_already_expired_link(client, auth):
    r = client.post(
        "/api/links", headers=auth,
        json={"long_url": "https://example.com", "expires_at": iso(timedelta(minutes=-1))},
    )
    assert r.status_code == 422
