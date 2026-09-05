"""User-private sources: list / create / PATCH (rename, retype, describe,
archive). Unique per (user, type, normalized_name); hard deletion is not
exposed — the API archives (SET NULL semantics already in the schema).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.serializers import source_dict
from app.core.deps import CurrentUser, DbDep
from app.core.errors import conflict, not_found, validation_error
from app.core.normalization import normalize_source_name, utcnow
from app.models.word import SOURCE_TYPES, Source

router = APIRouter(prefix="/sources", tags=["sources"])


def _get_owned_source(db: DbDep, user_id: uuid.UUID, source_id: uuid.UUID) -> Source:
    row = db.execute(
        select(Source).where(Source.id == source_id, Source.user_id == user_id)
    ).scalar_one_or_none()
    if row is None:
        raise not_found(code="source_not_found", message="来源不存在或不属于当前用户")
    return row


class SourceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    type: str = "manual"
    description: str | None = Field(default=None, max_length=4000)


class SourcePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    type: str | None = None
    description: str | None = Field(default=None, max_length=4000)
    archived: bool | None = None


def _validate_type(type_value: str) -> None:
    if type_value not in SOURCE_TYPES:
        raise validation_error(
            f"type 无效，允许值: {', '.join(SOURCE_TYPES)}",
            {"field": "type", "value": type_value},
        )


@router.get("")
def list_sources(
    user: CurrentUser,
    db: DbDep,
    include_archived: bool = Query(default=False),
) -> list[dict]:
    stmt = select(Source).where(Source.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Source.archived_at.is_(None))
    rows = db.execute(stmt.order_by(Source.created_at.desc())).scalars().all()
    return [source_dict(s) for s in rows]


@router.post("", status_code=201)
def create_source(body: SourceCreate, user: CurrentUser, db: DbDep) -> dict:
    _validate_type(body.type)
    source = Source(
        user_id=user.id,
        type=body.type,
        name=body.name.strip(),
        normalized_name=normalize_source_name(body.name),
        description=body.description,
    )
    db.add(source)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict(
            "duplicate_source", "同类型下已存在同名来源"
        ) from exc
    return source_dict(source)


@router.patch("/{source_id}")
def patch_source(
    source_id: uuid.UUID, body: SourcePatch, user: CurrentUser, db: DbDep
) -> dict:
    source = _get_owned_source(db, user.id, source_id)
    present = body.model_fields_set

    if "name" in present and body.name is not None:
        source.name = body.name.strip()
        source.normalized_name = normalize_source_name(body.name)
    if "type" in present and body.type is not None:
        _validate_type(body.type)
        source.type = body.type
    if "description" in present:
        source.description = body.description
    if "archived" in present and body.archived is not None:
        if body.archived and source.archived_at is None:
            source.archived_at = utcnow()
        elif not body.archived:
            source.archived_at = None
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise conflict(
            "duplicate_source", "同类型下已存在同名来源"
        ) from exc
    return source_dict(source)
