"""Spaced repetition (lexiora-srs-v1): scheduling cards + immutable logs."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Uuid,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.sheet import DailySheetItem
    from app.models.user import User
    from app.models.word import UserWord

CARD_STATES = ("new", "learning", "review", "relearning")
SCHEDULER_VERSION = "lexiora-srs-v1"


class ReviewCard(Base, TimestampMixin):
    """Scheduling state for one UserWord (1:1). Fields follow FSRS-style
    difficulty/stability; bump `scheduler_version` when the algorithm changes
    so old logs stay interpretable."""

    __tablename__ = "review_cards"
    __table_args__ = (
        UniqueConstraint("user_word_id", name="uq_review_cards_user_word_id"),
        Index("ix_review_cards_user_state_due", "user_id", "state", "due_at"),
        CheckConstraint(
            "state IN ('new', 'learning', 'review', 'relearning')", name="state_valid"
        ),
        CheckConstraint("difficulty BETWEEN 1 AND 10", name="difficulty_range"),
        CheckConstraint("stability_days >= 0", name="stability_nonneg"),
        CheckConstraint("review_count >= 0", name="review_count_nonneg"),
        CheckConstraint("lapse_count >= 0", name="lapse_count_nonneg"),
        CheckConstraint("version >= 0", name="version_nonneg"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_review_cards_user_id_users"),
        nullable=False,
    )
    user_word_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "user_words.id", ondelete="CASCADE", name="fk_review_cards_user_word_id_user_words"
        ),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="new", server_default="new"
    )
    difficulty: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), nullable=False, default=Decimal("5.00"), server_default=text("5.00")
    )
    stability_days: Mapped[Decimal] = mapped_column(
        Numeric(12, 4), nullable=False, default=Decimal("0"), server_default=text("0")
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    lapse_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    scheduler_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SCHEDULER_VERSION, server_default=SCHEDULER_VERSION
    )
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="review_cards")
    user_word: Mapped["UserWord"] = relationship(back_populates="card")
    logs: Mapped[list["ReviewLog"]] = relationship(
        back_populates="card", cascade="all, delete-orphan", passive_deletes=True
    )
    sheet_items: Mapped[list["DailySheetItem"]] = relationship(back_populates="review_card")


class ReviewLog(Base):
    """Immutable per-review audit row. Deduped by (user, client_event_id);
    ordered per card by (review_card_id, sequence_no)."""

    __tablename__ = "review_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "client_event_id", name="uq_review_logs_user_client_event"),
        UniqueConstraint("review_card_id", "sequence_no", name="uq_review_logs_card_sequence"),
        Index("ix_review_logs_user_reviewed", "user_id", "reviewed_at"),
        CheckConstraint(
            "rating IN ('again', 'hard', 'good', 'easy')", name="rating_valid"
        ),
        CheckConstraint(
            "state_before IN ('new', 'learning', 'review', 'relearning')",
            name="state_before_valid",
        ),
        CheckConstraint(
            "state_after IN ('new', 'learning', 'review', 'relearning')",
            name="state_after_valid",
        ),
        CheckConstraint("sequence_no >= 1", name="sequence_no_min"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_review_logs_user_id_users"),
        nullable=False,
    )
    review_card_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "review_cards.id", ondelete="CASCADE", name="fk_review_logs_review_card_id_review_cards"
        ),
        nullable=False,
    )
    client_event_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    sequence_no: Mapped[int] = mapped_column(Integer, nullable=False)
    rating: Mapped[str] = mapped_column(String(16), nullable=False)
    state_before: Mapped[str] = mapped_column(String(16), nullable=False)
    state_after: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    previous_stability_days: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    new_stability_days: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    previous_difficulty: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    new_difficulty: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    elapsed_days: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    scheduled_days: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    scheduler_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default=SCHEDULER_VERSION, server_default=SCHEDULER_VERSION
    )
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="review_logs")
    card: Mapped["ReviewCard"] = relationship(back_populates="logs")
