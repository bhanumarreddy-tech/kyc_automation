import { apiUrl } from "@/lib/api";
import type {
  ChunkBoundariesResponse,
  RagFilterSandboxResult,
  RagObservabilityResponse,
  RagStrategyCompareResult,
} from "@/types/ragObservability";

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

export async function fetchRagFilterSandbox(
  submissionId: string,
  options: {
    serialNo: number;
    minDense?: number;
    minLexical?: number;
    minFused?: number;
    recall?: boolean;
  },
): Promise<RagFilterSandboxResult> {
  const params = new URLSearchParams({
    serialNo: String(options.serialNo),
  });
  if (options.minDense != null) params.set("minDense", String(options.minDense));
  if (options.minLexical != null) params.set("minLexical", String(options.minLexical));
  if (options.minFused != null) params.set("minFused", String(options.minFused));
  if (options.recall) params.set("recall", "true");
  const url = apiUrl(
    `/api/history/${submissionId}/rag-filter-sandbox?${params.toString()}`,
  );
  const res = await fetch(url);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Filter sandbox failed (${res.status})`);
  }
  return res.json() as Promise<RagFilterSandboxResult>;
}

export async function fetchRagStrategyCompare(
  submissionId: string,
  serialNo: number,
): Promise<RagStrategyCompareResult> {
  const url = apiUrl(
    `/api/history/${submissionId}/rag-compare?serialNo=${serialNo}`,
  );
  const res = await fetch(url);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Strategy compare failed (${res.status})`);
  }
  return res.json() as Promise<RagStrategyCompareResult>;
}

export async function fetchChunkBoundaries(
  submissionId: string,
  documentId?: string,
): Promise<ChunkBoundariesResponse> {
  const params = new URLSearchParams();
  if (documentId) params.set("documentId", documentId);
  const qs = params.toString();
  const url = apiUrl(
    `/api/history/${submissionId}/chunk-boundaries${qs ? `?${qs}` : ""}`,
  );
  const res = await fetch(url);
  if (!res.ok) {
    const detail = await res.text().catch(() => "");
    throw new Error(detail || `Chunk boundaries failed (${res.status})`);
  }
  return res.json() as Promise<ChunkBoundariesResponse>;
}
