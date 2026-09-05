"""User-word library: paginated list (search/filters/sort), detail, PATCH.

Words (global dictionary) are never created/edited through this API — new
entries only come from POST /inbox captures. The only mutable user state here
lives on the UserWord row + its ReviewCard.

Status rules:
- `active`   -> requires >= 1 sense; card exists and is NOT suspended,
                due_at reset to now on activation.
- `inbox` / `known` / `archived` -> card (if any) is suspended.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.api.serializers import page_response, user_word_dict
from app.core.deps import CurrentUser, DbDep
from app.core.errors import conflict, not_found, validation_error
from app.core.normalization import normalize_lemma, utcnow
from app.models.review import ReviewCard
from app.models.word import (
    USER_WORD_STATUSES,
    Encounter,
    UserWord,
    UserWordSense,
    Word,
)

router = APIRouter(prefix="/user-words", tags=["user-words"])

_WORD_LOADS = (
    selectinload(UserWord.word),
    selectinload(UserWord.card),
    selectinload(UserWord.senses),
)

# Frontend sort keys. `due:asc` needs the card join.
_SORTS = {
    "created_at:desc": (UserWord.created_at.desc(), False),
    "created_at:asc": (UserWord.created_at.asc(), False),
    "lemma:asc": (Word.lemma.asc(), False),
    "familiarity:desc": (UserWord.familiarity.desc().nulls_last(), False),
    "due:asc": (ReviewCard.due_at.asc().nulls_last(), True),
}


def _get_owned_user_word(db: DbDep, user_id: uuid.UUID, word_id: uuid.UUID) -> UserWord:
    row = db.execute(
        select(UserWord)
        .where(UserWord.id == word_id, UserWord.user_id == user_id)
        .options(*_WORD_LOADS)
    ).scalar_one_or_none()
    if row is None:
        raise not_found(code="user_word_not_found", message="词条不存在或不属于当前用户")
    return row


def ensure_card(db: DbDep, user_word: UserWord) -> ReviewCard:
    """One scheduling card per user word (unique user_word_id); no-ops when
    a card already exists — concurrency-safe via ON CONFLICT DO NOTHING."""
    stmt = (
        pg_insert(ReviewCard)
        .values(user_id=user_word.user_id, user_word_id=user_word.id)
        .on_conflict_do_nothing(index_elements=[ReviewCard.user_word_id])
        .returning(ReviewCard.id)
    )
    card_id = db.execute(stmt).scalar_one_or_none()
    if card_id is None:
        card = db.execute(
            select(ReviewCard).where(ReviewCard.user_word_id == user_word.id)
        ).scalar_one()
    else:
        card = db.get(ReviewCard, card_id)
    db.flush()
    return card


def _apply_status(db: DbDep, user_word: UserWord, target: str) -> None:
    if target == user_word.status:
        return
    now = utcnow()
    if target == "active":
        sense_count = db.execute(
            select(func.count())
            .select_from(UserWordSense)
            .where(UserWordSense.user_word_id == user_word.id)
        ).scalar_one()
        if sense_count == 0:
            raise conflict("requires_sense", "激活词条前至少需要添加一个义项定义")
        if user_word.activated_at is None:
            user_word.activated_at = now
        card = ensure_card(db, user_word)
        card.suspended_at = None
        card.due_at = now  # activation (re)starts scheduling now
    else:  # inbox / known / archived all suspend the card
        if user_word.card is not None and user_word.card.suspended_at is None:
            user_word.card.suspended_at = now
        if target == "archived" and user_word.archived_at is None:
            user_word.archived_at = now
    user_word.status = target
    if target != "archived":
        user_word.archived_at = None


class UserWordPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    personal_phonetic: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=4000)
    status: str | None = None
    familiarity: int | None = Field(default=None, ge=0, le=5)


@router.get("")
def list_words(
    user: CurrentUser,
    db: DbDep,
    q: str | None = None,
    status: str | None = None,
    familiarity: int | None = Query(default=None, ge=0, le=5),
    source_id: uuid.UUID | None = None,
    sort: str = "created_at:desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    if status is not None and status not in USER_WORD_STATUSES:
        raise validation_error(
            f"status 无效，允许值: {', '.join(USER_WORD_STATUSES)}",
            {"field": "status", "value": status},
        )
    if sort not in _SORTS:
        raise validation_error(
            f"sort 无效，允许值: {', '.join(_SORTS)}",
            {"field": "sort", "value": sort},
        )

    filters = [UserWord.user_id == user.id]
    if status is not None:
        filters.append(UserWord.status == status)
    if familiarity is not None:
        filters.append(UserWord.familiarity == familiarity)
    if q and q.strip():
        filters.append(Word.normalized_lemma.contains(normalize_lemma(q.strip())))
    if source_id is not None:
        # Words met through this source (exists-subquery: no row duplication).
        filters.append(
            UserWord.id.in_(
                select(Encounter.user_word_id).where(
                    Encounter.user_id == user.id,
                    Encounter.source_id == source_id,
                )
            )
        )

    stmt = select(UserWord).join(UserWord.word)
    if _SORTS[sort][1]:
        stmt = stmt.outerjoin(ReviewCard, ReviewCard.user_word_id == UserWord.id)
    stmt = stmt.where(*filters)

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(_SORTS[sort][0])
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(*_WORD_LOADS)
        )
        .scalars()
        .all()
    )
    return page_response([user_word_dict(uw) for uw in rows], total, page, page_size)


@router.get("/{word_id}")
def get_word(word_id: uuid.UUID, user: CurrentUser, db: DbDep) -> dict:
    return user_word_dict(_get_owned_user_word(db, user.id, word_id))


@router.patch("/{word_id}")
def patch_word(
    word_id: uuid.UUID, body: UserWordPatch, user: CurrentUser, db: DbDep
) -> dict:
    user_word = _get_owned_user_word(db, user.id, word_id)
    present = body.model_fields_set

    if "personal_phonetic" in present:
        user_word.personal_phonetic = body.personal_phonetic
    if "note" in present:
        user_word.note = body.note
    if "familiarity" in present:
        user_word.familiarity = body.familiarity
    if "status" in present:
        if body.status is None or body.status not in USER_WORD_STATUSES:
            raise validation_error(
                f"status 无效，允许值: {', '.join(USER_WORD_STATUSES)}",
                {"field": "status"},
            )
        _apply_status(db, user_word, body.status)
    db.commit()
    return user_word_dict(_get_owned_user_word(db, user.id, word_id))
