/// <reference types="vite/client" />

interface ImportMetaEnv {
    /** Base URL for the backend API. Defaults to `/api` at the call sites. */
    readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
    readonly env: ImportMetaEnv;
}
