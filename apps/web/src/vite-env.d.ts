/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** API base URL; empty string means same-origin `/api/v1`. */
  readonly VITE_API_BASE_URL?: string;
  /** Dev-server proxy target for `/api/v1` (e.g. the FastAPI backend). */
  readonly VITE_API_PROXY_TARGET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
