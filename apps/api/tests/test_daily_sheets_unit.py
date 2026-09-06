"""Unit tests for the daily-sheet selection glue (``app.api.daily_sheets``).

These never need Postgres: ``_load_candidates`` is monkeypatched with a
fake ``UserWord`` map while the real ``select_daily`` + ``_make_rows`` run,
so the contract exercised is "``_run_selection`` hands the full
``SelectionResult`` to the row builder and gets back rows".

Regression: production 500 at ``_run_selection`` — the row builder was
called with ``result.items`` (a plain tuple), which has no ``.items``.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from app.api import daily_sheets
from app.api.daily_sheets import DailySheetRequest, _run_selection
from app.services.daily_selector import Candidate

NOW = datetime(2026, 9, 6, 12, 0, 0, tzinfo=UTC)


def _fake_user_word(uid: uuid.UUID) -> SimpleNamespace:
    """ORM-shaped UserWord row (plain attributes, no DB session required)."""
    return SimpleNamespace(
        id=uid,
        personal_phonetic="ˈæp.əl",
        word=SimpleNamespace(lemma="apple", normalized_lemma="apple"),
        senses=[],
        card=None,
    )


def test_run_selection_passes_full_selection_result_to_row_builder(monkeypatch):
    """_make_rows receives the SelectionResult object, not its bare .items
    tuple, and builds one full row per selected item."""
    uid = uuid.uuid4()
    overdue = Candidate(
        user_word_id=uid,
        normalized_lemma="apple",
        state="review",
        due_at=NOW - timedelta(days=2),  # overdue -> top review bucket
    )
    by_id = {uid: _fake_user_word(uid)}

    class _FakeDb:
        """Session stand-in: no UserSetting row exists (config comes from the
        request body)."""

        def get(self, model, key):
            return None

    monkeypatch.setattr(daily_sheets, "utcnow", lambda: NOW)
    monkeypatch.setattr(
        daily_sheets, "_load_candidates", lambda db, user, now_utc: ([], [overdue], by_id)
    )

    body = DailySheetRequest(
        template="compact",
        paper_size="a4",
        columns=1,
        review_count=1,
        new_count=0,
    )
    user = SimpleNamespace(id=uid)

    config, rows, warnings, sheet_date = _run_selection(_FakeDb(), user, body)

    assert warnings == ()
    assert sheet_date == date(2026, 9, 6)
    assert config["review_count"] == 1
    assert len(rows) == 1
    row = rows[0]
    assert row["user_word_id"] == uid
    assert row["lemma"] == "apple"
    assert row["normalized_lemma"] == "apple"
    assert row["personal_phonetic"] == "ˈæp.əl"
    assert row["senses"] == []
    assert row["item_type"] == "review"
    assert row["selection_reason"] == "overdue"
    assert row["sort_order"] == 1
    assert row["review_card_id"] is None
