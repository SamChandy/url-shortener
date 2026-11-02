from datetime import datetime, timedelta, timezone

from fakeredis import FakeRedis, FakeServer
from redis import Redis

from app.services.cache import CachedLink, LinkCache


def fake_cache(ttl=3600):
    client = FakeRedis(server=FakeServer(), decode_responses=True)
    return LinkCache(client, ttl), client


def test_cached_link_survives_a_json_round_trip():
    expires = datetime(2999, 1, 1, tzinfo=timezone.utc)
    original = CachedLink(link_id=7, long_url="https://example.com/x", expires_at=expires)
    assert CachedLink.from_json(original.to_json()) == original
    no_expiry = CachedLink(link_id=1, long_url="https://example.com", expires_at=None)
    assert CachedLink.from_json(no_expiry.to_json()) == no_expiry


def test_ttl_is_capped_by_the_links_own_expiry():
    cache, redis = fake_cache(ttl=3600)
    now = datetime.now(timezone.utc)
    cache.set("c", CachedLink(1, "https://example.com", now + timedelta(seconds=100)), now)
    assert 0 < redis.ttl("link:c") <= 100


def test_already_expired_links_are_not_cached():
    cache, redis = fake_cache()
    now = datetime.now(timezone.utc)
    cache.set("c", CachedLink(1, "https://example.com", now - timedelta(seconds=1)), now)
    assert redis.exists("link:c") == 0


def test_corrupt_entries_are_discarded():
    cache, redis = fake_cache()
    redis.set("link:bad", "{not json")
    assert cache.get("bad") is None
    assert redis.exists("link:bad") == 0


def test_a_dead_redis_trips_the_circuit_breaker():
    dead = Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2, socket_timeout=0.2)
    cache = LinkCache(dead, 3600)
    assert cache.available
    assert cache.get("x") is None
    assert not cache.available  # now skipped for 30 seconds instead of timing out each request


def test_no_client_means_no_cache():
    cache = LinkCache(None, 3600)
    assert not cache.available and cache.get("x") is None
