/**
 * @lexoria/api-client — thin typed HTTP client for the Lexiora API.
 *
 * Usage:
 *   import { createLexoriaApi, memoryTokenStore } from '@lexoria/api-client';
 *   export const api = createLexoriaApi({ baseUrl: '/api/v1' });
 *
 * Access tokens live in `memoryTokenStore` only; session persistence is the
 * HttpOnly refresh cookie. 401s heal via a single-flight cookie refresh and
 * the request is replayed once. See openapi/README.md for regenerating from
 * an OpenAPI document.
 */

export { createLexoriaApi, memoryTokenStore, apiRequest, LexoriaCore } from './client';
export type { LexoriaApiConfig } from './client';
export type { LexoriaApi } from './endpoints';
export { ApiError, SessionExpiredError, NetworkError, isApiError, messageOf, codeOf } from './errors';
export { newClientEventId } from './uuid';
export { DEFAULT_USER_SETTINGS } from './types';
export type * from './types';
export type { QueryParams, QueryValue, TokenStore, CoreConfig, RequestOptions, HttpMethod } from './http';
