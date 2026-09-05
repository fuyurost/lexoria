/**
 * Canonical Lexiora API domain types (approved model).
 *
 * These types are the single source of truth for everything the web app
 * renders; the HTTP layer (`endpoints.ts`) tolerantly normalizes whatever
 * the server sends into these shapes.
 *
 * When a real OpenAPI document becomes available, `pnpm generate:openapi`
 * replaces this hand-written contract wholesale (see `openapi/README.md`).
 */

/** ISO-8601 / RFC 3339 datetime strings. */
export type IsoDateTime = string;

/** UUID (v4) string, used for `client_event_id` and entity ids. */
export type Uuid = string;

/* ------------------------------------------------------------------ */
/* auth / users                                                       */
/* ------------------------------------------------------------------ */

export interface User {
  id: Uuid;
  username: string;
  email: string;
  created_at: IsoDateTime;
}

/** Register may return a User; the client ignores it and logs in instead. */
export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

/** Login identifier = username OR email (fixed field name). */
export interface LoginRequest {
  identifier: string;
  password: string;
}

export interface AuthSession {
  access_token: string;
  user: User;
}

export interface AccessTokens {
  access_token: string;
}

/* ------------------------------------------------------------------ */
/* user words / inbox (same aggregate)                                */
/* ------------------------------------------------------------------ */

/** A captured word starts as `inbox`, gets activated, then known/archived. */
export type WordStatus = 'inbox' | 'active' | 'known' | 'archived';

/** 0–5 self rating; null means unrated. */
export type Familiarity = 0 | 1 | 2 | 3 | 4 | 5;

export type CardState = 'new' | 'learning' | 'review' | 'relearning';

export interface CardInfo {
  id: Uuid;
  state: CardState;
  difficulty: number;
  stability_days: number;
  due_at: IsoDateTime | null;
  lapse_count: number;
  review_count: number;
  last_review_at: IsoDateTime | null;
  suspended_at: IsoDateTime | null;
  /** Bumped by every scheduled review; optimistic review sends must echo it. */
  version: number;
}

export interface Sense {
  id: Uuid;
  user_word_id: Uuid;
  part_of_speech: string | null;
  /** At least one of the two definitions is non-empty (server-enforced). */
  definition_zh: string;
  definition_en: string;
  sort_order: number;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface SourceRef {
  id: Uuid;
  name: string;
}

export interface UserWord {
  id: Uuid;
  /** Canonical dictionary word id the row is linked to. */
  word_id: Uuid;
  lemma: string;
  normalized_lemma: string;
  personal_phonetic: string | null;
  status: WordStatus;
  familiarity: Familiarity | null;
  note: string | null;
  card: CardInfo | null;
  senses: Sense[];
  first_seen_at: IsoDateTime;
  last_seen_at: IsoDateTime | null;
  encounter_count: number;
  /** Optional expansion; the client never assumes these columns exist. */
  recent_sources?: SourceRef[];
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

/**
 * Inbox rows ARE user-words (same aggregate, status ∈ WordStatus).
 * `user_word_created` tells the UI whether a capture created a NEW word or
 * re-captured an existing one; `replayed` signals an idempotent replay.
 */
export interface InboxItem extends UserWord {
  user_word_created: boolean;
  replayed: boolean;
}

export interface UserWordPatch {
  personal_phonetic?: string | null;
  status?: WordStatus;
  familiarity?: Familiarity | null;
  note?: string | null;
}

/** Query string for the library list endpoint. */
export interface WordListParams {
  q?: string;
  status?: WordStatus;
  source_id?: Uuid;
  familiarity?: number;
  page?: number;
  page_size?: number;
  sort?: WordSort;
}

export type WordSort =
  | 'created_at:desc'
  | 'created_at:asc'
  | 'lemma:asc'
  | 'familiarity:desc'
  | 'due:asc';

/** Capture (POST /inbox only — no word-creation route is assumed). */
export interface InboxCreate {
  text: string;
  source_id?: Uuid | null;
  encounter_type?: string | null;
  context?: string | null;
  note?: string | null;
  /** Idempotency key — mandatory. */
  client_event_id: Uuid;
}

export interface InboxListParams {
  q?: string;
  status?: WordStatus;
  page?: number;
  page_size?: number;
}

/* ------------------------------------------------------------------ */
/* senses                                                             */
/* ------------------------------------------------------------------ */

export interface SenseCreate {
  part_of_speech?: string | null;
  definition_zh?: string;
  definition_en?: string;
}

export interface SensePatch {
  part_of_speech?: string | null;
  definition_zh?: string;
  definition_en?: string;
  sort_order?: number;
}

/* ------------------------------------------------------------------ */
/* sources                                                            */
/* ------------------------------------------------------------------ */

export type SourceType = 'school' | 'ielts' | 'cet4' | 'exam' | 'reading' | 'manual' | 'other';

export interface Source {
  id: Uuid;
  type: SourceType;
  name: string;
  description: string | null;
  /** Null while the source is in use. */
  archived_at: IsoDateTime | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface SourceCreate {
  type?: SourceType;
  name: string;
  description?: string | null;
}

/** PATCH body: entity fields, plus an `archived` boolean the API translates. */
export type SourcePatch = Partial<SourceCreate> & { archived?: boolean };

/* ------------------------------------------------------------------ */
/* encounters                                                         */
/* ------------------------------------------------------------------ */

export interface Encounter {
  id: Uuid;
  user_word_id: Uuid;
  surface_text: string;
  source: Source | null;
  source_id: Uuid | null;
  type: string | null;
  context: string | null;
  note: string | null;
  encountered_at: IsoDateTime;
  created_at: IsoDateTime;
}

/** Encounters are append-only; idempotency key is mandatory. */
export interface EncounterCreate {
  user_word_id: Uuid;
  surface_text?: string | null;
  source_id?: Uuid | null;
  type?: string | null;
  context?: string | null;
  note?: string | null;
  client_event_id: Uuid;
}

/* ------------------------------------------------------------------ */
/* reviews                                                            */
/* ------------------------------------------------------------------ */

export interface ReviewCard {
  /** Aggregation primary key — the USER WORD id (top-level on the wire). */
  id: Uuid;
  user_word_id: Uuid;
  lemma: string;
  personal_phonetic: string | null;
  status: WordStatus;
  familiarity: Familiarity | null;
  senses: Sense[];
  /** The SRS card; `/review-cards/{card.id}/reviews` targets this id. */
  card: {
    id: Uuid;
    state: CardState;
    difficulty: number;
    stability_days: number;
    due_at: IsoDateTime | null;
    lapse_count: number;
    review_count: number;
    last_review_at: IsoDateTime | null;
    suspended_at: IsoDateTime | null;
    version: number;
  };
}

export interface ReviewQueue {
  items: ReviewCard[];
  total: number;
}

export type ReviewRating = 'again' | 'hard' | 'good' | 'easy';

export interface ReviewSubmission {
  rating: ReviewRating;
  client_event_id: Uuid;
  /** Echo the card version shown in the prompt; a mismatch is a 409 conflict. */
  expected_card_version: number;
}

export interface ReviewResult {
  card: CardInfo;
}

/* ------------------------------------------------------------------ */
/* daily sheets                                                       */
/* ------------------------------------------------------------------ */

export type SheetTemplate = 'compact' | 'test';
export type PaperSize = 'a4' | 'a5';
export type SheetColumns = 1 | 2;

/** The configuration REQUEST body keeps the selection params. */
export interface DailySheetConfig {
  template: SheetTemplate;
  paper_size: PaperSize;
  columns: SheetColumns;
  review_count: number;
  new_count: number;
  source_ids: Uuid[];
}

export type SheetSectionKind = 'review' | 'new';

export interface SheetEntryWord {
  lemma: string;
  personal_phonetic: string | null;
  part_of_speech: string | null;
  definition_zh: string;
  definition_en: string;
}

export interface DailySheetSection {
  kind: SheetSectionKind;
  words: SheetEntryWord[];
}

export interface DailySheetPreview {
  config: DailySheetConfig;
  sections: DailySheetSection[];
  word_total: number;
}

export interface SheetSnapshotItem {
  kind: SheetSectionKind;
  lemma: string;
  personal_phonetic: string | null;
  part_of_speech: string | null;
  definition_zh: string | null;
  definition_en: string | null;
}

/** Summary carries no status/error/count columns; counts may be derived. */
export interface DailySheetSummary {
  id: Uuid;
  sheet_date: string;
  timezone_snapshot: string;
  template: SheetTemplate;
  paper_size: PaperSize;
  columns: SheetColumns;
  /** Optional response-only fields derived from items. */
  actual_review_count?: number;
  actual_new_count?: number;
  created_at: IsoDateTime;
}

export interface DailySheetDetail extends DailySheetSummary {
  items?: SheetSnapshotItem[];
  preview?: DailySheetPreview | null;
  /** Populated instead when the backend returns raw sheet HTML. */
  html?: string | null;
}

/* ------------------------------------------------------------------ */
/* settings & stats                                                   */
/* ------------------------------------------------------------------ */

/** Field names are fixed by the API (no `default_` prefix). */
export interface UserSettings {
  timezone: string;
  daily_template: SheetTemplate;
  paper_size: PaperSize;
  columns: SheetColumns;
  review_count: number;
  new_count: number;
}

export const DEFAULT_USER_SETTINGS: UserSettings = {
  timezone: 'UTC',
  daily_template: 'compact',
  paper_size: 'a4',
  columns: 2,
  review_count: 20,
  new_count: 10,
};

export type UserSettingsPatch = Partial<UserSettings>;

export interface Stats {
  words_total: number;
  /** keyed by WordStatus */
  words_by_status: Partial<Record<WordStatus, number>>;
  due_today: number;
  reviewed_today: number;
  inbox_open: number;
  sources_total: number;
  streak_days: number;
}

/* ------------------------------------------------------------------ */
/* pagination                                                         */
/* ------------------------------------------------------------------ */

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  has_more: boolean;
}
