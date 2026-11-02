from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt


def creds(email="user@example.com", password="password123"):
    return {"email": email, "password": password}


def test_signup_returns_user_without_password(client):
    r = client.post("/api/auth/signup", json=creds())
    assert r.status_code == 201
    body = r.get_json()
    assert body["email"] == "user@example.com" and "id" in body
    assert "password" not in body and "hashed_password" not in body


def test_duplicate_email_is_rejected(client):
    client.post("/api/auth/signup", json=creds())
    assert client.post("/api/auth/signup", json=creds()).status_code == 409


def test_emails_are_case_insensitive(client):
    client.post("/api/auth/signup", json=creds("Test@Example.com"))
    assert client.post("/api/auth/signup", json=creds("test@example.com")).status_code == 409


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "password": "password123"},
        {"email": "a@example.com", "password": "short"},
        {"email": "a@example.com", "password": "x" * 73},  # bcrypt ignores bytes past 72
        {"email": "a@example.com"},
        {},
    ],
)
def test_invalid_signup_is_422(client, body):
    r = client.post("/api/auth/signup", json=body)
    assert r.status_code == 422
    assert "password123" not in r.get_data(as_text=True)


def test_non_json_body_is_400(client):
    r = client.post("/api/auth/signup", data="oops", content_type="text/plain")
    assert r.status_code == 400


def test_login_returns_a_working_token(client):
    client.post("/api/auth/signup", json=creds())
    r = client.post("/api/auth/login", json=creds())
    assert r.status_code == 200
    data = r.get_json()
    assert data["token_type"] == "bearer" and data["expires_in"] == 3600
    protected = client.get("/api/links", headers={"Authorization": f"Bearer {data['access_token']}"})
    assert protected.status_code == 200


def test_wrong_password_and_unknown_email_look_identical(client):
    client.post("/api/auth/signup", json=creds())
    wrong = client.post("/api/auth/login", json=creds(password="not-the-password"))
    unknown = client.post("/api/auth/login", json=creds(email="ghost@example.com"))
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.get_json() == unknown.get_json()
    assert wrong.headers["WWW-Authenticate"] == "Bearer"


def test_protected_route_needs_a_token(client):
    r = client.get("/api/links")
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("header", ["Bearer garbage", "Basic abc", "Bearer", ""])
def test_bad_authorization_headers_are_401(client, header):
    assert client.get("/api/links", headers={"Authorization": header}).status_code == 401


def test_expired_token_is_rejected(client, app):
    user_id = client.post("/api/auth/signup", json=creds()).get_json()["id"]
    secret = app.extensions["settings"].secret_key
    expired = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        secret, algorithm="HS256",
    )
    assert client.get("/api/links", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_token_for_a_missing_user_is_rejected(client, app):
    secret = app.extensions["settings"].secret_key
    token = jwt.encode(
        {"sub": "99999", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        secret, algorithm="HS256",
    )
    assert client.get("/api/links", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_token_signed_with_another_key_is_rejected(client):
    user_id = client.post("/api/auth/signup", json=creds()).get_json()["id"]
    forged = jwt.encode(
        {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "some-other-secret-key", algorithm="HS256",
    )
    assert client.get("/api/links", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
