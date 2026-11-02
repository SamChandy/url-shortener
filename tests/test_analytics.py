from datetime import datetime, timezone

import pytest

LINK_ENDPOINTS = ["total", "by-country", "by-device", "per-day"]


def get(client, path, headers=None):
    return client.get(f"/api/analytics{path}", headers=headers or {})


# ---------- access control ----------
@pytest.mark.parametrize("endpoint", LINK_ENDPOINTS)
def test_login_is_required(client, auth, new_link, endpoint):
    code = new_link(auth)["code"]
    assert get(client, f"/links/{code}/{endpoint}").status_code == 401


def test_top_links_requires_login(client):
    assert get(client, "/top-links").status_code == 401


@pytest.mark.parametrize("endpoint", LINK_ENDPOINTS)
def test_other_users_cannot_see_my_analytics(client, auth, other_auth, new_link, endpoint):
    code = new_link(auth)["code"]
    assert get(client, f"/links/{code}/{endpoint}", other_auth).status_code == 403
    assert get(client, f"/links/{code}/{endpoint}", auth).status_code == 200


@pytest.mark.parametrize("endpoint", LINK_ENDPOINTS)
def test_unknown_link_is_404(client, auth, endpoint):
    assert get(client, f"/links/nope1234/{endpoint}", auth).status_code == 404


# ---------- numbers ----------
def test_total_with_no_clicks_is_zero(client, auth, new_link):
    code = new_link(auth)["code"]
    assert get(client, f"/links/{code}/total", auth).get_json() == {"code": code, "total_clicks": 0}


def test_totals_and_breakdowns(client, auth, new_link, add_clicks):
    code = new_link(auth)["code"]
    add_clicks(
        code,
        {"n": 3, "country": "India", "device": "Mobile"},
        {"n": 2, "country": "Germany", "device": "PC"},
        {"n": 1, "country": "India", "device": "Tablet"},
    )
    assert get(client, f"/links/{code}/total", auth).get_json()["total_clicks"] == 6
    assert get(client, f"/links/{code}/by-country", auth).get_json() == [
        {"country": "India", "clicks": 4},
        {"country": "Germany", "clicks": 2},
    ]
    assert get(client, f"/links/{code}/by-device", auth).get_json() == [
        {"device": "Mobile", "clicks": 3},
        {"device": "PC", "clicks": 2},
        {"device": "Tablet", "clicks": 1},
    ]


def test_clicks_from_other_links_are_not_mixed_in(client, auth, new_link, add_clicks):
    mine, theirs = new_link(auth)["code"], new_link(auth)["code"]
    add_clicks(mine, {"n": 2})
    add_clicks(theirs, {"n": 5})
    assert get(client, f"/links/{mine}/total", auth).get_json()["total_clicks"] == 2


def test_per_day_fills_in_days_without_clicks(client, auth, new_link, add_clicks):
    code = new_link(auth)["code"]
    add_clicks(code, {"n": 2, "days_ago": 0}, {"n": 1, "days_ago": 2}, {"n": 5, "days_ago": 40})
    today = datetime.now(timezone.utc).date().isoformat()

    week = get(client, f"/links/{code}/per-day?days=7", auth).get_json()
    assert len(week) == 7
    assert week[-1] == {"date": today, "clicks": 2}
    assert week[-3]["clicks"] == 1 and week[-2]["clicks"] == 0
    assert [d["date"] for d in week] == sorted(d["date"] for d in week)
    assert sum(d["clicks"] for d in week) == 3  # the 40-day-old clicks are outside the window

    default = get(client, f"/links/{code}/per-day", auth).get_json()
    assert len(default) == 30 and sum(d["clicks"] for d in default) == 3
    assert sum(d["clicks"] for d in get(client, f"/links/{code}/per-day?days=60", auth).get_json()) == 8


@pytest.mark.parametrize("days", ["0", "366", "abc", "-3"])
def test_bad_days_value_is_422(client, auth, new_link, days):
    code = new_link(auth)["code"]
    assert get(client, f"/links/{code}/per-day?days={days}", auth).status_code == 422


def test_top_links_are_ranked_and_private(client, auth, other_auth, new_link, add_clicks):
    busy = new_link(auth, long_url="https://example.com/busy")["code"]
    quiet = new_link(auth, long_url="https://example.com/quiet")["code"]
    unused = new_link(auth, long_url="https://example.com/unused")["code"]
    stranger = new_link(other_auth, long_url="https://example.com/theirs")["code"]
    add_clicks(busy, {"n": 3})
    add_clicks(quiet, {"n": 1})
    add_clicks(stranger, {"n": 10})

    rows = get(client, "/top-links", auth).get_json()
    assert [(r["code"], r["clicks"]) for r in rows] == [(busy, 3), (quiet, 1), (unused, 0)]
    assert rows[0]["short_url"] == f"http://localhost:5000/{busy}"
    assert rows[0]["long_url"] == "https://example.com/busy"
    assert len(get(client, "/top-links?limit=1", auth).get_json()) == 1


@pytest.mark.parametrize("limit", ["0", "101", "x"])
def test_bad_limit_is_422(client, auth, limit):
    assert get(client, f"/top-links?limit={limit}", auth).status_code == 422


# ---------- the whole pipeline, end to end ----------
def test_a_real_redirect_shows_up_in_the_analytics(client, auth, new_link, clicks_for):
    code = new_link(auth)["code"]
    client.get(f"/{code}", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36"})
    clicks_for(code)  # waits for the background tracker
    assert get(client, f"/links/{code}/total", auth).get_json()["total_clicks"] == 1
    assert get(client, f"/links/{code}/by-country", auth).get_json() == [{"country": "Unknown", "clicks": 1}]
