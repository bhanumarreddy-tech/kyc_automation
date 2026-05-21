import { apiUrl } from "@/lib/api";

/** Build a download URL for a stored submission attachment. */
export function attachmentDownloadUrl(submissionId: string, objectKey: string): string {
  const q = new URLSearchParams({ objectKey });
  return apiUrl(
    `/api/history/${encodeURIComponent(submissionId)}/attachments/download?${q.toString()}`,
  );
}

/** Format pipeline duration for display in history and run summaries. */
export function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms) || ms < 0) {
    return "—";
  }
  if (ms < 1000) {
    return `${ms} ms`;
  }
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${seconds}s`;
}

/** One URL per line; trim, drop empties, preserve first-seen order (matches backend). */
export function parseReferenceUrlsFromText(raw: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    const u = line.trim();
    if (!u || seen.has(u)) continue;
    seen.add(u);
    out.push(u);
  }
  return out;
}
