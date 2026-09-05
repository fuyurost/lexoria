"""Tests for the review transaction layer (``app.api.reviews``) and the
ReviewLog/ReviewCard model fixes.

The core ORM<->scheduler<->log wiring is unit-tested with plain fakes (no
database). Full-transaction tests run against Postgres only when
TEST_DATABASE_URL is set and are skipped otherwise.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import CheckConstraint, create_engine, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.base import Base
from app.models.review import ReviewCard, ReviewLog
from app.services.memory import SCHEDULER_VERSION, CardSnapshot

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
requires_pg = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="TEST_DATABASE_URL 未设置，跳过 PG 集成测试"
)

from app.api.reviews import (  # noqa: E402  (after env-aware imports above)
    ReviewSubmit,
    apply_schedule,
    list_due_reviews,
    plan_review,
    require_rating,
    review_log_values,
    submit_review,
)

UTC = timezone.utc
NOW = datetime(2026, 3, 1, 12, 0, 0, tzinfo=UTC)


def fake_card(version: int = 3, **over: object) -> SimpleNamespace:
    """ORM-shaped card row (plain attributes, no DB session required)."""
    values = {
        "id": uuid.uuid4(),
        "state": "review",
        "difficulty": Decimal("5.00"),
        "stability_days": Decimal("10.0000"),
        "due_at": NOW - timedelta(days=2),
        "last_review_at": NOW - timedelta(days=7),
        "lapse_count": 2,
        "review_count": 10,
        "version": version,
        "user_word_id": uuid.uuid4(),
    }
    values.update(over)
    return SimpleNamespace(**values)


# --- model fixes (schema introspection, no DB) --------------------------------


def _checks(table) -> dict[str, str]:
    return {
        ck.name: str(ck.sqltext)
        for ck in table.constraints
        if isinstance(ck, CheckConstraint)
    }


def test_review_log_replaces_difficulty_with_previous_and_new():
    cols = ReviewLog.__table__.columns
    assert "difficulty" not in cols
    assert "previous_difficulty" in cols
    assert "new_difficulty" in cols
    assert not cols["previous_difficulty"].nullable
    assert not cols["new_difficulty"].nullable


def test_review_log_required_columns_are_not_nullable():
    cols = ReviewLog.__table__.columns
    for name in (
        "rating",
        "state_before",
        "state_after",
        "previous_due_at",
        "next_due_at",
        "previous_stability_days",
        "new_stability_days",
    ):
        assert not cols[name].nullable, name


def test_review_log_checks():
    checks = _checks(ReviewLog.__table__)
    assert "again" in checks["ck_review_logs_rating_valid"]
    assert "easy" in checks["ck_review_logs_rating_valid"]
    for state in ("new", "learning", "review", "relearning"):
        assert state in checks["ck_review_logs_state_before_valid"]
        assert state in checks["ck_review_logs_state_after_valid"]
    assert "sequence_no >= 1" in checks["ck_review_logs_sequence_no_min"]


def test_review_card_counter_checks():
    checks = _checks(ReviewCard.__table__)
    assert "review_count >= 0" in checks["ck_review_cards_review_count_nonneg"]
    assert "lapse_count >= 0" in checks["ck_review_cards_lapse_count_nonneg"]
    assert "version >= 0" in checks["ck_review_cards_version_nonneg"]


# --- pure mapping: ORM values -> snapshot -> card -> log fields ---------------


def test_plan_review_maps_orm_values_into_snapshot_and_schedules():
    card = fake_card()
    result = plan_review(card, "hard", NOW)
    assert result.before == CardSnapshot(
        state="review",
        difficulty=Decimal("5.00"),
        stability_days=Decimal("10.0000"),
        due_at=NOW - timedelta(days=2),
        last_review_at=NOW - timedelta(days=7),
        lapse_count=2,
        review_count=10,
    )
    # lexiora-srs-v1 hard path: elapsed 7d -> r=.7 -> factor 1.2775
    assert result.after.state == "review"
    assert result.after.difficulty == Decimal("5.25")
    assert result.after.stability_days == Decimal("12.7750")
    assert result.after.lapse_count == 2
    assert result.after.review_count == 11
    assert result.after.last_review_at == NOW
    assert result.scheduler_version == SCHEDULER_VERSION
    assert result.elapsed_days == Decimal("7.0000")
    assert result.scheduled_days == Decimal("12.7750")


def test_apply_schedule_mutates_card_and_bumps_version():
    card = fake_card(version=3)
    result = plan_review(card, "hard", NOW)
    apply_schedule(card, result)
    assert card.state == "review"
    assert card.difficulty == Decimal("5.25")
    assert card.stability_days == Decimal("12.7750")
    assert card.due_at == result.after.due_at
    assert card.last_review_at == NOW
    assert card.review_count == 11
    assert card.lapse_count == 2
    assert card.version == 4


def test_review_log_values_carry_complete_before_after():
    card = fake_card()
    result = plan_review(card, "hard", NOW)
    user_id, card_id, event = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    log = review_log_values(user_id=user_id, card_id=card_id, client_event_id=event, result=result)
    assert log["user_id"] == user_id
    assert log["review_card_id"] == card_id
    assert log["client_event_id"] == event
    assert log["sequence_no"] == result.after.review_count == 11
    assert log["rating"] == "hard"
    assert log["state_before"] == "review"
    assert log["state_after"] == "review"
    assert log["previous_due_at"] == result.before.due_at
    assert log["next_due_at"] == result.after.due_at
    assert log["previous_stability_days"] == Decimal("10.0000")
    assert log["new_stability_days"] == Decimal("12.7750")
    assert log["previous_difficulty"] == Decimal("5.00")
    assert log["new_difficulty"] == Decimal("5.25")
    assert log["elapsed_days"] == Decimal("7.0000")
    assert log["scheduled_days"] == Decimal("12.7750")
    assert log["scheduler_version"] == SCHEDULER_VERSION
    assert log["reviewed_at"] == result.reviewed_at == NOW


def test_rating_validation():
    require_rating("good")  # no raise
    with pytest.raises(AppError) as exc:
        require_rating("medium")
    assert exc.value.status_code == 422
    assert exc.value.code == "validation_error"


def test_review_submit_requires_expected_card_version():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ReviewSubmit(rating="good", client_event_id=uuid.uuid4())  # missing
    with pytest.raises(ValidationError):
        ReviewSubmit(
            rating="good", client_event_id=uuid.uuid4(), expected_card_version=-1  # ge=0
        )
    assert (
        ReviewSubmit(
            rating="good", client_event_id=uuid.uuid4(), expected_card_version=0
        ).expected_card_version
        == 0
    )


def test_plan_review_reviewed_at_is_typed_datetime():
    import inspect

    annotation = inspect.signature(plan_review).parameters["reviewed_at"].annotation
    assert annotation == "datetime"  # string under `from __future__ import annotations`
    assert not str(annotation).startswith("object")


# --- PG-backed transaction tests (skipped without TEST_DATABASE_URL) -----------


@requires_pg
class TestReviewTransaction:
    @pytest.fixture()
    def db(self):
        engine = create_engine(TEST_DATABASE_URL)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        session = Session(engine, expire_on_commit=False)
        try:
            yield session
        finally:
            session.close()
            Base.metadata.drop_all(engine)
            engine.dispose()

    def _seed_active_card(self, db: Session, *, due_delta: timedelta) -> tuple:
        from app.models.user import User
        from app.models.word import UserWord, UserWordSense, Word

        now = datetime.now(timezone.utc)
        user = User(
            id=uuid.uuid4(), username="u1", username_normalized="u1",
            email="u1@x.com", email_normalized="u1@x.com", password_hash="h",
        )
        word = Word(lemma="apple", normalized_lemma="apple")
        db.add_all([user, word])
        db.flush()
        uw = UserWord(user_id=user.id, word_id=word.id, status="active")
        card = ReviewCard(
            user_id=user.id,
            user_word_id=uw.id,
            state="review",
            difficulty=Decimal("5.00"),
            stability_days=Decimal("10.0000"),
            due_at=now - due_delta,
            last_review_at=now - timedelta(days=7),
            review_count=10,
            lapse_count=2,
            version=3,
        )
        sense = UserWordSense(
            user_id=user.id, user_word_id=uw.id,
            part_of_speech="n", definition_zh="苹果", sort_order=0,
        )
        db.add_all([card, sense])
        db.commit()
        return user, word, uw, card, now

    def test_submit_review_applies_schedule_and_appends_log(self, db):
        user, _word, _uw, card, now = self._seed_active_card(db, due_delta=timedelta(days=1))
        event = uuid.uuid4()

        resp = submit_review(
            card_id=card.id, body=ReviewSubmit(rating="hard", client_event_id=event,
                                               expected_card_version=3),
            user=user, db=db,
        )
        assert resp["replayed"] is False
        body = resp["card"]
        assert body["state"] == "review"
        assert body["difficulty"] == 5.25
        assert body["stability_days"] == 12.7750
        assert body["review_count"] == 11
        assert body["lapse_count"] == 2
        assert body["version"] == 4
        assert body["id"] == str(card.id)

        log = db.execute(
            select(ReviewLog).where(ReviewLog.client_event_id == event)
        ).scalar_one()
        assert log.sequence_no == 11
        assert log.rating == "hard"
        assert log.state_before == "review"
        assert log.state_after == "review"
        assert log.previous_difficulty == Decimal("5.00")
        assert log.new_difficulty == Decimal("5.25")
        assert log.previous_stability_days == Decimal("10.0000")
        assert log.new_stability_days == Decimal("12.7750")
        assert log.scheduler_version == SCHEDULER_VERSION
        assert log.elapsed_days == Decimal("7.0000")
        assert log.previous_due_at < log.next_due_at
        assert log.review_card_id == card.id

    def test_replay_same_event_is_idempotent(self, db):
        user, _word, _uw, card, _now = self._seed_active_card(db, due_delta=timedelta(days=1))
        event = uuid.uuid4()
        body = ReviewSubmit(rating="good", client_event_id=event, expected_card_version=3)
        first = submit_review(card_id=card.id, body=body, user=user, db=db)
        assert first["replayed"] is False
        second = submit_review(card_id=card.id, body=body, user=user, db=db)
        assert second["replayed"] is True
        assert second["card"]["version"] == 4  # unchanged by the replay
        assert len(db.execute(select(ReviewLog)).scalars().all()) == 1

    def test_replay_wins_even_with_stale_expected_version(self, db):
        user, _word, _uw, card, _now = self._seed_active_card(db, due_delta=timedelta(days=1))
        event = uuid.uuid4()
        first = submit_review(
            card_id=card.id,
            body=ReviewSubmit(rating="good", client_event_id=event, expected_card_version=3),
            user=user, db=db,
        )
        assert first["replayed"] is False
        stale = submit_review(
            card_id=card.id,
            body=ReviewSubmit(rating="good", client_event_id=event, expected_card_version=1),
            user=user, db=db,
        )
        assert stale["replayed"] is True  # idempotency probe runs before version check

    def test_version_conflict(self, db):
        user, _word, _uw, card, _now = self._seed_active_card(db, due_delta=timedelta(days=1))
        with pytest.raises(AppError) as exc:
            submit_review(
                card_id=card.id,
                body=ReviewSubmit(rating="good", client_event_id=uuid.uuid4(),
                                  expected_card_version=9),
                user=user, db=db,
            )
        assert exc.value.status_code == 409
        assert exc.value.code == "version_conflict"
        assert exc.value.details == {"expected": 9, "actual": card.version}

    def test_word_not_active_or_suspended_conflicts(self, db):
        from app.models.word import UserWord
        user, _word, uw, card, now = self._seed_active_card(db, due_delta=timedelta(days=1))
        uw.status = "known"
        card.suspended_at = now
        db.commit()
        with pytest.raises(AppError) as exc:
            submit_review(
                card_id=card.id,
                body=ReviewSubmit(rating="good", client_event_id=uuid.uuid4(),
                                  expected_card_version=3),
                user=user, db=db,
            )
        assert exc.value.status_code == 409
        assert exc.value.code == "word_not_active"

        uw.status = "active"
        card.suspended_at = now
        db.commit()
        with pytest.raises(AppError) as exc:
            submit_review(
                card_id=card.id,
                body=ReviewSubmit(rating="good", client_event_id=uuid.uuid4(),
                                  expected_card_version=3),
                user=user, db=db,
            )
        assert exc.value.code == "card_suspended"

    def test_foreign_card_is_404(self, db):
        from app.models.user import User
        from app.models.word import UserWord, Word
        now = datetime.now(timezone.utc)
        user = User(id=uuid.uuid4(), username="u1", username_normalized="u1",
                    email="u1@x.com", email_normalized="u1@x.com", password_hash="h")
        other = User(id=uuid.uuid4(), username="u2", username_normalized="u2",
                     email="u2@x.com", email_normalized="u2@x.com", password_hash="h")
        word = Word(lemma="banana", normalized_lemma="banana")
        db.add_all([user, other, word])
        db.flush()
        other_uw = UserWord(user_id=other.id, word_id=word.id, status="active")
        db.add(other_uw)
        db.flush()
        other_card = ReviewCard(
            user_id=other.id, user_word_id=other_uw.id, state="new",
            difficulty=Decimal("5.00"), stability_days=Decimal("0"),
            due_at=now, review_count=0, lapse_count=0, version=1,
        )
        db.add(other_card)
        db.commit()
        with pytest.raises(AppError) as exc:
            submit_review(
                card_id=other_card.id,
                body=ReviewSubmit(rating="again", client_event_id=uuid.uuid4(),
                                  expected_card_version=1),
                user=user, db=db,
            )
        assert exc.value.status_code == 404
        assert exc.value.code == "review_card_not_found"

    def test_existing_event_replays_its_own_card(self, db):
        user, _word, _uw, card, now = self._seed_active_card(db, due_delta=timedelta(days=1))
        # second card owned by the same user
        from app.models.user import User
        from app.models.word import UserWord, Word
        word2 = Word(lemma="pear", normalized_lemma="pear")
        db.add(word2)
        db.flush()
        uw2 = UserWord(user_id=user.id, word_id=word2.id, status="active")
        db.add(uw2)
        db.flush()
        card2 = ReviewCard(
            user_id=user.id, user_word_id=uw2.id, state="review",
            difficulty=Decimal("5.00"), stability_days=Decimal("10.0000"),
            due_at=now - timedelta(days=1), last_review_at=now - timedelta(days=7),
            review_count=10, lapse_count=2, version=3,
        )
        db.add(card2)
        db.flush()
        event = uuid.uuid4()
        db.add(ReviewLog(
            user_id=user.id, review_card_id=card2.id, client_event_id=event,
            sequence_no=11, rating="good", state_before="review", state_after="review",
            previous_due_at=now - timedelta(days=1), next_due_at=now + timedelta(days=3),
            previous_stability_days=Decimal("10.0000"), new_stability_days=Decimal("20.3700"),
            previous_difficulty=Decimal("5.00"), new_difficulty=Decimal("4.85"),
            elapsed_days=Decimal("7.0000"), scheduled_days=Decimal("20.3700"),
        ))
        db.commit()

        resp = submit_review(
            card_id=card.id,
            body=ReviewSubmit(rating="good", client_event_id=event, expected_card_version=3),
            user=user, db=db,
        )
        assert resp["replayed"] is True
        assert resp["card"]["id"] == str(card2.id)  # outcome belongs to the winner card
        assert len(db.execute(select(ReviewLog)).scalars().all()) == 1

    def test_today_queue_filters_orders_and_aggregates(self, db):
        from app.models.user import User
        from app.models.word import UserWord, Word

        now = datetime.now(timezone.utc)
        user = User(id=uuid.uuid4(), username="u1", username_normalized="u1",
                    email="u1@x.com", email_normalized="u1@x.com", password_hash="h")
        db.add(user)

        def make_word_uw(word_lemma: str, status: str, due: datetime, suspended: bool):
            word = Word(lemma=word_lemma, normalized_lemma=word_lemma)
            db.add(word)
            db.flush()
            uw = UserWord(user_id=user.id, word_id=word.id, status=status)
            db.add(uw)
            db.flush()
            card = ReviewCard(
                user_id=user.id, user_word_id=uw.id, state="review",
                difficulty=Decimal("5.00"), stability_days=Decimal("10.0000"),
                due_at=due, last_review_at=now - timedelta(days=7),
                review_count=5, lapse_count=1, version=2,
                suspended_at=now if suspended else None,
            )
            db.add(card)
            db.flush()
            return word, uw, card

        (_w, _uw, c1) = make_word_uw("alpha", "active", now - timedelta(days=2), False)
        (_w, _uw, c2) = make_word_uw("beta", "active", now - timedelta(hours=1), False)
        (_w, _uw, _cf) = make_word_uw("future", "active", now + timedelta(hours=1), False)
        (_w, _uw, _cs) = make_word_uw("susp", "active", now - timedelta(days=3), True)
        (_w, _uw, _ci) = make_word_uw("inbox", "inbox", now - timedelta(days=4), False)
        db.commit()

        resp = list_due_reviews(user=user, db=db)
        assert resp["total"] == 2
        items = resp["items"]
        assert [it["id"] for it in items] == [str(c1.user_word_id), str(c2.user_word_id)]
        assert [it["card"]["id"] for it in items] == [str(c1.id), str(c2.id)]
        assert [it["card"]["due_at"] for it in items] == sorted(it["card"]["due_at"] for it in items)
        for it in items:
            assert it["lemma"] in ("alpha", "beta")
            assert it["status"] == "active"
            assert it["card"]["suspended_at"] is None
            assert set(it["card"]) >= {
                "id", "state", "difficulty", "stability_days", "due_at",
                "last_review_at", "review_count", "lapse_count", "version",
            }
