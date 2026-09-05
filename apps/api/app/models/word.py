"""Dictionary words (global) and the user-private vocabulary layer.

- `Word` is a global dictionary entry, NOT owned by any user. Rows elsewhere
  that reference a Word do so with RESTRICT semantics (a Word in use cannot be
  hard-deleted).
- Everything else here (`Source`, `UserWord`, `UserWordSense`, `Encounter`) is
  user-private, carries `user_id` and cascade-deletes with its user.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Uuid,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.review import ReviewCard
    from app.models.sheet import DailySheetItem
    from app.models.user import User

USER_WORD_STATUSES = ("inbox", "active", "known", "archived")
SOURCE_TYPES = ("school", "ielts", "cet4", "exam", "reading", "manual", "other")
ENCOUNTER_TYPES = (
    "unclassified",
    "new",
    "forgotten",
    "confused",
    "familiar_word_new_meaning",
    "spelling_error",
    "usage_problem",
    "recognized",
)

_WORD_STATUS_SQL = "status IN ('inbox', 'active', 'known', 'archived')"
_ENCOUNTER_TYPE_SQL = (
    "type IN ('unclassified', 'new', 'forgotten', 'confused', "
    "'familiar_word_new_meaning', 'spelling_error', 'usage_problem', 'recognized')"
)
_SOURCE_TYPE_SQL = (
    "type IN ('school', 'ielts', 'cet4', 'exam', 'reading', 'manual', 'other')"
)


class Word(Base, TimestampMixin):
    """Dictionary entry. Language is English-only for now (`en`); uniqueness
    is on (language, normalized_lemma) so case/space variants collapse."""

    __tablename__ = "words"
    __table_args__ = (
        UniqueConstraint("language", "normalized_lemma", name="uq_words_language_normalized_lemma"),
        CheckConstraint("language = 'en'", name="language_en"),
        CheckConstraint("lemma <> ''", name="lemma_not_empty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    lemma: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_lemma: Mapped[str] = mapped_column(String(255), nullable=False)
    language: Mapped[str] = mapped_column(
        String(8), nullable=False, default="en", server_default="en"
    )

    user_words: Mapped[list["UserWord"]] = relationship(back_populates="word")


class Source(Base, TimestampMixin):
    """User-private source of vocabulary (school book, IELTS list, ...).
    Hard deletion of a source SET NULLs the FKs that reference it; the normal
    API flow archives it instead (sets archived_at)."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "type", "normalized_name", name="uq_sources_user_type_normalized_name"
        ),
        Index("ix_sources_user_id", "user_id"),
        CheckConstraint(_SOURCE_TYPE_SQL, name="type_valid"),
        CheckConstraint("name <> ''", name="name_not_empty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_sources_user_id_users"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="manual", server_default="manual"
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="sources")
    encounters: Mapped[list["Encounter"]] = relationship(back_populates="source")


class UserWord(Base, TimestampMixin):
    """A user's vocabulary row for one word (one row per user+word)."""

    __tablename__ = "user_words"
    __table_args__ = (
        UniqueConstraint("user_id", "word_id", name="uq_user_words_user_id_word_id"),
        Index("ix_user_words_word_id", "word_id"),
        Index("ix_user_words_user_status", "user_id", "status"),
        CheckConstraint(_WORD_STATUS_SQL, name="status_valid"),
        CheckConstraint(
            "familiarity IS NULL OR familiarity BETWEEN 0 AND 5",
            name="familiarity_range",
        ),
        CheckConstraint("encounter_count >= 1", name="encounter_count_min"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_user_words_user_id_users"),
        nullable=False,
    )
    word_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("words.id", name="fk_user_words_word_id_words"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="inbox", server_default="inbox"
    )
    familiarity: Mapped[int | None] = mapped_column(Integer)
    personal_phonetic: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    encounter_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="user_words")
    word: Mapped["Word"] = relationship(back_populates="user_words")
    senses: Mapped[list["UserWordSense"]] = relationship(
        back_populates="user_word", cascade="all, delete-orphan", passive_deletes=True
    )
    encounters: Mapped[list["Encounter"]] = relationship(
        back_populates="user_word", cascade="all, delete-orphan", passive_deletes=True
    )
    card: Mapped["ReviewCard | None"] = relationship(
        back_populates="user_word", cascade="all, delete-orphan", passive_deletes=True
    )
    sheet_items: Mapped[list["DailySheetItem"]] = relationship(back_populates="user_word")


class UserWordSense(Base, TimestampMixin):
    """One user-curated sense entry under a UserWord. At least one definition
    (zh or en) must be non-empty."""

    __tablename__ = "user_word_senses"
    __table_args__ = (
        UniqueConstraint(
            "user_word_id", "sort_order", name="uq_user_word_senses_user_word_sort"
        ),
        Index("ix_user_word_senses_user_id", "user_id"),
        CheckConstraint("sort_order >= 0", name="sort_order_nonneg"),
        CheckConstraint(
            "(coalesce(definition_zh, '') <> '') OR (coalesce(definition_en, '') <> '')",
            name="at_least_one_definition",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_user_word_senses_user_id_users"),
        nullable=False,
    )
    user_word_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "user_words.id", ondelete="CASCADE", name="fk_user_word_senses_user_word_id_user_words"
        ),
        nullable=False,
    )
    part_of_speech: Mapped[str | None] = mapped_column(String(32))
    definition_zh: Mapped[str | None] = mapped_column(Text)
    definition_en: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)

    user: Mapped["User"] = relationship(back_populates="user_word_senses")
    user_word: Mapped["UserWord"] = relationship(back_populates="senses")


class Encounter(Base):
    """A logged meeting of a vocabulary word in context. Idempotent per
    (user, client_event_id); word rows hard-deleted cascade here."""

    __tablename__ = "encounters"
    __table_args__ = (
        UniqueConstraint("user_id", "client_event_id", name="uq_encounters_user_client_event"),
        Index("ix_encounters_user_word", "user_id", "user_word_id"),
        Index("ix_encounters_source_id", "source_id"),
        CheckConstraint(_ENCOUNTER_TYPE_SQL, name="type_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_encounters_user_id_users"),
        nullable=False,
    )
    user_word_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "user_words.id", ondelete="CASCADE", name="fk_encounters_user_word_id_user_words"
        ),
        nullable=False,
    )
    source_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("sources.id", ondelete="SET NULL", name="fk_encounters_source_id_sources"),
    )
    client_event_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    surface_text: Mapped[str] = mapped_column(String(512), nullable=False)
    type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unclassified", server_default="unclassified"
    )
    context: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    encountered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="encounters")
    user_word: Mapped["UserWord"] = relationship(back_populates="encounters")
    source: Mapped["Source | None"] = relationship(back_populates="encounters")
