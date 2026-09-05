"""Encounters: append (syncs UserWord counters) and paginated listing.
Encounters are immutable — no update/delete endpoints.

Direct appends require `client_event_id` (idempotency, same rules as capture).
`surface_text` is optional: when supplied it is validated with clean_surface;
otherwise the word's canonical lemma is stored.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.capture import find_encounter_by_event, record_encounter
from app.api.serializers import encounter_dict, page_response
from app.core.deps import CurrentUser, DbDep
from app.core.errors import not_found, validation_error
from app.core.normalization import clean_surface
from app.models.word import ENCOUNTER_TYPES, Encounter, Source, UserWord

router = APIRouter(tags=["encounters"])

_SOURCE_LOAD = (selectinload(Encounter.source),)


def _validate_source(db: DbDep, user_id: uuid.UUID, source_id: uuid.UUID | None) -> None:
    if source_id is None:
        return
    source = db.execute(
        select(Source).where(Source.id == source_id, Source.user_id == user_id)
    ).scalar_one_or_none()
    if source is None:
        raise not_found(code="source_not_found", message="来源不存在或不属于当前用户")


def _owned_user_word(db: DbDep, user_id: uuid.UUID, word_id: uuid.UUID) -> UserWord:
    row = db.execute(
        select(UserWord).where(UserWord.id == word_id, UserWord.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        raise not_found(code="user_word_not_found", message="词条不存在或不属于当前用户")
    return row


class EncounterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_word_id: uuid.UUID
    client_event_id: uuid.UUID  # required: idempotency key
    source_id: uuid.UUID | None = None
    type: str = "unclassified"
    surface_text: str | None = Field(default=None, max_length=200)
    context: str | None = Field(default=None, max_length=4000)
    note: str | None = Field(default=None, max_length=4000)


@router.post("/encounters", status_code=201)
def create_encounter(body: EncounterCreate, user: CurrentUser, db: DbDep) -> dict:
    if body.type not in ENCOUNTER_TYPES:
        raise validation_error(
            f"type 无效，允许值: {', '.join(ENCOUNTER_TYPES)}",
            {"field": "type", "value": body.type},
        )
    _validate_source(db, user.id, body.source_id)
    user_word = _owned_user_word(db, user.id, body.user_word_id)

    if body.surface_text is not None:
        try:
            surface = clean_surface(body.surface_text)
        except ValueError as exc:
            raise validation_error(
                "surface_text 无法处理", {"field": "surface_text", "reason": str(exc)}
            ) from exc
    else:
        surface = user_word.word.lemma  # canonical fallback

    # Idempotency replay for repeated client events (no counter bump).
    existing = find_encounter_by_event(db, user.id, body.client_event_id)
    if existing is not None:
        return encounter_dict(existing)

    encounter, _created = record_encounter(
        db,
        user_id=user.id,
        user_word=user_word,
        surface_text=surface,
        encounter_type=body.type,
        context=body.context,
        note=body.note,
        client_event_id=body.client_event_id,
        revive=False,
        source_id=body.source_id,
    )
    db.commit()
    return encounter_dict(encounter)


@router.get("/encounters")
def list_encounters(
    user: CurrentUser,
    db: DbDep,
    user_word_id: uuid.UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    filters = [Encounter.user_id == user.id]
    if user_word_id is not None:
        _owned_user_word(db, user.id, user_word_id)  # 404 for foreign words
        filters.append(Encounter.user_word_id == user_word_id)
    base = select(Encounter).where(*filters)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(
            base.order_by(Encounter.encountered_at.desc(), Encounter.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .options(*_SOURCE_LOAD)
        )
        .scalars()
        .all()
    )
    return page_response([encounter_dict(e) for e in rows], total, page, page_size)


@router.get("/user-words/{word_id}/encounters")
def encounters_for_word(
    word_id: uuid.UUID, user: CurrentUser, db: DbDep
) -> list[dict]:
    _owned_user_word(db, user.id, word_id)
    rows = (
        db.execute(
            select(Encounter)
            .where(Encounter.user_id == user.id, Encounter.user_word_id == word_id)
            .order_by(Encounter.encountered_at.desc(), Encounter.created_at.desc())
            .options(*_SOURCE_LOAD)
        )
        .scalars()
        .all()
    )
    return [encounter_dict(e) for e in rows]
