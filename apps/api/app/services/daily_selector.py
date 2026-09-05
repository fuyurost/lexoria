"""Pure, deterministic daily review/new candidate selector (daily sheets).

No I/O, no database, no randomness: identical inputs always yield identical
:class:`SelectionResult`. Eligibility (active / not suspended / has a sense)
is the caller's job; the selector only applies the requested-source
intersection, per-word dedup, priority grouping and the review/new quotas.

Contract notes (conventions fixed here so behaviour is unambiguous):
* ``as_of`` anchors the 72h "recent Again" and 7d "recent Hard" windows;
  window lower edges are *inclusive* (``last_again_at >= as_of - 72h``) and
  future timestamps never qualify.
* Day window is ``[day_start, day_end)``: ``due < day_start`` is overdue,
  ``day_start <= due < day_end`` is due today, ``due >= day_end`` is future.
* ``requested_source_ids``: ``None``/empty means no source restriction;
  otherwise every candidate must share at least one source id with it.
* Dedup keeps the first input occurrence per ``user_word_id``, applied after
  the source filter.
* Review buckets by priority: ``overdue`` (due before day start) > state
  ``relearning`` or recent Again within 72h > ``due_today`` > recent Hard
  within 7d. Each word lands in its highest applicable bucket only; ordinary
  future cards never enter the pool. Every key is a total order ending in
  ``normalized_lemma`` then ``user_word_id``:
    - overdue: relearning state first, then due asc, then lapse desc,
      then lemma, then id
    - relearning / recent_again: again_count_7d desc, last_again desc,
      due asc, lemma, id
    - due_today: due asc, difficulty desc, lemma, id
    - recent_hard: last_hard desc, due asc, lemma, id
* New pool: ``is_new`` candidates ordered by activated_at asc, first_seen_at
  asc, normalized_lemma asc, user_word_id asc (missing timestamps sort last).
* Quota rules: take review up to ``review_count`` and new up to
  ``new_count`` first. If the new pool is short, the remaining review
  candidates fill the total (``review_count + new_count``); if the review
  pool is short, new intake never exceeds ``new_count``.
* ``sort_order`` is 1-based over the returned items (review block first, then
  the new block).
* Warnings: ``no_candidates`` when nothing at all is selected,
  ``candidate_pool_too_small`` when 1..total-1 items are selected.

Validation: timezone-aware datetimes are required; ``review_count`` /
``new_count`` must be non-negative integers whose sum is in 1..100;
``day_start`` must precede ``day_end``.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

# Same vocabulary as app/models/sheet.py DailySheetItem.selection_reason.
SELECTION_REASONS = (
    "overdue",
    "relearning",
    "recent_again",
    "due_today",
    "recent_hard",
    "new",
)

RECENT_AGAIN_WINDOW = timedelta(hours=72)
RECENT_HARD_WINDOW = timedelta(days=7)
_MAX_BATCH_SIZE = 100

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class Candidate:
    """One eligible vocabulary word with its scheduling signals.

    ``is_new`` splits the pools: new words never compete for review buckets.
    ``source_ids`` is the set of sources the word belongs to (used only for
    the requested-source intersection).
    """

    user_word_id: object
    normalized_lemma: str
    state: str
    due_at: datetime
    difficulty: Decimal = Decimal("5.00")
    lapse_count: int = 0
    last_again_at: datetime | None = None
    again_count_7d: int = 0
    last_hard_at: datetime | None = None
    activated_at: datetime | None = None
    first_seen_at: datetime | None = None
    is_new: bool = False
    source_ids: tuple[object, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectedItem:
    """One word chosen for the daily sheet."""

    item_type: str  # "review" | "new"
    reason: str  # one of SELECTION_REASONS
    sort_order: int  # 1-based position in the returned selection
    candidate: Candidate


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """Ordered selection plus machine-readable warnings."""

    items: tuple[SelectedItem, ...]
    warnings: tuple[str, ...]


def select_daily(
    candidates: list[Candidate],
    *,
    as_of: datetime,
    day_start: datetime,
    day_end: datetime,
    review_count: int,
    new_count: int,
    requested_source_ids: tuple[object, ...] | list[object] | None = None,
) -> SelectionResult:
    """Pick review + new words for one daily sheet (see module docstring)."""
    _require_aware(as_of, "as_of")
    _require_aware(day_start, "day_start")
    _require_aware(day_end, "day_end")
    if day_start >= day_end:
        raise ValueError("day_start must be earlier than day_end")
    _require_count("review_count", review_count)
    _require_count("new_count", new_count)
    total = review_count + new_count
    if total < 1 or total > _MAX_BATCH_SIZE:
        raise ValueError(
            f"review_count + new_count must be between 1 and {_MAX_BATCH_SIZE}, got {total}"
        )

    # Source intersection first, then per-word dedup (first occurrence wins).
    requested = set(requested_source_ids) if requested_source_ids else None
    kept: list[Candidate] = []
    seen: set[object] = set()
    for cand in candidates:
        if cand.user_word_id in seen:
            continue
        if requested is not None and not (requested & set(cand.source_ids)):
            continue
        seen.add(cand.user_word_id)
        kept.append(cand)

    for cand in kept:
        _validate_candidate(cand)

    new_sorted = sorted((c for c in kept if c.is_new), key=_new_sort_key)
    review_sorted = _ordered_review(kept, as_of, day_start, day_end)

    # Quotas: review first up to R, new up to N; a new-pool shortfall widens
    # the review budget (fills the total); review shortage never raises new.
    new_taken = min(new_count, len(new_sorted))
    review_budget = review_count + (new_count - new_taken)
    review_taken = min(review_budget, len(review_sorted))

    items = [
        SelectedItem(item_type="review", reason=reason, sort_order=i, candidate=cand)
        for i, (reason, cand) in enumerate(
            ((r, c) for _, r, c in review_sorted[:review_taken]), start=1
        )
    ]
    base = len(items)
    items.extend(
        SelectedItem(item_type="new", reason="new", sort_order=base + i, candidate=cand)
        for i, cand in enumerate(new_sorted[:new_taken], start=1)
    )

    if not items:
        warnings = ("no_candidates",)
    elif len(items) < total:
        warnings = ("candidate_pool_too_small",)
    else:
        warnings = ()
    return SelectionResult(items=tuple(items), warnings=warnings)


# --- review classification ----------------------------------------------------


def _ordered_review(
    kept: list[Candidate], as_of: datetime, day_start: datetime, day_end: datetime
) -> list[tuple[tuple, str, Candidate]]:
    """Bucket + sort review-eligible candidates by priority; returns
    (sort_key, reason, candidate) triples in final order."""
    classified: list[tuple[tuple, str, Candidate]] = []
    for cand in kept:
        if cand.is_new:
            continue
        bucket = _classify_review(cand, as_of, day_start, day_end)
        if bucket is not None:
            key, reason = bucket
            classified.append((key, reason, cand))
    classified.sort(key=lambda item: item[0])
    return classified


def _classify_review(
    cand: Candidate, as_of: datetime, day_start: datetime, day_end: datetime
) -> tuple[tuple, str] | None:
    """Highest applicable review bucket for one word, or None (no bucket)."""
    due = cand.due_at
    if due < day_start:
        # overdue: relearning state first, due asc, lapse desc, lemma, id.
        rank = 0 if cand.state == "relearning" else 1
        return (
            (0, rank, due, -cand.lapse_count, cand.normalized_lemma, cand.user_word_id),
            "overdue",
        )
    if cand.state == "relearning":
        return (
            (
                1,
                -cand.again_count_7d,
                _dt_desc_key(cand.last_again_at),
                due,
                cand.normalized_lemma,
                cand.user_word_id,
            ),
            "relearning",
        )
    if _recent(cand.last_again_at, as_of, RECENT_AGAIN_WINDOW):
        return (
            (
                1,
                -cand.again_count_7d,
                _dt_desc_key(cand.last_again_at),
                due,
                cand.normalized_lemma,
                cand.user_word_id,
            ),
            "recent_again",
        )
    if day_start <= due < day_end:
        # due_today: due asc, difficulty desc, lemma, id.
        return (
            (2, due, -cand.difficulty, cand.normalized_lemma, cand.user_word_id),
            "due_today",
        )
    if _recent(cand.last_hard_at, as_of, RECENT_HARD_WINDOW):
        # recent_hard: last_hard desc, due asc, lemma, id.
        return (
            (
                3,
                _dt_desc_key(cand.last_hard_at),
                due,
                cand.normalized_lemma,
                cand.user_word_id,
            ),
            "recent_hard",
        )
    return None  # ordinary future card: never enters the pool


# --- new ordering --------------------------------------------------------------


def _new_sort_key(cand: Candidate) -> tuple:
    return (
        _asc_optional_key(cand.activated_at),
        _asc_optional_key(cand.first_seen_at),
        cand.normalized_lemma,
        cand.user_word_id,
    )


# --- helpers -------------------------------------------------------------------


def _recent(value: datetime | None, as_of: datetime, window: timedelta) -> bool:
    """Trailing-window test, lower edge inclusive; future values never count."""
    if value is None:
        return False
    return as_of - window <= value <= as_of


def _asc_optional_key(value: datetime | None) -> tuple[bool, datetime]:
    """Ascending key that sorts present values first and ``None`` last."""
    return (value is None, value if value is not None else _EPOCH)


def _dt_desc_key(value: datetime | None) -> tuple[int, int]:
    """Descending key: most recent datetime first, ``None`` last."""
    if value is None:
        return (1, 0)
    return (0, -_utc_micros(value))


def _utc_micros(value: datetime) -> int:
    """Whole microseconds since the Unix epoch (exact integer, no floats)."""
    diff = value - _EPOCH
    return (diff.days * 86400 + diff.seconds) * 1_000_000 + diff.microseconds


def _validate_candidate(cand: Candidate) -> None:
    _require_aware(cand.due_at, f"candidate {cand.user_word_id!r} due_at")
    for name in ("last_again_at", "last_hard_at", "activated_at", "first_seen_at"):
        value = getattr(cand, name)
        if value is not None:
            _require_aware(value, f"candidate {cand.user_word_id!r} {name}")


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware; naive datetimes are rejected")


def _require_count(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer, got {value!r}")
