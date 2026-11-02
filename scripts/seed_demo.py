"""Fill the demo account with realistic fake clicks so the dashboard charts look alive.

Needs the server running (start.bat) because the links are created through the API.
Clicks are written straight into the database. Running it again is safe: it replaces
the clicks on the three demo links instead of adding to them.
"""
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://localhost:5000"
EMAIL, PASSWORD = "demo@example.com", "password123"
DAYS = 30

# (alias, destination, number of clicks, device mix: Mobile / PC / Tablet / Other)
DEMO_LINKS = [
    ("demo-docs", "https://docs.python.org/3/", 420, (30, 62, 5, 3)),
    ("demo-blog", "https://example.com/blog/launch-day", 160, (55, 38, 5, 2)),
    ("demo-promo", "https://example.com/summer-sale", 45, (80, 12, 6, 2)),
]
COUNTRIES = {
    "India": 30, "United States": 25, "Germany": 10, "United Kingdom": 9, "Brazil": 6,
    "Japan": 5, "France": 4, "Canada": 4, "Australia": 3, "Unknown": 4,
}
SOFTWARE = {  # device -> [(browser, os, weight)]
    "Mobile": [("Mobile Safari", "iOS", 45), ("Chrome Mobile", "Android", 55)],
    "Tablet": [("Mobile Safari", "iOS", 60), ("Chrome", "Android", 40)],
    "PC": [("Chrome", "Windows", 45), ("Edge", "Windows", 20), ("Safari", "Mac OS X", 20), ("Firefox", "Linux", 15)],
    "Other": [("Googlebot", "Other", 100)],
}
DEVICES = ("Mobile", "PC", "Tablet", "Other")


def day_weights(today: date, rng: random.Random) -> tuple[list[date], list[float]]:
    """More traffic on recent days and on weekdays, with some noise."""
    days = [today - timedelta(days=i) for i in range(DAYS)]
    weights = []
    for i, day in enumerate(days):
        growth = 0.4 + 0.6 * (DAYS - i) / DAYS
        weekday = 0.6 if day.weekday() >= 5 else 1.0
        weights.append(growth * weekday * rng.uniform(0.7, 1.3))
    return days, weights


def build_clicks(link_id: int, total: int, device_mix: tuple[int, ...], rng: random.Random, now: datetime) -> list[dict]:
    days, weights = day_weights(now.date(), rng)
    rows = []
    for day in rng.choices(days, weights, k=total):
        start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        seconds = max(1.0, (min(start + timedelta(days=1), now) - start).total_seconds())
        device = rng.choices(DEVICES, device_mix)[0]
        browser, os_name, _ = rng.choices(SOFTWARE[device], [w for _, _, w in SOFTWARE[device]])[0]
        rows.append(
            {
                "link_id": link_id,
                "clicked_at": start + timedelta(seconds=rng.uniform(0, seconds)),
                "country": rng.choices(list(COUNTRIES), list(COUNTRIES.values()))[0],
                "device": device,
                "browser": browser,
                "os": os_name,
            }
        )
    return rows


def api_headers() -> dict[str, str]:
    requests.post(f"{BASE}/api/auth/signup", json={"email": EMAIL, "password": PASSWORD})
    r = requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def ensure_links(headers: dict[str, str]) -> dict[str, int]:
    """Create the demo links if they do not exist yet; return alias -> link id."""
    existing = {l["code"]: l["id"] for l in requests.get(f"{BASE}/api/links?limit=100", headers=headers).json()}
    for alias, url, _, _ in DEMO_LINKS:
        if alias not in existing:
            r = requests.post(f"{BASE}/api/links", json={"long_url": url, "custom_alias": alias}, headers=headers)
            r.raise_for_status()
            existing[alias] = r.json()["id"]
    return {alias: existing[alias] for alias, *_ in DEMO_LINKS}


def main() -> None:
    from sqlalchemy import delete

    from app.config import get_settings
    from app.database import SessionLocal, init_db
    from app.models import Click

    ids = ensure_links(api_headers())
    rng, now = random.Random(42), datetime.now(timezone.utc)

    init_db(get_settings().database_url)
    with SessionLocal.session_factory() as db:
        db.execute(delete(Click).where(Click.link_id.in_(ids.values())))
        for alias, _, total, mix in DEMO_LINKS:
            db.add_all(Click(**row) for row in build_clicks(ids[alias], total, mix, rng, now))
        db.commit()

    print(f"Seeded {sum(t for _, _, t, _ in DEMO_LINKS)} clicks over the last {DAYS} days.")
    print(f"Log in to the dashboard with  {EMAIL}  /  {PASSWORD}")


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print("Could not reach the server. Is start.bat running in another window?")
