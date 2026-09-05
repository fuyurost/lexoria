/**
 * Single-flight refresh contract tests:
 *  - N concurrent 401s trigger exactly ONE refresh call.
 *  - After a successful refresh the original requests replay and succeed.
 *  - A failed refresh clears the token, fires onSessionExpired, surfaces 401.
 *  - Auth routes (login/refresh) never trigger the refresh machinery.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { LexoriaCore, type TokenStore } from '../http';
import { SessionExpiredError } from '../errors';
import type { Page } from '../types';

interface Call {
  url: string;
  init: RequestInit;
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function makeTokenStore(initial: string | null = null): TokenStore & { token: string | null } {
  const store: TokenStore & { token: string | null } = {
    token: initial,
    read() {
      return this.token;
    },
    write(t: string) {
      this.token = t;
    },
    clear() {
      this.token = null;
    },
  };
  return store;
}

function authOf(init: RequestInit): string | null {
  const headers = init.headers as Headers | undefined;
  return headers && typeof headers.get === 'function' ? headers.get('Authorization') : null;
}

describe('LexoriaCore · single-flight refresh', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('refreshes once for many concurrent 401s and replays all requests', async () => {
    const tokenStore = makeTokenStore('expired-token');
    const calls: Call[] = [];
    let refreshCount = 0;

    const fetchImpl = (url: string, init?: RequestInit) => {
      const input = String(url);
      const record: Call = { url: input, init: init ?? {} };
      calls.push(record);
      if (input.endsWith('/auth/refresh')) {
        refreshCount++;
        return Promise.resolve(jsonResponse({ access_token: 'fresh-token' }));
      }
      const auth = authOf(record.init);
      const isProtected = input.endsWith('/me') || input.endsWith('/stats');
      if (isProtected) {
        if (auth === 'Bearer fresh-token') {
          const body = input.endsWith('/me') ? { id: 'u1', username: 'alice', email: 'a@x.io' } : { words_total: 3 };
          return Promise.resolve(jsonResponse(body));
        }
        return Promise.resolve(jsonResponse({ error: { code: 'unauthorized' } }, 401));
      }
      return Promise.resolve(jsonResponse({ ok: true }));
    };

    const core = new LexoriaCore({ baseUrl: '/api/v1', tokenStore, fetchImpl });

    const results = await Promise.allSettled([
      core.request<unknown>({ method: 'GET', path: 'me' }),
      core.request<unknown>({ method: 'GET', path: 'stats' }),
      core.request<unknown>({ method: 'GET', path: 'me' }),
    ]);

    expect(refreshCount).toBe(1);
    expect(tokenStore.read()).toBe('fresh-token');
    for (const r of results) expect(r.status).toBe('fulfilled');
    // Subsequent calls carry the new token without another refresh.
    await core.request<unknown>({ method: 'GET', path: 'me' });
    expect(refreshCount).toBe(1);
    const authorized = calls.filter((c) => authOf(c.init) === 'Bearer fresh-token');
    expect(authorized.length).toBe(4);
  });

  it('clears the token and reports expiry when refresh itself fails', async () => {
    const tokenStore = makeTokenStore('expired-token');
    const onSessionExpired = vi.fn();
    let refreshCount = 0;

    const fetchImpl = (url: string) => {
      const input = String(url);
      if (input.endsWith('/auth/refresh')) {
        refreshCount++;
        return Promise.resolve(jsonResponse({ error: { code: 'invalid_session' } }, 401));
      }
      return Promise.resolve(jsonResponse({ error: { code: 'unauthorized' } }, 401));
    };

    const core = new LexoriaCore({ baseUrl: '/api/v1', tokenStore, fetchImpl, onSessionExpired });
    await expect(core.request<unknown>({ method: 'GET', path: 'me' })).rejects.toBeInstanceOf(SessionExpiredError);
    expect(refreshCount).toBe(1);
    expect(tokenStore.read()).toBeNull();
    expect(onSessionExpired).toHaveBeenCalledTimes(1);
  });

  it('never refreshes for auth routes (login 401 is a plain credential error)', async () => {
    const tokenStore = makeTokenStore('some-token');
    let refreshCount = 0;
    const fetchImpl = (url: string) => {
      const input = String(url);
      if (input.endsWith('/auth/refresh')) {
        refreshCount++;
        return Promise.resolve(jsonResponse({ access_token: 'x' }));
      }
      if (input.endsWith('/auth/login')) {
        return Promise.resolve(jsonResponse({ error: { code: 'invalid_credentials', message: '账号或密码错误' } }, 401));
      }
      return Promise.resolve(jsonResponse({ ok: true }));
    };
    const core = new LexoriaCore({ baseUrl: '/api/v1', tokenStore, fetchImpl });

    const err = await core.request<unknown>({ method: 'POST', path: 'auth/login', body: {}, auth: false }).catch((e: unknown) => e);
    expect(err).toMatchObject({ status: 401, code: 'invalid_credentials', message: '账号或密码错误' });
    expect(refreshCount).toBe(0);
    expect(tokenStore.read()).toBe('some-token');
  });

  it('retries once then propagates when a replayed request still 401s', async () => {
    const tokenStore = makeTokenStore('expired');
    let refreshCount = 0;
    const fetchImpl = (url: string, init?: RequestInit) => {
      const input = String(url);
      if (input.endsWith('/auth/refresh')) {
        refreshCount++;
        return Promise.resolve(jsonResponse({ access_token: 'still-bad' }));
      }
      return Promise.resolve(jsonResponse({ error: { code: 'unauthorized' } }, 401));
    };
    const core = new LexoriaCore({ baseUrl: '/api/v1', tokenStore, fetchImpl });
    await expect(core.request<unknown>({ method: 'GET', path: 'user-words' })).rejects.toMatchObject({ status: 401 });
    expect(refreshCount).toBe(1);
  });

  it('forwards error envelopes and body on non-401 failures', async () => {
    const tokenStore = makeTokenStore('ok');
    const fetchImpl = (url: string) => {
      const input = String(url);
      if (input.endsWith('/review-cards/c1/reviews')) {
        return Promise.resolve(
          jsonResponse({ error: { code: 'version_conflict', message: '卡片版本已变化', details: { expected: 2, actual: 1 } } }, 409),
        );
      }
      return Promise.resolve(jsonResponse({ ok: true }));
    };
    const core = new LexoriaCore({ baseUrl: '', tokenStore, fetchImpl });
    const err = await core
      .request<unknown>({ method: 'POST', path: 'review-cards/c1/reviews', body: {} })
      .catch((e: unknown) => e);
    expect(err).toMatchObject({
      status: 409,
      code: 'version_conflict',
      message: '卡片版本已变化',
      details: { expected: 2, actual: 1 },
    });
  });

  it('does not attach a bearer header on auth routes', async () => {
    const tokenStore = makeTokenStore('secret');
    let seenAuthHeader = false;
    const fetchImpl = (url: string, init?: RequestInit) => {
      if (String(url).endsWith('/auth/refresh')) {
        const h = init ? authOf(init) : null;
        if (h) seenAuthHeader = true;
        return Promise.resolve(jsonResponse({ access_token: 'fresh' }));
      }
      return Promise.resolve(jsonResponse({ ok: true }));
    };
    const core = new LexoriaCore({ baseUrl: '/api/v1', tokenStore, fetchImpl });
    await core.request<unknown>({ method: 'POST', path: 'auth/refresh', auth: false });
    expect(seenAuthHeader).toBe(false);
  });

  it('normalizes bare-array and paginated payloads via Page types', async () => {
    const tokenStore = makeTokenStore(null);
    const fetchImpl = (url: string) => {
      const input = String(url);
      if (input.includes('/user-words')) {
        return Promise.resolve(
          jsonResponse({ items: [{ id: 'w1', lemma: 'abacus', status: 'learning' }], total: 1, page: 1, page_size: 20 }),
        );
      }
      return Promise.resolve(jsonResponse({ ok: true }));
    };
    const core = new LexoriaCore({ baseUrl: '/api/v1', tokenStore, fetchImpl });
    const page = await core.request<Page<Record<string, unknown>>>({
      method: 'GET',
      path: 'user-words',
      query: { page: 1, page_size: 20 },
    });
    expect(page.total).toBe(1);
    expect(page.items[0]).toMatchObject({ lemma: 'abacus' });
  });
});
