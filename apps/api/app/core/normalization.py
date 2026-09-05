"""Pure, side-effect-free normalization helpers.

Every public function is a plain transformation: parse/format text or
timestamps. Validation and persistence live elsewhere. Kept import-free of
FastAPI/SQLAlchemy so it is trivially unit-testable. Functions may raise
ValueError on inputs that cannot be normalized.
"""
from __future__ import annotations

import unicodedata
from datetime import datetime, timezone


def _fold(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _collapse_spaces(value: str) -> str:
    return " ".join(value.split())


_CURLY_TO_STRAIGHT = str.maketrans(
    {"\u2018": "'", "\u2019": "'", "\u02bc": "'"}  # ‘ ’ ʼ -> '
)


def clean_surface(value: str) -> str:
    """Clean a captured surface form: NFKC, curly apostrophes to straight,
    Unicode whitespace collapsed and trimmed. Raises ValueError on control
    characters (Cc/Cf), output longer than 200 chars, or empty result."""
    folded = unicodedata.normalize("NFKC", value)
    if any(unicodedata.category(ch).startswith("C") for ch in folded):
        raise ValueError("text contains control characters")
    cleaned = " ".join(folded.translate(_CURLY_TO_STRAIGHT).split())
    if len(cleaned) > 200:
        raise ValueError("text is longer than 200 characters")
    if not cleaned:
        raise ValueError("text is empty after cleaning")
    return cleaned


def normalize_username(value: str) -> str:
    """NFKC casefold + trim. Internal whitespace is NOT removed — a space in
    the middle must make the caller's character-set validation reject the
    name (register checks against ^[a-z0-9._-]+$). Uniqueness key for
    usernames; the display form keeps the user's original casing."""
    return _fold(value.strip())


def normalize_email(value: str) -> str:
    """Trim + NFKC casefold; syntactic validation happens separately with
    email-validator."""
    return _fold(value.strip())


def normalize_identifier(value: str) -> str:
    """Normalize an arbitrary login identifier (email vs username is resolved
    by the caller on the '@' presence)."""
    return _fold(value.strip())


def normalize_lemma(value: str) -> str:
    """Dictionary lemma key: clean_surface then casefold."""
    return clean_surface(value).casefold()


def normalize_source_name(value: str) -> str:
    """Source unique key per (user, type): casefold + collapse whitespace."""
    return _collapse_spaces(_fold(value.strip()))


def utcnow() -> datetime:
    """Timezone-aware current instant (all DB timestamps are UTC)."""
    return datetime.now(timezone.utc)


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
