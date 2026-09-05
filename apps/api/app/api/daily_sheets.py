"""Daily printable sheets: preview / generate (PDF) / list / detail / pdf.

POST /daily-sheets/preview  — dry run: selection + escaped HTML, no writes.
POST /daily-sheets          — generate: select, snapshot, render PDF bytes,
                              atomically store under a random internal key,
                              then persist the sheet + items in one
                              transaction (stored file is removed if the DB
                              write fails).
GET  /daily-sheets          — paginated sheet summaries (counts derived from
                              item rows).
GET  /daily-sheets/{id}     — summary + per-item content snapshots.
GET  /daily-sheets/{id}/pdf — authenticated FileResponse; path safety is
                              enforced by resolve_pdf_path (never 404-leaks
                              another user's sheet because ownership is
                              checked first).

Selection rules (see app/services/daily_selector.py):
* eligible = UserWord.status 'active', card not suspended, >= 1 sense;
* new  = card.state 'new' with zero review logs;
* review = every other eligible card (scheduling buckets decide inclusion);
* signals (last Again, 7d Again count, last Hard, sources) come from
  ReviewLog + Encounter rows so the pure selector stays deterministic.
"""
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import contains_eager, selectinload

from app.api.serializers import page_response
from app.core.config import settings
from app.core.deps import CurrentUser, DbDep
from app.core.errors import AppError, not_found, validation_error
from app.core.normalization import to_iso, utcnow
from app.models.review import ReviewCard, ReviewLog
from app.models.sheet import ITEM_TYPES, DailySheet, DailySheetItem
from app.models.user import UserSetting
from app.models.word import Encounter, Source, UserWord, UserWordSense
from app.services import pdf as pdf_service
from app.services.daily_selector import Candidate, select_daily

router = APIRouter(prefix="/daily-sheets", tags=["daily-sheets"])

_SHEET_LOADS = (
    selectinload(UserWord.word),
    selectinload(UserWord.senses),
)

_ELIGIBLE = (
    UserWord.status == "active",
    ReviewCard.suspended_at.is_(None),
)


class DailySheetRequest(BaseModel):
    """Effective config: absent fields fall back to UserSetting, then to the
    column defaults (UTC / compact / a4 / 1 col / 10+10)."""

    model_config = ConfigDict(extra="forbid")

    template: Literal["compact", "test"] | None = None
    paper_size: Literal["a4", "a5"] | None = None
    columns: Literal[1, 2] | None = None
    review_count: int | None = Field(default=None, ge=0)
    new_count: int | None = Field(default=None, ge=0)
    source_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)


def _resolve_setting(db: DbDep, user_id: uuid.UUID) -> UserSetting | None:
    return db.get(UserSetting, user_id)


def _pick(value, fallback):
    return fallback if value is None else value


def _resolve_config(
    body: DailySheetRequest,
    setting: UserSetting | None,
) -> dict:
    """Effective request config (settings defaults applied + range check)."""
    review_count = _pick(body.review_count, setting.review_count if setting else 10)
    new_count = _pick(body.new_count, setting.new_count if setting else 10)
    total = review_count + new_count
    if not 1 <= total <= 100:
        raise validation_error(
            "当日数量(review_count + new_count)需在 1..100 之间",
            {"review_count": review_count, "new_count": new_count},
        )
    return {
        "template": _pick(body.template, setting.daily_template if setting else "compact"),
        "paper_size": _pick(body.paper_size, setting.paper_size if setting else "a4"),
        "columns": _pick(body.columns, setting.columns if setting else 1),
        "review_count": review_count,
        "new_count": new_count,
        "source_ids": list(body.source_ids) if body.source_ids is not None else None,
        "timezone": setting.timezone if setting else "UTC",
    }


def _tz(config: dict) -> ZoneInfo:
    try:
        return ZoneInfo(config["timezone"])
    except ZoneInfoNotFoundError as exc:
        raise validation_error(
            "未知的时区标识", {"field": "timezone", "value": config["timezone"]}
        ) from exc


def _day_window(tz: ZoneInfo, now_utc: datetime) -> tuple[date, datetime, datetime]:
    """sheet_date + [local 00:00, next local 00:00) as UTC instants."""
    local = now_utc.astimezone(tz)
    sheet_date = local.date()
    day_start = datetime.combine(sheet_date, time.min, tzinfo=tz).astimezone(UTC)
    day_end = datetime.combine(
        sheet_date + timedelta(days=1), time.min, tzinfo=tz
    ).astimezone(UTC)
    return sheet_date, day_start, day_end


def _validate_sources(db: DbDep, user_id: uuid.UUID, source_ids: list[uuid.UUID]) -> None:
    """Every requested source must exist and belong to the user."""
    found = set(
        db.execute(
            select(Source.id).where(
                Source.user_id == user_id, Source.id.in_(source_ids)
            )
        ).scalars()
    )
    missing = [str(sid) for sid in dict.fromkeys(source_ids) if sid not in found]
    if missing:
        raise not_found(
            code="source_not_found",
            message="source_ids 中存在不存在或不属于当前用户的来源",
            details={"source_ids": missing},
        )


def _load_candidates(
    db: DbDep,
    user: CurrentUser,
    now_utc: datetime,
) -> tuple[list[UserWord], list[Candidate], dict[uuid.UUID, UserWord]]:
    """Load eligible words + scheduling signals; returns ORM rows, selector
    candidates and a user_word_id -> row map (shared by callers)."""
    stmt = (
        select(UserWord)
        .join(ReviewCard, ReviewCard.user_word_id == UserWord.id)
        .where(UserWord.user_id == user.id, *_ELIGIBLE)
        .where(
            select(UserWordSense.id)
            .where(UserWordSense.user_word_id == UserWord.id)
            .exists()
        )
        .options(contains_eager(UserWord.card), *_SHEET_LOADS)
    )
    rows = db.execute(stmt).scalars().all()
    if not rows:
        return [], [], {}

    uw_ids = [uw.id for uw in rows]
    card_ids = [uw.card.id for uw in rows if uw.card is not None]

    # Distinct encounter source ids per word (one bulk query).
    sources: dict[uuid.UUID, set[uuid.UUID]] = {uw.id: set() for uw in rows}
    enc_rows = db.execute(
        select(Encounter.user_word_id, Encounter.source_id).where(
            Encounter.user_id == user.id,
            Encounter.user_word_id.in_(uw_ids),
            Encounter.source_id.is_not(None),
        )
    ).all()
    for word_id, source_id in enc_rows:
        sources.setdefault(word_id, set()).add(source_id)

    # ReviewLog signals (again/hard) + log count per card.
    cutoff = now_utc - timedelta(days=7)
    signals: dict[uuid.UUID, dict] = {}
    if card_ids:
        sig_rows = db.execute(
            select(
                ReviewLog.review_card_id,
                func.count().label("log_count"),
                func.max(ReviewLog.reviewed_at)
                .filter(ReviewLog.rating == "again")
                .label("last_again_at"),
                func.max(ReviewLog.reviewed_at)
                .filter(ReviewLog.rating == "hard")
                .label("last_hard_at"),
                func.count()
                .filter(ReviewLog.rating == "again", ReviewLog.reviewed_at >= cutoff)
                .label("again_count_7d"),
            )
            .where(ReviewLog.review_card_id.in_(card_ids))
            .group_by(ReviewLog.review_card_id)
        ).all()
        for row in sig_rows:
            signals[row.review_card_id] = {
                "log_count": row.log_count or 0,
                "last_again_at": row.last_again_at,
                "last_hard_at": row.last_hard_at,
                "again_count_7d": row.again_count_7d or 0,
            }

    candidates: list[Candidate] = []
    by_id: dict[uuid.UUID, UserWord] = {}
    for uw in rows:
        card = uw.card
        if card is None:
            continue  # join guarantees a card; defensive
        by_id[uw.id] = uw
        sig = signals.get(card.id, {})
        log_count = sig.get("log_count", 0)
        is_new = card.state == "new" and log_count == 0
        candidates.append(
            Candidate(
                user_word_id=uw.id,
                normalized_lemma=uw.word.normalized_lemma if uw.word else "",
                state=card.state,
                due_at=card.due_at,
                difficulty=card.difficulty,
                lapse_count=card.lapse_count,
                last_again_at=sig.get("last_again_at"),
                again_count_7d=sig.get("again_count_7d", 0),
                last_hard_at=sig.get("last_hard_at"),
                activated_at=uw.activated_at,
                first_seen_at=uw.first_seen_at,
                is_new=is_new,
                source_ids=tuple(sources.get(uw.id, ())),
            )
        )
    return rows, candidates, by_id


def _sense_dicts(uw: UserWord) -> list[dict]:
    ordered = sorted(uw.senses, key=lambda s: s.sort_order)
    return [
        {
            "part_of_speech": s.part_of_speech,
            "definition_zh": s.definition_zh,
            "definition_en": s.definition_en,
        }
        for s in ordered
    ]


def _make_rows(
    selection, by_id: dict[uuid.UUID, UserWord]
) -> list[dict]:
    """Selected items -> full row dicts (snapshot content + FK handles)."""
    result = []
    for item in selection.items:
        uw = by_id[item.candidate.user_word_id]
        result.append(
            {
                "sort_order": item.sort_order,
                "lemma": uw.word.lemma if uw.word else "",
                "normalized_lemma": uw.word.normalized_lemma if uw.word else "",
                "personal_phonetic": uw.personal_phonetic,
                "senses": _sense_dicts(uw),
                "item_type": item.item_type,
                "selection_reason": item.reason,
                "user_word_id": uw.id,
                "review_card_id": uw.card.id if uw.card else None,
            }
        )
    return result


def _counts(rows: list[dict]) -> tuple[int, int]:
    review_n = sum(1 for r in rows if r["item_type"] == "review")
    return review_n, len(rows) - review_n


def _word_summary(row: dict) -> dict:
    """Frontend preview/detail word shape (flat, first sense)."""
    senses = row.get("senses") or []
    first = senses[0] if senses else {}
    return {
        "lemma": row["lemma"],
        "personal_phonetic": row.get("personal_phonetic"),
        "part_of_speech": first.get("part_of_speech"),
        "definition_zh": first.get("definition_zh") or "",
        "definition_en": first.get("definition_en") or "",
    }


def _preview_response(
    config: dict,
    rows: list[dict],
    warnings: tuple[str, ...],
    sheet_date: date,
) -> dict:
    review_n, new_n = _counts(rows)
    sections = []
    for kind in ITEM_TYPES:  # "review" first, then "new"
        words = [_word_summary(r) for r in rows if r["item_type"] == kind]
        if words:
            sections.append({"kind": kind, "words": words})
    html = pdf_service.render_html(
        template=config["template"],
        paper_size=config["paper_size"],
        columns=config["columns"],
        sheet_date=sheet_date.isoformat(),
        rows=rows,
        review_count=review_n,
        new_count=new_n,
    )
    return {
        "config": {
            "template": config["template"],
            "paper_size": config["paper_size"],
            "columns": config["columns"],
            "review_count": config["review_count"],
            "new_count": config["new_count"],
            "source_ids": [str(s) for s in (config["source_ids"] or [])],
        },
        "sections": sections,
        "word_total": len(rows),
        "warnings": list(warnings),
        "html": html,
    }


def _run_selection(
    db: DbDep, user: CurrentUser, body: DailySheetRequest
) -> tuple[dict, list[dict], tuple[str, ...], date]:
    """Effective config + selected rows (+selector warnings) for a request."""
    config = _resolve_config(body, _resolve_setting(db, user.id))
    if config["source_ids"]:
        _validate_sources(db, user.id, config["source_ids"])
    tz = _tz(config)
    now_utc = utcnow()
    sheet_date, day_start, day_end = _day_window(tz, now_utc)
    _rows, candidates, by_id = _load_candidates(db, user, now_utc)
    requested = tuple(config["source_ids"]) if config["source_ids"] else None
    result = select_daily(
        candidates,
        as_of=now_utc,
        day_start=day_start,
        day_end=day_end,
        review_count=config["review_count"],
        new_count=config["new_count"],
        requested_source_ids=requested,
    )
    selected_rows = _make_rows(result.items, by_id)
    return config, selected_rows, result.warnings, sheet_date


def _owned_sheet(db: DbDep, user_id: uuid.UUID, sheet_id: uuid.UUID) -> DailySheet:
    sheet = db.execute(
        select(DailySheet).where(DailySheet.id == sheet_id, DailySheet.user_id == user_id)
    ).scalar_one_or_none()
    if sheet is None:
        raise not_found(code="daily_sheet_not_found", message="练习纸不存在或不属于当前用户")
    return sheet


def _summary_dict(sheet: DailySheet, review_n: int, new_n: int) -> dict:
    return {
        "id": str(sheet.id),
        "sheet_date": sheet.sheet_date.isoformat(),
        "timezone_snapshot": sheet.timezone_snapshot,
        "template": sheet.template,
        "paper_size": sheet.paper_size,
        "columns": sheet.columns,
        "actual_review_count": review_n,
        "actual_new_count": new_n,
        "created_at": to_iso(sheet.created_at),
    }


def _item_dict(item: DailySheetItem) -> dict:
    """API item = content snapshot + stable row fields (front-end friendly)."""
    snap = item.content_snapshot or {}
    senses = snap.get("senses") or []
    first = senses[0] if senses else {}
    return {
        "id": str(item.id),
        "kind": item.item_type,
        "sort_order": item.sort_order,
        "item_type": item.item_type,
        "selection_reason": item.selection_reason,
        "lemma": snap.get("lemma", ""),
        "normalized_lemma": snap.get("normalized_lemma"),
        "personal_phonetic": snap.get("personal_phonetic"),
        "part_of_speech": first.get("part_of_speech"),
        "definition_zh": first.get("definition_zh"),
        "definition_en": first.get("definition_en"),
        "senses": senses,
    }


# --- routes ----------------------------------------------------------------


@router.post("/preview")
def preview_sheet(
    body: DailySheetRequest, user: CurrentUser, db: DbDep
) -> dict:
    """Select words and render the escaped sheet HTML; persists nothing."""
    config, rows, warnings, sheet_date = _run_selection(db, user, body)
    return _preview_response(config, rows, warnings, sheet_date)


@router.post("", status_code=201)
def generate_sheet(
    body: DailySheetRequest, user: CurrentUser, db: DbDep
) -> dict:
    """Select, snapshot, render the PDF and persist sheet + items atomically."""
    config, rows, warnings, sheet_date = _run_selection(db, user, body)
    if not rows:
        raise AppError(
            422,
            "no_candidates",
            "没有可生成练习词的候选词（没有符合条件的 active 词汇）",
            details={"warnings": list(warnings)},
        )

    review_n, new_n = _counts(rows)
    html = pdf_service.render_html(
        template=config["template"],
        paper_size=config["paper_size"],
        columns=config["columns"],
        sheet_date=sheet_date.isoformat(),
        rows=rows,
        review_count=review_n,
        new_count=new_n,
    )
    try:
        pdf_bytes = pdf_service.render_pdf_bytes(html)
    except pdf_service.PdfUnavailableError as exc:
        raise pdf_service.pdf_unavailable_error() from exc
    except pdf_service.PdfRenderError as exc:
        raise pdf_service.pdf_render_error(str(exc)) from exc

    storage_key = None
    try:
        storage_key = pdf_service.store_pdf_bytes(
            pdf_bytes, settings.pdf_storage_dir
        )
    except pdf_service.PdfStorageError as exc:
        raise pdf_service.pdf_storage_error(str(exc)) from exc

    # Persist the sheet + items; remove the stored PDF if this fails so no
    # orphan file survives a failed transaction.
    try:
        sheet = DailySheet(
            user_id=user.id,
            sheet_date=sheet_date,
            timezone_snapshot=config["timezone"],
            template=config["template"],
            paper_size=config["paper_size"],
            columns=config["columns"],
            pdf_storage_key=storage_key,
        )
        db.add(sheet)
        db.flush()
        for row in rows:
            db.add(
                DailySheetItem(
                    user_id=user.id,
                    daily_sheet_id=sheet.id,
                    user_word_id=row["user_word_id"],
                    review_card_id=row["review_card_id"],
                    item_type=row["item_type"],
                    selection_reason=row["selection_reason"],
                    sort_order=row["sort_order"],
                    snapshot_schema_version=1,
                    content_snapshot=pdf_service.build_snapshot(
                        lemma=row["lemma"],
                        normalized_lemma=row["normalized_lemma"],
                        personal_phonetic=row["personal_phonetic"],
                        senses=row["senses"],
                        item_type=row["item_type"],
                        selection_reason=row["selection_reason"],
                    ),
                )
            )
        db.commit()
        db.refresh(sheet)
    except Exception:
        db.rollback()
        if storage_key is not None:
            pdf_service.delete_pdf(settings.pdf_storage_dir, storage_key)
        raise
    return _summary_dict(sheet, review_n, new_n)


@router.get("")
def list_sheets(
    user: CurrentUser,
    db: DbDep,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    base = select(DailySheet).where(DailySheet.user_id == user.id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    sheets = (
        db.execute(
            base.order_by(
                DailySheet.created_at.desc(), DailySheet.id.desc()
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    if sheets:
        agg = db.execute(
            select(
                DailySheetItem.daily_sheet_id,
                func.count().filter(DailySheetItem.item_type == "review"),
                func.count().filter(DailySheetItem.item_type == "new"),
            )
            .where(DailySheetItem.daily_sheet_id.in_([s.id for s in sheets]))
            .group_by(DailySheetItem.daily_sheet_id)
        ).all()
        for sheet_id, review_n, new_n in agg:
            counts[sheet_id] = (review_n or 0, new_n or 0)
    items = []
    for sheet in sheets:
        review_n, new_n = counts.get(sheet.id, (0, 0))
        items.append(_summary_dict(sheet, review_n, new_n))
    return page_response(items, total, page, page_size)


@router.get("/{sheet_id}")
def get_sheet(sheet_id: uuid.UUID, user: CurrentUser, db: DbDep) -> dict:
    sheet = _owned_sheet(db, user.id, sheet_id)
    item_rows = (
        db.execute(
            select(DailySheetItem)
            .where(DailySheetItem.daily_sheet_id == sheet.id)
            .order_by(DailySheetItem.sort_order)
        )
        .scalars()
        .all()
    )
    review_n = sum(1 for r in item_rows if r.item_type == "review")
    new_n = len(item_rows) - review_n
    detail = _summary_dict(sheet, review_n, new_n)
    detail["items"] = [_item_dict(item) for item in item_rows]
    return detail


@router.get("/{sheet_id}/pdf")
def get_sheet_pdf(sheet_id: uuid.UUID, user: CurrentUser, db: DbDep) -> FileResponse:
    sheet = _owned_sheet(db, user.id, sheet_id)
    path = pdf_service.resolve_pdf_path(settings.pdf_storage_dir, sheet.pdf_storage_key)
    if path is None:
        raise not_found(code="pdf_not_found", message="练习纸 PDF 不存在")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=f"daily-sheet-{sheet.sheet_date.isoformat()}.pdf",
    )
