"""Demo for step 4. Start the server (start.bat) first, then run try_analytics.bat."""
import time

import requests

BASE = "http://localhost:5000"
PASSWORD = "password123"

AGENTS = {
    "iPhone": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "iPad": "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Chrome": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Googlebot": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
}
VISITS = {"iPhone": 3, "Chrome": 2, "iPad": 1, "Googlebot": 1}  # 7 clicks in total


def login(email: str) -> dict[str, str]:
    requests.post(f"{BASE}/api/auth/signup", json={"email": email, "password": PASSWORD})
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def show(title: str, r: requests.Response) -> None:
    print(f"\n--- {title}: HTTP {r.status_code}")
    print(r.json())


def main() -> None:
    owner = login("demo@example.com")
    stranger = login("other@example.com")

    code = requests.post(f"{BASE}/api/links", json={"long_url": "https://example.com/analytics"}, headers=owner).json()["code"]
    print(f"Created link {code}; visiting it 7 times with different devices...")
    for agent, times in VISITS.items():
        for _ in range(times):
            requests.get(f"{BASE}/{code}", headers={"User-Agent": AGENTS[agent]}, allow_redirects=False)
    time.sleep(2)  # let the background tracker finish

    base = f"{BASE}/api/analytics/links/{code}"
    show("total (expect 7)", requests.get(f"{base}/total", headers=owner))
    show("by country (all 'Unknown' without a GeoIP file)", requests.get(f"{base}/by-country", headers=owner))
    show("by device (expect Mobile 3, PC 2, Tablet 1, Other 1)", requests.get(f"{base}/by-device", headers=owner))
    show("per day, last 7 days (today = 7)", requests.get(f"{base}/per-day?days=7", headers=owner))
    show("top links", requests.get(f"{BASE}/api/analytics/top-links?limit=5", headers=owner))

    print("\n===== access control =====")
    show("no token (expect 401)", requests.get(f"{base}/total"))
    show("someone else's link (expect 403)", requests.get(f"{base}/total", headers=stranger))
    show("unknown code (expect 404)", requests.get(f"{BASE}/api/analytics/links/nope1234/total", headers=owner))
    show("days=0 (expect 422)", requests.get(f"{base}/per-day?days=0", headers=owner))
    show("stranger's own top links (expect none of yours)", requests.get(f"{BASE}/api/analytics/top-links", headers=stranger))


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print("\nCould not reach the server. Is start.bat running in another window?")
