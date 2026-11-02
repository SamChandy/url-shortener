"""Try the API without fighting terminal quoting.

Start the server first (start.bat), then run try_api.bat in a second window.
"""
from datetime import datetime, timedelta, timezone

import requests

BASE = "http://localhost:5000"
EMAIL, PASSWORD = "demo@example.com", "password123"


def show(title: str, r: requests.Response) -> None:
    print(f"\n--- {title}: HTTP {r.status_code}")
    print(r.json())


def main() -> None:
    show("signup (409 if you ran this before)",
         requests.post(f"{BASE}/api/auth/signup", json={"email": EMAIL, "password": PASSWORD}))

    r = requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    show("login", r)
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    show("login with wrong password",
         requests.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": "wrong-password"}))

    def create(title: str, body: dict) -> None:
        show(title, requests.post(f"{BASE}/api/links", json=body, headers=headers))

    create("random code", {"long_url": "https://example.com/some/long/page?x=1"})
    create("custom alias (409 if you ran this before)",
           {"long_url": "https://example.com", "custom_alias": "my-link"})
    expiry = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    create("with expiry", {"long_url": "https://example.com", "expires_at": expiry})
    create("bad URL", {"long_url": "not a url"})
    create("self-referencing URL", {"long_url": "http://localhost:5000/abc"})
    create("expiry in the past", {"long_url": "https://example.com", "expires_at": "2020-01-01T00:00:00Z"})
    show("no token", requests.post(f"{BASE}/api/links", json={"long_url": "https://example.com"}))
    show("my links", requests.get(f"{BASE}/api/links", headers=headers))


if __name__ == "__main__":
    try:
        main()
    except requests.ConnectionError:
        print("\nCould not reach the server. Is start.bat running in another window?")
