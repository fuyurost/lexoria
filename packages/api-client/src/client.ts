/**
 * Public entry points: configure a single shared client, plus a tiny
 * memory-backed token store (the app keeps access tokens in memory only;
 * the refresh cookie is HttpOnly and managed by the browser/server).
 */
import { createEndpoints, type LexoriaApi } from './endpoints';
import { LexoriaCore, type CoreConfig, type TokenStore } from './http';
import type { RequestOptions } from './http';

export type { CoreConfig, TokenStore, RequestOptions } from './http';
export { LexoriaCore } from './http';

export interface LexoriaApiConfig {
  /** API base; include the version prefix, e.g. `/api/v1` or a full origin. */
  baseUrl: string;
  /** Access-token store; defaults to the shared memory store. */
  tokenStore?: TokenStore;
  fetchImpl?: typeof fetch;
  /** Fired when a 401 could not be healed (session truly expired). */
  onSessionExpired?: () => void;
}

/** Process-wide in-memory token store — the default for the web app. */
export const memoryTokenStore: TokenStore = (() => {
  let token: string | null = null;
  return {
    read: () => token,
    write: (t: string) => {
      token = t;
    },
    clear: () => {
      token = null;
    },
  };
})();

/** The configured core shared by the hand-written client AND regenerated code. */
let activeCore: LexoriaCore | null = null;

/**
 * Configure (once) and return the typed API surface. Idempotent: later calls
 * return the same endpoint objects bound to the original core.
 */
export function createLexoriaApi(config: LexoriaApiConfig): LexoriaApi {
  if (!activeCore) {
    activeCore = new LexoriaCore({
      baseUrl: config.baseUrl,
      tokenStore: config.tokenStore ?? memoryTokenStore,
      fetchImpl: config.fetchImpl,
      onSessionExpired: config.onSessionExpired,
    });
  }
  // Subsequent calls (e.g. from tests or hot module reload) reuse the same
  // configured core so refresh state and tokens stay consistent.
  return createEndpoints(activeCore);
}

/**
 * Low-level typed request against the configured core. Used by the
 * OpenAPI-regenerated client (`openapi/`) so it inherits refresh, cookies
 * and error normalization without reimplementing them.
 */
export function apiRequest<T>(opts: RequestOptions): Promise<T> {
  if (!activeCore) throw new Error('createLexoriaApi() 必须先于 apiRequest 调用');
  return activeCore.request<T>(opts);
}
