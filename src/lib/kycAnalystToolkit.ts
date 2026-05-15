import type { KYCRow } from "@/data/kycQuestions";

const AUDIT_KEY = "kyc_automation_audit_log_v1";
const ANALYST_NAME_KEY = "kyc_automation_analyst_name";
const URL_PRESETS_KEY = "kyc_automation_url_presets_v1";
const MAX_AUDIT_ENTRIES = 400;

export type AuditLogEntry = {
  at: string;
  action: string;
  analyst?: string;
  detail?: Record<string, unknown>;
};

export type UrlPreset = {
  id: string;
  name: string;
  urls: string[];
};

export function getAnalystName(): string {
  try {
    return localStorage.getItem(ANALYST_NAME_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setAnalystName(name: string): void {
  try {
    if (name.trim()) localStorage.setItem(ANALYST_NAME_KEY, name.trim());
    else localStorage.removeItem(ANALYST_NAME_KEY);
  } catch {
    /* ignore */
  }
}

export function appendAuditLog(entry: Omit<AuditLogEntry, "at"> & { at?: string }): void {
  try {
    const raw = localStorage.getItem(AUDIT_KEY);
    const list: AuditLogEntry[] = raw ? (JSON.parse(raw) as AuditLogEntry[]) : [];
    const next: AuditLogEntry = {
      at: entry.at ?? new Date().toISOString(),
      action: entry.action,
      analyst: entry.analyst,
      detail: entry.detail,
    };
    list.push(next);
    while (list.length > MAX_AUDIT_ENTRIES) list.shift();
    localStorage.setItem(AUDIT_KEY, JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

export function readAuditLog(): AuditLogEntry[] {
  try {
    const raw = localStorage.getItem(AUDIT_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw) as AuditLogEntry[];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function getSignOff(submissionId: string): boolean {
  try {
    return localStorage.getItem(`kyc_signoff_${submissionId}`) === "1";
  } catch {
    return false;
  }
}

export function setSignOff(submissionId: string, value: boolean): void {
  try {
    if (value) localStorage.setItem(`kyc_signoff_${submissionId}`, "1");
    else localStorage.removeItem(`kyc_signoff_${submissionId}`);
  } catch {
    /* ignore */
  }
}

function normAnswer(a: string): string {
  return a.trim().toLowerCase();
}

export function isUnansweredAnswer(a: string): boolean {
  const t = normAnswer(a);
  return !t || t === "not found";
}

export type RowDelta = {
  changed: boolean;
  tags: string[];
};

export function classifyRowDelta(current: KYCRow, prior: KYCRow | undefined): RowDelta {
  if (!prior) return { changed: false, tags: [] };
  const tags: string[] = [];
  if (normAnswer(current.answer) !== normAnswer(prior.answer)) tags.push("answer");
  if (current.validation !== prior.validation) tags.push("validation");
  if (isUnansweredAnswer(prior.answer) && !isUnansweredAnswer(current.answer)) tags.push("newly_answered");
  if (!isUnansweredAnswer(prior.answer) && isUnansweredAnswer(current.answer)) tags.push("lost_answer");
  return { changed: tags.length > 0, tags };
}

export function cloneRowsBaseline(rows: KYCRow[]): KYCRow[] {
  return JSON.parse(JSON.stringify(rows)) as KYCRow[];
}

export function loadUrlPresets(): UrlPreset[] {
  try {
    const raw = localStorage.getItem(URL_PRESETS_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw) as UrlPreset[];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function saveUrlPresets(presets: UrlPreset[]): void {
  try {
    localStorage.setItem(URL_PRESETS_KEY, JSON.stringify(presets));
  } catch {
    /* ignore */
  }
}

export function addUrlPreset(name: string, urls: string[]): UrlPreset {
  const trimmed = name.trim();
  const id =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const preset: UrlPreset = { id, name: trimmed || "Untitled bundle", urls: [...urls] };
  const list = loadUrlPresets();
  list.push(preset);
  saveUrlPresets(list);
  return preset;
}

export function deleteUrlPreset(id: string): void {
  saveUrlPresets(loadUrlPresets().filter((p) => p.id !== id));
}

const COMMENT_SNIPPETS_KEY = "kyc_automation_comment_snippets_v1";
const COMPANY_URL_PACKS_KEY = "kyc_automation_company_url_packs_v1";

export type CommentSnippet = { id: string; label: string; text: string };
export type CompanyUrlPack = { companyKey: string; urls: string[] };

export function defaultCommentSnippets(): CommentSnippet[] {
  return [
    {
      id: "sn-10k",
      label: "Needs 10-K citation",
      text: "Cite SEC Form 10-K section / exhibit; verify fiscal year.",
    },
    {
      id: "sn-third",
      label: "Third-party only",
      text: "Answer derived from third-party sources only — request primary filing.",
    },
  ];
}

export function loadCommentSnippets(): CommentSnippet[] {
  try {
    const raw = localStorage.getItem(COMMENT_SNIPPETS_KEY);
    if (!raw) return defaultCommentSnippets();
    const list = JSON.parse(raw) as CommentSnippet[];
    return Array.isArray(list) && list.length ? list : defaultCommentSnippets();
  } catch {
    return defaultCommentSnippets();
  }
}

export function saveCommentSnippets(list: CommentSnippet[]): void {
  try {
    localStorage.setItem(COMMENT_SNIPPETS_KEY, JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

export function loadCompanyUrlPacks(): CompanyUrlPack[] {
  try {
    const raw = localStorage.getItem(COMPANY_URL_PACKS_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw) as CompanyUrlPack[];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function saveCompanyUrlPack(companyKey: string, urls: string[]): void {
  const key = companyKey.trim().toLowerCase();
  if (!key) return;
  const list = loadCompanyUrlPacks().filter((p) => p.companyKey !== key);
  list.push({ companyKey: key, urls: [...urls] });
  try {
    localStorage.setItem(COMPANY_URL_PACKS_KEY, JSON.stringify(list));
  } catch {
    /* ignore */
  }
}
