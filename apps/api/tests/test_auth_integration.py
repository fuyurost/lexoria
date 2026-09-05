"""Auth behavior against a real Postgres (TEST_DATABASE_URL required)."""
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("TEST_DATABASE_URL") is None,
    reason="TEST_DATABASE_URL is required for PG integration tests",
)

PASSWORD = "correct horse battery staple!"


def register(client, username="alice", email="alice@example.com"):
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": email, "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def login(client, identifier, password=PASSWORD):
    resp = client.post(
        "/api/v1/auth/login",
        json={"identifier": identifier, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def auth_header(session):
    return {"Authorization": f"Bearer {session['access_token']}"}


def test_register_login_me_flow(client):
    register(client)
    # duplicate email -> 409 with machine code
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "alice2", "email": "alice@example.com", "password": PASSWORD},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "duplicate_email"

    # login by username and by email (case-insensitive), token_type + user
    for identifier in ("alice", "ALICE", "Alice@Example.COM"):
        session = login(client, identifier)
        assert session["token_type"] == "bearer"
        assert session["access_token"]
        assert session["user"]["username"] == "alice"
        assert session["user"]["email"] == "alice@example.com"
        assert client.cookies.get("lexoria_refresh")

    # wrong password -> uniform 401
    resp = client.post(
        "/api/v1/auth/login",
        json={"identifier": "alice", "password": "nope-nope-nope"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "invalid_credentials"

    # /me with the access token
    session = login(client, "alice")
    resp = client.get("/api/v1/me", headers=auth_header(session))
    assert resp.status_code == 200
    assert resp.json()["username"] == "alice"

    # /me without a token -> 401
    assert client.get("/api/v1/me").status_code == 401


def test_refresh_rotation_and_logout(client):
    register(client)
    session = login(client, "alice")
    old_cookie = client.cookies.get("lexoria_refresh")

    resp = client.post("/api/v1/auth/refresh")  # cookie-only, no auth header
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]
    new_cookie = client.cookies.get("lexoria_refresh")
    assert new_cookie and new_cookie != old_cookie  # rotated secret

    # Selector (session id) never changes across rotations.
    assert new_cookie.split(".", 1)[0] == old_cookie.split(".", 1)[0]

    # A replayed OLD token must NOT rotate again (token_hash pin in WHERE).
    replay = client.post(
        "/api/v1/auth/refresh", headers={"Cookie": f"lexoria_refresh={old_cookie}"}
    )
    assert replay.status_code == 401

    # A second refresh with the CURRENT cookie still works (selector stable).
    assert client.post("/api/v1/auth/refresh").status_code == 200
    third_cookie = client.cookies.get("lexoria_refresh")
    assert third_cookie.split(".", 1)[0] == old_cookie.split(".", 1)[0]

    # Cookie is scoped to /api/v1/auth and cleared on logout.
    assert "/api/v1/auth" in resp.headers["set-cookie"]

    resp = client.post("/api/v1/auth/logout")
    assert resp.status_code == 204
    assert "lexoria_refresh=" in resp.headers["set-cookie"]  # cleared

    # logged-out session can no longer refresh
    assert client.post("/api/v1/auth/refresh").status_code == 401

    # access token still valid until expiry
    me = client.get("/api/v1/me", headers=auth_header(session))
    assert me.status_code == 200


def test_username_display_case_preserved(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "Alice", "email": "alice@example.com", "password": PASSWORD},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["username"] == "Alice"  # display keeps casing

    # Duplicate only on the normalized form.
    dup = client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "email": "other@example.com", "password": PASSWORD},
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "duplicate_username"

    # Login accepts any casing of the username.
    session = login(client, "ALICE")
    assert session["user"]["username"] == "Alice"

    # Only trim differences / illegal characters are rejected.
    bad = client.post(
        "/api/v1/auth/register",
        json={"username": "  bob", "email": "bob@example.com", "password": PASSWORD},
    )
    assert bad.status_code == 422


def test_settings_get_patch(client):
    register(client)
    session = login(client, "alice")
    headers = auth_header(session)

    resp = client.get("/api/v1/settings", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["daily_template"] == "compact"
    assert resp.json()["columns"] == 2
    assert resp.json()["review_count"] == 20
    assert resp.json()["new_count"] == 10

    resp = client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"timezone": "Asia/Shanghai", "daily_template": "test", "columns": 2},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["timezone"] == "Asia/Shanghai"
    assert body["daily_template"] == "test"
    assert body["columns"] == 2

    # invalid zoneinfo name -> 422
    resp = client.patch("/api/v1/settings", headers=headers, json={"timezone": "Mars/Olympus"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"

    # out-of-range daily totals -> 422
    resp = client.patch(
        "/api/v1/settings", headers=headers, json={"review_count": 0, "new_count": 0}
    )
    assert resp.status_code == 422

    # unauthenticated settings access
    assert client.get("/api/v1/settings").status_code == 401


def test_register_validation(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "bad user!", "email": "x@y.com", "password": PASSWORD},
    )
    assert resp.status_code == 422

    resp = client.post(
        "/api/v1/auth/register",
        json={"username": "bob", "email": "not-an-email", "password": PASSWORD},
    )
    assert resp.status_code == 422
