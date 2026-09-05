import { createLexoriaApi, type LexoriaApi } from '@lexoria/api-client';
import { emitSessionEvent } from '@/lib/session';

/**
 * Shared API client. All requests hit `/api/v1` (same origin in prod; proxied
 * by the Vite dev server, overridable with VITE_API_BASE_URL). Token is memory
 * only; refresh cookie is HttpOnly. A terminal 401 fires `expired`, which the
 * auth store observes to drop the current user.
 */
const baseUrl: string = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

export const api: LexoriaApi = createLexoriaApi({
  baseUrl,
  onSessionExpired: () => emitSessionEvent('expired'),
});

export { baseUrl };
