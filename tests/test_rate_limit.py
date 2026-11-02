from types import SimpleNamespace

import pytest
from fakeredis import FakeRedis, FakeServer

from app.services import rate_limiter
from app.services.rate_limiter import RateLimiter, _LocalWindow


def create(client, headers, **kwargs):
    return client.post("/api/links", json={"long_url": "https://example.com"}, headers=headers, **kwargs)


# ---------- through the API ----------
@pytest.mark.app_config(rate_limit_requests=3)
def test_requests_over_the_limit_get_429(client, auth):
    statuses = [create(client, auth).status_code for _ in range(5)]
    assert statuses == [201, 201, 201, 429, 429]


@pytest.mark.app_config(rate_limit_requests=3)
def test_429_explains_when_to_retry(client, auth):
    for _ in range(3):
        create(client, auth)
    r = create(client, auth)
    assert r.status_code == 429
    assert 1 <= int(r.headers["Retry-After"]) <= 60
    assert "Too many requests" in r.get_json()["error"]


@pytest.mark.app_config(rate_limit_requests=3)
def test_remaining_requests_are_reported(client, auth):
    remaining = [create(client, auth).headers["X-RateLimit-Remaining"] for _ in range(3)]
    assert remaining == ["2", "1", "0"]
    assert create(client, auth).headers["X-RateLimit-Limit"] == "3"


@pytest.mark.app_config(rate_limit_requests=3)
def test_each_ip_has_its_own_quota(client, auth):
    for _ in range(3):
        create(client, auth)
    assert create(client, auth).status_code == 429
    other_ip = create(client, auth, environ_overrides={"REMOTE_ADDR": "10.0.0.2"})
    assert other_ip.status_code == 201


@pytest.mark.app_config(rate_limit_requests=3)
def test_the_quota_comes_back_when_the_window_resets(client, redis, auth):
    for _ in range(3):
        create(client, auth)
    assert create(client, auth).status_code == 429
    redis.delete("rl:create:127.0.0.1")  # what Redis does itself when the 60 s expire
    assert create(client, auth).status_code == 201


@pytest.mark.app_config(rate_limit_requests=3)
def test_only_link_creation_is_limited(client, auth):
    for _ in range(3):
        create(client, auth)
    assert create(client, auth).status_code == 429
    assert client.get("/api/links", headers=auth).status_code == 200
    assert client.get("/health").status_code == 200


@pytest.mark.app_config(rate_limit_requests=3)
def test_unauthenticated_attempts_count_too(client):
    statuses = [create(client, {}).status_code for _ in range(4)]
    assert statuses == [401, 401, 401, 429]


@pytest.mark.app_config(rate_limit_requests=2, redis="down")
def test_limit_still_applies_when_redis_is_down(client, auth):
    statuses = [create(client, auth).status_code for _ in range(3)]
    assert statuses == [201, 201, 429]


@pytest.mark.app_config(rate_limit_requests=1, rate_limit_enabled=False)
def test_limiting_can_be_switched_off(client, auth):
    responses = [create(client, auth) for _ in range(3)]
    assert [r.status_code for r in responses] == [201, 201, 201]
    assert "X-RateLimit-Limit" not in responses[0].headers


# ---------- the limiter on its own ----------
def make_limiter(limit=3, window=60):
    client = FakeRedis(server=FakeServer(), decode_responses=True)
    return RateLimiter(client, limit, window), client


def test_limiter_allows_exactly_the_limit():
    limiter, _ = make_limiter(limit=3)
    results = [limiter.check("t", "ip") for _ in range(5)]
    assert [r.allowed for r in results] == [True, True, True, False, False]
    assert [r.remaining for r in results] == [2, 1, 0, 0, 0]
    assert all(1 <= r.retry_after <= 60 for r in results)


def test_limiter_keeps_identities_and_scopes_apart():
    limiter, _ = make_limiter(limit=1)
    assert limiter.check("t", "ip-1").allowed
    assert not limiter.check("t", "ip-1").allowed
    assert limiter.check("t", "ip-2").allowed
    assert limiter.check("other-scope", "ip-1").allowed


def test_limiter_repairs_a_counter_that_lost_its_expiry():
    limiter, redis = make_limiter(limit=3)
    redis.set("rl:t:ip", 5)  # e.g. left behind by a crash between INCR and EXPIRE
    assert not limiter.check("t", "ip").allowed
    assert 0 < redis.ttl("rl:t:ip") <= 60


def test_local_fallback_window_counts_and_resets(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(rate_limiter, "time", SimpleNamespace(monotonic=lambda: now[0]))
    window = _LocalWindow(window_seconds=60)
    assert window.hit("k")[0] == 1
    assert window.hit("k")[0] == 2
    assert window.hit("other")[0] == 1
    now[0] += 61  # the window has passed
    assert window.hit("k")[0] == 1
