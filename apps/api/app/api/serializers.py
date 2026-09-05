"""API serializers: ORM rows -> JSON dicts (domain-correct field names)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.core.normalization import to_iso
from app.models.review import ReviewCard
from app.models.user import User, UserSetting
from app.models.word import Encounter, Source, UserWord, UserWordSense


def user_dict(user: User) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "username": user.username,
        "email": user.email,
        "created_at": to_iso(user.created_at),
    }


def settings_dict(row: UserSetting) -> dict[str, Any]:
    return {
        "timezone": row.timezone,
        "daily_template": row.daily_template,
        "paper_size": row.paper_size,
        "columns": row.columns,
        "review_count": row.review_count,
        "new_count": row.new_count,
    }


def source_dict(source: Source) -> dict[str, Any]:
    return {
        "id": str(source.id),
        "name": source.name,
        "type": source.type,
        "description": source.description,
        "archived_at": to_iso(source.archived_at),
        "created_at": to_iso(source.created_at),
        "updated_at": to_iso(source.updated_at),
    }


def _num(value: Decimal | float | None) -> float | None:
    return float(value) if value is not None else None


def card_dict(card: ReviewCard | None) -> dict[str, Any] | None:
    if card is None:
        return None
    return {
        "id": str(card.id),
        "state": card.state,
        "difficulty": _num(card.difficulty),
        "stability_days": _num(card.stability_days),
        "due_at": to_iso(card.due_at),
        "last_review_at": to_iso(card.last_review_at),
        "review_count": card.review_count,
        "lapse_count": card.lapse_count,
        "version": card.version,
        "scheduler_version": card.scheduler_version,
        "suspended_at": to_iso(card.suspended_at),
    }


def sense_dict(sense: UserWordSense) -> dict[str, Any]:
    return {
        "id": str(sense.id),
        "user_word_id": str(sense.user_word_id),
        "part_of_speech": sense.part_of_speech,
        "definition_zh": sense.definition_zh,
        "definition_en": sense.definition_en,
        "sort_order": sense.sort_order,
        "created_at": to_iso(sense.created_at),
        "updated_at": to_iso(sense.updated_at),
    }


def user_word_dict(user_word: UserWord) -> dict[str, Any]:
    """Requires `word`, `senses`, `card` relationships loaded (selectinload).
    `id` is the user_word id; `word_id` is the shared dictionary Word row."""
    word = user_word.word
    return {
        "id": str(user_word.id),
        "word_id": str(user_word.word_id),
        "lemma": word.lemma if word is not None else "",
        "normalized_lemma": word.normalized_lemma if word is not None else "",
        "personal_phonetic": user_word.personal_phonetic,
        "status": user_word.status,
        "familiarity": user_word.familiarity,
        "note": user_word.note,
        "senses": [sense_dict(s) for s in sorted(user_word.senses, key=lambda s: s.sort_order)],
        "card": card_dict(user_word.card),
        "first_seen_at": to_iso(user_word.first_seen_at),
        "last_seen_at": to_iso(user_word.last_seen_at),
        "encounter_count": user_word.encounter_count,
        "activated_at": to_iso(user_word.activated_at),
        "archived_at": to_iso(user_word.archived_at),
        "created_at": to_iso(user_word.created_at),
        "updated_at": to_iso(user_word.updated_at),
    }


def encounter_dict(encounter: Encounter) -> dict[str, Any]:
    return {
        "id": str(encounter.id),
        "user_word_id": str(encounter.user_word_id),
        "source_id": str(encounter.source_id) if encounter.source_id else None,
        "source": source_dict(encounter.source) if encounter.source is not None else None,
        "type": encounter.type,
        "surface_text": encounter.surface_text,
        "context": encounter.context,
        "note": encounter.note,
        "client_event_id": str(encounter.client_event_id),
        "encountered_at": to_iso(encounter.encountered_at),
        "created_at": to_iso(encounter.created_at),
    }


def inbox_item_dict(
    user_word: UserWord, encounter: Encounter | None = None
) -> dict[str, Any]:
    """Inbox item = the user-word row plus its triggering (or latest)
    encounter's capture context. `note` prefers the capture note."""
    item = user_word_dict(user_word)
    if encounter is not None:
        item.update(
            {
                "source_id": str(encounter.source_id) if encounter.source_id else None,
                "source": source_dict(encounter.source) if encounter.source is not None else None,
                "encounter_type": encounter.type,
                "surface_text": encounter.surface_text,
                "context": encounter.context,
                "client_event_id": str(encounter.client_event_id),
                "encountered_at": to_iso(encounter.encountered_at),
            }
        )
        item["note"] = encounter.note if encounter.note is not None else user_word.note
    return item


def page_response(
    items: list[dict[str, Any]], total: int, page: int, page_size: int
) -> dict[str, Any]:
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": page * page_size < total,
    }
