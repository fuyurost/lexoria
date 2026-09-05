"""User identity, per-user settings and refresh-token sessions.

All content in the app is user-private: every owned table carries `user_id`
and cascade-deletes with its user (ORM and DB level). Word (dictionary) is
the exception — it is global and referenced with RESTRICT semantics.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Uuid,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.review import ReviewCard, ReviewLog
    from app.models.sheet import DailySheet, DailySheetItem
    from app.models.word import Encounter, Source, UserWord, UserWordSense

DAILY_TEMPLATES = ("compact", "test")
PAPER_SIZES = ("a4", "a5")


class User(Base, TimestampMixin):
    """Account. Uniqueness is enforced on case-normalized columns, which the
    auth service fills from `username`/`email` (casefold + trim)."""

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("username_normalized", name="uq_users_username_normalized"),
        UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
        CheckConstraint(
            "username_normalized <> ''", name="username_normalized_not_empty"
        ),
        CheckConstraint("email_normalized <> ''", name="email_normalized_not_empty"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    username: Mapped[str] = mapped_column(String(150), nullable=False)
    username_normalized: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    settings: Mapped["UserSetting"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    refresh_sessions: Mapped[list["RefreshSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    sources: Mapped[list["Source"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    encounters: Mapped[list["Encounter"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    user_words: Mapped[list["UserWord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    user_word_senses: Mapped[list["UserWordSense"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    review_cards: Mapped[list["ReviewCard"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    review_logs: Mapped[list["ReviewLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    daily_sheets: Mapped[list["DailySheet"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    daily_sheet_items: Mapped[list["DailySheetItem"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class UserSetting(Base):
    """Per-user print/session preferences; `user_id` IS the primary key
    (exactly one row per user, no separate id)."""

    __tablename__ = "user_settings"
    __table_args__ = (
        CheckConstraint(
            "daily_template IN ('compact', 'test')", name="template_valid"
        ),
        CheckConstraint("paper_size IN ('a4', 'a5')", name="paper_size_valid"),
        CheckConstraint("columns IN (1, 2)", name="columns_valid"),
        CheckConstraint("review_count >= 0", name="review_count_nonneg"),
        CheckConstraint("new_count >= 0", name="new_count_nonneg"),
        CheckConstraint(
            "review_count + new_count BETWEEN 1 AND 100", name="daily_count_range"
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_user_settings_user_id_users"),
        primary_key=True,
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC", server_default="UTC"
    )
    daily_template: Mapped[str] = mapped_column(
        String(16), nullable=False, default="compact", server_default="compact"
    )
    paper_size: Mapped[str] = mapped_column(
        String(8), nullable=False, default="a4", server_default="a4"
    )
    columns: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default=text("2")
    )
    review_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default=text("20")
    )
    new_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10, server_default=text("10")
    )

    user: Mapped["User"] = relationship(back_populates="settings")


class RefreshSession(Base):
    """Persisted refresh token. Strict column set — stores only a SHA-256 hash
    of the opaque token; no device metadata."""

    __tablename__ = "refresh_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
        Index("ix_refresh_sessions_user_id", "user_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_refresh_sessions_user_id_users"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="refresh_sessions")
