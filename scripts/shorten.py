"""Interactive helper: log in (or sign up) and shorten URLs. Uses only the standard library."""
import getpass
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

BASE = os.getenv("API_URL", "http://localhost:5000").rstrip("/")


def _parse(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw or b"{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def call(method: str, path: str, body: dict | None = None, token: str | None = None):
    """Return (status_code, json_body, headers). Raises URLError if the server is unreachable."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, _parse(response.read()), response.headers
    except urllib.error.HTTPError as err:
        return err.code, _parse(err.read()), err.headers


def explain(status: int, body: dict, headers) -> str:
    text = body.get("error") or f"HTTP {status}"
    for detail in body.get("details", []):
        text += f"\n     - {detail.get('field')}: {detail.get('message')}"
    if status == 429:
        text += f"\n     Try again in {headers.get('Retry-After', 'a few')} seconds."
    return text


def log_in() -> str | None:
    email = input("Email: ").strip().lower()
    password = getpass.getpass("Password (what you type stays hidden): ")
    credentials = {"email": email, "password": password}

    status, body, headers = call("POST", "/api/auth/login", credentials)
    if status == 401:
        answer = input("\nNo account matches that. Create a NEW account with this email and password? [y/N] ")
        if answer.strip().lower() != "y":
            return None
        status, body, headers = call("POST", "/api/auth/signup", credentials)
        if status == 409:
            print("\nThat email already has an account, so the password you typed is wrong. Run this again.")
            return None
        if status != 201:
            print(f"\nCould not create the account: {explain(status, body, headers)}")
            return None
        print("Account created.")
        status, body, headers = call("POST", "/api/auth/login", credentials)
    if status != 200:
        print(f"\nLogin failed: {explain(status, body, headers)}")
        return None
    print("Logged in.")
    return body["access_token"]


def shorten(token: str) -> bool:
    long_url = input("\nURL to shorten (just press Enter to quit): ").strip()
    if not long_url:
        return False
    payload: dict[str, Any] = {"long_url": long_url}

    alias = input("Custom alias, e.g. my-link (Enter to skip): ").strip()
    if alias:
        payload["custom_alias"] = alias

    days = input("Expire after how many days? (Enter = never): ").strip()
    if days:
        if not days.isdigit() or int(days) < 1:
            print("   Days must be a whole number like 7, so no expiry was set.")
        else:
            payload["expires_at"] = (datetime.now(timezone.utc) + timedelta(days=int(days))).isoformat()

    status, body, headers = call("POST", "/api/links", payload, token)
    if status == 201:
        print(f"\n   Short link:  {body['short_url']}")
        print(f"   Points to :  {body['long_url']}")
        if body.get("expires_at"):
            print(f"   Expires   :  {body['expires_at']}")
        print("   Paste the short link into your browser to try it.")
    else:
        print(f"\n   Could not shorten it: {explain(status, body, headers)}")
    return True


def main() -> None:
    print(f"URL shortener at {BASE}\n")
    try:
        token = log_in()
        while token and shorten(token):
            pass
    except urllib.error.URLError:
        print(f"\nCould not reach the server at {BASE}. Is it running? (docker-start.bat or start.bat)")
    except (KeyboardInterrupt, EOFError):
        print()


if __name__ == "__main__":
    main()
