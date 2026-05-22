import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Clock,
  GitCompare,
  Layers,
  Loader2,
  SlidersHorizontal,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  fetchChunkBoundaries,
  fetchRagFilterSandbox,
  fetchRagStrategyCompare,
} from "@/lib/ragObservabilityApi";
import type {
  ChunkBoundariesResponse,
  RagChunkHit,
  RagFailureCase,
  RagRetrievalPass,
  RagStrategyCompareResult,
  RagTracePayload,
} from "@/types/ragObservability";

const TAG_LABELS: Record<string, string> = {
  full_corpus_fallback: "Full corpus",
  keyword_fallback: "Keyword fallback",
  no_index: "No index",
  zero_hits: "Zero hits",
  filter_too_strict: "Filter too strict",
  natives_only: "Natives only",
  recall_pass: "Recall pass",
  recall_zero_hits: "Recall empty",
  validation_miss: "Validation miss",
  rag_empty_hits: "RAG empty",
  indexing_skipped: "Index skipped",
  unknown_path: "Unknown",
};

const BOUNDARY_LABELS: Record<string, string> = {
  word_split: "Word split",
  entity_split: "Entity split",
  page_marker_at_boundary: "Page marker",
  short_overlap: "Short overlap",
};

function wouldPassFilter(
  hit: RagChunkHit,
  minDense: number,
  minLexical: number,
  minFused: number,
): boolean {
  return (
    hit.denseScore >= minDense ||
    hit.lexicalScore >= minLexical ||
    hit.fusedScore >= minFused
  );
}

function RangeSlider({
  id,
  label,
  value,
  min,
  max,
  step,
  onChange,
  format,
}: {
  id: string;
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (v: number) => void;
  format: (v: number) => string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-xs">
        <Label htmlFor={id}>{label}</Label>
        <span className="font-mono text-muted-foreground">{format(value)}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-primary"
      />
    </div>
  );
}

export function ThresholdSandbox({
  submissionId,
  pass,
  serialNo,
}: {
  submissionId: string;
  pass: RagRetrievalPass | null;
  serialNo: number | null;
}) {
  const [minDense, setMinDense] = useState(pass?.minDenseScore ?? 0.42);
  const [minLexical, setMinLexical] = useState(pass?.minLexicalScore ?? 0.02);
  const [minFused, setMinFused] = useState(pass?.minRelevance ?? 0.012);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (pass?.minDenseScore != null) setMinDense(pass.minDenseScore);
    if (pass?.minLexicalScore != null) setMinLexical(pass.minLexicalScore);
    if (pass?.minRelevance != null) setMinFused(pass.minRelevance);
  }, [pass]);

  const local = useMemo(() => {
    const candidates = pass?.hybridCandidates ?? [];
    const survivors = candidates.filter((c) =>
      wouldPassFilter(c, minDense, minLexical, minFused),
    );
    return {
      total: candidates.length,
      survivors: survivors.length,
      rejected: candidates.length - survivors.length,
      rows: candidates.map((c) => ({
        ...c,
        wouldPass: wouldPassFilter(c, minDense, minLexical, minFused),
      })),
    };
  }, [pass, minDense, minLexical, minFused]);

  useEffect(() => {
    if (!submissionId || serialNo == null) return;
    const timer = setTimeout(() => {
      setLoading(true);
      void fetchRagFilterSandbox(submissionId, {
        serialNo,
        minDense,
        minLexical,
        minFused,
      })
        .catch(() => undefined)
        .finally(() => setLoading(false));
    }, 400);
    return () => clearTimeout(timer);
  }, [submissionId, serialNo, minDense, minLexical, minFused]);

  if (!pass?.hybridCandidates?.length) {
    return (
      <Card className="p-4 text-sm text-muted-foreground">
        No hybrid candidates in trace — re-run validation to capture filter sandbox data.
      </Card>
    );
  }

  const baseline = pass.afterFilterCount;

  return (
    <Card className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <SlidersHorizontal className="h-4 w-4" />
        <h4 className="text-sm font-medium">Interactive threshold sandbox</h4>
        {loading ? <Loader2 className="h-3 w-3 animate-spin text-muted-foreground" /> : null}
      </div>
      <p className="text-xs text-muted-foreground">
        A chunk passes if dense ≥ min, lexical ≥ min, or fused ≥ min (OR gate). Original run kept{" "}
        {baseline} of {pass.hybridCandidateCount}.
      </p>
      <div className="grid gap-4 sm:grid-cols-3">
        <RangeSlider
          id="min-dense"
          label="Min dense (cosine)"
          value={minDense}
          min={0}
          max={1}
          step={0.01}
          onChange={setMinDense}
          format={(v) => v.toFixed(2)}
        />
        <RangeSlider
          id="min-lexical"
          label="Min lexical (ts_rank)"
          value={minLexical}
          min={0}
          max={0.2}
          step={0.005}
          onChange={setMinLexical}
          format={(v) => v.toFixed(3)}
        />
        <RangeSlider
          id="min-fused"
          label="Min fused (RRF)"
          value={minFused}
          min={0}
          max={0.05}
          step={0.001}
          onChange={setMinFused}
          format={(v) => v.toFixed(3)}
        />
      </div>
      <div className="flex flex-wrap gap-2 text-sm">
        <Badge variant={local.survivors > 0 ? "default" : "destructive"}>
          {local.survivors} survive
        </Badge>
        <Badge variant="outline">{local.rejected} rejected</Badge>
        {local.survivors !== baseline ? (
          <Badge variant="secondary">
            Δ {local.survivors - baseline} vs original ({baseline})
          </Badge>
        ) : null}
      </div>
      <div className="max-h-48 overflow-y-auto border rounded-md">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Pass</TableHead>
              <TableHead>File</TableHead>
              <TableHead>Dense</TableHead>
              <TableHead>Lex</TableHead>
              <TableHead>Fused</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {local.rows.slice(0, 12).map((row) => (
              <TableRow key={row.chunkId} className={row.wouldPass ? "" : "opacity-50"}>
                <TableCell>{row.wouldPass ? "✓" : "✗"}</TableCell>
                <TableCell className="max-w-[120px] truncate">{row.filename}</TableCell>
                <TableCell>{row.denseScore.toFixed(3)}</TableCell>
                <TableCell>{row.lexicalScore.toFixed(3)}</TableCell>
                <TableCell>{row.fusedScore.toFixed(3)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}

const STRATEGY_KEYS = ["dense", "hybrid", "hybridRerank"] as const;

export function StrategyComparePanel({
  submissionId,
  serialNo,
}: {
  submissionId: string;
  serialNo: number | null;
}) {
  const [data, setData] = useState<RagStrategyCompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (serialNo == null) return;
    setLoading(true);
    setError(null);
    void fetchRagStrategyCompare(submissionId, serialNo)
      .then(setData)
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Compare failed"),
      )
      .finally(() => setLoading(false));
  }, [submissionId, serialNo]);

  useEffect(() => {
    setData(null);
  }, [serialNo]);

  return (
    <Card className="p-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <GitCompare className="h-4 w-4" />
          <h4 className="text-sm font-medium">Side-by-side strategy compare</h4>
        </div>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          disabled={serialNo == null || loading}
          onClick={load}
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Run compare"}
        </Button>
      </div>
      {error ? <p className="text-xs text-destructive">{error}</p> : null}
      {!data ? (
        <p className="text-xs text-muted-foreground">
          Re-runs retrieval live: dense-only vs hybrid+filter vs full pipeline (includes Gemini
          rerank). Select a question and click Run compare.
        </p>
      ) : (
        <>
          {data.diff.sharedChunkIds.length ? (
            <p className="text-xs text-muted-foreground">
              {data.diff.sharedChunkIds.length} chunk(s) in all three strategies.
            </p>
          ) : null}
          <div className="grid gap-3 lg:grid-cols-3">
            {STRATEGY_KEYS.map((key) => {
              const strat = data.strategies[key];
              if (!strat) return null;
              const unique = data.diff.uniqueByStrategy[key] ?? [];
              return (
                <Card key={key} className="p-3 space-y-2 border-dashed">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium">{strat.label}</span>
                    <Badge variant="outline">{strat.durationMs}ms</Badge>
                  </div>
                  <p className="text-[10px] text-muted-foreground">{strat.description}</p>
                  <Badge>{strat.hitCount} hits</Badge>
                  {unique.length ? (
                    <p className="text-[10px] text-amber-600 dark:text-amber-400">
                      Unique: {unique.length}
                    </p>
                  ) : null}
                  <ul className="text-[10px] space-y-1 max-h-32 overflow-y-auto">
                    {strat.hits.map((h) => (
                      <li key={h.chunkId} className="truncate border-b pb-1">
                        #{h.rank ?? "?"} {h.filename} · d={h.denseScore.toFixed(2)}
                      </li>
                    ))}
                  </ul>
                </Card>
              );
            })}
          </div>
        </>
      )}
    </Card>
  );
}

export function ChunkBoundaryViewer({
  submissionId,
  defaultDocumentId,
}: {
  submissionId: string;
  defaultDocumentId?: string;
}) {
  const [data, setData] = useState<ChunkBoundariesResponse | null>(null);
  const [docId, setDocId] = useState(defaultDocumentId ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    void fetchChunkBoundaries(submissionId)
      .then((payload) => {
        setData(payload);
        const initial =
          defaultDocumentId ?? payload.documents[0]?.documentId ?? "";
        setDocId(initial);
      })
      .catch((e: unknown) =>
        setError(e instanceof Error ? e.message : "Failed to load chunks"),
      )
      .finally(() => setLoading(false));
  }, [submissionId, defaultDocumentId]);

  const selectedDoc = useMemo(
    () => data?.documents.find((d) => d.documentId === docId) ?? data?.documents[0],
    [data, docId],
  );

  return (
    <Card className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Layers className="h-4 w-4" />
        <h4 className="text-sm font-medium">Chunk boundary viewer</h4>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading chunks…
        </div>
      ) : error ? (
        <p className="text-xs text-destructive">{error}</p>
      ) : data ? (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={docId} onValueChange={setDocId}>
              <SelectTrigger className="w-[280px]">
                <SelectValue placeholder="Document" />
              </SelectTrigger>
              <SelectContent>
                {data.documents.map((d) => (
                  <SelectItem key={d.documentId} value={d.documentId}>
                    {d.filename} ({d.chunkCount} chunks)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Badge variant="outline">Overlap config: {data.config.overlapChars} chars</Badge>
            <Badge variant="secondary">{data.totalChunks} total chunks</Badge>
          </div>
          {selectedDoc ? (
            <Accordion type="multiple" className="w-full">
              {selectedDoc.chunks.map((chunk, idx) => (
                <AccordionItem key={chunk.chunkId} value={chunk.chunkId}>
                  <AccordionTrigger className="text-xs hover:no-underline">
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="font-mono">#{chunk.chunkIndex}</span>
                      {chunk.pageStart != null ? (
                        <Badge variant="outline">
                          p.{chunk.pageStart}
                          {chunk.pageEnd != null && chunk.pageEnd !== chunk.pageStart
                            ? `–${chunk.pageEnd}`
                            : ""}
                        </Badge>
                      ) : null}
                      <span className="text-muted-foreground">{chunk.charLength} chars</span>
                      {chunk.overlapWithNext > 0 ? (
                        <Badge variant="secondary">{chunk.overlapWithNext} overlap</Badge>
                      ) : null}
                      {chunk.boundaryIssues.map((issue) => (
                        <Badge key={issue} variant="destructive" className="text-[10px]">
                          {BOUNDARY_LABELS[issue] ?? issue}
                        </Badge>
                      ))}
                    </span>
                  </AccordionTrigger>
                  <AccordionContent>
                    <pre className="text-[10px] whitespace-pre-wrap bg-muted/40 p-2 rounded-md max-h-40 overflow-y-auto">
                      {chunk.contentPreview}
                    </pre>
                    {idx < selectedDoc.chunks.length - 1 && chunk.overlapWithNext > 0 ? (
                      <p className="text-[10px] text-muted-foreground mt-2">
                        Shares {chunk.overlapWithNext} characters with chunk #{chunk.chunkIndex + 1}
                      </p>
                    ) : null}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          ) : null}
        </>
      ) : null}
    </Card>
  );
}

export function FailureCaseGallery({
  cases,
  onSelectQuestion,
}: {
  cases: RagFailureCase[];
  onSelectQuestion?: (serialNo: number) => void;
}) {
  if (!cases.length) {
    return (
      <Card className="p-4 text-sm text-muted-foreground">
        No fallback or weak-retrieval cases — all questions used RAG successfully.
      </Card>
    );
  }

  return (
    <Card className="p-4 space-y-3">
      <div className="flex items-center gap-2">
        <AlertTriangle className="h-4 w-4 text-amber-500" />
        <h4 className="text-sm font-medium">Failure case gallery</h4>
        <Badge variant="secondary">{cases.length}</Badge>
      </div>
      <ul className="space-y-3 max-h-80 overflow-y-auto">
        {cases.map((c) => (
          <li key={c.serialNo} className="border rounded-md p-3 space-y-2 text-xs">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="font-medium text-primary hover:underline"
                onClick={() => onSelectQuestion?.(c.serialNo)}
              >
                Q{c.serialNo}
              </button>
              <Badge variant="outline">{c.sectionName}</Badge>
              <Badge>{c.validationPath}</Badge>
              {c.validation ? <Badge variant="secondary">{c.validation}</Badge> : null}
            </div>
            <p className="text-muted-foreground line-clamp-2">{c.question}</p>
            <div className="flex flex-wrap gap-1">
              {c.tags.map((tag) => (
                <Badge key={tag} variant="destructive" className="text-[10px]">
                  {TAG_LABELS[tag] ?? tag}
                </Badge>
              ))}
            </div>
            <ul className="list-disc pl-4 text-muted-foreground space-y-0.5">
              {c.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </Card>
  );
}

const FLAME_COLORS: Record<string, string> = {
  primaryRetrieve: "hsl(var(--chart-1))",
  validation: "hsl(var(--chart-5))",
  recallRetrieve: "hsl(var(--chart-2))",
  recallValidation: "hsl(var(--chart-3))",
  other: "hsl(var(--muted-foreground))",
};

function buildFlameRows(trace: RagTracePayload | null) {
  if (!trace?.questions?.length) return [];
  return trace.questions
    .filter((q) => q.durationMs != null)
    .map((q) => {
      const st = q.stageTiming;
      const rt = q.primaryRetrieval?.stageTiming;
      const primaryRetrieve =
        st?.primaryRetrieveMs ?? rt?.totalMs ?? rt?.hybridMs ?? 0;
      const validation = st?.validationMs ?? 0;
      const recallRetrieve = st?.recallRetrieveMs ?? 0;
      const recallValidation = st?.recallValidationMs ?? 0;
      const accounted =
        primaryRetrieve + validation + recallRetrieve + recallValidation;
      const other = Math.max(0, (q.durationMs ?? 0) - accounted);
      return {
        label: `Q${q.serialNo}`,
        serialNo: q.serialNo,
        primaryRetrieve,
        validation,
        recallRetrieve,
        recallValidation,
        other,
        total: q.durationMs ?? 0,
      };
    });
}

export function LatencyFlameChart({ trace }: { trace: RagTracePayload | null }) {
  const rows = useMemo(() => buildFlameRows(trace), [trace]);
  const hasStageData = rows.some(
    (r) => r.primaryRetrieve > 0 || r.validation > 0 || r.recallRetrieve > 0,
  );

  if (!rows.length) {
    return (
      <Card className="p-4 text-sm text-muted-foreground">
        No per-question timing data yet.
      </Card>
    );
  }

  const stackKeys = [
    "primaryRetrieve",
    "validation",
    "recallRetrieve",
    "recallValidation",
    "other",
  ] as const;

  const stackLabels: Record<string, string> = {
    primaryRetrieve: "Retrieve",
    validation: "Validate",
    recallRetrieve: "Recall retrieve",
    recallValidation: "Recall validate",
    other: "Other",
  };

  return (
    <Card className="p-4 space-y-4">
      <div className="flex items-center gap-2">
        <Clock className="h-4 w-4" />
        <h4 className="text-sm font-medium">Latency flame chart</h4>
        {trace?.pipelineTiming ? (
          <Badge variant="outline">
            Validation phase: {trace.pipelineTiming.validationMs ?? "?"}ms
          </Badge>
        ) : null}
      </div>
      {!hasStageData ? (
        <p className="text-xs text-muted-foreground">
          Re-run validation to capture stage-level timing (retrieve vs Gemini validate).
        </p>
      ) : null}
      <div className="h-64 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 8 }}>
            <CartesianGrid strokeDasharray="3 3" horizontal={false} />
            <XAxis type="number" unit="ms" tick={{ fontSize: 10 }} />
            <YAxis type="category" dataKey="label" width={48} tick={{ fontSize: 10 }} />
            <Tooltip
              formatter={(value: number, name: string) => [
                `${value}ms`,
                stackLabels[name] ?? name,
              ]}
            />
            {stackKeys.map((key) => (
              <Bar
                key={key}
                dataKey={key}
                stackId="a"
                fill={FLAME_COLORS[key]}
                name={key}
              />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}
