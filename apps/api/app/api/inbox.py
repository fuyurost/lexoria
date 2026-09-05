"""Capture endpoint (POST /inbox) and inbox listing (GET /inbox).

POST /inbox atomically creates Word + UserWord (PG ON CONFLICT) and records a
single Encounter. `client_event_id` is REQUIRED and idempotent: re-sending the
same event replays the original outcome without mutating counters. An archived
word re-captured is revived to `inbox`. Surface text is stored cleaned
(clean_surface), the dictionary lemma is its casefolded form.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.capture import (
    find_encounter_by_event,
    get_or_create_user_word,
    record_encounter,
    resolve_or_create_word,
)
from app.api.serializers import inbox_item_dict, page_response
from app.core.deps import CurrentUser, DbDep
from app.core.errors import not_found, validation_error
from app.core.normalization import clean_surface, normalize_lemma
from app.models.user import User
from app.models.word import (
    ENCOUNTER_TYPES,
    USER_WORD_STATUSES,
    Encounter,
    Source,
    UserWord,
    Word,
)

router = APIRouter(prefix="/inbox", tags=["inbox"])

_WORD_LOADS = (
    selectinload(UserWord.word),
    selectinload(UserWord.card),
    selectinload(UserWord.senses),
)


class CaptureIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200)
    encounter_type: str = "unclassified"
    source_id: uuid.UUID | None = None
    context: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, max_length=4000)
    client_event_id: uuid.UUID  # required: idempotency key


def _validate_source(db: DbDep, user: User, source_id: uuid.UUID | None) -> None:
    if source_id is None:
        return
    source = db.execute(
        select(Source).where(Source.id == source_id, Source.user_id == user.id)
    ).scalar_one_or_none()
    if source is None:
        raise not_found(code="source_not_found", message="来源不存在或不属于当前用户")


@router.post("", status_code=201)
def capture(body: CaptureIn, user: CurrentUser, db: DbDep) -> dict:
    if body.encounter_type not in ENCOUNTER_TYPES:
        raise validation_error(
            f"encounter_type 无效，允许值: {', '.join(ENCOUNTER_TYPES)}",
            {"field": "encounter_type", "value": body.encounter_type},
        )
    _validate_source(db, user, body.source_id)
    try:
        surface = clean_surface(body.text)
    except ValueError as exc:
        raise validation_error(
            "捕获文本无法处理", {"field": "text", "reason": str(exc)}
        ) from exc

    # Fast path for repeats — dedupe correctness lives in record_encounter
    # (event lookup + unique-constraint race handling), not this query.
    existing = find_encounter_by_event(db, user.id, body.client_event_id)
    if existing is not None:
        user_word = db.get(UserWord, existing.user_word_id)
        return {
            "user_word_created": False,
            "replayed": True,
            **inbox_item_dict(user_word, existing),
        }

    word = resolve_or_create_word(db, surface)
    user_word, user_word_created = get_or_create_user_word(db, user.id, word.id)
    encounter, encounter_created = record_encounter(
        db,
        user_id=user.id,
        user_word=user_word,
        surface_text=surface,
        encounter_type=body.encounter_type,
        context=body.context,
        note=body.note,
        client_event_id=body.client_event_id,
        revive=True,
        created=user_word_created,
        source_id=body.source_id,
    )
    db.commit()
    db.refresh(user_word)
    return {
        "user_word_created": user_word_created,
        "replayed": not encounter_created,
        **inbox_item_dict(user_word, encounter),
    }


@router.get("")
def list_inbox(
    user: CurrentUser,
    db: DbDep,
    q: str | None = None,
    status: str | None = Query(default="inbox"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    if status is not None and status not in USER_WORD_STATUSES:
        raise validation_error(
            f"status 无效，允许值: {', '.join(USER_WORD_STATUSES)}",
            {"field": "status", "value": status},
        )

    filters = [UserWord.user_id == user.id]
    if status is not None:
        filters.append(UserWord.status == status)
    if q and q.strip():
        filters.append(Word.normalized_lemma.contains(normalize_lemma(q.strip())))
    stmt = select(UserWord).join(UserWord.word).where(*filters)
    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(UserWord.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(*_WORD_LOADS)
        )
        .scalars()
        .all()
    )
    # Latest encounter per word, fetched in one query.
    latest: dict[uuid.UUID, Encounter] = {}
    ids = [uw.id for uw in rows]
    if ids:
        found = (
            db.execute(
                select(Encounter)
                .where(Encounter.user_word_id.in_(ids))
                .options(selectinload(Encounter.source))
                .order_by(
                    Encounter.encountered_at.desc(), Encounter.created_at.desc()
                )
            )
            .scalars()
            .all()
        )
        for encounter in found:
            latest.setdefault(encounter.user_word_id, encounter)
    return page_response(
        [inbox_item_dict(uw, latest.get(uw.id)) for uw in rows],
        total,
        page,
        page_size,
    )
