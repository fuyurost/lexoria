"""initial schema v2: users, vocabulary, lexiora-srs, daily sheets

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-05

UUID primary keys; case-normalized unique identity; every user-owned table
carries user_id and cascades with the user; `words` is global (RESTRICT);
sources hard-delete SET NULL (normal API flow archives).
Constraint/index names match the naming convention in app/db/base.py.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- users ------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(length=150), nullable=False),
        sa.Column("username_normalized", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("email_normalized", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username_normalized", name="uq_users_username_normalized"),
        sa.UniqueConstraint("email_normalized", name="uq_users_email_normalized"),
        sa.CheckConstraint("username_normalized <> ''", name="ck_users_username_normalized_not_empty"),
        sa.CheckConstraint("email_normalized <> ''", name="ck_users_email_normalized_not_empty"),
    )

    # ---- user_settings (user_id is the PK) -------------------------------
    op.create_table(
        "user_settings",
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_settings_user_id_users"),
            nullable=False,
        ),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="UTC"),
        sa.Column("daily_template", sa.String(length=16), nullable=False, server_default="compact"),
        sa.Column("paper_size", sa.String(length=8), nullable=False, server_default="a4"),
        sa.Column("columns", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default=sa.text("20")),
        sa.Column("new_count", sa.Integer(), nullable=False, server_default=sa.text("10")),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_settings"),
        sa.CheckConstraint("daily_template IN ('compact', 'test')", name="ck_user_settings_template_valid"),
        sa.CheckConstraint("paper_size IN ('a4', 'a5')", name="ck_user_settings_paper_size_valid"),
        sa.CheckConstraint("columns IN (1, 2)", name="ck_user_settings_columns_valid"),
        sa.CheckConstraint("review_count >= 0", name="ck_user_settings_review_count_nonneg"),
        sa.CheckConstraint("new_count >= 0", name="ck_user_settings_new_count_nonneg"),
        sa.CheckConstraint(
            "review_count + new_count BETWEEN 1 AND 100", name="ck_user_settings_daily_count_range"
        ),
    )

    # ---- refresh_sessions ------------------------------------------------
    op.create_table(
        "refresh_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_refresh_sessions_user_id_users"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_refresh_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_refresh_sessions_token_hash"),
    )

    # ---- words (global dictionary, RESTRICT from referrers) --------------
    op.create_table(
        "words",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lemma", sa.String(length=255), nullable=False),
        sa.Column("normalized_lemma", sa.String(length=255), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False, server_default="en"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_words"),
        sa.UniqueConstraint("language", "normalized_lemma", name="uq_words_language_normalized_lemma"),
        sa.CheckConstraint("language = 'en'", name="ck_words_language_en"),
        sa.CheckConstraint("lemma <> ''", name="ck_words_lemma_not_empty"),
    )

    # ---- sources (user-private) ------------------------------------------
    op.create_table(
        "sources",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_sources_user_id_users"),
            nullable=False,
        ),
        sa.Column("type", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_sources"),
        sa.UniqueConstraint("user_id", "type", "normalized_name", name="uq_sources_user_type_normalized_name"),
        sa.CheckConstraint(
            "type IN ('school', 'ielts', 'cet4', 'exam', 'reading', 'manual', 'other')",
            name="ck_sources_type_valid",
        ),
        sa.CheckConstraint("name <> ''", name="ck_sources_name_not_empty"),
    )

    # ---- user_words -------------------------------------------------------
    op.create_table(
        "user_words",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_words_user_id_users"),
            nullable=False,
        ),
        sa.Column(
            "word_id",
            sa.Uuid(),
            sa.ForeignKey("words.id", name="fk_user_words_word_id_words"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="inbox"),
        sa.Column("familiarity", sa.Integer(), nullable=True),
        sa.Column("personal_phonetic", sa.String(length=255), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("encounter_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_user_words"),
        sa.UniqueConstraint("user_id", "word_id", name="uq_user_words_user_id_word_id"),
        sa.CheckConstraint("status IN ('inbox', 'active', 'known', 'archived')", name="ck_user_words_status_valid"),
        sa.CheckConstraint(
            "familiarity IS NULL OR familiarity BETWEEN 0 AND 5", name="ck_user_words_familiarity_range"
        ),
        sa.CheckConstraint("encounter_count >= 1", name="ck_user_words_encounter_count_min"),
    )

    # ---- user_word_senses -------------------------------------------------
    op.create_table(
        "user_word_senses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_user_word_senses_user_id_users"),
            nullable=False,
        ),
        sa.Column(
            "user_word_id",
            sa.Uuid(),
            sa.ForeignKey(
                "user_words.id", ondelete="CASCADE", name="fk_user_word_senses_user_word_id_user_words"
            ),
            nullable=False,
        ),
        sa.Column("part_of_speech", sa.String(length=32), nullable=True),
        sa.Column("definition_zh", sa.Text(), nullable=True),
        sa.Column("definition_en", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_user_word_senses"),
        sa.UniqueConstraint("user_word_id", "sort_order", name="uq_user_word_senses_user_word_sort"),
        sa.CheckConstraint("sort_order >= 0", name="ck_user_word_senses_sort_order_nonneg"),
        sa.CheckConstraint(
            "(coalesce(definition_zh, '') <> '') OR (coalesce(definition_en, '') <> '')",
            name="ck_user_word_senses_at_least_one_definition",
        ),
    )

    # ---- encounters -------------------------------------------------------
    op.create_table(
        "encounters",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_encounters_user_id_users"),
            nullable=False,
        ),
        sa.Column(
            "user_word_id",
            sa.Uuid(),
            sa.ForeignKey(
                "user_words.id", ondelete="CASCADE", name="fk_encounters_user_word_id_user_words"
            ),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("sources.id", ondelete="SET NULL", name="fk_encounters_source_id_sources"),
            nullable=True,
        ),
        sa.Column("client_event_id", sa.Uuid(), nullable=False),
        sa.Column("surface_text", sa.String(length=512), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False, server_default="unclassified"),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("encountered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_encounters"),
        sa.UniqueConstraint("user_id", "client_event_id", name="uq_encounters_user_client_event"),
        sa.CheckConstraint(
            "type IN ('unclassified', 'new', 'forgotten', 'confused', "
            "'familiar_word_new_meaning', 'spelling_error', 'usage_problem', 'recognized')",
            name="ck_encounters_type_valid",
        ),
    )

    # ---- review_cards -----------------------------------------------------
    op.create_table(
        "review_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_review_cards_user_id_users"),
            nullable=False,
        ),
        sa.Column(
            "user_word_id",
            sa.Uuid(),
            sa.ForeignKey(
                "user_words.id", ondelete="CASCADE", name="fk_review_cards_user_word_id_user_words"
            ),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("difficulty", sa.Numeric(precision=6, scale=2), nullable=False, server_default=sa.text("5.00")),
        sa.Column("stability_days", sa.Numeric(precision=12, scale=4), nullable=False, server_default=sa.text("0")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lapse_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("scheduler_version", sa.String(length=32), nullable=False, server_default="lexiora-srs-v1"),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_review_cards"),
        sa.UniqueConstraint("user_word_id", name="uq_review_cards_user_word_id"),
        sa.CheckConstraint(
            "state IN ('new', 'learning', 'review', 'relearning')", name="ck_review_cards_state_valid"
        ),
        sa.CheckConstraint("difficulty BETWEEN 1 AND 10", name="ck_review_cards_difficulty_range"),
        sa.CheckConstraint("stability_days >= 0", name="ck_review_cards_stability_nonneg"),
        sa.CheckConstraint("review_count >= 0", name="ck_review_cards_review_count_nonneg"),
        sa.CheckConstraint("lapse_count >= 0", name="ck_review_cards_lapse_count_nonneg"),
        sa.CheckConstraint("version >= 0", name="ck_review_cards_version_nonneg"),
    )

    # ---- review_logs ------------------------------------------------------
    op.create_table(
        "review_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_review_logs_user_id_users"),
            nullable=False,
        ),
        sa.Column(
            "review_card_id",
            sa.Uuid(),
            sa.ForeignKey(
                "review_cards.id", ondelete="CASCADE", name="fk_review_logs_review_card_id_review_cards"
            ),
            nullable=False,
        ),
        sa.Column("client_event_id", sa.Uuid(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("rating", sa.String(length=16), nullable=False),
        sa.Column("state_before", sa.String(length=16), nullable=False),
        sa.Column("state_after", sa.String(length=16), nullable=False),
        sa.Column("previous_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_stability_days", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("new_stability_days", sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column("previous_difficulty", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("new_difficulty", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("elapsed_days", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("scheduled_days", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("scheduler_version", sa.String(length=32), nullable=False, server_default="lexiora-srs-v1"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_review_logs"),
        sa.UniqueConstraint("user_id", "client_event_id", name="uq_review_logs_user_client_event"),
        sa.UniqueConstraint("review_card_id", "sequence_no", name="uq_review_logs_card_sequence"),
        sa.CheckConstraint(
            "rating IN ('again', 'hard', 'good', 'easy')", name="ck_review_logs_rating_valid"
        ),
        sa.CheckConstraint(
            "state_before IN ('new', 'learning', 'review', 'relearning')",
            name="ck_review_logs_state_before_valid",
        ),
        sa.CheckConstraint(
            "state_after IN ('new', 'learning', 'review', 'relearning')",
            name="ck_review_logs_state_after_valid",
        ),
        sa.CheckConstraint("sequence_no >= 1", name="ck_review_logs_sequence_no_min"),
    )

    # ---- daily_sheets -----------------------------------------------------
    op.create_table(
        "daily_sheets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_daily_sheets_user_id_users"),
            nullable=False,
        ),
        sa.Column("sheet_date", sa.Date(), nullable=False),
        sa.Column("timezone_snapshot", sa.String(length=64), nullable=False),
        sa.Column("template", sa.String(length=16), nullable=False, server_default="compact"),
        sa.Column("paper_size", sa.String(length=8), nullable=False, server_default="a4"),
        sa.Column("columns", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("pdf_storage_key", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id", name="pk_daily_sheets"),
        sa.CheckConstraint("template IN ('compact', 'test')", name="ck_daily_sheets_template_valid"),
        sa.CheckConstraint("paper_size IN ('a4', 'a5')", name="ck_daily_sheets_paper_size_valid"),
        sa.CheckConstraint("columns IN (1, 2)", name="ck_daily_sheets_columns_valid"),
    )

    # ---- daily_sheet_items ------------------------------------------------
    op.create_table(
        "daily_sheet_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_daily_sheet_items_user_id_users"),
            nullable=False,
        ),
        sa.Column(
            "daily_sheet_id",
            sa.Uuid(),
            sa.ForeignKey(
                "daily_sheets.id", ondelete="CASCADE", name="fk_daily_sheet_items_sheet_id_daily_sheets"
            ),
            nullable=False,
        ),
        sa.Column(
            "user_word_id",
            sa.Uuid(),
            sa.ForeignKey(
                "user_words.id", ondelete="CASCADE", name="fk_daily_sheet_items_user_word_id_user_words"
            ),
            nullable=False,
        ),
        sa.Column(
            "review_card_id",
            sa.Uuid(),
            sa.ForeignKey(
                "review_cards.id", ondelete="SET NULL", name="fk_daily_sheet_items_review_card_id_review_cards"
            ),
            nullable=True,
        ),
        sa.Column("item_type", sa.String(length=16), nullable=False, server_default="new"),
        sa.Column("selection_reason", sa.String(length=32), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("snapshot_schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("content_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.PrimaryKeyConstraint("id", name="pk_daily_sheet_items"),
        sa.UniqueConstraint("daily_sheet_id", "sort_order", name="uq_daily_sheet_items_sheet_sort"),
        sa.UniqueConstraint("daily_sheet_id", "user_word_id", name="uq_daily_sheet_items_sheet_user_word"),
        sa.CheckConstraint("item_type IN ('review', 'new')", name="ck_daily_sheet_items_item_type_valid"),
        sa.CheckConstraint(
            "selection_reason IN ('overdue', 'relearning', 'recent_again', "
            "'due_today', 'recent_hard', 'new')",
            name="ck_daily_sheet_items_selection_reason_valid",
        ),
    )

    # ---- indexes ----------------------------------------------------------
    op.create_index("ix_refresh_sessions_user_id", "refresh_sessions", ["user_id"])
    op.create_index("ix_sources_user_id", "sources", ["user_id"])
    op.create_index("ix_user_words_word_id", "user_words", ["word_id"])
    op.create_index("ix_user_words_user_status", "user_words", ["user_id", "status"])
    op.create_index("ix_user_word_senses_user_id", "user_word_senses", ["user_id"])
    op.create_index("ix_encounters_user_word", "encounters", ["user_id", "user_word_id"])
    op.create_index("ix_encounters_source_id", "encounters", ["source_id"])
    op.create_index("ix_review_cards_user_state_due", "review_cards", ["user_id", "state", "due_at"])
    op.create_index("ix_review_logs_user_reviewed", "review_logs", ["user_id", "reviewed_at"])
    op.create_index("ix_daily_sheets_user_date", "daily_sheets", ["user_id", "sheet_date"])


def downgrade() -> None:
    op.drop_table("daily_sheet_items")
    op.drop_table("daily_sheets")
    op.drop_table("review_logs")
    op.drop_table("review_cards")
    op.drop_table("encounters")
    op.drop_table("user_word_senses")
    op.drop_table("user_words")
    op.drop_table("sources")
    op.drop_table("words")
    op.drop_table("refresh_sessions")
    op.drop_table("user_settings")
    op.drop_table("users")
