"""Tests for the pure ``lexiora-srs-v1`` scheduler (``app.services.memory``).

No database, no network: only the deterministic scheduling core is exercised.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.memory import (
    CARD_STATES,
    RATINGS,
    SCHEDULER_VERSION,
    CardSnapshot,
    ScheduleResult,
    schedule,
)

UTC = timezone.utc
BASE = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)


def at(days=0, hours=0, minutes=0, seconds=0, microseconds=0) -> datetime:
    """Whole-minute UTC anchor by default; fine-grained offsets for ceil tests."""
    return BASE + timedelta(
        days=days, hours=hours, minutes=minutes, seconds=seconds, microseconds=microseconds
    )


def card(
    state="new",
    difficulty="5.00",
    stability="0",
    last_review_at=None,
    lapse=0,
    count=0,
) -> CardSnapshot:
    return CardSnapshot(
        state=state,
        difficulty=Decimal(difficulty),
        stability_days=Decimal(stability),
        due_at=at(days=-30),
        last_review_at=last_review_at,
        lapse_count=lapse,
        review_count=count,
    )


# --- new ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rating", "state_after", "difficulty", "stability", "due_delta"),
    [
        ("again", "learning", "6.00", "0.2500", timedelta(minutes=10)),
        ("hard", "learning", "5.25", "1.0000", timedelta(days=1)),
        ("good", "review", "4.85", "3.0000", timedelta(days=3)),
        ("easy", "review", "4.40", "7.0000", timedelta(days=7)),
    ],
)
def test_new_card_transitions(rating, state_after, difficulty, stability, due_delta):
    result = schedule(card(), rating, at())
    after = result.after
    assert after.state == state_after
    assert after.difficulty == Decimal(difficulty)
    assert after.stability_days == Decimal(stability)
    assert after.due_at == at() + due_delta
    assert after.last_review_at == at()
    assert after.review_count == 1
    assert after.lapse_count == 0
    assert result.rating == rating
    assert result.scheduler_version == SCHEDULER_VERSION
    assert result.elapsed_days == Decimal("0.0000")  # no previous review anchor
    assert result.reviewed_at == at()


def test_new_card_short_interval_logged_in_days():
    result = schedule(card(), "again", at())
    assert result.scheduled_days == Decimal("0.0069")  # 10 min / 1440, 4 dp
    assert schedule(card(), "hard", at()).scheduled_days == Decimal("1.0000")


# --- learning -----------------------------------------------------------------


def learning_card(stability="2.0000", difficulty="6.00", lapse=1, count=3):
    return card(
        state="learning",
        difficulty=difficulty,
        stability=stability,
        last_review_at=at(days=-2, hours=-6),
        lapse=lapse,
        count=count,
    )


@pytest.mark.parametrize(
    ("rating", "state_after", "stability", "due_delta"),
    [
        ("again", "learning", "1.4000", timedelta(minutes=10)),  # max(.25, .7*2)
        ("hard", "learning", "2.0000", timedelta(days=1)),  # max(1, 2)
        ("good", "review", "3.6000", timedelta(days=3, hours=14, minutes=24)),  # max(3, 3.6)
        ("easy", "review", "7.0000", timedelta(days=7)),  # max(7, 4.4)
    ],
)
def test_learning_transitions(rating, state_after, stability, due_delta):
    before = learning_card()
    result = schedule(before, rating, at())
    after = result.after
    assert after.state == state_after
    assert after.stability_days == Decimal(stability)
    assert after.due_at == at() + due_delta
    assert after.last_review_at == at()
    assert after.review_count == before.review_count + 1
    assert after.lapse_count == before.lapse_count  # lapse only on review+again
    if rating in ("good", "easy"):
        assert result.scheduled_days == after.stability_days
    assert result.elapsed_days == Decimal("2.2500")  # 2d 6h anchor


def test_learning_stability_floors():
    small = learning_card(stability="0.1000")
    assert schedule(small, "again", at()).after.stability_days == Decimal("0.2500")  # .7*.1 < .25
    assert schedule(small, "hard", at()).after.stability_days == Decimal("1.0000")
    assert schedule(small, "good", at()).after.stability_days == Decimal("3.0000")
    assert schedule(small, "easy", at()).after.stability_days == Decimal("7.0000")


def test_review_count_increments_from_arbitrary_base():
    before = learning_card(count=41)
    assert schedule(before, "again", at()).after.review_count == 42


# --- review -------------------------------------------------------------------


def review_card(stability="10.0000", difficulty="5.00", lapse=2, count=10, last=at(days=-7)):
    return card(
        state="review",
        difficulty=difficulty,
        stability=stability,
        last_review_at=last,
        lapse=lapse,
        count=count,
    )


def test_review_again_moves_to_relearning_and_lapses():
    before = review_card()
    result = schedule(before, "again", at())
    after = result.after
    assert after.state == "relearning"
    assert after.stability_days == Decimal("3.5000")  # max(.25, .35*10)
    assert after.difficulty == Decimal("6.00")
    assert after.due_at == at() + timedelta(minutes=10)
    assert after.lapse_count == before.lapse_count + 1
    assert after.review_count == before.review_count + 1
    assert result.elapsed_days == Decimal("7.0000")


def test_review_hard_uses_elapsed_anchor_and_factor():
    # elapsed 7d, S=10 -> r = .7; D 5 -> 5.25
    # factor = 1.15 + .03*4.75 + .05*(-.3) = 1.2775 -> S = 12.775
    before = review_card()
    result = schedule(before, "hard", at())
    after = result.after
    assert after.state == "review"
    assert after.stability_days == Decimal("12.7750")
    assert after.difficulty == Decimal("5.25")
    assert after.due_at == at(days=12, hours=18, minutes=36)  # +12.775 d, whole minutes
    assert after.lapse_count == before.lapse_count
    assert result.elapsed_days == Decimal("7.0000")
    assert result.scheduled_days == Decimal("12.7750")


def test_review_r_clamps_low_when_recalled_early():
    # elapsed 1d vs S=200 -> r = .005 -> clamped to .5; factor = 1.7+.08*5.15+.15*(-.5) = 2.037
    before = review_card(stability="200.0000", last=at(days=-1))
    result = schedule(before, "good", at())
    after = result.after
    assert after.state == "review"
    assert after.stability_days == Decimal("407.4000")  # 200 * 2.037
    assert after.due_at == at(days=407, hours=9, minutes=36)  # +407.4 d
    assert result.elapsed_days == Decimal("1.0000")


def test_review_r_clamps_high_when_overdue():
    # elapsed 30d vs S=10 -> r = 3 -> clamped to 2
    # factor = 1.7 + .08*5.15 + .15*1 = 2.262 -> S = 22.62
    before = review_card(stability="10.0000", last=at(days=-30))
    result = schedule(before, "good", at())
    assert result.after.stability_days == Decimal("22.6200")
    assert result.after.due_at == at(days=22, hours=14, minutes=53)  # +22.62 d, ceiled
    assert result.elapsed_days == Decimal("30.0000")


def test_review_easy_factor_upper_clamp():
    # D 1 -> easy delta -.6 clamps D' to 1; r=2 -> raw 2.5+.12*9+.25 = 3.83 -> clamp 3.8
    before = review_card(difficulty="1.00", last=at(days=-30))
    result = schedule(before, "easy", at())
    after = result.after
    assert after.difficulty == Decimal("1.00")
    assert after.stability_days == Decimal("38.0000")  # 10 * 3.8
    assert after.due_at == at(days=38)


def test_review_difficulty_clamp_keeps_max_when_hard():
    # D 10 -> hard delta clamps to 10; r=2 (elapsed 100d) -> factor 1.15+.05 = 1.2
    before = review_card(difficulty="10.00", last=at(days=-100))
    after = schedule(before, "hard", at()).after
    assert after.difficulty == Decimal("10.00")
    assert after.stability_days == Decimal("12.0000")


def test_review_without_previous_anchor_uses_zero_elapsed():
    # no last_review_at -> elapsed 0 -> r clamped to .5
    before = review_card(last=None)
    after = schedule(before, "hard", at()).after
    assert schedule(before, "hard", at()).elapsed_days == Decimal("0.0000")
    assert after.stability_days == Decimal("12.6750")  # 10 * (1.15+.1425-.025)


def test_review_negative_elapsed_clamped_to_zero():
    # clock skew: last_review_at in the future -> elapsed 0 -> r = .5
    before = review_card(last=at(days=5))
    result = schedule(before, "good", at())
    assert result.elapsed_days == Decimal("0.0000")
    assert result.after.stability_days == Decimal("20.3700")
    assert result.after.due_at == at(days=20, hours=8, minutes=53)  # +20.37 d ceils to 8h53m


def test_stability_quantized_to_4dp_round_half_up():
    # S=.1234; elapsed .25d -> r=1 -> factor 1.15 -> S' = .14191 -> 0.1419 (5th digit 1: down)
    before = review_card(stability="0.1234", difficulty="10.00", last=at(hours=-6))
    result = schedule(before, "hard", at())
    assert result.after.stability_days == Decimal("0.1419")
    assert result.after.due_at == at(hours=3, minutes=25)  # +.1419 d, ceiled minute
    # elapsed .5d -> r=2 -> factor 1.2 -> S' = .14808 -> 0.1481 (5th digit 8: up)
    before = review_card(stability="0.1234", difficulty="10.00", last=at(hours=-12))
    result = schedule(before, "hard", at())
    assert result.after.stability_days == Decimal("0.1481")
    assert result.after.due_at == at(hours=3, minutes=34)  # +.1481 d, ceiled minute


# --- relearning ---------------------------------------------------------------


def relearning_card(stability="10.0000", difficulty="4.00", lapse=3, count=5):
    return card(
        state="relearning",
        difficulty=difficulty,
        stability=stability,
        last_review_at=at(days=-2),
        lapse=lapse,
        count=count,
    )


@pytest.mark.parametrize(
    ("rating", "state_after", "stability", "due_delta"),
    [
        ("again", "relearning", "7.0000", timedelta(minutes=10)),  # max(.25, .7*10)
        ("hard", "relearning", "9.0000", timedelta(days=1)),  # max(.75, .9*10)
        ("good", "review", "13.0000", timedelta(days=13)),  # max(2, 1.3*10)
        ("easy", "review", "17.0000", timedelta(days=17)),  # max(4, 1.7*10)
    ],
)
def test_relearning_transitions(rating, state_after, stability, due_delta):
    before = relearning_card()
    result = schedule(before, rating, at())
    after = result.after
    assert after.state == state_after
    assert after.stability_days == Decimal(stability)
    assert after.due_at == at() + due_delta
    assert after.last_review_at == at()
    assert after.review_count == before.review_count + 1
    assert after.lapse_count == before.lapse_count  # relearning+again never lapses
    assert result.after.difficulty == {
        "again": Decimal("5.00"),
        "hard": Decimal("4.25"),
        "good": Decimal("3.85"),
        "easy": Decimal("3.40"),
    }[rating]


def test_relearning_again_does_not_increment_lapse():
    before = relearning_card(lapse=3)
    after = schedule(before, "again", at()).after
    assert after.state == "relearning"
    assert after.lapse_count == 3


def test_relearning_stability_floors():
    small = relearning_card(stability="0.1000", difficulty="4.00")
    assert schedule(small, "again", at()).after.stability_days == Decimal("0.2500")
    assert schedule(small, "hard", at()).after.stability_days == Decimal("0.7500")
    assert schedule(small, "good", at()).after.stability_days == Decimal("2.0000")
    assert schedule(small, "easy", at()).after.stability_days == Decimal("4.0000")


# --- difficulty clamps --------------------------------------------------------


def test_difficulty_upper_clamp():
    high = card(difficulty="9.50")
    assert schedule(high, "again", at()).after.difficulty == Decimal("10.00")
    assert schedule(card(difficulty="10.00"), "hard", at()).after.difficulty == Decimal("10.00")


def test_difficulty_lower_clamp():
    low = card(difficulty="1.20")
    assert schedule(low, "easy", at()).after.difficulty == Decimal("1.00")
    assert schedule(card(difficulty="1.00"), "good", at()).after.difficulty == Decimal("1.00")


def test_difficulty_delta_precision():
    # 5.37 + .25 = 5.62 quantized to 2 dp with no drift
    assert schedule(card(difficulty="5.37"), "hard", at()).after.difficulty == Decimal("5.62")
    assert schedule(card(difficulty="5.00"), "good", at()).after.difficulty == Decimal("4.85")


# --- due-time rounding --------------------------------------------------------


def test_due_ceil_to_whole_minute():
    reviewed = at(seconds=37, microseconds=123456)
    result = schedule(card(), "again", reviewed)
    assert result.after.due_at == at(minutes=11)  # 12:00:37.123 +10m -> 12:11:00
    assert result.after.due_at.second == 0
    assert result.after.due_at.microsecond == 0

    result = schedule(card(), "good", reviewed)
    assert result.after.due_at == at(days=3, minutes=1)  # +3d from 12:00:37 -> next minute


def test_due_timezone_preserved():
    result = schedule(card(), "again", at())
    assert result.after.due_at.tzinfo is UTC
    assert result.after.due_at.utcoffset() == timedelta(0)


# --- determinism / immutability ------------------------------------------------


def test_deterministic_same_input_same_result():
    before = review_card()
    first = schedule(before, "good", at())
    second = schedule(before, "good", at())
    assert first == second
    assert first.after == second.after
    assert first.scheduled_days == second.scheduled_days
    assert first.elapsed_days == second.elapsed_days


def test_input_snapshot_never_mutated():
    before = review_card()
    snapshot = (
        before.state,
        before.difficulty,
        before.stability_days,
        before.due_at,
        before.last_review_at,
        before.lapse_count,
        before.review_count,
    )
    result = schedule(before, "again", at())
    assert result.before is before
    assert result.after is not before
    assert (
        before.state,
        before.difficulty,
        before.stability_days,
        before.due_at,
        before.last_review_at,
        before.lapse_count,
        before.review_count,
    ) == snapshot


def test_result_holds_complete_before_and_after_values():
    before = review_card()
    result = schedule(before, "again", at())
    assert isinstance(result, ScheduleResult)
    assert isinstance(result.before, CardSnapshot)
    assert isinstance(result.after, CardSnapshot)
    assert result.before == before
    for field in (
        "state",
        "difficulty",
        "stability_days",
        "due_at",
        "last_review_at",
        "lapse_count",
        "review_count",
    ):
        assert getattr(result.before, field) == getattr(before, field)


# --- full state x rating matrix invariants ------------------------------------


@pytest.mark.parametrize("state", CARD_STATES)
@pytest.mark.parametrize("rating", RATINGS)
def test_every_state_rating_produces_valid_schedule(state, rating):
    bases = {
        "new": card(),
        "learning": learning_card(),
        "review": review_card(),
        "relearning": relearning_card(),
    }
    before = bases[state]
    reviewed = at()
    result = schedule(before, rating, reviewed)
    after = result.after

    assert after.state in CARD_STATES
    assert Decimal("1") <= after.difficulty <= Decimal("10")
    assert after.difficulty.as_tuple().exponent >= -2
    assert after.stability_days >= 0
    assert after.stability_days.as_tuple().exponent >= -4
    assert after.review_count == before.review_count + 1
    assert after.last_review_at == reviewed
    assert after.lapse_count == before.lapse_count + (
        1 if state == "review" and rating == "again" else 0
    )
    assert after.due_at > reviewed
    assert after.due_at.second == 0 and after.due_at.microsecond == 0
    assert after.due_at.tzinfo is not None
    assert result.before == before
    assert result.rating == rating
    assert result.reviewed_at == reviewed
    assert result.scheduler_version == SCHEDULER_VERSION
    assert result.after.difficulty == result.before.difficulty + {
        "again": Decimal("1"),
        "hard": Decimal("0.25"),
        "good": Decimal("-0.15"),
        "easy": Decimal("-0.6"),
    }[rating]  # exact math inside the clamp bounds used here


# --- validation ---------------------------------------------------------------


def test_rejects_invalid_state():
    with pytest.raises(ValueError):
        schedule(card(state="mastered"), "good", at())
    with pytest.raises(ValueError):
        schedule(card(state="NEW"), "good", at())
    with pytest.raises(ValueError):
        schedule(card(state=""), "good", at())


def test_rejects_invalid_rating():
    with pytest.raises(ValueError):
        schedule(card(), "medium", at())
    with pytest.raises(ValueError):
        schedule(card(), "", at())
    with pytest.raises(ValueError):
        schedule(card(), "Good", at())  # case-sensitive


def test_rejects_naive_reviewed_at():
    with pytest.raises(ValueError):
        schedule(card(), "good", datetime(2026, 1, 5, 12, 0))


def test_rejects_naive_due_at():
    with pytest.raises(ValueError):
        schedule(
            CardSnapshot(
                state="new",
                difficulty=Decimal("5.00"),
                stability_days=Decimal("0"),
                due_at=datetime(2026, 1, 5, 12, 0),
            ),
            "good",
            at(),
        )


def test_rejects_naive_last_review_at():
    with pytest.raises(ValueError):
        schedule(
            CardSnapshot(
                state="review",
                difficulty=Decimal("5.00"),
                stability_days=Decimal("10.0000"),
                due_at=at(),
                last_review_at=datetime(2026, 1, 1, 12, 0),
            ),
            "hard",
            at(),
        )
