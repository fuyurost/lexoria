"""GET /stats integration test (TEST_DATABASE_URL required)."""
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("TEST_DATABASE_URL") is None,
    reason="TEST_DATABASE_URL is required for PG integration tests",
)

PASSWORD = "correct horse battery staple!"


def _headers(client):
    client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": PASSWORD},
    )
    session = client.post(
        "/api/v1/auth/login", json={"identifier": "alice", "password": PASSWORD}
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def _capture(client, headers, text):
    resp = client.post(
        "/api/v1/inbox",
        headers=headers,
        json={"text": text, "client_event_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_stats_zero_state(client):
    headers = _headers(client)
    body = client.get("/api/v1/stats", headers=headers).json()
    assert body == {
        "words_total": 0,
        "words_by_status": {"inbox": 0, "active": 0, "known": 0, "archived": 0},
        "due_today": 0,
        "reviewed_today": 0,
        "captured_today": 0,
        "inbox_open": 0,
        "sources_total": 0,
        "streak_days": 0,
    }
    assert client.get("/api/v1/stats").status_code == 401


def test_stats_reflects_activity(client):
    headers = _headers(client)
    first = _capture(client, headers, "Alpha")
    _capture(client, headers, "Beta")

    source = client.post(
        "/api/v1/sources", headers=headers, json={"name": "Reader", "type": "reading"}
    ).json()

    # Activate "Alpha" (sense + card, due immediately).
    client.post(
        f"/api/v1/user-words/{first['id']}/senses",
        headers=headers,
        json={"definition_zh": "第一个"},
    )
    client.patch(
        f"/api/v1/user-words/{first['id']}", headers=headers, json={"status": "active"}
    )

    body = client.get("/api/v1/stats", headers=headers).json()
    assert body["words_total"] == 2
    assert body["words_by_status"] == {"inbox": 1, "active": 1, "known": 0, "archived": 0}
    assert body["inbox_open"] == 1
    assert body["captured_today"] == 2
    assert body["sources_total"] == 1
    assert body["due_today"] == 1  # active, not suspended, due <= now
    assert body["reviewed_today"] == 0
    assert body["streak_days"] == 0

    # Archiving removes it from the current-vocabulary total and due_today.
    client.patch(
        f"/api/v1/user-words/{first['id']}", headers=headers, json={"status": "archived"}
    )
    after = client.get("/api/v1/stats", headers=headers).json()
    assert after["words_by_status"]["archived"] == 1
    assert after["words_total"] == 1  # archived excluded
    assert after["due_today"] == 0
