"""Demo for step 5: send 25 link-creation requests quickly.

Wait about a minute after running other try_*.bat files first, because they
also create links from your IP and count toward the same limit.
"""
import requests

BASE = "http://localhost:5000"
EMAIL, PASSWORD = "demo@example.com", "password123"


def main() -> None:
    requests.post(f"{BASE}/api/auth/signup", json={"email": EMAIL, "password": PASSWORD})
    token = requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    results: list[int] = []
    for i in range(1, 26):
        r = requests.post(f"{BASE}/api/links", json={"long_url": f"https://example.com/page/{i}"}, headers=headers)
        results.append(r.status_code)
        extra = f"remaining={r.headers.get('X-RateLimit-Remaining')}"
        if r.status_code == 429:
            extra = f"Retry-After={r.headers.get('Retry-After')}s  body={r.json()}"
        print(f"request {i:>2}: HTTP {r.status_code}  {extra}")

    print(f"\n{results.count(201)} created (201), {results.count(429)} blocked (429). Expected: 20 and 5 on a fresh minute.")
    other = requests.get(f"{BASE}/api/links", headers=headers)
    print(f"Reading links is NOT limited: GET /api/links -> HTTP {other.status_code}")


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print("\nCould not reach the server. Is start.bat running in another window?")
