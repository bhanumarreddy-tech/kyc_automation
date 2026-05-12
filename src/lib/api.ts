/**

 * Optional: set in `.env.production` / build env when the API lives on another

 * origin. No trailing slash.

 *

 * Examples:

 * - Same-origin (Docker Compose nginx proxy): leave unset → `/api/...`.

 * - Split hosts: `VITE_API_BASE_URL=https://your-api.example.com`

 */

const configuredBackend = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim();



/**

 * Build a fully-qualified API URL.

 *

 * - `vite dev`: relative `/api/...` → Vite proxy → localhost:8000.

 * - production: `VITE_API_BASE_URL` if set; otherwise relative `/api/...`

 *   (same browser origin — use with a reverse proxy or CDN routing).

 */

export function apiUrl(path: string): string {

  const suffix = path.startsWith("/") ? path : `/${path}`;

  if (import.meta.env.DEV) {

    return suffix;

  }

  if (configuredBackend && configuredBackend.length > 0) {

    return `${configuredBackend.replace(/\/$/, "")}${suffix}`;

  }

  return suffix;

}


