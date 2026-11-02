import pytest
from sqlalchemy import delete

from app.database import SessionLocal
from app.models import Link
from app.services import tracker

IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)


def test_redirect_is_a_307_not_a_301(client, auth, new_link):
    code = new_link(auth, long_url="https://example.com/target?a=1")["code"]
    r = client.get(f"/{code}")
    assert r.status_code == 307
    assert r.headers["Location"] == "https://example.com/target?a=1"
    assert r.headers["Cache-Control"] == "no-store"


def test_first_request_misses_the_cache_and_the_second_hits(client, auth, new_link):
    code = new_link(auth)["code"]
    assert client.get(f"/{code}").headers["X-Cache"] == "MISS"
    assert client.get(f"/{code}").headers["X-Cache"] == "HIT"


def test_cache_entry_has_a_ttl_of_at_most_one_hour(client, redis, auth, new_link):
    code = new_link(auth)["code"]
    client.get(f"/{code}")
    assert 0 < redis.ttl(f"link:{code}") <= 3600


def test_cache_serves_requests_even_if_the_database_row_is_gone(client, auth, new_link):
    code = new_link(auth)["code"]
    assert client.get(f"/{code}").status_code == 307
    tracker.wait_until_idle(10)
    with SessionLocal.session_factory() as db:
        db.execute(delete(Link).where(Link.code == code))
        db.commit()
    r = client.get(f"/{code}")
    assert r.status_code == 307 and r.headers["X-Cache"] == "HIT"


def test_unknown_code_is_404_json(client):
    r = client.get("/doesnotexist")
    assert r.status_code == 404
    assert "error" in r.get_json()


def test_health_is_not_swallowed_by_the_catch_all_route(client):
    assert client.get("/health").get_json() == {"status": "ok"}



@pytest.mark.app_config(cache_enabled=False)
def test_cache_can_be_switched_off(client, redis, auth, new_link):
    code = new_link(auth)["code"]
    assert client.get(f"/{code}").headers["X-Cache"] == "BYPASS"
    assert client.get(f"/{code}").headers["X-Cache"] == "BYPASS"
    assert redis.keys("link:*") == []


@pytest.mark.app_config(redis="down")
def test_redirect_still_works_when_redis_is_down(client, auth, new_link):
    code = new_link(auth)["code"]
    r = client.get(f"/{code}")
    assert r.status_code == 307 and r.headers["X-Cache"] == "BYPASS"
    assert client.get(f"/{code}").status_code == 307


def test_a_visit_records_one_click(client, auth, new_link, clicks_for):
    code = new_link(auth)["code"]
    client.get(f"/{code}", headers={"User-Agent": IPHONE})
    clicks = clicks_for(code)
    assert len(clicks) == 1
    assert clicks[0].country == "Unknown"  # no GeoIP file in tests


def test_head_requests_are_not_counted(client, auth, new_link, clicks_for):
    code = new_link(auth)["code"]
    assert client.head(f"/{code}").status_code == 307
    assert clicks_for(code) == []


def test_unknown_codes_record_nothing(client, clicks_for):
    client.get("/nope1234")
    assert clicks_for("nope1234") == []


def test_a_failing_tracker_never_breaks_the_redirect(client, auth, new_link, monkeypatch):
    def boom(event):
        raise RuntimeError("database exploded")

    monkeypatch.setattr("app.services.tracker.record_click", boom)
    code = new_link(auth)["code"]
    assert client.get(f"/{code}").status_code == 307
    assert tracker.wait_until_idle(10)  # the failure was logged, not left pending


@pytest.mark.app_config(click_tracking_enabled=False)
def test_click_tracking_can_be_switched_off(client, auth, new_link, clicks_for):
    code = new_link(auth)["code"]
    assert client.get(f"/{code}").status_code == 307
    assert clicks_for(code) == []
