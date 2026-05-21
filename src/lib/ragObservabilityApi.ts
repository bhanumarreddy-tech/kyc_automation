import { apiUrl } from "@/lib/api";
import type { RagObservabilityResponse } from "@/types/ragObservability";

export async function fetchRagObservability(
  submissionId: string,
): Promise<RagObservabilityResponse> {
  const res = await fetch(apiUrl(`/api/history/${submissionId}/rag-observability`));
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Failed to load RAG observability (${res.status})`);
  }
  return res.json() as Promise<RagObservabilityResponse>;
}
