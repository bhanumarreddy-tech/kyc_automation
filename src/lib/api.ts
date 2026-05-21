/**
 * Optional: set in `.env.development` / `.env.production` when the API lives on
 * another origin. No trailing slash.
 *
 * Examples:
 * - Same-origin (Docker Compose nginx proxy): leave unset → `/api/...`.
 * - Split hosts: `VITE_API_BASE_URL=https://your-api.example.com`
 */
const configuredBackend = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();

/**
 * Build a fully-qualified API URL.
 *
 * - `VITE_API_BASE_URL` set: absolute origin + path (e.g. staging Railway).
 * - unset in dev: relative `/api/...` → Vite proxy → localhost:8000.
 * - unset in production: relative `/api/...` (same origin / reverse proxy).
 */
export function apiUrl(path: string): string {
  const suffix = path.startsWith("/") ? path : `/${path}`;

  if (configuredBackend && configuredBackend.length > 0) {
    return `${configuredBackend.replace(/\/$/, "")}${suffix}`;
  }

  return suffix;
}
