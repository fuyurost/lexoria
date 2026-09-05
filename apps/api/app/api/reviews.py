"""Reviews: today's due queue + the single review transaction endpoint.

POST /review-cards/{card_id}/reviews is the only writer of ReviewLog rows;
logs are immutable — no update/delete endpoints exist.

Transaction order (all in one request-scoped session/commit):
1. Cheap idempotency probe on (user_id, client_event_id); a hit returns the
   recorded outcome unchanged (``replayed: true``).
2. SELECT the card joined with its UserWord FOR UPDATE, scoped to the user.
3. Re-probe the event now that the row lock is held (a concurrent duplicate
   may have committed between steps 1 and 2).
4. Guard checks: ownership/404, word status active + card not suspended
   (409), expected_card_version (409 version_conflict).
5. Build a CardSnapshot from ORM values and schedule with the pure
   ``app.services.memory`` engine at the server UTC instant.
6. Mutate the card, append the full-before/after ReviewLog
   (``sequence_no = after.review_count``), single commit.
7. An IntegrityError on the (user, client_event_id) unique key rolls back and
   answers idempotently with the winner's outcome.

Every ORM<->schedule<->log mapping lives in module-level helpers
(``plan_review`` / ``apply_schedule`` / ``review_log_values``) so the wiring
is unit-testable without a database.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, contains_eager, selectinload

from app.api.serializers import card_dict, page_response, user_word_dict
from app.core.deps import CurrentUser, DbDep
from app.core.errors import conflict, not_found, validation_error
from app.core.normalization import utcnow
from app.models.review import ReviewCard, ReviewLog
from app.models.user import User
from app.models.word import UserWord
from app.services.memory import RATINGS, SCHEDULER_VERSION, CardSnapshot, ScheduleResult, schedule

router = APIRouter(tags=["reviews"])

_TODAY_LOADS = (
    contains_eager(UserWord.card),
    selectinload(UserWord.word),
    selectinload(UserWord.senses),
)


class ReviewSubmit(BaseModel):
    """One review event. ``rating``, ``client_event_id`` and
    ``expected_card_version`` (>= 0, optimistic-lock check) are required."""

    model_config = ConfigDict(extra="forbid")

    rating: str = Field(min_length=1, max_length=16)
    client_event_id: uuid.UUID
    expected_card_version: int = Field(ge=0)


# --- pure ORM <-> scheduler <-> log mapping (DB-free) -------------------------


def require_rating(rating: str) -> None:
    """422 unless ``rating`` is one of the scheduler ratings."""
    if rating not in RATINGS:
        raise validation_error(
            f"rating 无效，允许值: {', '.join(RATINGS)}",
            {"field": "rating", "value": rating},
        )


def plan_review(card: ReviewCard, rating: str, reviewed_at: datetime) -> ScheduleResult:
    """Snapshot the card row into a CardSnapshot and run lexiora-srs-v1."""
    snapshot = CardSnapshot(
        state=card.state,
        difficulty=card.difficulty,
        stability_days=card.stability_days,
        due_at=card.due_at,
        last_review_at=card.last_review_at,
        lapse_count=card.lapse_count,
        review_count=card.review_count,
    )
    return schedule(snapshot, rating, reviewed_at)


def apply_schedule(card: ReviewCard, result: ScheduleResult) -> None:
    """Write the scheduled ``after`` state onto the card row; version + 1."""
    after = result.after
    card.state = after.state
    card.difficulty = after.difficulty
    card.stability_days = after.stability_days
    card.due_at = after.due_at
    card.last_review_at = after.last_review_at
    card.review_count = after.review_count
    card.lapse_count = after.lapse_count
    card.version = card.version + 1


def review_log_values(
    *,
    user_id: uuid.UUID,
    card_id: uuid.UUID,
    client_event_id: uuid.UUID,
    result: ScheduleResult,
) -> dict:
    """Column values for the immutable ReviewLog row (full before/after)."""
    before, after = result.before, result.after
    return {
        "user_id": user_id,
        "review_card_id": card_id,
        "client_event_id": client_event_id,
        "sequence_no": after.review_count,
        "rating": result.rating,
        "state_before": before.state,
        "state_after": after.state,
        "previous_due_at": before.due_at,
        "next_due_at": after.due_at,
        "previous_stability_days": before.stability_days,
        "new_stability_days": after.stability_days,
        "previous_difficulty": before.difficulty,
        "new_difficulty": after.difficulty,
        "elapsed_days": result.elapsed_days,
        "scheduled_days": result.scheduled_days,
        "scheduler_version": result.scheduler_version,
        "reviewed_at": result.reviewed_at,
    }


# --- queries ------------------------------------------------------------------


def find_review_log(db: Session, user_id: uuid.UUID, client_event_id: uuid.UUID) -> ReviewLog | None:
    return db.execute(
        select(ReviewLog).where(
            ReviewLog.user_id == user_id,
            ReviewLog.client_event_id == client_event_id,
        )
    ).scalar_one_or_none()


def _owned_card_for_update(db: Session, user_id: uuid.UUID, card_id: uuid.UUID) -> ReviewCard | None:
    """Card + its UserWord row, locked FOR UPDATE, scoped to the user."""
    return db.execute(
        select(ReviewCard)
        .join(UserWord, UserWord.id == ReviewCard.user_word_id)
        .where(ReviewCard.id == card_id, ReviewCard.user_id == user_id)
        .with_for_update()
    ).scalar_one_or_none()


def _replay_response(db: Session, user_id: uuid.UUID, card_id: uuid.UUID) -> dict:
    card = db.get(ReviewCard, card_id)
    if card is None or card.user_id != user_id:
        card = None  # defensive: the log's FK keeps the card alive
    return {"card": card_dict(card), "replayed": True}


# --- endpoints ----------------------------------------------------------------


@router.get("/reviews/today", summary="Due review queue")
def list_due_reviews(
    user: CurrentUser,
    db: DbDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Active, unsuspended cards due at or before the server instant, ordered
    by due_at then card id; items aggregate the word + senses + card state."""
    now = utcnow()
    stmt = (
        select(UserWord)
        .join(UserWord.card)
        .where(
            UserWord.user_id == user.id,
            UserWord.status == "active",
            ReviewCard.suspended_at.is_(None),
            ReviewCard.due_at <= now,
        )
    )
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(ReviewCard.due_at.asc(), ReviewCard.id.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(*_TODAY_LOADS)
        )
        .scalars()
        .all()
    )
    return page_response([user_word_dict(uw) for uw in rows], total, page, page_size)


@router.post("/review-cards/{card_id}/reviews", summary="Submit one review")
def submit_review(
    card_id: uuid.UUID, body: ReviewSubmit, user: CurrentUser, db: DbDep
) -> dict:
    require_rating(body.rating)

    # 1. Idempotency replay (cheap probe before locking anything).
    existing = find_review_log(db, user.id, body.client_event_id)
    if existing is not None:
        return _replay_response(db, user.id, existing.review_card_id)

    # 2. Lock the card (+ user word) for this user.
    card = _owned_card_for_update(db, user.id, card_id)
    if card is None:
        raise not_found(code="review_card_not_found", message="复习卡片不存在或不属于当前用户")

    # 3. Re-probe the event now that the lock is held.
    existing = find_review_log(db, user.id, body.client_event_id)
    if existing is not None:
        return _replay_response(db, user.id, existing.review_card_id)

    # 4. Guard checks.
    word = card.user_word
    if word.status != "active":
        raise conflict(code="word_not_active", message="该词条当前不可复习（状态非 active）")
    if card.suspended_at is not None:
        raise conflict(code="card_suspended", message="该词条已暂停复习")
    if body.expected_card_version != card.version:
        raise conflict(
            code="version_conflict",
            message="卡片版本已变化，请刷新后重试",
            details={"expected": body.expected_card_version, "actual": card.version},
        )

    # 5-6. Schedule, mutate the card, append the full log, one commit.
    try:
        result = plan_review(card, body.rating, utcnow())
    except ValueError as exc:
        raise validation_error(
            "复习请求无法调度", {"field": "rating", "reason": str(exc)}
        ) from exc
    apply_schedule(card, result)
    db.add(ReviewLog(**review_log_values(
        user_id=user.id,
        card_id=card.id,
        client_event_id=body.client_event_id,
        result=result,
    )))
    try:
        db.commit()
    except IntegrityError:
        # 7. Concurrent duplicate (user_id, client_event_id): undo and replay.
        db.rollback()
        existing = find_review_log(db, user.id, body.client_event_id)
        if existing is not None:
            return _replay_response(db, user.id, existing.review_card_id)
        raise conflict(code="review_conflict", message="复习事件冲突，请重试") from None
    return {"card": card_dict(card), "replayed": False}
