/** Error model shared with the UI. Mirrors the unified JSON error envelope. */

export interface ErrorEnvelope {
  code?: string;
  message?: string;
  detail?: string;
  details?: unknown;
}

export type ErrorDetails = Record<string, unknown> | null;

export class ApiError extends Error {
  readonly status: number;
  /** Server-provided machine code (e.g. `version_conflict`, `duplicate`). */
  readonly code: string | null;
  readonly details: ErrorDetails;
  /** Raw response body when it could be captured. */
  readonly body: unknown;

  constructor(status: number, message: string, opts?: { code?: string | null; details?: ErrorDetails; body?: unknown }) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = opts?.code ?? null;
    this.details = opts?.details ?? null;
    this.body = opts?.body;
  }
}

/** Raised when a 401 could not be healed by the single-flight refresh. */
export class SessionExpiredError extends ApiError {
  constructor() {
    super(401, '登录状态已失效，请重新登录', { code: 'session_expired' });
    this.name = 'SessionExpiredError';
  }
}

/** Fetch-level failure (offline, DNS, CORS, …): status 0. */
export class NetworkError extends ApiError {
  constructor(cause: unknown) {
    super(0, '网络请求失败，请检查连接后重试', {
      code: 'network_error',
      details: cause instanceof Error ? { reason: cause.message } : null,
    });
    this.name = 'NetworkError';
  }
}

export function isApiError(err: unknown): err is ApiError {
  return err instanceof ApiError;
}

/**
 * Extract the most informative message/code out of an unknown error so the
 * UI can render one line (used by toasts, inline errors and tests).
 */
export function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return '发生未知错误';
}

/** Extract an error `code` (machine readable) when present. */
export function codeOf(err: unknown): string | null {
  if (err instanceof ApiError) return err.code;
  return null;
}
