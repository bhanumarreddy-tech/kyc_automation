/// <reference types="vite/client" />



interface ImportMetaEnv {

  /**

   * Production API origin (no trailing slash). When unset, requests use

   * relative `/api/...` (same origin as the SPA).

   */

  readonly VITE_API_BASE_URL?: string;

}

