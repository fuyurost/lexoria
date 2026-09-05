/**
 * Tolerant decoders: normalize raw JSON into the canonical types in `types.ts`
 * (approved model). Unknown/missing fields degrade to safe defaults.
 */
import type {
  CardInfo,
  CardState,
  DailySheetDetail,
  DailySheetPreview,
  DailySheetSummary,
  Encounter,
  Familiarity,
  InboxItem,
  Page,
  ReviewCard,
  Sense,
  SheetColumns,
  SheetEntryWord,
  Source,
  SourceType,
  Stats,
  User,
  UserSettings,
  UserWord,
  WordStatus,
  SheetSnapshotItem,
} from './types';
import { DEFAULT_USER_SETTINGS } from './types';

export function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

export function asStr(v: unknown, fallback: string | null = null): string | null {
  return typeof v === 'string' ? v : fallback;
}

export function asNum(v: unknown, fallback = 0): number {
  return typeof v === 'number' && Number.isFinite(v) ? v : fallback;
}

export function asBool(v: unknown, fallback = false): boolean {
  return typeof v === 'boolean' ? v : fallback;
}

function asUuid(v: unknown): string | null {
  return typeof v === 'string' && v.length > 0 ? v : null;
}

/* ------------------------------------------------------------------ */

export function pickAccessToken(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  const direct = asStr(payload.access_token) ?? asStr(payload.token);
  if (direct) return direct;
  if (isRecord(payload.data)) {
    return asStr(payload.data.access_token) ?? asStr(payload.data.token);
  }
  return null;
}

export function pickUser(payload: unknown): User | null {
  if (!isRecord(payload)) return null;
  const candidate: unknown = isRecord(payload.user)
    ? payload.user
    : payload.data && isRecord(payload.data) && isRecord(payload.data.user)
      ? payload.data.user
      : payload;
  if (!isRecord(candidate)) return null;
  const id = asUuid(candidate.id);
  if (!id) return null;
  return {
    id,
    username: asStr(candidate.username, '') ?? '',
    email: asStr(candidate.email, '') ?? '',
    created_at: asStr(candidate.created_at, new Date().toISOString()) ?? new Date().toISOString(),
  };
}

/* ------------------------------------------------------------------ */

const WORD_STATUSES: WordStatus[] = ['inbox', 'active', 'known', 'archived'];
const FAMILIARITIES = [0, 1, 2, 3, 4, 5] as const;

const CARD_STATES = ['new', 'learning', 'review', 'relearning'] as const;

export function normalizeCard(raw: unknown): CardInfo | null {
  if (!isRecord(raw)) return null;
  const id = asUuid(raw.id);
  if (!id) return null;
  const stateRaw = asStr(raw.state);
  const state: CardState = CARD_STATES.includes(stateRaw as CardState) ? (stateRaw as CardState) : asNum(raw.review_count, 0) > 0 ? 'review' : 'new';
  return {
    id,
    state,
    difficulty: asNum(raw.difficulty, 1),
    stability_days: asNum(raw.stability_days),
    due_at: asStr(raw.due_at),
    lapse_count: asNum(raw.lapse_count),
    review_count: asNum(raw.review_count),
    last_review_at: asStr(raw.last_review_at),
    suspended_at: asStr(raw.suspended_at),
    version: asNum(raw.version, 1),
  };
}

export function normalizeSense(raw: unknown): Sense | null {
  if (!isRecord(raw)) return null;
  const id = asUuid(raw.id);
  if (!id) return null;
  const user_word_id = asUuid(raw.user_word_id);
  if (!user_word_id) return null;
  return {
    id,
    user_word_id,
    part_of_speech: asStr(raw.part_of_speech),
    definition_zh: asStr(raw.definition_zh, '') ?? '',
    definition_en: asStr(raw.definition_en, '') ?? '',
    sort_order: asNum(raw.sort_order),
    created_at: asStr(raw.created_at, new Date().toISOString()) ?? new Date().toISOString(),
    updated_at: asStr(raw.updated_at, new Date().toISOString()) ?? new Date().toISOString(),
  };
}

const SOURCE_TYPES = ['school', 'ielts', 'cet4', 'exam', 'reading', 'manual', 'other'] as const;

export function normalizeSource(raw: unknown): Source | null {
  if (!isRecord(raw)) return null;
  const id = asUuid(raw.id);
  if (!id) return null;
  const now = new Date().toISOString();
  const typeRaw = asStr(raw.type);
  const type: SourceType = SOURCE_TYPES.includes(typeRaw as SourceType) ? (typeRaw as SourceType) : 'other';
  return {
    id,
    type,
    name: asStr(raw.name, '') ?? '',
    description: asStr(raw.description),
    archived_at: asStr(raw.archived_at),
    created_at: asStr(raw.created_at, now) ?? now,
    updated_at: asStr(raw.updated_at, now) ?? now,
  };
}

export function normalizeUserWord(raw: unknown): UserWord | null {
  if (!isRecord(raw)) return null;
  const id = asUuid(raw.id);
  if (!id) return null;
  const now = new Date().toISOString();
  const created_at = asStr(raw.created_at, now) ?? now;
  const updated_at = asStr(raw.updated_at, now) ?? now;
  const statusRaw = asStr(raw.status, 'inbox');
  const status: WordStatus = WORD_STATUSES.includes(statusRaw as WordStatus) ? (statusRaw as WordStatus) : 'inbox';
  const famRaw = raw.familiarity === null || raw.familiarity === undefined ? null : asNum(raw.familiarity, -1);
  const familiarity: Familiarity | null =
    famRaw !== null && FAMILIARITIES.includes(famRaw as Familiarity) ? (famRaw as Familiarity) : null;
  const rawSenses = Array.isArray(raw.senses) ? raw.senses : [];
  const senses: Sense[] = rawSenses.map(normalizeSense).filter((s): s is Sense => s !== null);
  const recentRaw = Array.isArray(raw.recent_sources) ? raw.recent_sources : null;
  const recent_sources = recentRaw
    ? recentRaw
        .map((r) => {
          if (!isRecord(r)) return null;
          const sid = asUuid(r.id) ?? asUuid(r.source_id);
          const name = asStr(r.name);
          if (!sid || !name) return null;
          return { id: sid, name };
        })
        .filter((s): s is { id: string; name: string } => s !== null)
    : undefined;
  return {
    id,
    word_id: asUuid(raw.word_id) ?? '',
    lemma: asStr(raw.lemma, '') ?? '',
    normalized_lemma: asStr(raw.normalized_lemma) ?? (asStr(raw.lemma, '') ?? '').toLocaleLowerCase(),
    personal_phonetic: asStr(raw.personal_phonetic),
    status,
    familiarity,
    note: asStr(raw.note),
    card: isRecord(raw.card) ? normalizeCard(raw.card) : null,
    senses,
    first_seen_at: asStr(raw.first_seen_at, created_at) ?? created_at,
    last_seen_at: asStr(raw.last_seen_at),
    encounter_count: asNum(raw.encounter_count),
    recent_sources: recent_sources && recent_sources.length ? recent_sources : undefined,
    created_at,
    updated_at,
  };
}

/** Inbox rows are the same aggregate + capture outcome flags. */
export function normalizeInboxItem(raw: unknown): InboxItem | null {
  const word = normalizeUserWord(raw);
  if (!word) return null;
  return {
    ...word,
    user_word_created: isRecord(raw) ? asBool(raw.user_word_created) : false,
    replayed: isRecord(raw) ? asBool(raw.replayed) : false,
  };
}

export function normalizeEncounter(raw: unknown): Encounter | null {
  if (!isRecord(raw)) return null;
  const id = asUuid(raw.id);
  if (!id) return null;
  const created_at = asStr(raw.created_at, new Date().toISOString()) ?? new Date().toISOString();
  return {
    id,
    user_word_id: asUuid(raw.user_word_id) ?? '',
    surface_text: asStr(raw.surface_text, '') ?? '',
    source: isRecord(raw.source) ? normalizeSource(raw.source) : null,
    source_id: asUuid(raw.source_id),
    type: asStr(raw.type),
    context: asStr(raw.context),
    note: asStr(raw.note),
    encountered_at: asStr(raw.encountered_at, created_at) ?? created_at,
    created_at,
  };
}

/* ------------------------------------------------------------------ */

export function normalizeReviewCard(raw: unknown): ReviewCard | null {
  if (!isRecord(raw)) return null;
  const word = isRecord(raw.word) ? normalizeUserWord(raw.word) : null;
  const cardRaw = isRecord(raw.card) ? raw.card : {};
  // Aggregation semantics: the top-level `id` IS the user-word id; the
  // review-cards/:id route targets the NESTED card id.
  const userWordId =
    asUuid(raw.user_word_id) ?? asUuid(raw.id) ?? asUuid(raw.word_id) ?? asUuid(word ? word.id : null) ?? '';
  const cardId = asUuid(cardRaw.id) ?? asUuid(raw.review_card_id) ?? '';
  if (!cardId) return null;
  const sensesRaw = Array.isArray(raw.senses)
    ? raw.senses
    : word && word.senses.length
      ? word.senses
      : Array.isArray(raw.word_senses)
        ? raw.word_senses
        : [];
  const senses: Sense[] = sensesRaw.map(normalizeSense).filter((s): s is Sense => s !== null);
  const lemma = asStr(raw.lemma ?? (word ? word.lemma : ''), '') ?? '';
  const famRaw = raw.familiarity === null || raw.familiarity === undefined
    ? word ? word.familiarity : null
    : asNum(raw.familiarity, -1);
  const familiarity: Familiarity | null =
    famRaw !== null && FAMILIARITIES.includes(famRaw as Familiarity) ? (famRaw as Familiarity) : null;
  const statusRaw = asStr(raw.status ?? (word ? word.status : null), 'active');
  const status: WordStatus = WORD_STATUSES.includes(statusRaw as WordStatus) ? (statusRaw as WordStatus) : 'active';
  const cardStateRaw = asStr(cardRaw.state);
  const cardState: CardState =
    CARD_STATES.includes(cardStateRaw as CardState) ? (cardStateRaw as CardState) : asNum(cardRaw.review_count, 0) > 0 ? 'review' : 'new';
  return {
    id: userWordId,
    user_word_id: userWordId,
    lemma,
    personal_phonetic: asStr(raw.personal_phonetic ?? raw.phonetic ?? (word ? word.personal_phonetic : null)),
    status,
    familiarity,
    senses,
    card: {
      id: cardId,
      state: cardState,
      difficulty: asNum(cardRaw.difficulty, 1),
      stability_days: asNum(cardRaw.stability_days),
      due_at: asStr(cardRaw.due_at),
      lapse_count: asNum(cardRaw.lapse_count),
      review_count: asNum(cardRaw.review_count),
      last_review_at: asStr(cardRaw.last_review_at),
      suspended_at: asStr(cardRaw.suspended_at),
      version: asNum(cardRaw.version, 1),
    },
  };
}

/* ------------------------------------------------------------------ */

/** Accepts `{ items, total, … }`, `{ data: [...] }`, or a bare array. */
export function normalizePage<T>(
  raw: unknown,
  item: (r: unknown) => T | null,
): Page<T> {
  let itemsRaw: unknown[] | null = null;
  let total = 0;
  let page = 1;
  let pageSize = 20;
  if (Array.isArray(raw)) {
    itemsRaw = raw;
  } else if (isRecord(raw)) {
    for (const key of ['items', 'data', 'words', 'cards'] as const) {
      const v = raw[key];
      if (Array.isArray(v)) {
        itemsRaw = v;
        break;
      }
    }
    if (typeof raw.total === 'number') total = raw.total;
    if (typeof raw.page === 'number') page = raw.page;
    if (typeof raw.page_size === 'number') pageSize = raw.page_size;
  }
  if (!itemsRaw) itemsRaw = [];
  const items: T[] = itemsRaw.map(item).filter((x): x is T => x !== null);
  const resolvedTotal = total > 0 ? total : items.length;
  const hasMore = !Array.isArray(raw) && isRecord(raw) ? asBool(raw.has_more, page * pageSize < resolvedTotal) : false;
  return { items, page, page_size: pageSize, total: resolvedTotal, has_more: hasMore };
}

export function normalizeList<T>(raw: unknown, item: (r: unknown) => T | null): T[] {
  return normalizePage(raw, item).items;
}

/* ------------------------------------------------------------------ */

export function normalizeSettings(raw: unknown): UserSettings {
  if (!isRecord(raw)) return { ...DEFAULT_USER_SETTINGS };
  const templateRaw = asStr(raw.daily_template, DEFAULT_USER_SETTINGS.daily_template);
  const template = templateRaw === 'test' ? 'test' : 'compact';
  const sizeRaw = asStr(raw.paper_size, DEFAULT_USER_SETTINGS.paper_size);
  const paper_size = sizeRaw === 'a5' ? 'a5' : 'a4';
  const colsRaw = asNum(raw.columns, DEFAULT_USER_SETTINGS.columns);
  const columns: SheetColumns = colsRaw === 1 ? 1 : 2;
  return {
    timezone: asStr(raw.timezone, DEFAULT_USER_SETTINGS.timezone) ?? DEFAULT_USER_SETTINGS.timezone,
    daily_template: template,
    paper_size,
    columns,
    review_count: asNum(raw.review_count, DEFAULT_USER_SETTINGS.review_count),
    new_count: asNum(raw.new_count, DEFAULT_USER_SETTINGS.new_count),
  };
}

/* ------------------------------------------------------------------ */

export function normalizeStats(raw: unknown): Stats {
  const fallback: Stats = {
    words_total: 0,
    words_by_status: {},
    due_today: 0,
    reviewed_today: 0,
    inbox_open: 0,
    sources_total: 0,
    streak_days: 0,
  };
  if (!isRecord(raw)) return fallback;
  const words = isRecord(raw.words) ? raw.words : {};
  const byStatusRaw = isRecord(raw.words_by_status)
    ? raw.words_by_status
    : isRecord(words.by_status)
      ? words.by_status
      : {};
  const byStatus: Partial<Record<WordStatus, number>> = {};
  for (const key of Object.keys(byStatusRaw)) {
    if (WORD_STATUSES.includes(key as WordStatus)) byStatus[key as WordStatus] = asNum(byStatusRaw[key]);
  }
  return {
    words_total: asNum(raw.words_total, asNum(words.total)),
    words_by_status: byStatus,
    due_today: asNum(raw.due_today),
    reviewed_today: asNum(raw.reviewed_today),
    inbox_open: asNum(raw.inbox_open),
    sources_total: asNum(raw.sources_total),
    streak_days: asNum(raw.streak_days),
  };
}

/* ------------------------------------------------------------------ */

const RATINGS: Array<'again' | 'hard' | 'good' | 'easy'> = ['again', 'hard', 'good', 'easy'];

export function normalizeRating(raw: unknown): 'again' | 'hard' | 'good' | 'easy' | null {
  return RATINGS.includes(raw as 'again') ? (raw as 'again' | 'hard' | 'good' | 'easy') : null;
}

export function normalizeSheetConfig(raw: unknown): DailySheetPreview['config'] | null {
  if (!isRecord(raw)) return null;
  const templateRaw = asStr(raw.template);
  const template = templateRaw === 'test' || templateRaw === 'compact' ? templateRaw : null;
  if (!template) return null;
  const paperRaw = asStr(raw.paper_size);
  const paper_size = paperRaw === 'a4' || paperRaw === 'a5' ? paperRaw : null;
  if (!paper_size) return null;
  const colsRaw = asNum(raw.columns, 1);
  const columns: SheetColumns = colsRaw === 1 ? 1 : 2;
  const sourceIdsRaw = Array.isArray(raw.source_ids) ? raw.source_ids : [];
  return {
    template,
    paper_size,
    columns,
    review_count: asNum(raw.review_count),
    new_count: asNum(raw.new_count),
    source_ids: sourceIdsRaw.filter((x): x is string => typeof x === 'string'),
  };
}

export function normalizeSheetWord(raw: unknown): SheetEntryWord | null {
  if (!isRecord(raw)) return null;
  const lemma = asStr(raw.lemma ?? raw.word ?? raw.text);
  if (!lemma) return null;
  return {
    lemma,
    personal_phonetic: asStr(raw.personal_phonetic ?? raw.phonetic),
    part_of_speech: asStr(raw.part_of_speech),
    definition_zh: asStr(raw.definition_zh, '') ?? asStr(raw.definition, '') ?? '',
    definition_en: asStr(raw.definition_en, '') ?? '',
  };
}

export function normalizeSheetPreview(raw: unknown): DailySheetPreview | null {
  if (!isRecord(raw)) return null;
  const config = normalizeSheetConfig(raw.config ?? raw);
  if (!config) return null;
  const sectionsRaw = Array.isArray(raw.sections) ? raw.sections : [];
  const sections: DailySheetPreview['sections'] = [];
  for (const secRaw of sectionsRaw) {
    if (!isRecord(secRaw)) continue;
    const kindRaw = asStr(secRaw.kind);
    if (kindRaw !== 'review' && kindRaw !== 'new') continue;
    const wordsRaw = Array.isArray(secRaw.words) ? secRaw.words : [];
    const mapped: Array<SheetEntryWord | null> = wordsRaw.map(normalizeSheetWord);
    const words = mapped.filter((w): w is SheetEntryWord => w !== null);
    sections.push({ kind: kindRaw as 'review' | 'new', words });
  }
  const counted = sections.reduce((n, s) => n + s.words.length, 0);
  return {
    config,
    sections,
    word_total: asNum(raw.word_total, counted),
  };
}

export function normalizeSheetSummary(raw: unknown): DailySheetSummary | null {
  if (!isRecord(raw)) return null;
  const id = asUuid(raw.id);
  if (!id) return null;
  const templateRaw = asStr(raw.template, 'compact');
  const paperRaw = asStr(raw.paper_size, 'a4');
  const colsRaw = asNum(raw.columns, 1);
  return {
    id,
    sheet_date: asStr(raw.sheet_date, '') ?? '',
    timezone_snapshot: asStr(raw.timezone_snapshot, 'UTC') ?? 'UTC',
    template: templateRaw === 'test' ? 'test' : 'compact',
    paper_size: paperRaw === 'a5' ? 'a5' : 'a4',
    columns: colsRaw === 1 ? 1 : 2,
    actual_review_count: typeof raw.actual_review_count === 'number' ? raw.actual_review_count : undefined,
    actual_new_count: typeof raw.actual_new_count === 'number' ? raw.actual_new_count : undefined,
    created_at: asStr(raw.created_at, new Date().toISOString()) ?? new Date().toISOString(),
  };
}

export function normalizeSheetSnapshotItem(raw: unknown): SheetSnapshotItem | null {
  if (!isRecord(raw)) return null;
  const lemma = asStr(raw.lemma ?? raw.word ?? raw.text);
  if (!lemma) return null;
  const kindRaw = asStr(raw.kind, 'review');
  return {
    kind: kindRaw === 'new' ? 'new' : 'review',
    lemma,
    personal_phonetic: asStr(raw.personal_phonetic ?? raw.phonetic),
    part_of_speech: asStr(raw.part_of_speech),
    definition_zh: asStr(raw.definition_zh, null) ?? asStr(raw.definition, null),
    definition_en: asStr(raw.definition_en, null),
  };
}

export function normalizeSheetDetail(raw: unknown): DailySheetDetail | null {
  const summary = normalizeSheetSummary(raw);
  if (!summary) return null;
  if (!isRecord(raw)) return { ...summary };
  const itemsRaw = Array.isArray(raw.items) ? raw.items : [];
  const mapped: Array<SheetSnapshotItem | null> = itemsRaw.map(normalizeSheetSnapshotItem);
  const items = mapped.filter((x): x is SheetSnapshotItem => x !== null);
  return {
    ...summary,
    items: items.length ? items : undefined,
    preview: isRecord(raw.preview) ? normalizeSheetPreview(raw.preview) : null,
    html: typeof raw.html === 'string' ? raw.html : null,
  };
}
