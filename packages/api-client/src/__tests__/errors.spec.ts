import { describe, expect, it } from 'vitest';
import { ApiError, codeOf, isApiError, messageOf, SessionExpiredError, NetworkError } from '../errors';
import { newClientEventId } from '../uuid';
import { normalizePage, normalizeUserWord, normalizeStats, normalizeSettings, normalizeSheetSummary, normalizeSheetDetail } from '../normalize';
import { DEFAULT_USER_SETTINGS } from '../types';

describe('errors', () => {
  it('carries status/code/details from a unified envelope', () => {
    const err = new ApiError(409, 'boom', { code: 'version_conflict', details: { a: 1 } });
    expect(err.status).toBe(409);
    expect(err.code).toBe('version_conflict');
    expect(err.details).toEqual({ a: 1 });
    expect(isApiError(err)).toBe(true);
    expect(isApiError(new Error('x'))).toBe(false);
  });

  it('exposes stable messages and codes for the UI', () => {
    expect(messageOf(new ApiError(500, '服务器错误'))).toBe('服务器错误');
    expect(messageOf(new Error('plain'))).toBe('plain');
    expect(messageOf('junk')).toBe('发生未知错误');
    expect(codeOf(new ApiError(409, 'x', { code: 'version_conflict' }))).toBe('version_conflict');
    expect(codeOf(new Error('x'))).toBeNull();
  });

  it('differentiates expired sessions and network failures', () => {
    const expired = new SessionExpiredError();
    expect(expired.status).toBe(401);
    expect(expired.code).toBe('session_expired');
    const net = new NetworkError(new TypeError('fetch failed'));
    expect(net.status).toBe(0);
    expect(net.code).toBe('network_error');
  });
});

describe('newClientEventId', () => {
  it('produces valid v4 UUIDs', () => {
    const seen = new Set<string>();
    for (let i = 0; i < 50; i++) {
      const id = newClientEventId();
      expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
      seen.add(id);
    }
    expect(seen.size).toBe(50);
  });
});

describe('normalizers', () => {
  it('fills safe defaults for missing word fields', () => {
    const word = normalizeUserWord({ id: 'w1', lemma: 'serendipity', senses: undefined, card: undefined });
    expect(word).not.toBeNull();
    expect(word!.senses).toEqual([]);
    expect(word!.card).toBeNull();
    expect(word!.personal_phonetic).toBeNull();
    expect(word!.familiarity).toBeNull();
    expect(word!.status).toBe('inbox');
    expect(word!.normalized_lemma).toBe('serendipity');
    expect(word!.encounter_count).toBe(0);
  });

  it('accepts the full status/familiarity enum ranges and drops unknown ones', () => {
    for (const status of ['inbox', 'active', 'known', 'archived']) {
      expect(normalizeUserWord({ id: 'x', lemma: 'x', status })!.status).toBe(status);
    }
    expect(normalizeUserWord({ id: 'x', lemma: 'x', status: 'learning' })!.status).toBe('inbox');
    for (const f of [0, 1, 2, 3, 4, 5]) {
      expect(normalizeUserWord({ id: 'x', lemma: 'x', familiarity: f })!.familiarity).toBe(f);
    }
    expect(normalizeUserWord({ id: 'x', lemma: 'x', familiarity: 9 })!.familiarity).toBeNull();
  });

  it('tolerates bare arrays and nested wrappers for pages/lists', () => {
    const bare = normalizePage([{ id: 'w1' }], (r) => (typeof r === 'object' && r !== null ? { ok: true } : null));
    expect(bare.items.length).toBe(1);
    const wrapped = normalizePage({ data: [{ id: 'w1' }], total: 3, page: 1, page_size: 10 }, (r) =>
      typeof r === 'object' && r !== null ? { ok: true } : null,
    );
    expect(wrapped.total).toBe(3);
  });

  it('normalizes stats from nested and flat shapes with the new status keys', () => {
    const flat = normalizeStats({ words_total: 10, words_by_status: { inbox: 4, active: 6 }, due_today: 2 });
    expect(flat.words_total).toBe(10);
    expect(flat.words_by_status.inbox).toBe(4);
    expect(flat.words_by_status.active).toBe(6);
    expect(flat.due_today).toBe(2);
    const nested = normalizeStats({ words: { total: 7, by_status: { known: 7 } } });
    expect(nested.words_total).toBe(7);
    expect(nested.words_by_status.known).toBe(7);
  });

  it('clamps settings to the allowed option sets (no default_ prefix)', () => {
    const s = normalizeSettings({
      timezone: 'Asia/Shanghai',
      daily_template: 'weird',
      paper_size: 'a3',
      columns: 3,
    });
    expect(s.timezone).toBe('Asia/Shanghai');
    expect(s.daily_template).toBe('compact');
    expect(s.paper_size).toBe('a4');
    expect(s.columns).toBe(2);
    expect(s.review_count).toBe(DEFAULT_USER_SETTINGS.review_count);
    expect(s).not.toHaveProperty('default_sheet_template');
  });

  it('normalizes card fields of the approved model', () => {
    const word = normalizeUserWord({
      id: 'w1',
      lemma: 'x',
      card: { id: 'c1', difficulty: 1.8, stability_days: 3, due_at: null, lapse_count: 2, review_count: 7, last_review_at: null, suspended_at: null, version: 4 },
    });
    expect(word!.card).toMatchObject({ difficulty: 1.8, stability_days: 3, review_count: 7, version: 4 });
    expect(word!.card).not.toHaveProperty('ease');
    expect(word!.card).not.toHaveProperty('interval_days');
  });

  it('normalizes sheet summaries without status/error/count columns', () => {
    const s = normalizeSheetSummary({ id: 'd1', sheet_date: '2026-09-05', timezone_snapshot: 'Asia/Shanghai', template: 'test', paper_size: 'a5', columns: 1, actual_review_count: 8, created_at: '2026-09-05T00:00:00Z' });
    expect(s).toMatchObject({ template: 'test', paper_size: 'a5', columns: 1, sheet_date: '2026-09-05', actual_review_count: 8 });
    expect(s).not.toHaveProperty('status');
    expect(s).not.toHaveProperty('error');
    const detail = normalizeSheetDetail({ ...s, items: [{ kind: 'review', lemma: 'ephemeral', definition_zh: '短暂的' }] });
    expect(detail?.items?.[0]).toMatchObject({ lemma: 'ephemeral', definition_zh: '短暂的' });
  });
});
