import { useEffect, useState } from "react";
import { ExternalLink, Loader2, Sparkles } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type { KYCRow } from "@/data/kycQuestions";
import { apiUrl } from "@/lib/api";

interface SimilarMatch {
  submissionId: string;
  companyName: string;
  similarity: number;
}

interface PipelineIntelligenceStripProps {
  companyName: string;
  submissionId?: string | null;
  intelligence: Record<string, unknown> | null;
  rows: KYCRow[];
}

export function PipelineIntelligenceStrip({
  companyName,
  submissionId,
  intelligence,
  rows,
}: PipelineIntelligenceStripProps) {
  const [similar, setSimilar] = useState<SimilarMatch[]>([]);
  const [narrative, setNarrative] = useState<string | null>(null);
  const [narrBusy, setNarrBusy] = useState(false);
  const [qaSerials, setQaSerials] = useState<number[] | null>(null);
  const [qaBusy, setQaBusy] = useState(false);
  const [intelOpen, setIntelOpen] = useState(true);

  useEffect(() => {
    const q = companyName.trim();
    if (q.length < 2) {
      setSimilar([]);
      return;
    }
    let cancelled = false;
    const ex = submissionId?.trim();
    const qs = new URLSearchParams({ companyName: q });
    if (ex) qs.set("excludeSubmissionId", ex);
    void fetch(apiUrl(`/api/entity-resolution/similar?${qs.toString()}`))
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        if (cancelled || !Array.isArray(data)) return;
        setSimilar(
          data
            .map((it: unknown) => {
              const o = it as Record<string, unknown>;
              return {
                submissionId: String(o.submissionId ?? ""),
                companyName: String(o.companyName ?? ""),
                similarity: Number(o.similarity ?? 0),
              };
            })
            .filter((x) => x.submissionId && x.companyName),
        );
      })
      .catch(() => {
        if (!cancelled) setSimilar([]);
      });
    return () => {
      cancelled = true;
    };
  }, [companyName, submissionId]);

  const tier =
    typeof intelligence?.riskTierSuggested === "string" ? intelligence.riskTierSuggested : null;
  const screening = intelligence?.screening as Record<string, unknown> | undefined;
  const alerts = Array.isArray(screening?.alerts) ? screening.alerts : [];
  const violations = Array.isArray(intelligence?.playbookViolations)
    ? (intelligence.playbookViolations as Record<string, unknown>[])
    : [];
  const hints = Array.isArray(intelligence?.registryHints)
    ? (intelligence.registryHints as Record<string, unknown>[])
    : [];
  const extract =
    typeof intelligence?.structuredExtractSummary === "string"
      ? intelligence.structuredExtractSummary
      : null;

  if (!intelligence && similar.length === 0) {
    return null;
  }

  const runNarrative = async () => {
    setNarrBusy(true);
    try {
      const body: Record<string, unknown> = {
        companyName: companyName.trim() || "Unknown entity",
      };
      if (submissionId?.trim()) {
        body.submissionId = submissionId.trim();
      } else {
        body.rows = rows;
      }
      const res = await fetch(apiUrl("/api/narrative"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || `Narrative failed (${res.status})`);
      }
      const data = (await res.json()) as { narrative?: string };
      setNarrative(data.narrative ?? "");
    } catch (e) {
      setNarrative(e instanceof Error ? e.message : "Narrative request failed");
    } finally {
      setNarrBusy(false);
    }
  };

  const runQaSample = async () => {
    if (!submissionId?.trim()) return;
    setQaBusy(true);
    try {
      const res = await fetch(
        apiUrl(
          `/api/history/${encodeURIComponent(submissionId.trim())}/qa-sample?n=${encodeURIComponent(
            String(8),
          )}`,
        ),
      );
      if (!res.ok) {
        const t = await res.text();
        throw new Error(t || `QA sample failed (${res.status})`);
      }
      const data = (await res.json()) as { serials?: number[] };
      setQaSerials(Array.isArray(data.serials) ? data.serials : []);
    } catch {
      setQaSerials([]);
    } finally {
      setQaBusy(false);
    }
  };

  return (
    <Collapsible open={intelOpen} onOpenChange={setIntelOpen}>
      <CollapsibleTrigger
        type="button"
        className="flex w-full items-center justify-between gap-2 rounded-md border border-input bg-muted/30 px-3 py-2 text-left text-sm shadow-sm hover:bg-accent/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <span className="font-medium">Intelligence & triage</span>
        <span className="text-muted-foreground text-xs">
          {tier ? `Suggested tier ${tier}` : "Screening / playbook / registry"}
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent className="space-y-3 pt-2">
        {!intelligence ? (
          <p className="text-xs text-muted-foreground">
            No pipeline intelligence blob on this load (older save). Similar submissions may still appear
            below.
          </p>
        ) : (
          <>
            {tier ? (
              <div className="flex flex-wrap gap-2 items-center">
                <Badge variant="outline" className="font-mono text-xs">
                  {tier}
                </Badge>
              </div>
            ) : null}

            <div className="grid gap-3 md:grid-cols-2">
              <div className="border rounded-md p-3 space-y-2 text-sm">
                <div className="font-medium text-foreground text-xs uppercase text-muted-foreground">
                  Screening (sandbox stub)
                </div>
                {alerts.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No demo alerts.</p>
                ) : (
                  <ul className="space-y-2 text-xs">
                    {alerts.map((a, idx) => {
                      const item = a as Record<string, unknown>;
                      const sev = String(item.severity ?? "");
                      const sum = String(item.summary ?? "");
                      return (
                        <li key={idx} className="border-l-2 pl-2">
                          <span className="font-medium">{String(item.type ?? "ALERT")}</span>
                          {sev ? ` · ${sev}` : ""}
                          {sum ? <div className="text-muted-foreground mt-0.5">{sum}</div> : null}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>

              <div className="border rounded-md p-3 space-y-2 text-sm">
                <div className="font-medium text-foreground text-xs uppercase text-muted-foreground">
                  Playbook flags
                </div>
                {violations.length === 0 ? (
                  <p className="text-xs text-muted-foreground">No YAML playbook hits.</p>
                ) : (
                  <ul className="space-y-1 text-xs max-h-40 overflow-y-auto">
                    {violations.map((v, idx) => (
                      <li key={idx}>
                        Q{v.serialNo}: {String(v.message ?? "")}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            <div className="border rounded-md p-3 space-y-2 text-sm">
              <div className="font-medium text-xs uppercase text-muted-foreground">Registry shortcuts</div>
              <div className="flex flex-wrap gap-2">
                {hints.length === 0 ? (
                  <span className="text-xs text-muted-foreground">—</span>
                ) : (
                  hints.map((h, idx) => {
                    const lab = String(h.label ?? "");
                    const url = String(h.url ?? "");
                    return (
                      <Button key={`${lab}-${idx}`} variant="secondary" size="sm" asChild>
                        <a href={url} target="_blank" rel="noopener noreferrer">
                          <ExternalLink className="h-3 w-3 mr-1" />
                          {lab || "Open"}
                        </a>
                      </Button>
                    );
                  })
                )}
              </div>
            </div>

            {extract ? (
              <div className="border rounded-md p-3 space-y-1 text-xs">
                <div className="font-medium uppercase text-muted-foreground">Structured extract sketch</div>
                <pre className="whitespace-pre-wrap max-h-48 overflow-y-auto bg-muted/30 rounded p-2">
                  {extract}
                </pre>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                No Gemini extract (missing API key, short documents, or failure).
              </p>
            )}
          </>
        )}

        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="default" disabled={narrBusy} onClick={() => void runNarrative()}>
            {narrBusy ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : <Sparkles className="h-3 w-3 mr-1" />}
            Draft narrative memo
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={qaBusy || !submissionId?.trim()}
            title={!submissionId?.trim() ? "Save run to History first for QA sampling" : undefined}
            onClick={() => void runQaSample()}
          >
            {qaBusy ? <Loader2 className="h-3 w-3 mr-1 animate-spin" /> : null}
            QA serial sample
          </Button>
        </div>

        {narrative != null ? (
          <div className="border rounded-md p-3 text-xs whitespace-pre-wrap bg-background">{narrative}</div>
        ) : null}

        {qaSerials ? (
          <p className="text-xs">
            QA spot-check priorities (AI validation ≠ Yes):{" "}
            <span className="font-mono">{qaSerials.join(", ") || "—"}</span>
          </p>
        ) : null}

        <div className="border rounded-md p-3 space-y-2 text-sm">
          <div className="font-medium text-xs uppercase text-muted-foreground">
            Possibly related submissions (fuzzy)
          </div>
          {similar.length === 0 ? (
            <p className="text-xs text-muted-foreground">No close matches in recent history.</p>
          ) : (
            <ul className="text-xs space-y-1">
              {similar.slice(0, 8).map((m) => (
                <li key={m.submissionId} className="flex justify-between gap-2">
                  <span className="truncate">{m.companyName}</span>
                  <span className="text-muted-foreground shrink-0">
                    {(100 * m.similarity).toFixed(1)}%
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}
