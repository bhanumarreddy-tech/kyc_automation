import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import type {
  RagObservabilityResponse,
  RagQuestionTrace,
  RagRetrievalPass,
  RagTechnique,
  SimilarityMatrix,
} from "@/types/ragObservability";

const PIPELINE_STEPS = [
  { key: "index", label: "Contextualize + embed", tone: "bg-slate-500" },
  { key: "multi", label: "Multi-query hybrid", tone: "bg-sky-500" },
  { key: "filter", label: "Relevance filter", tone: "bg-violet-500" },
  { key: "rerank", label: "Gemini rerank", tone: "bg-amber-500" },
  { key: "mmr", label: "MMR diversity", tone: "bg-emerald-500" },
  { key: "validate", label: "Gemini validation", tone: "bg-rose-500" },
];

const waterfallConfig = {
  denseScore: { label: "Dense cosine", color: "hsl(var(--chart-1))" },
  lexicalScore: { label: "Lexical rank", color: "hsl(var(--chart-2))" },
  fusedScore: { label: "RRF fused", color: "hsl(var(--chart-3))" },
  rerankScore: { label: "Final rerank", color: "hsl(var(--chart-4))" },
} satisfies ChartConfig;

export function PipelineFlowCard({ pass }: { pass: RagRetrievalPass | null }) {
  if (!pass) {
    return (
      <p className="text-sm text-muted-foreground">
        Select a question with a RAG retrieval trace to see the pipeline.
      </p>
    );
  }
  const techniques = new Set(pass.techniques ?? []);
  return (
    <Card className="p-4 space-y-4">
      <h4 className="text-sm font-medium">Retrieval pipeline (this pass)</h4>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {PIPELINE_STEPS.map((step, idx) => {
          let active = true;
          if (step.key === "multi") active = techniques.has("multi_query");
          if (step.key === "rerank")
            active =
              techniques.has("gemini_rerank") || techniques.has("token_rerank");
          if (step.key === "mmr") active = techniques.has("mmr_diversity");
          return (
            <div key={step.key} className="flex items-center gap-2">
              <span
                className={`rounded-full px-2 py-1 text-white ${active ? step.tone : "bg-muted text-muted-foreground"}`}
              >
                {step.label}
              </span>
              {idx < PIPELINE_STEPS.length - 1 ? (
                <span className="text-muted-foreground">→</span>
              ) : null}
            </div>
          );
        })}
      </div>
      {pass.expandedQueries && pass.expandedQueries.length > 1 ? (
        <div className="space-y-1">
          <p className="text-xs font-medium text-muted-foreground">Query variants</p>
          {pass.expandedQueries.map((q) => (
            <p key={q} className="text-xs border rounded-md p-2 bg-muted/30 truncate">
              {q}
            </p>
          ))}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {(pass.techniques ?? []).map((t) => (
          <Badge key={t} variant="secondary">
            {t.replaceAll("_", " ")}
          </Badge>
        ))}
        {pass.rerankMethod ? (
          <Badge variant="outline">rerank: {pass.rerankMethod}</Badge>
        ) : null}
      </div>
    </Card>
  );
}

export function ScoreWaterfallChart({ pass }: { pass: RagRetrievalPass | null }) {
  const wf = pass?.scoreWaterfall;
  const data = wf
    ? [
        { stage: "Dense", value: wf.denseScore, fill: "var(--color-denseScore)" },
        { stage: "Lexical", value: wf.lexicalScore, fill: "var(--color-lexicalScore)" },
        { stage: "RRF", value: wf.fusedScore, fill: "var(--color-fusedScore)" },
        { stage: "Rerank", value: wf.rerankScore, fill: "var(--color-rerankScore)" },
      ]
    : [];

  if (!wf) {
    return (
      <p className="text-sm text-muted-foreground">
        Top-hit score waterfall appears after a run with retrieval traces.
      </p>
    );
  }

  return (
    <Card className="p-4 space-y-3">
      <div>
        <h4 className="text-sm font-medium">Score waterfall (top hit)</h4>
        <p className="text-xs text-muted-foreground mt-1">
          {wf.filename} — how scores evolve from vector search to final ranking
        </p>
      </div>
      <ChartContainer config={waterfallConfig} className="h-[220px] w-full">
        <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} />
          <XAxis dataKey="stage" tickLine={false} axisLine={false} />
          <YAxis domain={[0, 1]} tickLine={false} axisLine={false} width={32} />
          <Tooltip content={<ChartTooltipContent />} />
          <Bar dataKey="value" radius={4}>
            {data.map((entry) => (
              <Cell key={entry.stage} fill={entry.fill} />
            ))}
          </Bar>
        </BarChart>
      </ChartContainer>
      <p className="text-xs text-muted-foreground">
        Note: RRF fused scores are rank-based (~0.01–0.03), while dense scores are cosine
        similarity (0–1). The filter uses dense ≥ threshold OR lexical match.
      </p>
    </Card>
  );
}

function heatColor(value: number): string {
  const v = Math.max(0, Math.min(1, value));
  const hue = Math.round(220 - v * 220);
  return `hsl(${hue} 70% ${35 + v * 25}%)`;
}

export function SimilarityHeatmap({ matrix }: { matrix: SimilarityMatrix | null | undefined }) {
  if (!matrix?.labels?.length) {
    return (
      <p className="text-sm text-muted-foreground">
        Similarity heatmap loads for the selected question when trace includes query embeddings.
      </p>
    );
  }

  return (
    <Card className="p-4 space-y-3 overflow-x-auto">
      <div>
        <h4 className="text-sm font-medium">Query ↔ chunk similarity</h4>
        <p className="text-xs text-muted-foreground mt-1">
          Cosine similarity between the query embedding and each retrieved chunk (darker = more
          similar).
        </p>
      </div>
      <div className="min-w-[320px]">
        <div
          className="grid gap-1 text-[10px]"
          style={{
            gridTemplateColumns: `100px repeat(${matrix.labels.length}, minmax(48px, 1fr))`,
          }}
        >
          <div />
          {matrix.labels.map((label) => (
            <div key={label} className="truncate text-center text-muted-foreground" title={label}>
              {label}
            </div>
          ))}
          <div className="text-muted-foreground pr-2">Query</div>
          {matrix.queryRow.map((v, i) => (
            <div
              key={`q-${i}`}
              className="h-8 rounded-sm flex items-center justify-center text-white font-mono"
              style={{ backgroundColor: heatColor(v) }}
              title={`${matrix.labels[i]}: ${v}`}
            >
              {v.toFixed(2)}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

export function TechniquesGuide({ techniques }: { techniques: RagTechnique[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {techniques.map((t) => (
        <Card key={t.id} className={`p-4 space-y-2 ${t.enabled ? "" : "opacity-60"}`}>
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-medium">{t.name}</h4>
            <Badge variant={t.enabled ? "default" : "outline"}>
              {t.enabled ? "Active" : "Off"}
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground">{t.description}</p>
        </Card>
      ))}
    </div>
  );
}

export function FilterDiagnostics({ pass }: { pass: RagRetrievalPass | null }) {
  if (!pass?.hybridCandidates?.length) return null;
  const rejected = pass.hybridCandidates.filter((c) => c.filteredOut);
  if (!rejected.length) {
    return (
      <Card className="p-4 text-sm text-muted-foreground">
        All hybrid candidates passed the relevance filter (dense ≥ {pass.minDenseScore ?? "?"}{" "}
        or lexical ≥ {pass.minLexicalScore ?? "?"}).
      </Card>
    );
  }
  return (
    <Card className="p-4 space-y-2">
      <h4 className="text-sm font-medium">Why chunks were filtered out</h4>
      <ul className="text-xs space-y-2 max-h-48 overflow-y-auto">
        {rejected.slice(0, 8).map((c) => (
          <li key={c.chunkId} className="border rounded-md p-2 bg-muted/20">
            <span className="font-medium">{c.filename}</span>
            <span className="text-muted-foreground"> — {c.filterReason ?? "below thresholds"}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

export function LearningIdeasCard() {
  const ideas = [
    {
      title: "Interactive threshold sandbox",
      body: "Drag min-dense / min-lexical sliders and see live how many chunks survive the filter.",
    },
    {
      title: "Side-by-side strategy compare",
      body: "Run dense-only vs hybrid vs hybrid+rerank on the same question and diff the hit lists.",
    },
    {
      title: "Chunk boundary viewer",
      body: "Show how documents were split (overlap, page markers) and which boundaries split entities.",
    },
    {
      title: "Failure case gallery",
      body: "Auto-surface questions that fell back to keyword/full-corpus paths with root-cause tags.",
    },
    {
      title: "Latency flame chart",
      body: "Break down embed, retrieve, rerank, and validation ms per question to spot bottlenecks.",
    },
  ];
  return (
    <Card className="p-4 space-y-3">
      <h4 className="text-sm font-medium">Future UI ideas for learning RAG</h4>
      <ul className="space-y-2 text-xs text-muted-foreground">
        {ideas.map((item) => (
          <li key={item.title}>
            <span className="font-medium text-foreground">{item.title}:</span> {item.body}
          </li>
        ))}
      </ul>
    </Card>
  );
}

export type { RagQuestionTrace, RagObservabilityResponse };
