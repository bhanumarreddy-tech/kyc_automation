import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  BrainCircuit,
  Loader2,
  Network,
  Search,
} from "lucide-react";
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetchRagObservability } from "@/lib/ragObservabilityApi";
import type {
  EmbeddingPoint,
  RagChunkHit,
  RagObservabilityResponse,
  RagQuestionTrace,
  RagRetrievalPass,
} from "@/types/ragObservability";

interface RagObservabilityPanelProps {
  submissionId: string | null | undefined;
  companyName: string;
}

const PATH_LABELS: Record<string, string> = {
  rag: "Hybrid RAG",
  keyword: "Keyword fallback",
  full_corpus: "Full corpus",
  natives_only: "Native attachments only",
  unknown: "Unknown",
};

function pathBadgeVariant(path: string | null | undefined) {
  switch (path) {
    case "rag":
      return "default" as const;
    case "keyword":
      return "secondary" as const;
    case "full_corpus":
      return "outline" as const;
    default:
      return "outline" as const;
  }
}

function FunnelBar({
  label,
  count,
  max,
  tone,
}: {
  label: string;
  count: number;
  max: number;
  tone: string;
}) {
  const pct = max > 0 ? Math.max(4, Math.round((count / max) * 100)) : 0;
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{label}</span>
        <span className="font-mono">{count}</span>
      </div>
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${tone}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function ScoreTable({ rows, title }: { rows: RagChunkHit[]; title: string }) {
  if (!rows.length) {
    return (
      <p className="text-sm text-muted-foreground py-4">{title}: no chunks.</p>
    );
  }
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium">{title}</h4>
      <div className="rounded-md border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10">#</TableHead>
              <TableHead>Document</TableHead>
              <TableHead className="text-right">Dense</TableHead>
              <TableHead className="text-right">Lexical</TableHead>
              <TableHead className="text-right">RRF</TableHead>
              <TableHead className="text-right">Rerank</TableHead>
              <TableHead>Preview</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, idx) => (
              <TableRow
                key={row.chunkId}
                className={row.filteredOut ? "opacity-50" : undefined}
              >
                <TableCell className="font-mono text-xs">
                  {row.rank ?? idx + 1}
                  {row.filteredOut ? (
                    <Badge variant="outline" className="ml-1 text-[10px]">
                      filtered
                    </Badge>
                  ) : null}
                </TableCell>
                <TableCell className="text-xs max-w-[140px] truncate">
                  {row.filename}
                  {row.pageStart != null ? ` p.${row.pageStart}` : ""}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {row.denseScore.toFixed(3)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {row.lexicalScore.toFixed(3)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {row.fusedScore.toFixed(4)}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {row.rerankScore.toFixed(4)}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground max-w-[280px]">
                  {row.contentPreview}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function RetrievalPassView({ pass, label }: { pass: RagRetrievalPass; label: string }) {
  const maxCount = Math.max(
    pass.hybridCandidateCount,
    pass.afterFilterCount,
    pass.hits.length,
    1,
  );
  return (
    <Card className="p-4 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h4 className="font-medium">{label}</h4>
        <Badge variant="outline">min relevance {pass.minRelevance}</Badge>
        <Badge variant="outline">top-K {pass.retrieveTopK}</Badge>
      </div>
      <p className="text-xs text-muted-foreground whitespace-pre-wrap border rounded-md p-2 bg-muted/30">
        {pass.query}
      </p>
      <div className="grid gap-3 sm:grid-cols-3">
        <FunnelBar
          label="Hybrid candidates"
          count={pass.hybridCandidateCount}
          max={maxCount}
          tone="bg-sky-500"
        />
        <FunnelBar
          label="After relevance filter"
          count={pass.afterFilterCount}
          max={maxCount}
          tone="bg-violet-500"
        />
        <FunnelBar
          label="Final hits (reranked)"
          count={pass.hits.length}
          max={maxCount}
          tone="bg-emerald-500"
        />
      </div>
      <ScoreTable rows={pass.hybridCandidates} title="Hybrid pool (dense + lexical + RRF)" />
      <ScoreTable rows={pass.hits} title="Selected evidence chunks" />
    </Card>
  );
}

function QuestionRetrievalDetail({ question }: { question: RagQuestionTrace }) {
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2 items-start justify-between">
        <div>
          <p className="text-sm font-medium">
            Q{question.serialNo} · {question.sectionName}
          </p>
          <p className="text-sm text-muted-foreground mt-1">{question.question}</p>
          <p className="text-xs text-muted-foreground mt-2">
            Answer preview: {question.answerPreview}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge variant={pathBadgeVariant(question.validationPath)}>
            {PATH_LABELS[question.validationPath ?? "unknown"] ??
              question.validationPath}
          </Badge>
          {question.validation ? (
            <Badge variant={question.validation === "Yes" ? "default" : "secondary"}>
              Validation: {question.validation}
            </Badge>
          ) : null}
          {question.durationMs != null ? (
            <Badge variant="outline">{question.durationMs} ms</Badge>
          ) : null}
        </div>
      </div>
      {question.primaryRetrieval ? (
        <RetrievalPassView pass={question.primaryRetrieval} label="Primary retrieval" />
      ) : (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>No primary retrieval trace</AlertTitle>
          <AlertDescription>
            This question used{" "}
            {PATH_LABELS[question.validationPath ?? "unknown"] ?? "a non-RAG path"}.
          </AlertDescription>
        </Alert>
      )}
      {question.recallRetrieval ? (
        <RetrievalPassView pass={question.recallRetrieval} label="Recall pass (wider retrieval)" />
      ) : null}
    </div>
  );
}

function EmbeddingMap({
  data,
  selectedQuestion,
  highlightChunkIds,
}: {
  data: RagObservabilityResponse["embeddingMap"];
  selectedQuestion: RagQuestionTrace | null;
  highlightChunkIds: Set<string>;
}) {
  const scatterData = useMemo(() => {
    const chunks = data.chunkPoints.map((p) => ({
      ...p,
      size: highlightChunkIds.has(p.chunkId ?? "") ? 120 : 40,
      opacity: highlightChunkIds.size
        ? highlightChunkIds.has(p.chunkId ?? "")
          ? 1
          : 0.25
        : 0.85,
    }));
    const queries = data.queryPoints
      .filter((q) =>
        selectedQuestion
          ? q.serialNo === selectedQuestion.serialNo
          : true,
      )
      .map((p) => ({ ...p, size: 160, opacity: 1 }));
    return { chunks, queries };
  }, [data, highlightChunkIds, selectedQuestion]);

  if (!data.chunkPoints.length) {
    return (
      <Alert>
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>No embeddings indexed</AlertTitle>
        <AlertDescription>
          Chunk vectors are stored in Postgres after RAG indexing. Run a new submission with RAG
          enabled to populate this view.
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
        <span>{data.stats.chunkCount} chunks</span>
        <span>·</span>
        <span>{data.stats.documentCount} documents</span>
        <span>·</span>
        <span>2D {data.method.toUpperCase()} projection of {data.stats.chunkCount} chunk vectors</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {data.documents.map((doc) => (
          <span key={doc.documentId} className="inline-flex items-center gap-1 text-xs">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: doc.color }}
            />
            {doc.label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1 text-xs ml-2">
          <span className="inline-block h-2.5 w-2.5 rounded-full bg-rose-500" />
          Query embedding
        </span>
      </div>
      <div className="h-[420px] w-full rounded-lg border bg-card">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart margin={{ top: 16, right: 16, bottom: 16, left: 16 }}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-border/40" />
            <XAxis type="number" dataKey="x" name="PC1" tick={{ fontSize: 11 }} />
            <YAxis type="number" dataKey="y" name="PC2" tick={{ fontSize: 11 }} />
            <ZAxis type="number" dataKey="size" range={[40, 400]} />
            <Tooltip
              cursor={{ strokeDasharray: "3 3" }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as EmbeddingPoint & {
                  size?: number;
                };
                return (
                  <div className="rounded-md border bg-popover p-2 text-xs shadow-md max-w-xs">
                    <p className="font-medium">
                      {p.kind === "query" ? p.label : p.filename || p.documentId}
                    </p>
                    {p.kind === "chunk" ? (
                      <>
                        <p className="text-muted-foreground mt-1">{p.contentPreview}</p>
                        {p.pageStart != null ? (
                          <p className="mt-1">Page {p.pageStart}</p>
                        ) : null}
                      </>
                    ) : null}
                  </div>
                );
              }}
            />
            <Scatter
              name="Chunks"
              data={scatterData.chunks}
              fill="#8884d8"
              shape={(props) => {
                const { cx, cy, payload } = props as {
                  cx: number;
                  cy: number;
                  payload: EmbeddingPoint & { size?: number; opacity?: number };
                };
                if (cx == null || cy == null) return null;
                return (
                  <circle
                    cx={cx}
                    cy={cy}
                    r={Math.sqrt(payload.size ?? 40) / 2.2}
                    fill={payload.color}
                    fillOpacity={payload.opacity ?? 0.85}
                    stroke={highlightChunkIds.has(payload.chunkId ?? "") ? "#f43f5e" : "transparent"}
                    strokeWidth={2}
                  />
                );
              }}
            />
            <Scatter
              name="Queries"
              data={scatterData.queries}
              fill="#f43f5e"
              shape="star"
            />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <p className="text-xs text-muted-foreground">
        Points are 768-dimensional chunk embeddings projected with PCA. Nearby points are
        semantically similar. Select a question in the Retrieval tab to highlight retrieved chunks.
      </p>
    </div>
  );
}

function OverviewTab({ data }: { data: RagObservabilityResponse }) {
  const trace = data.trace;
  const config = trace?.config ?? {};
  const indexing = trace?.indexing;
  const questions = trace?.questions ?? [];

  const pathCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const q of questions) {
      const key = q.validationPath ?? "unknown";
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    return [...counts.entries()];
  }, [questions]);

  return (
    <div className="space-y-4">
      {!data.hasTrace ? (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Trace captured on next run</AlertTitle>
          <AlertDescription>
            Per-question retrieval traces are saved for submissions processed after this update.
            Embedding map below uses indexed chunk vectors from Postgres.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Card className="p-3">
          <p className="text-xs text-muted-foreground">Indexed chunks</p>
          <p className="text-2xl font-semibold">{indexing?.chunkCount ?? data.embeddingMap.stats.chunkCount}</p>
        </Card>
        <Card className="p-3">
          <p className="text-xs text-muted-foreground">Documents</p>
          <p className="text-2xl font-semibold">{indexing?.documentCount ?? data.embeddingMap.stats.documentCount}</p>
        </Card>
        <Card className="p-3">
          <p className="text-xs text-muted-foreground">Questions traced</p>
          <p className="text-2xl font-semibold">{questions.length}</p>
        </Card>
        <Card className="p-3">
          <p className="text-xs text-muted-foreground">RAG path usage</p>
          <p className="text-2xl font-semibold">
            {questions.filter((q) => q.validationPath === "rag").length}
            <span className="text-sm text-muted-foreground font-normal"> / {questions.length || "—"}</span>
          </p>
        </Card>
      </div>

      {pathCounts.length ? (
        <Card className="p-4 space-y-2">
          <h4 className="text-sm font-medium">Validation paths</h4>
          <div className="flex flex-wrap gap-2">
            {pathCounts.map(([path, count]) => (
              <Badge key={path} variant={pathBadgeVariant(path)}>
                {PATH_LABELS[path] ?? path}: {count}
              </Badge>
            ))}
          </div>
        </Card>
      ) : null}

      <Card className="p-4 space-y-3">
        <h4 className="text-sm font-medium">RAG configuration snapshot</h4>
        <div className="grid gap-2 sm:grid-cols-2 text-xs font-mono">
          {Object.entries(config).map(([key, value]) => (
            <div key={key} className="flex justify-between gap-2 border-b border-border/40 pb-1">
              <span className="text-muted-foreground">{key}</span>
              <span>{String(value)}</span>
            </div>
          ))}
        </div>
      </Card>

      {indexing?.documents?.length ? (
        <Card className="p-4 space-y-2">
          <h4 className="text-sm font-medium">Indexed sources</h4>
          <ul className="text-sm space-y-1">
            {indexing.documents.map((doc) => (
              <li key={doc.documentId} className="flex justify-between gap-2">
                <span>{doc.filename}</span>
                <span className="text-xs text-muted-foreground">{doc.kind ?? "file"}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

export function RagObservabilityPanel({
  submissionId,
  companyName,
}: RagObservabilityPanelProps) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<RagObservabilityResponse | null>(null);
  const [selectedSerial, setSelectedSerial] = useState<string>("");

  useEffect(() => {
    if (!open || !submissionId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchRagObservability(submissionId)
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        const first = payload.trace?.questions?.[0]?.serialNo;
        if (first != null) setSelectedSerial(String(first));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load RAG data");
        setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, submissionId]);

  const selectedQuestion = useMemo(() => {
    if (!data?.trace?.questions?.length || !selectedSerial) return null;
    return (
      data.trace.questions.find((q) => String(q.serialNo) === selectedSerial) ?? null
    );
  }, [data, selectedSerial]);

  const highlightChunkIds = useMemo(() => {
    const ids = new Set<string>();
    if (!selectedQuestion) return ids;
    for (const pass of [
      selectedQuestion.primaryRetrieval,
      selectedQuestion.recallRetrieval,
    ]) {
      if (!pass) continue;
      for (const hit of pass.hits) ids.add(hit.chunkId);
    }
    return ids;
  }, [selectedQuestion]);

  const disabled = !submissionId?.trim();

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button type="button" size="sm" variant="outline" disabled={disabled}>
          <BrainCircuit className="h-4 w-4 mr-1" />
          RAG explorer
        </Button>
      </SheetTrigger>
      <SheetContent side="right" className="w-full sm:max-w-3xl lg:max-w-5xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <Network className="h-5 w-5" />
            RAG under the hood
          </SheetTitle>
          <SheetDescription>
            Hybrid retrieval, embedding space, and per-question evidence for {companyName}.
          </SheetDescription>
        </SheetHeader>

        {loading ? (
          <div className="flex items-center justify-center py-24 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin mr-2" />
            Loading RAG observability…
          </div>
        ) : error ? (
          <Alert variant="destructive" className="mt-4">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Could not load RAG data</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        ) : data ? (
          <Tabs defaultValue="overview" className="mt-4">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="embeddings">Embedding map</TabsTrigger>
              <TabsTrigger value="retrieval">Per-question retrieval</TabsTrigger>
            </TabsList>

            <TabsContent value="overview" className="mt-4">
              <OverviewTab data={data} />
            </TabsContent>

            <TabsContent value="embeddings" className="mt-4">
              <EmbeddingMap
                data={data.embeddingMap}
                selectedQuestion={selectedQuestion}
                highlightChunkIds={highlightChunkIds}
              />
            </TabsContent>

            <TabsContent value="retrieval" className="mt-4 space-y-4">
              {data.trace?.questions?.length ? (
                <>
                  <div className="flex flex-wrap items-center gap-2">
                    <Search className="h-4 w-4 text-muted-foreground" />
                    <Select value={selectedSerial} onValueChange={setSelectedSerial}>
                      <SelectTrigger className="w-[280px]">
                        <SelectValue placeholder="Select question" />
                      </SelectTrigger>
                      <SelectContent>
                        {data.trace.questions.map((q) => (
                          <SelectItem key={q.serialNo} value={String(q.serialNo)}>
                            Q{q.serialNo} · {q.sectionName} ·{" "}
                            {PATH_LABELS[q.validationPath ?? "unknown"] ?? q.validationPath}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {selectedQuestion ? (
                    <QuestionRetrievalDetail question={selectedQuestion} />
                  ) : null}
                </>
              ) : (
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertTitle>No per-question traces yet</AlertTitle>
                  <AlertDescription>
                    Re-run this submission to capture retrieval traces. The embedding map tab still
                    shows chunk clusters from the vector index.
                  </AlertDescription>
                </Alert>
              )}
            </TabsContent>
          </Tabs>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
