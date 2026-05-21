import { apiUrl } from "@/lib/api";
import type { KYCRow } from "@/data/kycQuestions";
import { hydrateKycRows } from "@/data/kycQuestions";

export type JobSnapshot = {
  jobId: string;
  status: string;
  phase: string;
  detail: string;
  answerCompleted: number;
  answerTotal: number;
  validateCompleted: number;
  validateTotal: number;
};

export type ProcessJobResult = {
  rows: KYCRow[];
  submissionId?: string | null;
  savedAt?: string | null;
  durationMs?: number | null;
  attachedDocuments?: {
    filename: string;
    sizeBytes?: number | null;
    contentType?: string;
    objectKey?: string | null;
  }[];
  referenceUrls?: string[];
  pipelineErrors?: { sectionNo: number; phase: string; message: string; errorId: string }[];
  intelligence?: Record<string, unknown> | null;
};

function parseJobSnapshot(raw: Record<string, unknown>): JobSnapshot {
  return {
    jobId: String(raw.jobId ?? ""),
    status: String(raw.status ?? ""),
    phase: String(raw.phase ?? ""),
    detail: String(raw.detail ?? ""),
    answerCompleted: Number(raw.answerCompleted ?? 0) || 0,
    answerTotal: Number(raw.answerTotal ?? 8) || 8,
    validateCompleted: Number(raw.validateCompleted ?? 0) || 0,
    validateTotal: Number(raw.validateTotal ?? 64) || 64,
  };
}

export async function subscribeProcessJob(
  jobId: string,
  onUpdate: (snap: JobSnapshot) => void,
  opts?: { intervalMs?: number; signal?: AbortSignal },
): Promise<ProcessJobResult> {
  const intervalMs = opts?.intervalMs ?? 700;
  const url = apiUrl(`/api/process/jobs/${encodeURIComponent(jobId)}`);

  for (;;) {
    if (opts?.signal?.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    const res = await fetch(url);
    if (!res.ok) {
      const t = await res.text();
      throw new Error(t || `Job poll failed (${res.status})`);
    }
    const envelope = (await res.json()) as {
      job?: Record<string, unknown>;
      result?: Record<string, unknown>;
      error?: string;
    };
    const jRaw = envelope.job as Record<string, unknown> | undefined;
    if (jRaw) {
      onUpdate(parseJobSnapshot(jRaw));
    }
    const j = jRaw ? parseJobSnapshot(jRaw) : null;
    if (envelope.error && j?.status === "failed") {
      throw new Error(envelope.error);
    }
    if (j?.status === "completed" && envelope.result) {
      const r = envelope.result as {
        rows?: unknown[];
        submissionId?: string;
        savedAt?: string;
        durationMs?: number;
        attachedDocuments?: ProcessJobResult["attachedDocuments"];
        referenceUrls?: string[];
        pipelineErrors?: ProcessJobResult["pipelineErrors"];
        intelligence?: ProcessJobResult["intelligence"];
      };
      if (!r.rows || !Array.isArray(r.rows)) {
        throw new Error("Invalid job result: missing rows");
      }
      return {
        rows: hydrateKycRows(r.rows as unknown[]),
        submissionId: r.submissionId ?? null,
        savedAt: r.savedAt ?? null,
        durationMs: r.durationMs ?? null,
        attachedDocuments: r.attachedDocuments,
        referenceUrls: r.referenceUrls,
        pipelineErrors: r.pipelineErrors,
        intelligence: r.intelligence ?? null,
      };
    }
    if (j?.status === "failed") {
      throw new Error(envelope.error || "Pipeline job failed");
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

export async function pollProcessJobUntilDone(
  jobId: string,
  opts?: { intervalMs?: number; signal?: AbortSignal },
): Promise<ProcessJobResult> {
  return subscribeProcessJob(jobId, () => {}, opts);
}

export async function startProcessJob(formData: FormData): Promise<string> {
  const res = await fetch(apiUrl("/api/process/async"), {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || `Start job failed (${res.status})`);
  }
  const data = (await res.json()) as { jobId?: string };
  if (!data.jobId) throw new Error("No jobId returned");
  return data.jobId;
}

export async function startRerunJob(formData: FormData): Promise<string> {
  const res = await fetch(apiUrl("/api/process/rerun/async"), {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || `Start rerun job failed (${res.status})`);
  }
  const data = (await res.json()) as { jobId?: string };
  if (!data.jobId) throw new Error("No jobId returned");
  return data.jobId;
}

export async function cancelProcessJob(jobId: string): Promise<void> {
  await fetch(apiUrl(`/api/process/jobs/${encodeURIComponent(jobId)}/cancel`), {
    method: "POST",
  });
}

export async function fetchProcessJobStatus(jobId: string): Promise<{
  job: JobSnapshot;
  error?: string;
}> {
  const res = await fetch(apiUrl(`/api/process/jobs/${encodeURIComponent(jobId)}`));
  if (!res.ok) {
    const t = await res.text();
    throw new Error(t || `Job status failed (${res.status})`);
  }
  const envelope = (await res.json()) as {
    job?: Record<string, unknown>;
    error?: string;
  };
  const raw = envelope.job as Record<string, unknown>;
  return { job: parseJobSnapshot(raw), error: envelope.error };
}
