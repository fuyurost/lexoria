"""Tests for the pure daily candidate selector (``app.services.daily_selector``).

No database, no network: deterministic selection logic only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.daily_selector import (
    RECENT_AGAIN_WINDOW,
    RECENT_HARD_WINDOW,
    Candidate,
    SelectedItem,
    SelectionResult,
    select_daily,
)

UTC = timezone.utc
AS_OF = datetime(2026, 1, 5, 12, 0, 0, tzinfo=UTC)
DAY_START = datetime(2026, 1, 5, 0, 0, 0, tzinfo=UTC)
DAY_END = datetime(2026, 1, 6, 0, 0, 0, tzinfo=UTC)


def ts(year=2026, month=1, day=1, hour=0, minute=0, second=0, microsecond=0) -> datetime:
    return datetime(year, month, day, hour, minute, second, microsecond, tzinfo=UTC)


def cand(
    uid,
    *,
    lemma="word",
    state="review",
    due=None,
    lapse=0,
    last_again=None,
    again7=0,
    last_hard=None,
    activated=None,
    first_seen=None,
    is_new=False,
    sources=(),
    difficulty="5.00",
) -> Candidate:
    return Candidate(
        user_word_id=uid,
        normalized_lemma=lemma,
        state=state,
        due_at=due if due is not None else ts(day=5, hour=10),
        difficulty=Decimal(difficulty),
        lapse_count=lapse,
        last_again_at=last_again,
        again_count_7d=again7,
        last_hard_at=last_hard,
        activated_at=activated,
        first_seen_at=first_seen,
        is_new=is_new,
        source_ids=tuple(sources),
    )


def pick(cands, review=1, new=0, sources=None):
    return select_daily(
        list(cands),
        as_of=AS_OF,
        day_start=DAY_START,
        day_end=DAY_END,
        review_count=review,
        new_count=new,
        requested_source_ids=sources,
    )


def ids(result: SelectionResult) -> list[str]:
    return [item.candidate.user_word_id for item in result.items]


def reasons(result: SelectionResult) -> list[str]:
    return [item.reason for item in result.items]


# --- review bucket priority ---------------------------------------------------


def test_review_bucket_priority_and_ordering():
    candidates = [
        cand("rl-over", state="relearning", due=ts(day=4, hour=20)),  # overdue + relearning
        cand("over", due=ts(day=4, hour=22), lapse=7),  # overdue
        cand("rl", state="relearning", due=ts(day=5, hour=9)),  # relearning band
        cand("recent", due=ts(day=5, hour=10), last_again=ts(day=4, hour=12), again7=2),
        cand("due", due=ts(day=5, hour=6)),  # due today
        cand("hard", due=ts(day=6, hour=2), last_hard=ts(day=3)),  # recent hard, future due
        cand("fut", due=ts(day=9)),  # ordinary future: never in pool
    ]
    result = pick(candidates, review=6)
    assert ids(result) == ["rl-over", "over", "recent", "rl", "due", "hard"]
    assert reasons(result) == [
        "overdue", "overdue", "recent_again", "relearning", "due_today", "recent_hard",
    ]
    assert [i.item_type for i in result.items] == ["review"] * 6
    assert [i.sort_order for i in result.items] == list(range(1, 7))
    assert result.warnings == ()


def test_overdue_bucket_sorts_relearning_first_then_due_then_lapse_desc():
    candidates = [
        cand("x", due=ts(day=4, hour=10), lapse=2),
        cand("z", due=ts(day=4, hour=10), lapse=5),
        cand("rl", state="relearning", due=ts(day=4, hour=12), lapse=1),
        cand("y", due=ts(day=4, hour=10), lapse=2),
    ]
    result = pick(candidates, review=4)
    assert ids(result) == ["rl", "z", "x", "y"]  # relearning first; then lapse desc; id tie
    assert reasons(result) == ["overdue"] * 4


def test_relearning_band_sorts_again_count_then_last_again_then_due():
    candidates = [
        cand("m", due=ts(day=5, hour=20), last_again=ts(day=5, hour=10), again7=2),
        cand("n", due=ts(day=5, hour=21), last_again=ts(day=5, hour=9), again7=3),
        cand("p", due=ts(day=5, hour=19), last_again=ts(day=5, hour=9), again7=3),
        cand("q", due=ts(day=5, hour=19), last_again=ts(day=5, hour=9), again7=3),
    ]
    result = pick(candidates, review=4)
    assert ids(result) == ["p", "q", "n", "m"]  # count desc, last_again desc, due asc, id
    assert reasons(result) == ["recent_again"] * 4


def test_due_today_sorts_by_due_then_id():
    result = pick(
        [
            cand("aa", due=ts(day=5, hour=8)),
            cand("bb", due=ts(day=5, hour=8)),
            cand("cc", due=ts(day=5, hour=7)),
        ],
        review=3,
    )
    assert ids(result) == ["cc", "aa", "bb"]
    assert reasons(result) == ["due_today"] * 3


def test_due_today_sorts_difficulty_desc_then_lemma_then_id():
    # same due time: difficulty desc first, then lemma asc, then id
    result = pick(
        [
            cand("a", due=ts(day=5, hour=8), difficulty="6.00", lemma="zeta"),
            cand("c", due=ts(day=5, hour=8), difficulty="6.00", lemma="beta"),
            cand("b", due=ts(day=5, hour=8), difficulty="4.00", lemma="alpha"),
            cand("d", due=ts(day=5, hour=7), difficulty="9.00", lemma="zzz"),
        ],
        review=4,
    )
    # d due earliest; then difficulty 6.00 (lemma beta < zeta) before difficulty 4.00
    assert ids(result) == ["d", "c", "a", "b"]
    assert reasons(result) == ["due_today"] * 4


def test_overdue_tiebreak_lemma_before_id():
    # identical due + lapse: normalized_lemma asc decides before user_word_id
    result = pick(
        [
            cand("x0", due=ts(day=4, hour=10), lapse=2, lemma="pear"),
            cand("x1", due=ts(day=4, hour=10), lapse=2, lemma="apple"),
        ],
        review=2,
    )
    assert ids(result) == ["x1", "x0"]  # apple < pear although x0 < x1


def test_recent_band_tiebreak_lemma_before_id():
    # identical count/last_again/due: normalized_lemma asc, then id
    result = pick(
        [
            cand("zz", due=ts(day=5, hour=19), last_again=ts(day=5, hour=9), again7=1,
                 lemma="zebra"),
            cand("aa", due=ts(day=5, hour=19), last_again=ts(day=5, hour=9), again7=1,
                 lemma="apple"),
        ],
        review=2,
    )
    assert ids(result) == ["aa", "zz"]
    assert reasons(result) == ["recent_again", "recent_again"]


def test_recent_hard_tiebreak_lemma_before_id():
    # identical last_hard + due: normalized_lemma asc, then id
    result = pick(
        [
            cand("zz", due=ts(day=10), last_hard=ts(day=3), lemma="zebra"),
            cand("aa", due=ts(day=10), last_hard=ts(day=3), lemma="apple"),
        ],
        review=2,
    )
    assert ids(result) == ["aa", "zz"]
    assert reasons(result) == ["recent_hard", "recent_hard"]


def test_recent_hard_sorts_most_recent_hard_first():
    result = pick(
        [
            cand("old", due=ts(day=10), last_hard=ts(day=3, hour=10)),
            cand("newer", due=ts(day=10), last_hard=ts(day=4, hour=10)),
        ],
        review=2,
    )
    assert ids(result) == ["newer", "old"]
    assert reasons(result) == ["recent_hard", "recent_hard"]


# --- new pool ----------------------------------------------------------------


def test_new_words_sorted_by_activated_then_first_seen_then_lemma_then_id():
    jan2_10 = ts(day=2, hour=10)
    result = pick(
        [
            cand("x", is_new=True, activated=jan2_10, first_seen=ts(day=2, hour=9), lemma="apple"),
            cand("y", is_new=True, activated=jan2_10, first_seen=ts(day=2, hour=9), lemma="apple"),
            cand("w", is_new=True, activated=jan2_10, first_seen=ts(day=2, hour=8), lemma="zoo"),
            cand("z", is_new=True, activated=ts(day=3), first_seen=ts(day=3), lemma="aardvark"),
            cand("noa", is_new=True, activated=None, first_seen=None, lemma="anon"),
        ],
        review=0,
        new=5,
    )
    assert ids(result) == ["w", "x", "y", "z", "noa"]
    assert reasons(result) == ["new"] * 5
    assert [i.item_type for i in result.items] == ["new"] * 5


def test_review_items_come_before_new_items():
    result = pick(
        [
            cand("n1", is_new=True, activated=ts(day=1)),
            cand("n2", is_new=True, activated=ts(day=2)),
            cand("r1", due=ts(day=5, hour=8)),
        ],
        review=1,
        new=2,
    )
    assert ids(result) == ["r1", "n1", "n2"]
    assert [i.item_type for i in result.items] == ["review", "new", "new"]
    assert reasons(result) == ["due_today", "new", "new"]
    assert [i.sort_order for i in result.items] == [1, 2, 3]


def test_no_new_selected_when_new_count_zero():
    result = pick([cand("n1", is_new=True), cand("r1", due=ts(day=5, hour=8))], review=1, new=0)
    assert ids(result) == ["r1"]
    assert [i.item_type for i in result.items] == ["review"]


# --- quotas: fill rules ------------------------------------------------------


def test_new_shortage_fills_total_from_remaining_review():
    review_pool = [cand(f"r{i}", due=ts(day=5, hour=i)) for i in range(1, 11)]
    new_pool = [cand("n1", is_new=True), cand("n2", is_new=True)]
    result = pick(review_pool + new_pool, review=3, new=5)
    # review budget = 3 + (5 - 2) = 6 -> earliest 6 reviews + both new = 8 == total
    assert ids(result) == [f"r{i}" for i in range(1, 7)] + ["n1", "n2"]
    assert [i.item_type for i in result.items] == ["review"] * 6 + ["new"] * 2
    assert result.warnings == ()


def test_no_filler_when_new_pool_meets_quota():
    review_pool = [cand(f"r{i}", due=ts(day=5, hour=i)) for i in range(1, 11)]
    new_pool = [cand(f"n{i}", is_new=True, activated=ts(day=1, hour=i)) for i in range(1, 6)]
    result = pick(review_pool + new_pool, review=3, new=5)
    assert ids(result) == ["r1", "r2", "r3", "n1", "n2", "n3", "n4", "n5"]
    assert [i.item_type for i in result.items] == ["review"] * 3 + ["new"] * 5


def test_review_shortage_never_exceeds_new_quota():
    review_pool = [cand(f"r{i}", due=ts(day=5, hour=i)) for i in range(1, 5)]
    new_pool = [cand(f"n{i}", is_new=True, activated=ts(day=1, hour=i)) for i in range(1, 21)]
    result = pick(review_pool + new_pool, review=10, new=5)
    assert ids(result) == [f"r{i}" for i in range(1, 5)] + [f"n{i}" for i in range(1, 6)]
    assert [i.item_type for i in result.items] == ["review"] * 4 + ["new"] * 5
    assert result.warnings == ("candidate_pool_too_small",)  # 9 < 15


# --- dedup + source filter ----------------------------------------------------


def test_duplicate_word_kept_once_first_occurrence():
    result = pick(
        [cand("w1", due=ts(day=5, hour=7)), cand("w1", due=ts(day=5, hour=9))],
        review=2,
    )
    assert len(result.items) == 1
    assert result.items[0].candidate.user_word_id == "w1"
    assert result.items[0].candidate.due_at == ts(day=5, hour=7)


def test_source_intersection_filters_review_and_new():
    candidates = [
        cand("w1", sources=("A", "B"), due=ts(day=5, hour=8)),
        cand("w2", sources=("C",), due=ts(day=5, hour=9)),
        cand("n1", is_new=True, sources=(), activated=ts(day=1)),
        cand("n2", is_new=True, sources=("A",), activated=ts(day=2)),
    ]
    result = pick(candidates, review=5, new=5, sources=["A"])
    assert ids(result) == ["w1", "n2"]  # only candidates sharing source A
    assert result.warnings == ("candidate_pool_too_small",)

    result = pick(candidates, review=5, new=5, sources=None)
    assert ids(result) == ["w1", "w2", "n1", "n2"]

    result = pick(candidates, review=5, new=5, sources=[])
    assert ids(result) == ["w1", "w2", "n1", "n2"]  # empty request = no filter


def test_source_filter_applies_before_dedup():
    # first occurrence fails the source check, the duplicate passes -> word kept
    result = pick(
        [cand("w9", sources=("B",), due=ts(day=5, hour=6)),
         cand("w9", sources=("A",), due=ts(day=5, hour=7))],
        review=1,
        sources=["A"],
    )
    assert ids(result) == ["w9"]
    assert result.items[0].candidate.due_at == ts(day=5, hour=7)


# --- warnings ----------------------------------------------------------------


def test_no_candidates_warning_when_input_empty():
    result = pick([], review=2, new=3)
    assert result.items == ()
    assert result.warnings == ("no_candidates",)


def test_no_candidates_warning_when_all_future_ordinary():
    result = pick([cand("f1", due=ts(day=9)), cand("f2", due=ts(day=10))], review=1, new=1)
    assert result.items == ()
    assert result.warnings == ("no_candidates",)


def test_pool_too_small_warning_when_partial_selection():
    result = pick([cand("r1", due=ts(day=5, hour=8))], review=10, new=0)
    assert len(result.items) == 1
    assert result.warnings == ("candidate_pool_too_small",)


def test_future_ordinary_never_fills_the_pool():
    # Even with an empty review need, future ordinary cards are not candidates.
    result = pick([cand("f1", due=ts(day=9))], review=1, new=0)
    assert result.items == ()
    assert result.warnings == ("no_candidates",)


# --- determinism --------------------------------------------------------------


def test_same_input_is_deterministic():
    candidates = [
        cand("a", due=ts(day=4, hour=22), lapse=3),
        cand("b", state="relearning", due=ts(day=5, hour=9)),
        cand("c", due=ts(day=5, hour=8), last_again=ts(day=5, hour=2), again7=1),
        cand("n1", is_new=True, activated=ts(day=1)),
    ]
    first = pick(candidates, review=3, new=1)
    second = pick(candidates, review=3, new=1)
    assert first == second
    assert ids(first) == ids(second)
    assert first.items == second.items
    assert first.warnings == second.warnings


# --- 72h / 7d window boundaries ------------------------------------------------


def test_recent_again_72h_boundary_inclusive():
    exactly = cand("a", due=ts(day=6, hour=10), last_again=AS_OF - RECENT_AGAIN_WINDOW, again7=1)
    result = pick([exactly], review=1)
    assert reasons(result) == ["recent_again"]

    just_outside = cand(
        "b", due=ts(day=6, hour=10), last_again=AS_OF - RECENT_AGAIN_WINDOW - timedelta(microseconds=1)
    )
    assert pick([just_outside], review=1).items == ()
    assert pick([just_outside], review=1).warnings == ("no_candidates",)

    future = cand("c", due=ts(day=6, hour=10), last_again=AS_OF + timedelta(hours=1), again7=1)
    assert pick([future], review=1).items == ()


def test_recent_hard_7d_boundary_inclusive():
    exactly = cand("a", due=ts(day=10), last_hard=AS_OF - RECENT_HARD_WINDOW)
    result = pick([exactly], review=1)
    assert reasons(result) == ["recent_hard"]

    just_outside = cand(
        "b", due=ts(day=10), last_hard=AS_OF - RECENT_HARD_WINDOW - timedelta(microseconds=1)
    )
    assert pick([just_outside], review=1).items == ()

    future = cand("c", due=ts(day=10), last_hard=AS_OF + timedelta(hours=1))
    assert pick([future], review=1).items == ()


# --- day window boundaries ----------------------------------------------------


def test_day_window_boundaries():
    # due == day_start -> not overdue, is due today
    assert reasons(pick([cand("a", due=DAY_START)], review=1)) == ["due_today"]
    # due just before day_start -> overdue
    assert reasons(pick([cand("b", due=DAY_START - timedelta(microseconds=1))], review=1)) == [
        "overdue"
    ]
    # due == day_end -> future (excluded)
    assert pick([cand("c", due=DAY_END)], review=1).items == ()
    # due just before day_end -> due today
    assert reasons(pick([cand("d", due=DAY_END - timedelta(microseconds=1))], review=1)) == [
        "due_today"
    ]


def test_due_today_takes_precedence_over_recent_hard():
    # hard within 7d but due today -> higher bucket wins
    result = pick([cand("a", due=ts(day=5, hour=8), last_hard=ts(day=4))], review=1)
    assert reasons(result) == ["due_today"]
    # relearning state wins over due_today
    result = pick([cand("b", state="relearning", due=ts(day=5, hour=8))], review=1)
    assert reasons(result) == ["relearning"]
    # overdue wins over recent_again signal
    result = pick(
        [cand("c", due=ts(day=4, hour=8), last_again=ts(day=5, hour=0), again7=3)], review=1
    )
    assert reasons(result) == ["overdue"]


# --- validation ---------------------------------------------------------------


@pytest.mark.parametrize("attr", ["as_of", "day_start", "day_end"])
def test_rejects_naive_window_datetimes(attr):
    kwargs = {"as_of": AS_OF, "day_start": DAY_START, "day_end": DAY_END}
    kwargs[attr] = datetime(2026, 1, 5, 12, 0, 0)  # naive
    with pytest.raises(ValueError):
        select_daily(
            [cand("a", due=ts(day=5))],
            as_of=kwargs["as_of"],
            day_start=kwargs["day_start"],
            day_end=kwargs["day_end"],
            review_count=1,
            new_count=0,
        )


def test_rejects_inverted_day_window():
    with pytest.raises(ValueError):
        select_daily([], as_of=AS_OF, day_start=DAY_END, day_end=DAY_START, review_count=1, new_count=0)
    with pytest.raises(ValueError):
        select_daily([], as_of=AS_OF, day_start=DAY_START, day_end=DAY_START, review_count=1, new_count=0)


def test_rejects_negative_counts():
    with pytest.raises(ValueError):
        pick([cand("a")], review=-1, new=0)
    with pytest.raises(ValueError):
        pick([cand("a")], review=1, new=-2)


def test_rejects_total_out_of_1_100():
    with pytest.raises(ValueError):
        pick([cand("a")], review=0, new=0)
    with pytest.raises(ValueError):
        pick([cand("a")], review=60, new=60)
    with pytest.raises(ValueError):
        pick([cand("a")], review=100, new=1)


def test_total_bounds_edges_accepted():
    assert pick([cand("a", due=ts(day=5, hour=8))], review=1, new=0).items
    assert pick([cand("a", due=ts(day=5, hour=8))], review=100, new=0).items
    assert pick([cand("a", due=ts(day=5, hour=8))], review=0, new=1).items


def test_rejects_bool_count():
    with pytest.raises(ValueError):
        pick([cand("a")], review=True, new=0)


def test_rejects_naive_candidate_datetimes():
    naive = cand("a", due=ts(day=5, hour=8))
    with pytest.raises(ValueError):
        select_daily(
            [Candidate("a", "word", "review", datetime(2026, 1, 5, 8, 0))],
            as_of=AS_OF, day_start=DAY_START, day_end=DAY_END, review_count=1, new_count=0,
        )
    with pytest.raises(ValueError):
        select_daily(
            [Candidate("a", "word", "review", ts(day=5, hour=8),
                       last_again_at=datetime(2026, 1, 4, 8, 0))],
            as_of=AS_OF, day_start=DAY_START, day_end=DAY_END, review_count=1, new_count=0,
        )
    # is_new candidates are validated too (due_at is checked for every kept word)
    with pytest.raises(ValueError):
        select_daily(
            [Candidate("n", "word", "new", datetime(2026, 1, 5, 8, 0), is_new=True)],
            as_of=AS_OF, day_start=DAY_START, day_end=DAY_END, review_count=0, new_count=1,
        )


# --- output shape -------------------------------------------------------------


def test_selected_item_shape():
    item = cand("a", due=ts(day=4, hour=22), lapse=2)
    result = pick([item], review=1)
    (selected,) = result.items
    assert isinstance(selected, SelectedItem)
    assert selected.item_type == "review"
    assert selected.reason == "overdue"
    assert selected.sort_order == 1
    assert selected.candidate is item
    assert isinstance(result, SelectionResult)


def test_joint_shortage_respects_both_caps():
    # review pool (2) < R and new pool (1) < N: review intake stays capped at
    # pool size, new intake never exceeds N, total falls short -> warning.
    result = pick(
        [cand("r1", due=ts(day=5, hour=8)), cand("r2", due=ts(day=5, hour=9))],
        review=5,
        new=3,
    )
    # with no new candidates at all, review budget = 5 + 3 -> both reviews taken
    assert [i.item_type for i in result.items] == ["review", "review"]
    assert result.warnings == ("candidate_pool_too_small",)  # 2 < 8

    result = pick(
        [cand("r1", due=ts(day=5, hour=8)), cand("r2", due=ts(day=5, hour=9)),
         cand("n1", is_new=True), cand("n2", is_new=True), cand("n3", is_new=True),
         cand("n4", is_new=True), cand("n5", is_new=True)],
        review=5,
        new=3,
    )
    # review shortage does NOT pull in more than N new items (2 reviews + 3 new)
    assert [i.item_type for i in result.items] == ["review", "review", "new", "new", "new"]
    assert result.warnings == ("candidate_pool_too_small",)  # 5 < 8
