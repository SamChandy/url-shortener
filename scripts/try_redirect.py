"""Demo for step 3. Start the server (start.bat) first, then run try_redirect.bat."""
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

BASE = "http://localhost:5000"
EMAIL, PASSWORD = "demo@example.com", "password123"

AGENTS = {
    "iPhone": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "iPad": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Windows Chrome": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
}


def hit(code: str, agent: str | None = None, method: str = "GET") -> requests.Response:
    headers = {"User-Agent": AGENTS[agent]} if agent else {}
    return requests.request(method, f"{BASE}/{code}", headers=headers, allow_redirects=False)


def describe(title: str, r: requests.Response) -> None:
    extra = f"  Location={r.headers.get('Location')}  X-Cache={r.headers.get('X-Cache')}" if r.status_code == 307 else f"  {r.text.strip()}"
    print(f"{title}: HTTP {r.status_code}{extra}")


def main() -> None:
    requests.post(f"{BASE}/api/auth/signup", json={"email": EMAIL, "password": PASSWORD})
    token = requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    def create(body: dict) -> str:
        return requests.post(f"{BASE}/api/links", json=body, headers=headers).json()["code"]

    code = create({"long_url": "https://example.com/hello"})
    print(f"Created short code: {code}\n")

    describe("1st visit (cache miss)", hit(code))
    describe("2nd visit (hit if Redis is running)", hit(code))
    for name in AGENTS:
        describe(f"visit as {name}", hit(code, name))
    describe("HEAD request (not counted)", hit(code, method="HEAD"))
    describe("unknown code", hit("nope1234"))

    soon = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()
    expiring = create({"long_url": "https://example.com/soon", "expires_at": soon})
    describe("\nexpiring link, right away", hit(expiring))
    print("waiting 6 seconds for it to expire...")
    time.sleep(6)
    describe("expiring link, after expiry", hit(expiring))

    time.sleep(1.5)  # let the background tracker finish writing
    from sqlalchemy import func, select

    from app.config import get_settings
    from app.database import SessionLocal, init_db
    from app.models import Click, Link

    init_db(get_settings().database_url)
    with SessionLocal() as db:
        rows = db.execute(
            select(Click.device, Click.browser, Click.os, Click.country, func.count())
            .join(Link, Link.id == Click.link_id)
            .where(Link.code == code)
            .group_by(Click.device, Click.browser, Click.os, Click.country)
        ).all()
    print(f"\nClicks stored in the database for {code}:")
    for device, browser, os_name, country, n in rows:
        print(f"  {n} x  device={device:<7} browser={browser:<14} os={os_name:<9} country={country}")


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print("\nCould not reach the server. Is start.bat running in another window?")
