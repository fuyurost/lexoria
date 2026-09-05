"""Daily printable sheets (PDF export input) + their item rows.

Multiple sheets per user per day are allowed. Items carry a full
`content_snapshot` (JSONB) so a sheet stays printable even if vocabulary
changes later.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Uuid,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.review import ReviewCard
    from app.models.user import User
    from app.models.word import UserWord

DAILY_TEMPLATES = ("compact", "test")
PAPER_SIZES = ("a4", "a5")
ITEM_TYPES = ("review", "new")
SELECTION_REASONS = (
    "overdue",
    "relearning",
    "recent_again",
    "due_today",
    "recent_hard",
    "new",
)

_TEMPLATE_SQL = "template IN ('compact', 'test')"
_PAPER_SQL = "paper_size IN ('a4', 'a5')"
_COLUMNS_SQL = "columns IN (1, 2)"


class DailySheet(Base):
    """A generated sheet (one row per print job). `timezone_snapshot` records
    the user timezone at generation so sheet_date stays unambiguous."""

    __tablename__ = "daily_sheets"
    __table_args__ = (
        Index("ix_daily_sheets_user_date", "user_id", "sheet_date"),
        CheckConstraint(_TEMPLATE_SQL, name="template_valid"),
        CheckConstraint(_PAPER_SQL, name="paper_size_valid"),
        CheckConstraint(_COLUMNS_SQL, name="columns_valid"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_daily_sheets_user_id_users"),
        nullable=False,
    )
    sheet_date: Mapped[date] = mapped_column(Date, nullable=False)
    timezone_snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    template: Mapped[str] = mapped_column(
        String(16), nullable=False, default="compact", server_default="compact"
    )
    paper_size: Mapped[str] = mapped_column(
        String(8), nullable=False, default="a4", server_default="a4"
    )
    columns: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default=text("2")
    )
    # Storage key of the exported PDF inside PDF_STORAGE_DIR. Rows are only
    # created AFTER a successful PDF export, so this is never null.
    pdf_storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="daily_sheets")
    items: Mapped[list["DailySheetItem"]] = relationship(
        back_populates="sheet", cascade="all, delete-orphan", passive_deletes=True
    )


class DailySheetItem(Base):
    """A concrete vocabulary row on a sheet (snapshot the content at
    generation time; references stay for drill-through)."""

    __tablename__ = "daily_sheet_items"
    __table_args__ = (
        UniqueConstraint("daily_sheet_id", "sort_order", name="uq_daily_sheet_items_sheet_sort"),
        UniqueConstraint(
            "daily_sheet_id", "user_word_id", name="uq_daily_sheet_items_sheet_user_word"
        ),
        CheckConstraint("item_type IN ('review', 'new')", name="item_type_valid"),
        CheckConstraint(
            "selection_reason IN ('overdue', 'relearning', 'recent_again', "
            "'due_today', 'recent_hard', 'new')",
            name="selection_reason_valid",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_daily_sheet_items_user_id_users"),
        nullable=False,
    )
    daily_sheet_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "daily_sheets.id", ondelete="CASCADE", name="fk_daily_sheet_items_sheet_id_daily_sheets"
        ),
        nullable=False,
    )
    user_word_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "user_words.id", ondelete="CASCADE", name="fk_daily_sheet_items_user_word_id_user_words"
        ),
        nullable=False,
    )
    review_card_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey(
            "review_cards.id", ondelete="SET NULL", name="fk_daily_sheet_items_review_card_id_review_cards"
        ),
    )
    item_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="new", server_default="new"
    )
    selection_reason: Mapped[str] = mapped_column(String(32), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_schema_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1")
    )
    content_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    user: Mapped["User"] = relationship(back_populates="daily_sheet_items")
    sheet: Mapped["DailySheet"] = relationship(back_populates="items")
    user_word: Mapped["UserWord"] = relationship(back_populates="sheet_items")
    review_card: Mapped["ReviewCard | None"] = relationship(back_populates="sheet_items")
