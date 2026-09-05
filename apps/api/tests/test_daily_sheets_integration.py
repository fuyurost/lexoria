"""Daily-sheet endpoints against a real Postgres (TEST_DATABASE_URL required).

The router is mounted on a TEMPORARY FastAPI app here (same error envelope
handlers as app.main) because app.main's router list is owned centrally —
daily_sheets is registered there by the main wiring change, not by this
module. Reuses the auth router so tests authenticate exactly like the other
integration suites.
"""
from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy import create_engine, update
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.review import ReviewCard

pytestmark = pytest.mark.skipif(
    os.getenv("TEST_DATABASE_URL") is None,
    reason="TEST_DATABASE_URL is required for PG integration tests",
)

PASSWORD = "correct horse battery staple!"
WEASYPRINT_READY = False


def _build_app() -> FastAPI:
    from app.api import auth, daily_sheets
    from app.core.errors import AppError
    from app.main import (
        app_error_handler,
        http_error_handler,
        unhandled_handler,
        validation_handler,
    )

    app = FastAPI(title="daily-sheets-test")
    api = APIRouter(prefix="/api/v1")
    api.include_router(auth.router)
    api.include_router(daily_sheets.router)
    app.include_router(api)
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_handler)
    return app


@pytest.fixture()
def client(tmp_path):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.db.base import Base
    from app.services import pdf as pdf_service

    global WEASYPRINT_READY
    WEASYPRINT_READY = pdf_service.weasyprint_available()

    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    original_pdf_dir = settings.pdf_storage_dir
    settings.pdf_storage_dir = str(tmp_path / "pdfs")

    app = _build_app()
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        settings.pdf_storage_dir = original_pdf_dir
        Base.metadata.drop_all(engine)
        engine.dispose()


def _auth(client, username: str = "alice") -> dict:
    client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": f"{username}@example.com", "password": PASSWORD},
    )
    session = client.post(
        "/api/v1/auth/login", json={"identifier": username, "password": PASSWORD}
    ).json()
    return {"Authorization": f"Bearer {session['access_token']}"}


def _capture(client, headers, text, source_id=None, event=None) -> dict:
    body = {
        "text": text,
        "encounter_type": "unclassified",
        "client_event_id": str(event or uuid.uuid4()),
    }
    if source_id is not None:
        body["source_id"] = source_id
    resp = client.post("/api/v1/inbox", headers=headers, json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _activate(client, headers, item_id: str, sense_zh: str = "定义") -> dict:
    resp = client.post(
        f"/api/v1/user-words/{item_id}/senses",
        headers=headers,
        json={"part_of_speech": "n.", "definition_zh": sense_zh},
    )
    assert resp.status_code == 201, resp.text
    resp = client.patch(
        f"/api/v1/user-words/{item_id}",
        headers=headers,
        json={"status": "active", "familiarity": 3},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _seed_words(client, headers, count: int, source_id=None, prefix="w") -> list[dict]:
    """Capture + sense + activate `count` words; returns the activated items."""
    out = []
    for i in range(count):
        item = _capture(client, headers, f"{prefix}{i}", source_id=source_id)
        activated = _activate(client, headers, item["id"], sense_zh=f"{prefix}{i}释义")
        out.append(activated)
    return out


def _force_review(client, user_word_id: str, due_days_ago: int = 1) -> None:
    """Flip an activated card to a due 'review' state (no grading API yet)."""
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    try:
        with engine.begin() as conn:
            conn.execute(
                update(ReviewCard)
                .where(ReviewCard.user_word_id == uuid.UUID(user_word_id))
                .values(
                    state="review",
                    due_at=datetime.now(UTC).replace(microsecond=0)
                    - timedelta(days=due_days_ago),
                )
            )
    finally:
        engine.dispose()


# --- preview ---------------------------------------------------------------


def test_preview_empty_pool_returns_empty_sections_and_warnings(client):
    headers = _auth(client)
    resp = client.post(
        "/api/v1/daily-sheets/preview",
        headers=headers,
        json={
            "template": "test",
            "paper_size": "a5",
            "columns": 2,
            "review_count": 5,
            "new_count": 5,
            "source_ids": [],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["word_total"] == 0
    assert body["sections"] == []
    assert body["warnings"] == ["no_candidates"]
    assert body["config"]["template"] == "test"
    assert "Daily Sheet" in body["html"]
    assert "复习 <b>0</b>" in body["html"]


def test_preview_groups_review_and_new_with_escape_safe_html(client):
    headers = _auth(client)
    _seed_words(client, headers, 3, prefix="new")  # all state=new -> new pool
    # One review candidate: state review + overdue.
    overdue = _seed_words(client, headers, 1, prefix="over")[0]
    _force_review(client, overdue["id"], due_days_ago=1)
    # Sense text with markup must be escaped in the returned html.
    resp = client.post(
        "/api/v1/user-words/{id}/senses".format(id=overdue["id"]),
        headers=headers,
        json={"part_of_speech": "v.", "definition_zh": "过期<b>旧词</b>"},
    )
    assert resp.status_code == 201, resp.text

    resp = client.post(
        "/api/v1/daily-sheets/preview",
        headers=headers,
        json={
            "template": "compact",
            "paper_size": "a4",
            "columns": 1,
            "review_count": 1,
            "new_count": 2,
            "source_ids": [],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    kinds = [s["kind"] for s in body["sections"]]
    assert kinds == ["review", "new"]
    assert body["sections"][0]["words"][0]["lemma"] == "over0"
    assert len(body["sections"][1]["words"]) == 2
    assert body["word_total"] == 3
    assert body["warnings"] == []  # full quota met
    # The preview html escapes the user-authored sense definition.
    assert "<b>旧词</b>" not in body["html"]
    assert "&lt;b&gt;旧词&lt;/b&gt;" in body["html"]


def test_preview_source_filter_and_foreign_source_rejected(client):
    headers = _auth(client)
    source = client.post(
        "/api/v1/sources", headers=headers, json={"name": "Reader", "type": "reading"}
    ).json()
    _seed_words(client, headers, 1, prefix="sourced", source_id=source["id"])
    _seed_words(client, headers, 1, prefix="plain")

    resp = client.post(
        "/api/v1/daily-sheets/preview",
        headers=headers,
        json={
            "template": "compact",
            "paper_size": "a4",
            "columns": 1,
            "review_count": 0,
            "new_count": 1,
            "source_ids": [source["id"]],
        },
    )
    assert resp.status_code == 200, resp.text
    words = [s["words"][0]["lemma"] for s in resp.json()["sections"]]
    assert words == ["sourced0"]

    # A source the user does not own -> 404 (mirrors other source endpoints).
    resp = client.post(
        "/api/v1/daily-sheets/preview",
        headers=headers,
        json={
            "template": "compact",
            "paper_size": "a4",
            "columns": 1,
            "review_count": 1,
            "new_count": 1,
            "source_ids": [str(uuid.uuid4())],
        },
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "source_not_found"


def test_preview_validation_rules(client):
    headers = _auth(client)
    bad_bodies = [
        {"template": "fancy"},  # enum
        {"paper_size": "a3"},
        {"columns": 3},
        {"review_count": -1},
        {"review_count": 60, "new_count": 60},  # total > 100
        {"review_count": 0, "new_count": 0},  # total < 1
        {"unknown": 1},  # extra="forbid"
    ]
    for body in bad_bodies:
        resp = client.post(
            "/api/v1/daily-sheets/preview", headers=headers, json=body
        )
        assert resp.status_code == 422, (body, resp.text)
        assert resp.json()["error"]["code"] == "validation_error", body


# --- generate / detail / pdf ------------------------------------------------


def test_generate_empty_pool_is_422_no_candidates(client):
    headers = _auth(client)
    resp = client.post(
        "/api/v1/daily-sheets",
        headers=headers,
        json={"template": "compact", "paper_size": "a4", "columns": 1,
              "review_count": 5, "new_count": 5, "source_ids": []},
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "no_candidates"


def test_generate_persists_summary_items_and_pdf(client):
    headers = _auth(client)
    words = _seed_words(client, headers, 4, prefix="gen")
    overdue = words[0]
    _force_review(client, overdue["id"], due_days_ago=1)

    if not WEASYPRINT_READY:
        pytest.skip("WeasyPrint not importable; PDF generation untestable here")

    resp = client.post(
        "/api/v1/daily-sheets",
        headers=headers,
        json={"template": "compact", "paper_size": "a5", "columns": 2,
              "review_count": 2, "new_count": 2, "source_ids": []},
    )
    assert resp.status_code == 201, resp.text
    summary = resp.json()
    sheet_id = summary["id"]
    assert summary["template"] == "compact"
    assert summary["paper_size"] == "a5"
    assert summary["columns"] == 2
    assert summary["actual_review_count"] == 1
    assert summary["actual_new_count"] == 2
    assert summary["timezone_snapshot"] == "UTC"
    assert summary["created_at"].endswith("Z")

    detail = client.get(f"/api/v1/daily-sheets/{sheet_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["actual_review_count"] == 1
    assert len(body["items"]) == 3
    first, *rest = body["items"]
    assert first["kind"] == "review"
    assert first["item_type"] == "review"
    assert first["selection_reason"] == "overdue"
    assert first["lemma"] == "gen0"
    assert first["normalized_lemma"] == "gen0"
    assert len(first["senses"]) <= 2
    assert set(first["senses"][0]) == {"part_of_speech", "definition_zh", "definition_en"}
    # Snapshots never carry a rendering fingerprint.
    for item in body["items"]:
        assert "html" not in item
    assert {i["kind"] for i in rest} == {"new"}

    pdf = client.get(f"/api/v1/daily-sheets/{sheet_id}/pdf", headers=headers)
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"
    assert len(pdf.content) > 1000


def test_generate_respects_user_timezone_for_sheet_date(client):
    headers = _auth(client)
    resp = client.patch(
        "/api/v1/settings",
        headers=headers,
        json={"timezone": "Asia/Shanghai", "daily_template": "test"},
    )
    assert resp.status_code == 200, resp.text
    _seed_words(client, headers, 1, prefix="tz")

    if not WEASYPRINT_READY:
        pytest.skip("WeasyPrint not importable; PDF generation untestable here")

    tz = ZoneInfo("Asia/Shanghai")
    before = datetime.now(tz).date()
    resp = client.post(
        "/api/v1/daily-sheets",
        headers=headers,
        json={"template": "test", "paper_size": "a5", "columns": 1,
              "review_count": 0, "new_count": 1, "source_ids": []},
    )
    after = datetime.now(tz).date()
    assert resp.status_code == 201, resp.text
    summary = resp.json()
    assert summary["timezone_snapshot"] == "Asia/Shanghai"
    # A wall-clock day rollover between the two `now` calls can shift the
    # expected date by one — both values are acceptable.
    assert summary["sheet_date"] in {before.isoformat(), after.isoformat()}


def test_list_paginates_summaries_and_ownership_is_enforced(client):
    alice = _auth(client, "alice")
    bob = _auth(client, "bob")

    if not WEASYPRINT_READY:
        pytest.skip("WeasyPrint not importable; PDF generation untestable here")

    _seed_words(client, alice, 1, prefix="own")
    resp = client.post(
        "/api/v1/daily-sheets",
        headers=alice,
        json={"template": "compact", "paper_size": "a4", "columns": 1,
              "review_count": 0, "new_count": 1, "source_ids": []},
    )
    assert resp.status_code == 201, resp.text
    sheet_id = resp.json()["id"]

    listing = client.get("/api/v1/daily-sheets", headers=alice).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == sheet_id
    assert listing["items"][0]["actual_new_count"] == 1
    assert "created_at" in listing["items"][0]

    # Cross-user reads never leak: identical 404 for detail and pdf.
    for path in (f"/api/v1/daily-sheets/{sheet_id}",
                 f"/api/v1/daily-sheets/{sheet_id}/pdf"):
        resp = client.get(path, headers=bob)
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "daily_sheet_not_found"

    # bob's list is empty.
    assert client.get("/api/v1/daily-sheets", headers=bob).json()["total"] == 0
