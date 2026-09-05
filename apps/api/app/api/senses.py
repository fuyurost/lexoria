"""Sense CRUD (frozen API paths).

- POST   /user-words/{word_id}/senses          (nested under the word)
- PATCH  /user-word-senses/{sense_id}
- DELETE /user-word-senses/{sense_id}          (ownership via sense.user_id)

Create/patch require at least one non-empty definition (definition_zh/en);
reordering uses explicit sort_order with 409 on occupied slots; the last sense
of a non-inbox word cannot be deleted.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.serializers import sense_dict
from app.core.deps import CurrentUser, DbDep
from app.core.errors import conflict, not_found, validation_error
from app.models.word import UserWord, UserWordSense

router = APIRouter(tags=["senses"])


def _get_owned_word(db: DbDep, user_id: uuid.UUID, word_id: uuid.UUID) -> UserWord:
    row = db.execute(
        select(UserWord).where(UserWord.id == word_id, UserWord.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        raise not_found(code="user_word_not_found", message="词条不存在或不属于当前用户")
    return row


def _get_owned_sense(db: DbDep, user_id: uuid.UUID, sense_id: uuid.UUID) -> UserWordSense:
    row = db.get(UserWordSense, sense_id)
    if row is None or row.user_id != user_id:
        raise not_found(code="sense_not_found", message="义项不存在或不属于当前用户")
    return row


def _require_definition(definition_zh: str | None, definition_en: str | None) -> None:
    if not (definition_zh or "").strip() and not (definition_en or "").strip():
        raise validation_error(
            "definition_zh 与 definition_en 至少填写一项",
            {"field": "definition"},
        )


class SenseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_of_speech: str | None = Field(default=None, max_length=32)
    definition_zh: str | None = Field(default=None, max_length=4000)
    definition_en: str | None = Field(default=None, max_length=4000)


class SensePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    part_of_speech: str | None = Field(default=None, max_length=32)
    definition_zh: str | None = Field(default=None, max_length=4000)
    definition_en: str | None = Field(default=None, max_length=4000)
    sort_order: int | None = Field(default=None, ge=0)


@router.post("/user-words/{word_id}/senses", status_code=201)
def create_sense(
    word_id: uuid.UUID, body: SenseCreate, user: CurrentUser, db: DbDep
) -> dict:
    user_word = _get_owned_word(db, user.id, word_id)
    _require_definition(body.definition_zh, body.definition_en)
    next_order = db.execute(
        select(func.coalesce(func.max(UserWordSense.sort_order), -1) + 1).where(
            UserWordSense.user_word_id == user_word.id
        )
    ).scalar_one()
    sense = UserWordSense(
        user_id=user.id,
        user_word_id=user_word.id,
        part_of_speech=body.part_of_speech,
        definition_zh=body.definition_zh,
        definition_en=body.definition_en,
        sort_order=next_order,
    )
    db.add(sense)
    db.commit()
    return sense_dict(sense)


@router.patch("/user-word-senses/{sense_id}")
def patch_sense(
    sense_id: uuid.UUID, body: SensePatch, user: CurrentUser, db: DbDep
) -> dict:
    sense = _get_owned_sense(db, user.id, sense_id)
    present = body.model_fields_set

    if "part_of_speech" in present:
        sense.part_of_speech = body.part_of_speech
    if "definition_zh" in present:
        sense.definition_zh = body.definition_zh
    if "definition_en" in present:
        sense.definition_en = body.definition_en
    _require_definition(sense.definition_zh, sense.definition_en)
    if "sort_order" in present and body.sort_order is not None:
        sense.sort_order = body.sort_order
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict(
            "sort_order_taken",
            "该排序位置已被占用；先调整其它义项的 sort_order 后再试",
        ) from exc
    return sense_dict(sense)


@router.delete("/user-word-senses/{sense_id}", status_code=204)
def delete_sense(sense_id: uuid.UUID, user: CurrentUser, db: DbDep) -> None:
    sense = _get_owned_sense(db, user.id, sense_id)
    user_word = db.get(UserWord, sense.user_word_id)
    remaining = db.execute(
        select(func.count())
        .select_from(UserWordSense)
        .where(
            UserWordSense.user_word_id == sense.user_word_id,
            UserWordSense.id != sense.id,
        )
    ).scalar_one()
    if remaining == 0 and user_word is not None and user_word.status != "inbox":
        raise conflict(
            "last_sense",
            "该词条不在 inbox 状态，至少需要保留一个义项",
        )
    db.delete(sense)
    db.commit()
