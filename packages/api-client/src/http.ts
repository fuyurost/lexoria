/**
 * Low-level HTTP core.
 *
 * - Bearer token is attached from an injectable store (memory in the web app).
 * - The refresh cookie is HttpOnly and never touches JS; every request sends
 *   `credentials: 'include'`.
 * - A 401 on a non-auth request triggers ONE single-flight `POST auth/refresh`
 *   (concurrent 401s share the same in-flight promise) and replays the request
 *   once. If the refresh fails the session is cleared and `onSessionExpired`
 *   fires.
 * - Errors are normalized into `ApiError` (unified JSON error envelope).
 */
import { ApiError, NetworkError, SessionExpiredError } from './errors';
import { isRecord } from './normalize';

export type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

export type QueryValue = string | number | boolean | string[] | null | undefined;
export type QueryParams = Record<string, QueryValue>;

export interface RequestOptions {
  method: HttpMethod;
  /** Path relative to `baseUrl` (which already includes `/api/v1`). */
  path: string;
  query?: QueryParams;
  body?: unknown;
  /** Whether the request carries the session and may trigger refresh. */
  auth?: boolean;
  /** Response handling: parse JSON, return a Blob, or keep raw text. */
  responseType?: 'json' | 'blob' | 'text';
  headers?: Record<string, string>;
}

export interface TokenStore {
  read(): string | null;
  write(token: string): void;
  clear(): void;
}

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface CoreConfig {
  /** e.g. `''` (same origin, `/api/v1`) or `https://api.example.com/api/v1`. */
  baseUrl: string;
  tokenStore: TokenStore;
  fetchImpl?: FetchLike;
  /** Invoked exactly when a 401 could not be healed by refresh. */
  onSessionExpired?: () => void;
  /** Injectable for tests. */
  now?: () => Date;
  refreshPath?: string;
}

function firstString(...vals: unknown[]): string | null {
  for (const v of vals) if (typeof v === 'string') return v;
  return null;
}

function extractErrorEnvelope(payload: unknown): { code: string | null; message: string | null; details: Record<string, unknown> | null } {
  if (!isRecord(payload)) return { code: null, message: null, details: null };
  // Accepted shapes: { error: { code, message, details } } | { code, message, detail(s) }
  const err = isRecord(payload.error) ? payload.error : null;
  const code = typeof (err ? err.code : payload.code) === 'string' ? String((err ? err.code : payload.code)) : null;
  const message = err ? firstString(err.detail, err.details, err.message) : firstString(payload.detail, payload.details, payload.message);
  const details = err && isRecord(err.details) ? err.details : isRecord(payload.details) ? payload.details : null;
  return { code, message, details };
}

function fallbackMessage(status: number, method: string, path: string): string {
  if (status === 401) return '登录状态无效或已过期';
  if (status === 403) return '没有权限执行此操作';
  if (status === 404) return '请求的资源不存在';
  if (status === 409) return '数据版本冲突，请刷新后重试';
  if (status >= 500) return '服务器开小差了，请稍后重试';
  return `请求失败（HTTP ${status}）· ${method} ${path}`;
}

export class LexoriaCore {
  private readonly baseUrl: string;
  private readonly tokenStore: TokenStore;
  private readonly fetchImpl: FetchLike;
  readonly onSessionExpired: (() => void) | undefined;
  private readonly refreshPath: string;
  /** Single-flight refresh promise shared by every concurrent 401. */
  private inflightRefresh: Promise<boolean> | null = null;

  constructor(config: CoreConfig) {
    this.baseUrl = config.baseUrl.replace(/\/+$/, '');
    this.tokenStore = config.tokenStore;
    this.fetchImpl = config.fetchImpl ?? globalThis.fetch.bind(globalThis);
    this.onSessionExpired = config.onSessionExpired;
    this.refreshPath = config.refreshPath ?? 'auth/refresh';
  }

  private isAuthRoute(path: string): boolean {
    return path === this.refreshPath || path.startsWith('auth/');
  }

  private buildUrl(path: string, query?: QueryParams): string {
    const url = `${this.baseUrl}/${path}`;
    if (!query) return url;
    const parts: string[] = [];
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      if (Array.isArray(value)) {
        for (const v of value) {
          if (v === undefined || v === null) continue;
          parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(v))}`);
        }
      } else {
        parts.push(`${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
      }
    }
    return parts.length ? `${url}?${parts.join('&')}` : url;
  }

  private async rawFetch(opts: RequestOptions, headers: Headers): Promise<Response> {
    const { method, path, query, body } = opts;
    if (body !== undefined) headers.set('Content-Type', 'application/json');
    const init: RequestInit = {
      method,
      headers,
      credentials: 'include',
      body: body !== undefined ? JSON.stringify(body) : undefined,
    };
    try {
      return await this.fetchImpl(this.buildUrl(path, query), init);
    } catch (err) {
      throw new NetworkError(err);
    }
  }

  private async readErrorPayload(res: Response): Promise<{ payload: unknown; text: string }> {
    const text = await res.text();
    let payload: unknown = text;
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = text;
    }
    return { payload, text };
  }

  /** POST auth/refresh once. Returns whether a new access token was stored. */
  private async attemptRefresh(): Promise<boolean> {
    const headers = new Headers({ Accept: 'application/json' });
    const res = await this.rawFetch(
      { method: 'POST', path: this.refreshPath, auth: false, responseType: 'json' },
      headers,
    );
    if (!res.ok) return false;
    let payload: unknown = null;
    const text = await res.text();
    try {
      payload = text ? JSON.parse(text) : null;
    } catch {
      payload = null;
    }
    const token = extractAccessToken(payload);
    if (!token) return false;
    this.tokenStore.write(token);
    return true;
  }

  /** Single-flight wrapper over `attemptRefresh`. */
  private refreshToken(): Promise<boolean> {
    if (this.inflightRefresh) return this.inflightRefresh;
    const run = this.attemptRefresh().finally(() => {
      this.inflightRefresh = null;
    });
    this.inflightRefresh = run;
    return run;
  }

  /** Public for tests/edge callers: force a cookie-based refresh. */
  refreshNow(): Promise<boolean> {
    return this.refreshToken();
  }

  private async toError(res: Response, path: string, method: HttpMethod): Promise<ApiError> {
    const { payload } = await this.readErrorPayload(res);
    const env = extractErrorEnvelope(payload);
    const message = env.message ?? fallbackMessage(res.status, method, path);
    return new ApiError(res.status, message, { code: env.code, details: env.details, body: payload });
  }

  async request<T>(opts: RequestOptions): Promise<T> {
    const { method, path, responseType = 'json', auth = true, headers: extraHeaders } = opts;
    const authRoute = this.isAuthRoute(path);

    for (let attempt = 0; attempt < 2; attempt++) {
      const headers = new Headers({ Accept: responseType === 'blob' ? 'application/pdf, application/octet-stream' : 'application/json' });
      if (extraHeaders) for (const [k, v] of Object.entries(extraHeaders)) headers.set(k, v);
      const token = this.tokenStore.read();
      if (token && auth && !authRoute) headers.set('Authorization', `Bearer ${token}`);

      const res = await this.rawFetch(opts, headers);

      if (res.status === 401 && auth && !authRoute && attempt === 0) {
        const healed = await this.refreshToken();
        if (healed) continue;
        this.tokenStore.clear();
        this.onSessionExpired?.();
        throw new SessionExpiredError();
      }

      if (!res.ok) throw await this.toError(res, path, method);

      if (res.status === 204) return undefined as T;
      if (responseType === 'blob') return (await res.blob()) as T;
      if (responseType === 'text') return (await res.text()) as T;
      const text = await res.text();
      if (!text) return undefined as T;
      return JSON.parse(text) as T;
    }
    // Unreachable: the loop either returns or throws.
    throw new SessionExpiredError();
  }
}

function extractAccessToken(payload: unknown): string | null {
  if (!isRecord(payload)) return null;
  if (typeof payload.access_token === 'string') return payload.access_token;
  if (typeof payload.token === 'string') return payload.token;
  if (isRecord(payload.data)) {
    if (typeof payload.data.access_token === 'string') return payload.data.access_token;
    if (typeof payload.data.token === 'string') return payload.data.token;
  }
  return null;
}
