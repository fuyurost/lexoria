"""lexiora-srs-v1: deterministic spaced-repetition scheduling core.

Pure and immutable: no I/O, no database, no wall clock. ``schedule`` turns an
input :class:`CardSnapshot` + ``rating`` + ``reviewed_at`` into a complete
:class:`ScheduleResult` holding both the untouched input snapshot (``before``)
and the fully updated snapshot (``after``).

Determinism guarantees
----------------------
* Every quantity is :class:`decimal.Decimal` built from string/int literals —
  never ``float`` — so results are reproducible across runs and platforms.
* Difficulty is quantized to 2 decimal places (``Numeric(6, 2)``), stability
  and elapsed days to 4 (``Numeric(12, 4)``), always ``ROUND_HALF_UP``.
* Due times are the review event plus the scheduled interval, rounded up to
  the next whole minute.
* ``review_count`` always increases by one; ``lapse_count`` increases only
  when a card in state ``review`` is rated ``again``.

Validation: naive (tz-less) datetimes and unknown ``state``/``rating`` values
raise :class:`ValueError` before any computation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

SCHEDULER_VERSION = "lexiora-srs-v1"

CARD_STATES = ("new", "learning", "review", "relearning")
RATINGS = ("again", "hard", "good", "easy")

_DIFFICULTY_MIN = Decimal("1")
_DIFFICULTY_MAX = Decimal("10")
_DIFFICULTY_Q = Decimal("0.01")
_STABILITY_Q = Decimal("0.0001")
_ELAPSED_Q = Decimal("0.0001")
_ZERO = Decimal("0")

# Difficulty delta applied for every rating, clamped to [1, 10].
_DIFFICULTY_DELTA = {
    "again": Decimal("1"),
    "hard": Decimal("0.25"),
    "good": Decimal("-0.15"),
    "easy": Decimal("-0.6"),
}

# Retrievability window: r = clamp(.5, 2, elapsed / max(S, .25)).
_R_MIN = Decimal("0.5")
_R_MAX = Decimal("2")
_R_STABILITY_FLOOR = Decimal("0.25")

_MICROSECONDS_PER_DAY = Decimal(86400000000)
_MINUTES_PER_DAY = Decimal("1440")


@dataclass(frozen=True, slots=True)
class CardSnapshot:
    """Immutable scheduling state of one card at a point in time."""

    state: str
    difficulty: Decimal
    stability_days: Decimal
    due_at: datetime
    last_review_at: datetime | None = None
    lapse_count: int = 0
    review_count: int = 0


@dataclass(frozen=True, slots=True)
class ScheduleResult:
    """Complete before/after outcome of one review event.

    ``before`` is the input snapshot untouched; ``after`` is the new card
    state (``last_review_at`` set to ``reviewed_at``, ``review_count``
    incremented). ``elapsed_days``/``scheduled_days`` mirror the
    ``review_logs`` columns.
    """

    scheduler_version: str
    rating: str
    reviewed_at: datetime
    elapsed_days: Decimal
    scheduled_days: Decimal
    before: CardSnapshot
    after: CardSnapshot


def schedule(card: CardSnapshot, rating: str, reviewed_at: datetime) -> ScheduleResult:
    """Schedule ``card`` after ``rating`` given at ``reviewed_at`` (UTC).

    Raises ``ValueError`` for naive datetimes or unknown ``state``/``rating``.
    """
    if card.state not in CARD_STATES:
        raise ValueError(
            f"invalid state {card.state!r}; expected one of {', '.join(CARD_STATES)}"
        )
    if rating not in RATINGS:
        raise ValueError(f"invalid rating {rating!r}; expected one of {', '.join(RATINGS)}")
    _require_aware(card.due_at, "card.due_at")
    if card.last_review_at is not None:
        _require_aware(card.last_review_at, "card.last_review_at")
    _require_aware(reviewed_at, "reviewed_at")

    elapsed = _elapsed_days(reviewed_at, card.last_review_at)
    difficulty_after = _next_difficulty(card.difficulty, rating)
    state_after, stability_after, due_after, lapse_after, interval_days = _advance(
        card, rating, reviewed_at, elapsed, difficulty_after
    )

    after = CardSnapshot(
        state=state_after,
        difficulty=difficulty_after,
        stability_days=stability_after,
        due_at=due_after,
        last_review_at=reviewed_at,
        lapse_count=lapse_after,
        review_count=card.review_count + 1,
    )
    return ScheduleResult(
        scheduler_version=SCHEDULER_VERSION,
        rating=rating,
        reviewed_at=reviewed_at,
        elapsed_days=_quantize(elapsed, _ELAPSED_Q),
        scheduled_days=interval_days,
        before=card,
        after=after,
    )


def _advance(
    card: CardSnapshot,
    rating: str,
    reviewed_at: datetime,
    elapsed: Decimal,
    difficulty: Decimal,
) -> tuple[str, Decimal, datetime, int, Decimal]:
    """Apply the state machine; returns (state, stability, due, lapse, interval_days)."""
    stability = card.stability_days
    lapse = card.lapse_count

    # --- new / learning ----------------------------------------------------
    if card.state in ("new", "learning"):
        if rating == "again":
            stability = _quantize_stability(_max(Decimal("0.25"), Decimal("0.7") * stability))
            return "learning", stability, _due_after_minutes(reviewed_at, 10), lapse, _minutes_to_days(10)
        if rating == "hard":
            stability = _quantize_stability(_max(Decimal("1"), stability))
            return "learning", stability, _due_after_minutes(reviewed_at, 1440), lapse, _minutes_to_days(1440)
        if rating == "good":
            stability = _quantize_stability(_max(Decimal("3"), Decimal("1.8") * stability))
            return "review", stability, _due_after_days(reviewed_at, stability), lapse, stability
        stability = _quantize_stability(_max(Decimal("7"), Decimal("2.2") * stability))
        return "review", stability, _due_after_days(reviewed_at, stability), lapse, stability

    # --- review ------------------------------------------------------------
    if card.state == "review":
        if rating == "again":
            stability = _quantize_stability(_max(Decimal("0.25"), Decimal("0.35") * stability))
            return "relearning", stability, _due_after_minutes(reviewed_at, 10), lapse + 1, _minutes_to_days(10)

        # r = clamp(.5, 2, elapsed / max(S, .25))
        r = _clamp(_R_MIN, _R_MAX, elapsed / _max(stability, _R_STABILITY_FLOOR))
        factor = _interval_factor(rating, r, difficulty)
        stability = _quantize_stability(stability * factor)
        return "review", stability, _due_after_days(reviewed_at, stability), lapse, stability

    # --- relearning --------------------------------------------------------
    if rating == "again":
        stability = _quantize_stability(_max(Decimal("0.25"), Decimal("0.7") * stability))
        return "relearning", stability, _due_after_minutes(reviewed_at, 10), lapse, _minutes_to_days(10)
    if rating == "hard":
        stability = _quantize_stability(_max(Decimal("0.75"), Decimal("0.9") * stability))
        return "relearning", stability, _due_after_minutes(reviewed_at, 1440), lapse, _minutes_to_days(1440)
    if rating == "good":
        stability = _quantize_stability(_max(Decimal("2"), Decimal("1.3") * stability))
        return "review", stability, _due_after_days(reviewed_at, stability), lapse, stability
    stability = _quantize_stability(_max(Decimal("4"), Decimal("1.7") * stability))
    return "review", stability, _due_after_days(reviewed_at, stability), lapse, stability


def _interval_factor(rating: str, r: Decimal, difficulty: Decimal) -> Decimal:
    """Multiplicative interval factor for a successful ``review`` rating.

    factor = clamp(lo, hi, base + a*(10 - D') + b*(r - 1)) with per-rating
    coefficients; D' is the already-updated difficulty.
    """
    if rating == "hard":
        base, a, b, lo, hi = (
            Decimal("1.15"), Decimal("0.03"), Decimal("0.05"), Decimal("1.05"), Decimal("1.5"),
        )
    elif rating == "good":
        base, a, b, lo, hi = (
            Decimal("1.7"), Decimal("0.08"), Decimal("0.15"), Decimal("1.3"), Decimal("2.6"),
        )
    else:  # easy
        base, a, b, lo, hi = (
            Decimal("2.5"), Decimal("0.12"), Decimal("0.25"), Decimal("1.8"), Decimal("3.8"),
        )
    raw = base + a * (_DIFFICULTY_MAX - difficulty) + b * (r - Decimal("1"))
    return _clamp(lo, hi, raw)


def _next_difficulty(current: Decimal, rating: str) -> Decimal:
    """Difficulty after the rating delta, quantized to 2 dp and clamped to [1, 10]."""
    adjusted = _quantize(current + _DIFFICULTY_DELTA[rating], _DIFFICULTY_Q)
    return _clamp(_DIFFICULTY_MIN, _DIFFICULTY_MAX, adjusted)


def _elapsed_days(reviewed_at: datetime, last_review_at: datetime | None) -> Decimal:
    """Fractional days between the two reviews, floored at zero.

    Computed from exact integer microseconds (never float) so it is
    deterministic.
    """
    if last_review_at is None:
        return _ZERO
    span = reviewed_at - last_review_at
    if span <= timedelta(0):
        return _ZERO
    total_us = (span.days * 86400 + span.seconds) * 1_000_000 + span.microseconds
    return Decimal(total_us) / Decimal("86400000000")


def _due_after_minutes(reviewed_at: datetime, minutes: int) -> datetime:
    """reviewed_at + interval, rounded up to the next whole minute."""
    return _ceil_minute(reviewed_at + timedelta(minutes=minutes))


def _due_after_days(reviewed_at: datetime, days: Decimal) -> datetime:
    """reviewed_at + ``days`` (4 dp) as exact microseconds, then ceil to minute."""
    return _ceil_minute(reviewed_at + timedelta(microseconds=int(days * _MICROSECONDS_PER_DAY)))


def _quantize_stability(value: Decimal) -> Decimal:
    return _quantize(value, _STABILITY_Q)


def _quantize(value: Decimal, quantum: Decimal) -> Decimal:
    return value.quantize(quantum, rounding=ROUND_HALF_UP)


def _clamp(low: Decimal, high: Decimal, value: Decimal) -> Decimal:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _max(a: Decimal, b: Decimal) -> Decimal:
    return a if a >= b else b


def _minutes_to_days(minutes: int) -> Decimal:
    return _quantize(Decimal(minutes) / _MINUTES_PER_DAY, _ELAPSED_Q)


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware; naive datetimes are rejected")


def _ceil_minute(value: datetime) -> datetime:
    if value.second == 0 and value.microsecond == 0:
        return value
    return value.replace(second=0, microsecond=0) + timedelta(minutes=1)
