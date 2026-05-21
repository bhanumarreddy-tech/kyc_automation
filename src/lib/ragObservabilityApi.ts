import { apiUrl } from "@/lib/api";
import type { RagObservabilityResponse } from "@/types/ragObservability";

export async function fetchRagObservability(
  submissionId: string,
  options?: { serialNo?: number; recall?: boolean },
): Promise<RagObservabilityResponse> {
  const params = new URLSearchParams();
  if (options?.serialNo != null) params.set("serialNo", String(options.serialNo));
  if (options?.recall) params.set("recall", "true");
  const qs = params.toString();
  const url = apiUrl(
    `/api/history/${submissionId}/rag-observability${qs ? `?${qs}` : ""}`,
  );
  const res = await fetch(url);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Failed to load RAG observability (${res.status})`);
  }
  return res.json() as Promise<RagObservabilityResponse>;
}
