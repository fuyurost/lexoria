"""Capture pipeline: Word/UserWord upserts + Encounter recording.

Concurrency model (Postgres):
- Word rows are created idempotently with INSERT ... ON CONFLICT DO UPDATE on
  the (language, normalized_lemma) unique index — two concurrent captures of
  the same term converge on one row.
- UserWord rows use INSERT ... ON CONFLICT DO NOTHING on (user_id, word_id).
- Encounter dedupe: the client_event lookup happens first; a true race on the
  (user_id, client_event_id) unique constraint rolls back the whole capture
  and returns the pre-existing event (no double counting).

Counting: a freshly created UserWord is inserted with encounter_count=1 and is
NOT incremented by its first encounter; every subsequent encounter atomically
increments it (+1). Replayed events never bump counters.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import conflict, validation_error
from app.core.normalization import normalize_lemma
from app.models.user import User  # noqa: F401 (type clarity)
from app.models.word import Encounter, UserWord, Word


def resolve_or_create_word(db: Session, surface: str) -> Word:
    """Find or create the dictionary word for a surface form (language 'en').
    Raises ValueError when the surface cannot be normalized."""
    lemma = normalize_lemma(surface)
    if not lemma:
        raise validation_error("无法从捕获文本解析词条")
    stmt = (
        pg_insert(Word)
        .values(language="en", lemma=lemma, normalized_lemma=lemma)
        .on_conflict_do_update(
            index_elements=[Word.language, Word.normalized_lemma],
            set_={Word.normalized_lemma: Word.normalized_lemma},  # no-op update
        )
        .returning(Word.id)
    )
    word_id = db.execute(stmt).scalar_one()
    word = db.get(Word, word_id)
    assert word is not None
    return word


def get_or_create_user_word(
    db: Session, user_id: uuid.UUID, word_id: uuid.UUID
) -> tuple[UserWord, bool]:
    """(row, created). Concurrent-safe via ON CONFLICT DO NOTHING; a fresh
    row is inserted with encounter_count=1 (server default preserved)."""
    row = db.execute(
        select(UserWord).where(UserWord.user_id == user_id, UserWord.word_id == word_id)
    ).scalar_one_or_none()
    if row is not None:
        return row, False
    stmt = (
        pg_insert(UserWord)
        .values(
            user_id=user_id,
            word_id=word_id,
            status="inbox",
            encounter_count=1,
        )
        .on_conflict_do_nothing(index_elements=[UserWord.user_id, UserWord.word_id])
        .returning(UserWord.id)
    )
    inserted_id = db.execute(stmt).scalar_one_or_none()
    if inserted_id is not None:
        row = db.get(UserWord, inserted_id)
        assert row is not None
        return row, True
    # Lost a race: another transaction created the row first.
    row = db.execute(
        select(UserWord).where(UserWord.user_id == user_id, UserWord.word_id == word_id)
    ).scalar_one()
    return row, False


def find_encounter_by_event(
    db: Session, user_id: uuid.UUID, client_event_id: uuid.UUID
) -> Encounter | None:
    return db.execute(
        select(Encounter).where(
            Encounter.user_id == user_id,
            Encounter.client_event_id == client_event_id,
        )
    ).scalar_one_or_none()


def _touch_user_word(
    db: Session,
    user_word: UserWord,
    *,
    created: bool,
    revive: bool,
    now: datetime,
) -> None:
    """created rows only record last_seen (count is already 1); existing rows
    get an atomic +1. `revive` moves an archived row back to inbox."""
    if created:
        values: dict[str, Any] = {"last_seen_at": now}
    else:
        values = {
            "encounter_count": UserWord.encounter_count + 1,
            "last_seen_at": now,
        }
        if revive and user_word.status == "archived":
            values["status"] = "inbox"
            values["archived_at"] = None
    db.execute(update(UserWord).where(UserWord.id == user_word.id).values(**values))
    db.flush()


def record_encounter(
    db: Session,
    *,
    user_id: uuid.UUID,
    user_word: UserWord,
    surface_text: str,
    encounter_type: str,
    context: str | None,
    note: str | None,
    client_event_id: uuid.UUID | None,
    revive: bool,
    created: bool = False,
    source_id: uuid.UUID | None = None,
    encountered_at: datetime | None = None,
) -> tuple[Encounter, bool]:
    """Inserts one encounter and updates the word counters.

    Returns (encounter, created). When `created` is False the event already
    existed and NOTHING was mutated (idempotent replay).
    """
    now = encountered_at or datetime.now(timezone.utc)
    if client_event_id is not None:
        existing = find_encounter_by_event(db, user_id, client_event_id)
        if existing is not None:
            return existing, False

    _touch_user_word(db, user_word, created=created, revive=revive, now=now)

    encounter = Encounter(
        user_id=user_id,
        user_word_id=user_word.id,
        source_id=source_id,
        client_event_id=client_event_id or uuid.uuid4(),
        surface_text=surface_text,
        type=encounter_type,
        context=context,
        note=note,
        encountered_at=now,
    )
    db.add(encounter)
    try:
        db.flush()
    except IntegrityError:
        # Concurrent duplicate (user_id, client_event_id): undo this capture
        # entirely and hand back the winner once it becomes visible.
        db.rollback()
        assert client_event_id is not None
        winner = find_encounter_by_event(db, user_id, client_event_id)
        if winner is not None:
            return winner, False
        raise conflict(
            code="duplicate_event",
            message="捕获事件冲突，请重试",
        ) from None
    return encounter, True
