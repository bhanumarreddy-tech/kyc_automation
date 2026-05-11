/**
 * Hardcoded base URL for the deployed FastAPI backend.
 *
 * Replace this with the real backend origin once the FastAPI service is
 * deployed (Render / Railway / Fly.io / Cloud Run / etc.). No trailing
 * slash.
 */
const PROD_BACKEND_URL = "https://CHANGE_ME.example.com";

/**
 * Build a fully-qualified API URL.
 *
 * In dev (`vite dev`) this returns a relative path like `/api/process`
 * so Vite's proxy in `vite.config.ts` can forward it to the local
 * FastAPI server on :8000. In a production build it prefixes the path
 * with `PROD_BACKEND_URL` so the deployed SPA can reach the separately
 * hosted backend.
 */
export function apiUrl(path: string): string {
  const suffix = path.startsWith("/") ? path : `/${path}`;
  if (import.meta.env.DEV) {
    return suffix;
  }
  return `${PROD_BACKEND_URL.replace(/\/$/, "")}${suffix}`;
}
