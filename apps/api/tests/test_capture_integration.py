"""Capture / inbox / words / senses / sources / encounters integration tests
against a real Postgres (TEST_DATABASE_URL required)."""
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("TEST_DATABASE_URL") is None,
    reason="TEST_DATABASE_URL is required for PG integration tests",
)

PASSWORD = "correct horse battery staple!"


def auth_pair(client):
    client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "email": "alice@example.com", "password": PASSWORD},
    )
    session = client.post(
        "/api/v1/auth/login", json={"identifier": "alice", "password": PASSWORD}
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def capture(client, headers, text, event=None, **extra):
    body = {
        "text": text,
        "encounter_type": "unclassified",
        "client_event_id": str(event or uuid.uuid4()),
        **extra,
    }
    resp = client.post("/api/v1/inbox", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_capture_idempotent_and_counts(client):
    headers = auth_pair(client)
    event = uuid.uuid4()

    first = capture(client, headers, "Hello", event=event)
    assert first["status"] == "inbox"
    assert first["lemma"] == "hello"
    assert first["encounter_count"] == 1
    assert first["user_word_created"] is True
    assert first["replayed"] is False

    # Same client event -> replay, no extra counting, identical encounter id.
    replay = capture(client, headers, "Hello", event=event)
    assert replay["id"] == first["id"]
    assert replay["client_event_id"] == first["client_event_id"]
    assert replay["encounter_count"] == 1
    assert replay["user_word_created"] is False
    assert replay["replayed"] is True

    # A new event bumps the counter and adds an encounter.
    again = capture(client, headers, "Hello", event=uuid.uuid4())
    assert again["id"] == first["id"]
    assert again["encounter_count"] == 2

    # Normalized case-insensitive lemma converges on the same word.
    upper = capture(client, headers, "  HELLO! ", event=uuid.uuid4())
    assert upper["id"] == first["id"]
    assert upper["encounter_count"] == 3

    # Encounters are unique per event.
    resp = client.get(
        f"/api/v1/user-words/{first['id']}/encounters", headers=headers
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 3


def test_inbox_list_and_transitions(client):
    headers = auth_pair(client)
    item = capture(client, headers, "Serendipity", event=uuid.uuid4())

    resp = client.get("/api/v1/inbox", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["id"] == item["id"]

    # Activation without a sense -> 409
    resp = client.patch(
        f"/api/v1/user-words/{item['id']}",
        headers=headers,
        json={"status": "active"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "requires_sense"

    # Add a sense, then activate -> ReviewCard is created exactly once.
    resp = client.post(
        f"/api/v1/user-words/{item['id']}/senses",
        headers=headers,
        json={"part_of_speech": "noun", "definition_zh": "机缘巧合"},
    )
    assert resp.status_code == 201, resp.text
    sense_id = resp.json()["id"]

    resp = client.patch(
        f"/api/v1/user-words/{item['id']}",
        headers=headers,
        json={"status": "active", "familiarity": 4},
    )
    assert resp.status_code == 200, resp.text
    active = resp.json()
    assert active["status"] == "active"
    assert active["familiarity"] == 4
    card_id = active["card"]["id"]

    again = client.patch(
        f"/api/v1/user-words/{item['id']}",
        headers=headers,
        json={"status": "active"},
    )
    assert again.json()["card"]["id"] == card_id  # no duplicate card

    # Deleting the only sense of an active word -> 409
    resp = client.delete(
        f"/api/v1/user-words/{item['id']}/senses/{sense_id}", headers=headers
    )
    assert resp.status_code == 409

    # Known -> suspends the card
    resp = client.patch(
        f"/api/v1/user-words/{item['id']}",
        headers=headers,
        json={"status": "known"},
    )
    assert resp.status_code == 200
    assert resp.json()["card"]["suspended_at"] is not None

    # Archived word re-captured -> revived to inbox, counter keeps counting.
    resp = client.patch(
        f"/api/v1/user-words/{item['id']}",
        headers=headers,
        json={"status": "archived"},
    )
    assert resp.json()["status"] == "archived"

    revived = capture(client, headers, "Serendipity", event=uuid.uuid4())
    assert revived["id"] == item["id"]
    assert revived["status"] == "inbox"
    assert revived["archived_at"] is None
    assert revived["encounter_count"] == 2


def test_sources_ownership_and_uniqueness(client):
    headers = auth_pair(client)
    resp = client.post(
        "/api/v1/sources", headers=headers, json={"name": "IELTS 词汇", "type": "ielts"}
    )
    assert resp.status_code == 201, resp.text
    source = resp.json()
    assert source["type"] == "ielts"

    # same (user, type, normalized name) -> 409
    dup = client.post(
        "/api/v1/sources", headers=headers, json={"name": "ielts 词汇", "type": "ielts"}
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "duplicate_source"

    # capture referencing a source that is not the user's -> 404
    resp = client.post(
        "/api/v1/inbox",
        headers=headers,
        json={"text": "word", "source_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404

    # capture with a real source resolves into the item
    item = capture(client, headers, "Word", source_id=source["id"], event=uuid.uuid4())
    assert item["source_id"] == source["id"]

    # archive hides it from the default list
    resp = client.patch(
        f"/api/v1/sources/{source['id']}", headers=headers, json={"archived": True}
    )
    assert resp.status_code == 200
    listed = client.get("/api/v1/sources", headers=headers).json()
    assert listed == []
    listed_all = client.get(
        "/api/v1/sources?include_archived=true", headers=headers
    ).json()
    assert len(listed_all) == 1


def test_encounter_append_and_pagination(client):
    headers = auth_pair(client)
    item = capture(client, headers, "Absorb", event=uuid.uuid4())

    resp = client.post(
        "/api/v1/encounters",
        headers=headers,
        json={
            "user_word_id": item["id"],
            "client_event_id": str(uuid.uuid4()),
            "type": "recognized",
            "context": "in a book",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["type"] == "recognized"

    # same client event replays idempotently
    event = uuid.uuid4()
    first = client.post(
        "/api/v1/encounters",
        headers=headers,
        json={"user_word_id": item["id"], "client_event_id": str(event)},
    )
    second = client.post(
        "/api/v1/encounters",
        headers=headers,
        json={"user_word_id": item["id"], "client_event_id": str(event)},
    )
    assert first.json()["id"] == second.json()["id"]

    detail = client.get(f"/api/v1/user-words/{item['id']}", headers=headers).json()
    assert detail["encounter_count"] == 2  # capture(1) + append(1); replay ignored

    page = client.get("/api/v1/encounters", headers=headers).json()
    assert page["total"] == 2

    # foreign word id -> 404
    resp = client.post(
        "/api/v1/encounters",
        headers=headers,
        json={"user_word_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


def test_capture_requires_client_event(client):
    headers = auth_pair(client)
    resp = client.post(
        "/api/v1/inbox", headers=headers, json={"text": "hello", "encounter_type": "new"}
    )
    assert resp.status_code == 422  # client_event_id is required

    resp = client.post(
        "/api/v1/inbox",
        headers=headers,
        json={"text": "hello", "client_event_id": str(uuid.uuid4()), "encounter_type": "nope"},
    )
    assert resp.status_code == 422


def test_capture_cleans_surface_and_lemma(client):
    headers = auth_pair(client)
    item = capture(client, headers, "\u201cCan\u2019t\u2003stop\u2019", event=uuid.uuid4())
    # NFKC + curly apostrophes -> straight + Unicode whitespace collapsed
    # (the leading left double quote is preserved verbatim).
    assert item["surface_text"] == "\u201cCan't stop'"
    assert item["lemma"] == "\u201ccan't stop'"

    # Control characters are rejected.
    resp = client.post(
        "/api/v1/inbox",
        headers=headers,
        json={"text": "bad\x00text", "client_event_id": str(uuid.uuid4())},
    )
    assert resp.status_code == 422


def test_encounter_requires_event_and_cleans_surface(client):
    headers = auth_pair(client)
    item = capture(client, headers, "Absorb", event=uuid.uuid4())

    resp = client.post(
        "/api/v1/encounters",
        headers=headers,
        json={"user_word_id": item["id"]},  # no client_event_id
    )
    assert resp.status_code == 422

    resp = client.post(
        "/api/v1/encounters",
        headers=headers,
        json={
            "user_word_id": item["id"],
            "client_event_id": str(uuid.uuid4()),
            "type": "recognized",
            "surface_text": "  Absorbing\u2019s  ",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["surface_text"] == "Absorbing's"


def test_words_source_filter_and_due_sort(client):
    headers = auth_pair(client)
    source = client.post(
        "/api/v1/sources", headers=headers, json={"name": "Reader", "type": "reading"}
    ).json()
    item = capture(
        client, headers, "Capture", event=uuid.uuid4(), source_id=source["id"]
    )

    resp = client.get(f"/api/v1/user-words?source_id={source['id']}", headers=headers)
    assert resp.status_code == 200
    assert [w["id"] for w in resp.json()["items"]] == [item["id"]]

    other = client.post(
        "/api/v1/sources", headers=headers, json={"name": "Other", "type": "manual"}
    ).json()
    assert (
        client.get(f"/api/v1/user-words?source_id={other['id']}", headers=headers)
        .json()["total"]
        == 0
    )

    # Sort key is `due:asc`; the freshly activated card has due_at == now.
    sense = client.post(
        f"/api/v1/user-words/{item['id']}/senses",
        headers=headers,
        json={"definition_zh": "捕获"},
    ).json()
    client.patch(
        f"/api/v1/user-words/{item['id']}", headers=headers, json={"status": "active"}
    )
    resp = client.get("/api/v1/user-words?sort=due:asc", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["items"][0]["id"] == item["id"]
    assert resp.json()["items"][0]["card"]["due_at"] is not None
    assert resp.json()["items"][0]["card"]["suspended_at"] is None


def test_status_suspension_rules(client):
    headers = auth_pair(client)
    item = capture(client, headers, "Suspendable", event=uuid.uuid4())
    client.post(
        f"/api/v1/user-words/{item['id']}/senses",
        headers=headers,
        json={"definition_zh": "可挂起的"},
    )

    resp = client.patch(
        f"/api/v1/user-words/{item['id']}", headers=headers, json={"status": "active"}
    )
    assert resp.json()["card"]["suspended_at"] is None
    assert resp.json()["card"]["due_at"] is not None

    # inbox / known / archived ALL suspend the card; only active is live.
    for target in ("inbox", "known", "archived"):
        resp = client.patch(
            f"/api/v1/user-words/{item['id']}", headers=headers, json={"status": target}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == target
        assert resp.json()["card"]["suspended_at"] is not None, target

    # Reactivating clears suspension and resets due_at.
    resp = client.patch(
        f"/api/v1/user-words/{item['id']}", headers=headers, json={"status": "active"}
    )
    assert resp.json()["card"]["suspended_at"] is None
    assert resp.json()["card"]["due_at"] is not None
