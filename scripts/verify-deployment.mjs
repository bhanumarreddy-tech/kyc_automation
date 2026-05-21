/**
 * Split-deploy smoke checks: Workers static SPA vs FastAPI backend.
 *
 * Profiles (recommended):
 *   npm run smoke:staging
 *   npm run smoke:production
 *
 * Or pass a profile name:
 *   node scripts/verify-deployment.mjs staging
 *
 * Override individual targets:
 *   KYC_WORKERS_ORIGIN=https://...
 *   KYC_BACKEND_BASE_URL=https://xxx.up.railway.app
 */

const PROFILES = {
  production: {
    workersOrigin: "https://kycautomation.bhanu-marreddy.workers.dev",
    backendBase: "https://kycautomation-production.up.railway.app",
  },
  staging: {
    workersOrigin: "https://kyc-automation-staging.bhanu-marreddy.workers.dev",
    backendBase: "https://kycautomation-staging.up.railway.app",
  },
};

const profileName = (
  process.argv[2] ||
  process.env.KYC_DEPLOY_ENV ||
  "production"
).trim().toLowerCase();

const profile = PROFILES[profileName] || PROFILES.production;
if (!PROFILES[profileName]) {
  console.warn(`Unknown profile "${profileName}" — using production defaults.`);
}

const WORKERS_ORIGIN =
  process.env.KYC_WORKERS_ORIGIN?.replace(/\/$/, "") || profile.workersOrigin;

const BACKEND_BASE =
  process.env.KYC_BACKEND_BASE_URL?.trim().replace(/\/$/, "") ||
  profile.backendBase;

const hardFailures = [];

function note(msg) {
  console.log(`• ${msg}`);
}

function remind(msg) {
  console.warn(`! ${msg}`);
}

function warnHard(msg) {
  hardFailures.push(msg);
  console.warn(`✖ ${msg}`);
}

async function fetchText(url, init = {}) {
  const res = await fetch(url, { redirect: "follow", ...init });
  const text = await res.text();
  const ct = res.headers.get("content-type") || "";
  return { res, text, ct };
}

async function getMainJsUrl() {
  const { text, ct } = await fetchText(`${WORKERS_ORIGIN}/`);
  if (!ct.includes("text/html")) warnHard(`Workers / not HTML (${ct}).`);
  const m = text.match(/<script[^>]+src="([^"]+\.js)"/);
  if (!m) {
    warnHard("Could not find main script src on Workers index.html.");
    return null;
  }
  const scriptPath = m[1].startsWith("http") ? m[1] : `${WORKERS_ORIGIN}${m[1].startsWith("/") ? "" : "/"}${m[1]}`;
  return scriptPath;
}

async function verifyWorkersHealthTrap() {
  const { text, ct, res } = await fetchText(`${WORKERS_ORIGIN}/api/health`);
  if (ct.includes("application/json")) {
    try {
      const j = JSON.parse(text);
      if (j && j.status === "ok") {
        note("Workers /api/health returned backend-style JSON — verify this is intentional (proxy or unified host).");
        return;
      }
    } catch {
      /* fall through */
    }
  }
  if (text.trimStart().startsWith("<!")) {
    note(
      `Workers GET /api/health → HTTP ${res.status}, text/html SPA body (misleading OK for curl; not FastAPI).`
    );
    return;
  }
  warnHard(`Workers /api/health unexpected: HTTP ${res.status}, content-type=${ct}`);
}

async function verifyBundleUsesBackendBase(mainJsUrl) {
  if (!mainJsUrl) return;
  const { text } = await fetchText(mainJsUrl);

  const hasRelativeProcess =
    text.includes("/api/process") || text.includes('"/api/process"') || text.includes("'/api/process'");

  const looksLikeExternalApi =
    /https:\/\/[^\s"']+\/api\/process/i.test(text) ||
    /\.up\.railway\.app\b/i.test(text) ||
    /railway\.app\b/i.test(text);

  if (!hasRelativeProcess && !looksLikeExternalApi)
    remind("Main bundle: could not infer /api/process path (minification changed literals?).");

  if (looksLikeExternalApi) {
    const expectedHost = new URL(BACKEND_BASE).host;
    if (text.includes(expectedHost)) {
      note(`Main bundle references expected backend host (${expectedHost}).`);
    } else {
      warnHard(
        `Main bundle references an external API host but not the expected ${expectedHost} — rebuild with the matching .env file.`
      );
    }
  } else if (hasRelativeProcess) {
    warnHard(
      "Main bundle uses relative /api/process → browser calls Workers origin unless Cloudflare proxies /api to Railway (this repo wrangler assets-only does not)."
    );
  }
}

async function verifyBackendHealth() {
  const url = `${BACKEND_BASE}/api/health`;
  try {
    const { text, ct, res } = await fetchText(url);
    if (!res.ok) {
      warnHard(`Backend GET ${url} → HTTP ${res.status}`);
      return;
    }
    if (!ct.includes("application/json")) {
      warnHard(`Backend GET ${url} → not JSON (${ct}).`);
      return;
    }
    const j = JSON.parse(text);
    if (j && j.status === "ok") note(`Backend health OK: ${url}`);
    else warnHard(`Backend health JSON unexpected: ${text.slice(0, 200)}`);
  } catch (e) {
    warnHard(`Backend health request failed: ${e instanceof Error ? e.message : e}`);
  }
}

async function verifyWorkersPostToApi() {
  const form = new FormData();
  form.append("company_name", "SmokeTestCo");
  const res = await fetch(`${WORKERS_ORIGIN}/api/process`, { method: "POST", body: form });
  if (res.status === 405) {
    note("Workers POST /api/process → HTTP 405 (no FastAPI; matches split deploy without Workers /api routing).");
    return;
  }
  if (!res.ok) warnHard(`Workers POST /api/process → HTTP ${res.status}`);
  else note(`Workers POST /api/process returned HTTP ${res.status} (inspect network if unexpected).`);
}

async function main() {
  console.log(`Profile:        ${profileName}`);
  console.log(`Workers origin: ${WORKERS_ORIGIN}`);
  console.log(`Backend base:   ${BACKEND_BASE}`);
  await verifyWorkersHealthTrap();
  const mainJsUrl = await getMainJsUrl();
  if (mainJsUrl) note(`Fetched bundle: ${mainJsUrl}`);
  await verifyBundleUsesBackendBase(mainJsUrl);
  await verifyWorkersPostToApi();
  await verifyBackendHealth();

  if (hardFailures.length) {
    console.error(`\n${hardFailures.length} failure(s) — fix deploy pairing and retry.`);
    process.exitCode = 1;
  } else {
    console.log("\nSmoke checks finished (no hard failures).");
  }
}

main();
