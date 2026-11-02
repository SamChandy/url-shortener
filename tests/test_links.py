import re

import pytest

INVALID_URLS = [
    "not a url",
    "ftp://example.com/file",
    "http://",
    "javascript:alert(1)",
    "http://user:pass@example.com",
    "http://hello",  # no dot in the hostname
    "//example.com",
    "https://exa mple.com",
]
SELF_REFERENCING_URLS = [
    "http://localhost:5000/abc",
    "https://LOCALHOST/x",
    "http://127.0.0.1:5000/x",
    "http://0.0.0.0/x",
    "http://[::1]/x",
]


def post_link(client, headers, **body):
    return client.post("/api/links", json=body, headers=headers)


def test_create_link_with_random_code(client, auth):
    r = post_link(client, auth, long_url="https://example.com/some/page?x=1")
    assert r.status_code == 201
    body = r.get_json()
    assert re.fullmatch(r"[A-Za-z0-9]{7}", body["code"])
    assert body["short_url"] == f"http://localhost:5000/{body['code']}"
    assert body["long_url"] == "https://example.com/some/page?x=1"
    assert body["expires_at"] is None and body["created_at"]


def test_creating_a_link_requires_login(client):
    assert post_link(client, {}, long_url="https://example.com").status_code == 401


def test_each_link_gets_a_different_code(client, auth):
    codes = {post_link(client, auth, long_url="https://example.com").get_json()["code"] for _ in range(10)}
    assert len(codes) == 10


def test_custom_alias(client, auth):
    r = post_link(client, auth, long_url="https://example.com", custom_alias="my-link_1")
    assert r.status_code == 201 and r.get_json()["code"] == "my-link_1"


def test_taken_alias_is_409_even_for_another_user(client, auth, other_auth):
    post_link(client, auth, long_url="https://example.com", custom_alias="taken")
    r = post_link(client, other_auth, long_url="https://example.org", custom_alias="taken")
    assert r.status_code == 409


@pytest.mark.parametrize("alias", ["ab", "has space", "bad/slash", "x" * 33, "api", "ADMIN", "héllo"])
def test_invalid_or_reserved_alias_is_422(client, auth, alias):
    r = post_link(client, auth, long_url="https://example.com", custom_alias=alias)
    assert r.status_code == 422


def test_blank_alias_means_random_code(client, auth):
    r = post_link(client, auth, long_url="https://example.com", custom_alias="  ")
    assert r.status_code == 201 and len(r.get_json()["code"]) == 7


@pytest.mark.parametrize("url", INVALID_URLS)
def test_invalid_urls_are_rejected(client, auth, url):
    assert post_link(client, auth, long_url=url).status_code == 422


@pytest.mark.parametrize("url", SELF_REFERENCING_URLS)
def test_self_referencing_urls_are_rejected(client, auth, url):
    r = post_link(client, auth, long_url=url)
    assert r.status_code == 422
    assert "back to this service" in r.get_json()["error"]


@pytest.mark.app_config(base_url="https://sho.rt")
def test_the_configured_base_url_host_is_blocked(client, auth):
    assert post_link(client, auth, long_url="https://sho.rt/abc").status_code == 422
    assert post_link(client, auth, long_url="https://example.com/abc").status_code == 201


def test_missing_long_url_reports_the_field(client, auth):
    r = post_link(client, auth)
    assert r.status_code == 422
    assert any(d["field"] == "long_url" for d in r.get_json()["details"])


def test_expiry_in_the_future_is_accepted(client, auth):
    r = post_link(client, auth, long_url="https://example.com", expires_at="2999-01-01T00:00:00Z")
    assert r.status_code == 201
    assert r.get_json()["expires_at"].startswith("2999-01-01T00:00:00")


def test_naive_expiry_is_treated_as_utc(client, auth):
    r = post_link(client, auth, long_url="https://example.com", expires_at="2999-01-01T00:00:00")
    assert r.status_code == 201


@pytest.mark.parametrize("value", ["2020-01-01T00:00:00Z", "not-a-date"])
def test_past_or_garbage_expiry_is_422(client, auth, value):
    assert post_link(client, auth, long_url="https://example.com", expires_at=value).status_code == 422


def test_list_shows_only_my_links_newest_first(client, auth, other_auth, new_link):
    first = new_link(auth, long_url="https://example.com/1")
    second = new_link(auth, long_url="https://example.com/2")
    theirs = new_link(other_auth, long_url="https://example.com/3")

    mine = client.get("/api/links", headers=auth).get_json()
    assert [link["code"] for link in mine] == [second["code"], first["code"]]
    assert [link["code"] for link in client.get("/api/links", headers=other_auth).get_json()] == [theirs["code"]]


def test_code_collision_is_retried(client, auth, monkeypatch):
    codes = iter(["aaaaaaa", "aaaaaaa", "bbbbbbb"])  # 2nd link first collides, then gets bbbbbbb
    monkeypatch.setattr("app.services.shortener.generate_code", lambda length: next(codes))
    assert post_link(client, auth, long_url="https://example.com/1").get_json()["code"] == "aaaaaaa"
    assert post_link(client, auth, long_url="https://example.com/2").get_json()["code"] == "bbbbbbb"


def test_gives_up_after_repeated_collisions(client, auth, monkeypatch):
    monkeypatch.setattr("app.services.shortener.generate_code", lambda length: "ccccccc")
    assert post_link(client, auth, long_url="https://example.com/1").status_code == 201
    r = post_link(client, auth, long_url="https://example.com/2")
    assert r.status_code == 500 and "error" in r.get_json()
