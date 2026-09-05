/**
 * Typed endpoint surface (approved model). Every function maps 1:1 to one
 * HTTP call through the shared core (single-flight refresh lives there),
 * normalizing responses into the canonical types.
 *
 * There are NO assumed routes: inbox status transitions (active/known/
 * archive) use `PATCH /user-words/:id { status }`, and new words are only
 * ever created server-side through `POST /inbox`.
 */
import type { LexoriaCore, RequestOptions } from './http';
import {
  normalizeEncounter,
  normalizeInboxItem,
  normalizeList,
  normalizePage,
  normalizeReviewCard,
  normalizeSense,
  normalizeSettings,
  normalizeSheetDetail,
  normalizeSheetPreview,
  normalizeSheetSummary,
  normalizeSource,
  normalizeStats,
  normalizeUserWord,
  pickAccessToken,
  pickUser,
} from './normalize';
import type {
  AccessTokens,
  AuthSession,
  DailySheetConfig,
  DailySheetDetail,
  DailySheetPreview,
  DailySheetSummary,
  Encounter,
  EncounterCreate,
  InboxCreate,
  InboxItem,
  InboxListParams,
  LoginRequest,
  Page,
  RegisterRequest,
  ReviewQueue,
  ReviewResult,
  ReviewSubmission,
  Sense,
  SenseCreate,
  SensePatch,
  Source,
  SourceCreate,
  SourcePatch,
  Stats,
  User,
  UserSettings,
  UserSettingsPatch,
  UserWord,
  UserWordPatch,
  WordListParams,
} from './types';

export interface LexoriaApi {
  readonly auth: {
    /** POST auth/register — may return a User; the client then logs in. */
    register(body: RegisterRequest): Promise<void>;
    /** POST auth/login — `identifier` (username or email) + password. */
    login(body: LoginRequest): Promise<AuthSession>;
    logout(): Promise<void>;
    /** POST auth/refresh — cookie-based; returns a fresh access token. */
    refresh(): Promise<AccessTokens>;
  };
  readonly me: {
    get(): Promise<User>;
  };
  readonly settings: {
    get(): Promise<UserSettings>;
    update(patch: UserSettingsPatch): Promise<UserSettings>;
  };
  readonly inbox: {
    /** POST inbox — capture. Returns the (aggregate) user-word row. */
    create(body: InboxCreate): Promise<InboxItem>;
    list(params?: InboxListParams): Promise<Page<InboxItem>>;
  };
  readonly words: {
    list(params?: WordListParams): Promise<Page<UserWord>>;
    get(id: string): Promise<UserWord>;
    /** PATCH user-words/:id — also carries inbox transitions via `status`. */
    update(id: string, patch: UserWordPatch): Promise<UserWord>;
  };
  readonly senses: {
    create(userWordId: string, body: SenseCreate): Promise<Sense>;
    update(senseId: string, patch: SensePatch): Promise<Sense>;
    remove(senseId: string): Promise<void>;
  };
  readonly sources: {
    list(): Promise<Source[]>;
    create(body: SourceCreate): Promise<Source>;
    update(id: string, patch: SourcePatch): Promise<Source>;
  };
  readonly encounters: {
    /** Append-only; `client_event_id` is mandatory for idempotency. */
    create(body: EncounterCreate): Promise<Encounter>;
    forWord(userWordId: string): Promise<Encounter[]>;
  };
  readonly reviews: {
    /** GET reviews/today — due cards of active words. */
    today(): Promise<ReviewQueue>;
    /** POST review-cards/:id/reviews — 409 on `expected_card_version` mismatch. */
    submit(cardId: string, body: ReviewSubmission): Promise<ReviewResult>;
  };
  readonly dailySheets: {
    preview(config: DailySheetConfig): Promise<DailySheetPreview | { html: string }>;
    create(config: DailySheetConfig): Promise<DailySheetSummary>;
    list(): Promise<Page<DailySheetSummary>>;
    get(id: string): Promise<DailySheetDetail>;
    /** Authenticated blob download of the rendered PDF. */
    pdf(id: string): Promise<Blob>;
  };
  readonly stats: {
    get(): Promise<Stats>;
  };
}

export function createEndpoints(core: LexoriaCore): LexoriaApi {
  const call = <T>(opts: RequestOptions): Promise<T> => core.request<T>(opts);

  const auth = {
    register: (body: RegisterRequest) => call<void>({ method: 'POST', path: 'auth/register', body, auth: false }),
    login: async (body: LoginRequest) => {
      const raw = await call<unknown>({ method: 'POST', path: 'auth/login', body, auth: false });
      const user = pickUser(raw);
      const token = pickAccessToken(raw);
      if (!user || !token) {
        throw new Error('登录响应格式不正确');
      }
      return { access_token: token, user } as AuthSession;
    },
    logout: () => call<void>({ method: 'POST', path: 'auth/logout', auth: false }),
    refresh: async () => {
      const raw = await call<unknown>({ method: 'POST', path: 'auth/refresh', auth: false });
      const token = pickAccessToken(raw);
      if (!token) throw new Error('刷新令牌响应格式不正确');
      return { access_token: token } as AccessTokens;
    },
  };

  const me = {
    get: async () => {
      const raw = await call<unknown>({ method: 'GET', path: 'me' });
      const user = pickUser(raw);
      if (!user) throw new Error('当前用户响应格式不正确');
      return user;
    },
  };

  const settings = {
    get: async () => normalizeSettings(await call<unknown>({ method: 'GET', path: 'settings' })),
    update: async (patch: UserSettingsPatch) =>
      normalizeSettings(await call<unknown>({ method: 'PATCH', path: 'settings', body: patch })),
  };

  const inbox = {
    create: async (body: InboxCreate) => {
      const raw = await call<unknown>({ method: 'POST', path: 'inbox', body });
      const item = normalizeInboxItem(raw);
      if (!item) throw new Error('收件箱响应格式不正确');
      return item;
    },
    list: async (params: InboxListParams = {}) => {
      const query: Record<string, string | number | undefined> = {};
      if (params.q) query.q = params.q;
      if (params.status) query.status = params.status;
      if (params.page !== undefined) query.page = params.page;
      if (params.page_size !== undefined) query.page_size = params.page_size;
      return normalizePage<InboxItem>(await call<unknown>({ method: 'GET', path: 'inbox', query }), normalizeInboxItem);
    },
  };

  const words = {
    list: async (params: WordListParams = {}) => {
      const query: Record<string, string | number | undefined> = {};
      if (params.q) query.q = params.q;
      if (params.status) query.status = params.status;
      if (params.source_id) query.source_id = params.source_id;
      if (params.familiarity !== undefined) query.familiarity = params.familiarity;
      if (params.page !== undefined) query.page = params.page;
      if (params.page_size !== undefined) query.page_size = params.page_size;
      if (params.sort) query.sort = params.sort;
      return normalizePage<UserWord>(await call<unknown>({ method: 'GET', path: 'user-words', query }), normalizeUserWord);
    },
    get: async (id: string) => {
      const raw = await call<unknown>({ method: 'GET', path: `user-words/${id}` });
      const word = normalizeUserWord(raw);
      if (!word) throw new Error('词条响应格式不正确');
      return word;
    },
    update: async (id: string, patch: UserWordPatch) => {
      const raw = await call<unknown>({ method: 'PATCH', path: `user-words/${id}`, body: patch });
      const word = normalizeUserWord(raw);
      if (!word) throw new Error('词条更新响应格式不正确');
      return word;
    },
  };

  const senses = {
    create: async (userWordId: string, body: SenseCreate) => {
      const raw = await call<unknown>({ method: 'POST', path: `user-words/${userWordId}/senses`, body });
      const sense = normalizeSense(raw);
      if (!sense) throw new Error('义项响应格式不正确');
      return sense;
    },
    update: async (senseId: string, patch: SensePatch) => {
      const raw = await call<unknown>({ method: 'PATCH', path: `user-word-senses/${senseId}`, body: patch });
      const sense = normalizeSense(raw);
      if (!sense) throw new Error('义项更新响应格式不正确');
      return sense;
    },
    remove: (senseId: string) => call<void>({ method: 'DELETE', path: `user-word-senses/${senseId}` }),
  };

  const sources = {
    list: async () =>
      normalizeList<Source>(await call<unknown>({ method: 'GET', path: 'sources' }), normalizeSource),
    create: async (body: SourceCreate) => {
      const raw = await call<unknown>({ method: 'POST', path: 'sources', body });
      const source = normalizeSource(raw);
      if (!source) throw new Error('来源创建响应格式不正确');
      return source;
    },
    update: async (id: string, patch: SourcePatch) => {
      const raw = await call<unknown>({ method: 'PATCH', path: `sources/${id}`, body: patch });
      const source = normalizeSource(raw);
      if (!source) throw new Error('来源更新响应格式不正确');
      return source;
    },
  };

  const encounters = {
    create: async (body: EncounterCreate) => {
      const raw = await call<unknown>({ method: 'POST', path: 'encounters', body });
      const encounter = normalizeEncounter(raw);
      if (!encounter) throw new Error('遇词记录响应格式不正确');
      return encounter;
    },
    forWord: async (userWordId: string) =>
      normalizeList<Encounter>(
        await call<unknown>({ method: 'GET', path: `user-words/${userWordId}/encounters` }),
        normalizeEncounter,
      ),
  };

  const reviews = {
    today: async () => {
      const raw = await call<unknown>({ method: 'GET', path: 'reviews/today' });
      const page = normalizePage(raw, normalizeReviewCard);
      return { items: page.items, total: page.total };
    },
    submit: async (cardId: string, body: ReviewSubmission) => {
      const raw = await call<unknown>({ method: 'POST', path: `review-cards/${cardId}/reviews`, body });
      const card = isCardResult(raw);
      if (!card) throw new Error('复习提交响应格式不正确');
      return { card };
    },
  };

  const dailySheets = {
    preview: async (config: DailySheetConfig) => {
      const raw = await call<unknown>({ method: 'POST', path: 'daily-sheets/preview', body: config });
      if (typeof raw === 'string') {
        return { html: raw };
      }
      const preview = normalizeSheetPreview(raw);
      if (preview) return preview;
      return { html: '' };
    },
    create: async (config: DailySheetConfig) => {
      const raw = await call<unknown>({ method: 'POST', path: 'daily-sheets', body: config });
      const summary = normalizeSheetSummary(raw);
      if (!summary) throw new Error('练习纸生成响应格式不正确');
      return summary;
    },
    list: async () =>
      normalizePage<DailySheetSummary>(await call<unknown>({ method: 'GET', path: 'daily-sheets' }), normalizeSheetSummary),
    get: async (id: string) => {
      const raw = await call<unknown>({ method: 'GET', path: `daily-sheets/${id}` });
      const detail = normalizeSheetDetail(raw);
      if (!detail) throw new Error('练习纸响应格式不正确');
      return detail;
    },
    pdf: (id: string) => call<Blob>({ method: 'GET', path: `daily-sheets/${id}/pdf`, responseType: 'blob' }),
  };

  const stats = {
    get: async () => normalizeStats(await call<unknown>({ method: 'GET', path: 'stats' })),
  };

  return { auth, me, settings, inbox, words, senses, sources, encounters, reviews, dailySheets, stats };
}

function isCardResult(raw: unknown): ReviewResult['card'] | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const rec = raw as Record<string, unknown>;
  const cardRaw = rec.card;
  if (typeof cardRaw === 'object' && cardRaw !== null && typeof (cardRaw as Record<string, unknown>).id === 'string') {
    const c = cardRaw as Record<string, unknown>;
    return {
      id: String(c.id),
      state: (String(c.state ?? 'new')) as ReviewResult['card']['state'],
      difficulty: typeof c.difficulty === 'number' ? c.difficulty : 1,
      stability_days: typeof c.stability_days === 'number' ? c.stability_days : 0,
      due_at: typeof c.due_at === 'string' ? c.due_at : null,
      lapse_count: typeof c.lapse_count === 'number' ? c.lapse_count : 0,
      review_count: typeof c.review_count === 'number' ? c.review_count : 0,
      last_review_at: typeof c.last_review_at === 'string' ? c.last_review_at : null,
      suspended_at: typeof c.suspended_at === 'string' ? c.suspended_at : null,
      version: typeof c.version === 'number' ? c.version : 1,
    };
  }
  return null;
}
