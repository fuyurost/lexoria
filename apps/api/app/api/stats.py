"""GET /stats — per-user dashboard counters.

Day boundaries are computed in Python from the user's settings timezone and
converted to UTC instants; every query filters on those instants (>= start,
< end), so no Postgres timezone string functions are involved. Streak days
are also derived from ReviewLog instants converted to local dates in Python.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter
from sqlalchemy import func, select

from app.core.deps import CurrentUser, DbDep
from app.models.review import ReviewCard, ReviewLog
from app.models.user import UserSetting
from app.models.word import Encounter, Source, UserWord

router = APIRouter(tags=["stats"])

STATUS_KEYS = ("inbox", "active", "known", "archived")


def _user_timezone(db: DbDep, user_id: object) -> ZoneInfo:
    row = db.get(UserSetting, user_id)
    name = row.timezone if row is not None else "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _local_day_bounds(tz: ZoneInfo, now: datetime) -> tuple[datetime, datetime]:
    """(utc_start, utc_end) of the user's current local day."""
    local = now.astimezone(tz)
    start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def _streak_days(dates: set, today) -> int:
    """Consecutive review days ending today or yesterday; 0 when none/broken."""
    if not dates:
        return 0
    latest = max(dates)
    if latest < today - timedelta(days=1):
        return 0
    streak = 0
    cursor = latest
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@router.get("/stats")
def stats(user: CurrentUser, db: DbDep) -> dict:
    now = datetime.now(timezone.utc)
    tz = _user_timezone(db, user.id)
    day_start_utc, day_end_utc = _local_day_bounds(tz, now)
    today_local = now.astimezone(tz).date()

    status_rows = db.execute(
        select(UserWord.status, func.count())
        .where(UserWord.user_id == user.id)
        .group_by(UserWord.status)
    ).all()
    status_counts = {status: count for status, count in status_rows}
    words_by_status = {key: int(status_counts.get(key, 0)) for key in STATUS_KEYS}
    # Current vocabulary total = inbox + active + known (archived excluded).
    words_total = sum(words_by_status[key] for key in ("inbox", "active", "known"))

    due_today = db.execute(
        select(func.count())
        .select_from(UserWord)
        .join(ReviewCard, ReviewCard.user_word_id == UserWord.id)
        .where(
            UserWord.user_id == user.id,
            UserWord.status == "active",
            ReviewCard.suspended_at.is_(None),
            ReviewCard.due_at <= now,
        )
    ).scalar_one()

    reviewed_today = db.execute(
        select(func.count())
        .select_from(ReviewLog)
        .where(
            ReviewLog.user_id == user.id,
            ReviewLog.reviewed_at >= day_start_utc,
            ReviewLog.reviewed_at < day_end_utc,
        )
    ).scalar_one()

    captured_today = db.execute(
        select(func.count())
        .select_from(Encounter)
        .where(
            Encounter.user_id == user.id,
            Encounter.encountered_at >= day_start_utc,
            Encounter.encountered_at < day_end_utc,
        )
    ).scalar_one()

    sources_total = db.execute(
        select(func.count())
        .select_from(Source)
        .where(Source.user_id == user.id, Source.archived_at.is_(None))
    ).scalar_one()

    log_times = db.execute(
        select(ReviewLog.reviewed_at).where(ReviewLog.user_id == user.id)
    ).scalars()
    local_dates = {reviewed.astimezone(tz).date() for reviewed in log_times}

    return {
        "words_total": words_total,
        "words_by_status": words_by_status,
        "due_today": due_today,
        "reviewed_today": reviewed_today,
        "captured_today": captured_today,
        "inbox_open": words_by_status["inbox"],
        "sources_total": sources_total,
        "streak_days": _streak_days(local_dates, today_local),
    }
