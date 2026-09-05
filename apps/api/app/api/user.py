"""Current user + per-user print settings."""
from __future__ import annotations

from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.serializers import settings_dict, user_dict
from app.core.deps import CurrentUser, DbDep
from app.core.errors import validation_error
from app.models.user import User, UserSetting

router = APIRouter(tags=["me", "settings"])


@router.get("/me")
def me(user: CurrentUser) -> dict:
    return user_dict(user)


class SettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str | None = None
    daily_template: Literal["compact", "test"] | None = None
    paper_size: Literal["a4", "a5"] | None = None
    columns: Literal[1, 2] | None = None
    review_count: int | None = Field(default=None, ge=0)
    new_count: int | None = Field(default=None, ge=0)


def _get_or_create_settings(db: DbDep, user: User) -> UserSetting:
    row = db.get(UserSetting, user.id)
    if row is None:
        row = UserSetting(user_id=user.id)
        db.add(row)
        db.flush()
    return row


@router.get("/settings")
def get_settings(user: CurrentUser, db: DbDep) -> dict:
    existing = db.get(UserSetting, user.id)
    if existing is None:
        row = UserSetting(user_id=user.id)
        db.add(row)
        db.commit()  # persist the lazily-created default row
        return settings_dict(row)
    return settings_dict(existing)


@router.patch("/settings")
def patch_settings(body: SettingsPatch, user: CurrentUser, db: DbDep) -> dict:
    row = _get_or_create_settings(db, user)

    if body.timezone is not None:
        try:
            ZoneInfo(body.timezone)
        except ZoneInfoNotFoundError as exc:
            raise validation_error(
                "未知的时区标识", {"field": "timezone", "value": body.timezone}
            ) from exc
        row.timezone = body.timezone
    if body.daily_template is not None:
        row.daily_template = body.daily_template
    if body.paper_size is not None:
        row.paper_size = body.paper_size
    if body.columns is not None:
        row.columns = body.columns
    if body.review_count is not None:
        row.review_count = body.review_count
    if body.new_count is not None:
        row.new_count = body.new_count

    total = row.review_count + row.new_count
    if not 1 <= total <= 100:
        db.rollback()
        raise validation_error(
            "当日数量(review_count + new_count)需在 1..100 之间",
            {"review_count": row.review_count, "new_count": row.new_count},
        )
    db.commit()
    return settings_dict(row)
