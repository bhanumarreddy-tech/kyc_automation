import {
  useEffect,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  ExternalLink,
  Eye,
  Filter,
  LayoutList,
  ListOrdered,
  Loader2,
  Pencil,
  PanelRight,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import type {
  KYCRow,
  KycAgentReconValue,
  SourceLink,
  ValidationSource,
  ValidationStatus,
} from "@/data/kycQuestions";
import { ExportOptions } from "@/components/kyc/ExportOptions";
import { KYCStatsBar } from "@/components/kyc/KYCStatsBar";
import { KYCCoverageCharts } from "@/components/kyc/KYCCoverageCharts";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { apiUrl } from "@/lib/api";
import { classifyRowDelta, readAuditLog, type AuditLogEntry } from "@/lib/kycAnalystToolkit";

type EditingField = "answer" | "sources" | "analystComments";

export type SortColumnId =
  | "sectionNo"
  | "serialNo"
  | "question"
  | "answer"
  | "sources"
  | "validation"
  | "confidenceScore"
  | "validationSources"
  | "kycAgentRecon"
  | "analystComments";

export type AiValidationFilter = "any" | "yes" | "no" | "empty";

export type KycReconColumnFilter = "any" | "yes" | "no" | "na" | "empty";

const SORT_COLUMN_LABELS: Record<SortColumnId, string> = {
  sectionNo: "Section No.",
  serialNo: "Question No.",
  question: "Question",
  answer: "Answers",
  sources: "Sources",
  validation: "AI Validation",
  confidenceScore: "Conf.",
  validationSources: "AI Validation Sources",
  kycAgentRecon: "KYC_Agent_Recon",
  analystComments: "Analyst Comments",
};

export interface TableFiltersState {
  sectionNo: string;
  serialNo: string;
  question: string;
  answer: string;
  sources: string;
  aiValidation: AiValidationFilter;
  aiValidationSources: string;
  kycAgentRecon: KycReconColumnFilter;
  analyst: string;
}

const INITIAL_FILTERS: TableFiltersState = {
  sectionNo: "",
  serialNo: "",
  question: "",
  answer: "",
  sources: "",
  aiValidation: "any",
  aiValidationSources: "",
  kycAgentRecon: "any",
  analyst: "",
};

function filtersAreActive(f: TableFiltersState): boolean {
  return (
    f.sectionNo.trim() !== "" ||
    f.serialNo.trim() !== "" ||
    f.question.trim() !== "" ||
    f.answer.trim() !== "" ||
    f.sources.trim() !== "" ||
    f.aiValidation !== "any" ||
    f.aiValidationSources.trim() !== "" ||
    f.kycAgentRecon !== "any" ||
    f.analyst.trim() !== ""
  );
}

interface ResultsTableProps {
  companyName: string;
  rows: KYCRow[];
  onReset: () => void;
  onRowChange: (serialNo: number, updates: Partial<KYCRow>) => void;
  comparisonBaseline?: KYCRow[] | null;
  comparisonLabel?: string | null;
  onClearComparison?: () => void;
  submissionMeta?: { submissionId: string | null; savedAt: string | null };
  referenceUrls?: string[];
  attachedDocuments?: { filename: string; objectKey?: string | null }[];
  analystName?: string;
  onAnalystNameChange?: (name: string) => void;
  signOff?: boolean;
  onSignOffChange?: (value: boolean) => void;
  onAudit?: (entry: Omit<AuditLogEntry, "at">) => void;
  /** Latest pipeline-derived bundle (screening stub, playbook, registry shortcuts, extracts). */
  pipelineIntelligence?: Record<string, unknown> | null;
  /** Server-backed escalations (e.g. from history metadata). */
  initialEscalatedSerials?: number[];
}

const sourcesToText = (sources: SourceLink[]): string =>
  sources.map((s) => (s.title ? `${s.title} | ${s.url}` : s.url)).join("\n");

const textToSources = (text: string): SourceLink[] => {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const idx = line.indexOf("|");
      if (idx > -1) {
        const title = line.slice(0, idx).trim();
        const url = line.slice(idx + 1).trim();
        return { title: title || url, url };
      }
      return { title: line, url: line };
    });
};

const validationSourcesToText = (sources: ValidationSource[]): string =>
  sources
    .map((s) => {
      const parts = [s.document];
      if (s.url?.trim()) parts.push(s.url.trim());
      if (typeof s.page === "number") parts.push(`p.${s.page}`);
      if (s.excerpt) parts.push(s.excerpt);
      return parts.join(" | ");
    })
    .join("\n");

const EXCERPT_PREVIEW_MAX_CHARS = 240;

function pickPrimaryValidationSource(sources: ValidationSource[]): ValidationSource | undefined {
  if (!sources.length) return undefined;
  const withExcerpt = sources.find((s) => (s.excerpt ?? "").trim().length > 0);
  return withExcerpt ?? sources[0];
}

function collapseWs(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

/** Tooltip listing all sources (documents + excerpt clues). */
function validationSourcesTooltip(sources: ValidationSource[]): string {
  return sources
    .map((s, i) => {
      const head = [s.document, typeof s.page === "number" ? `p.${s.page}` : ""]
        .filter(Boolean)
        .join(" ");
      const ex = collapseWs(s.excerpt ?? "");
      if (ex)
        return `${i + 1}. ${head} — "${ex.length > 300 ? `${ex.slice(0, 299)}…` : ex}"`;
      return `${i + 1}. ${head}`;
    })
    .join(" | ");
}

interface ValidationPreviewInline {
  title: string;
  summary: ReactNode;
}

function buildValidationSourcesPreview(
  sources: ValidationSource[],
  muted: boolean,
): ValidationPreviewInline {
  const primary = pickPrimaryValidationSource(sources)!;
  const rest = sources.length > 1 ? sources.length - 1 : 0;
  const title = validationSourcesTooltip(sources);
  const excerptRaw = collapseWs(primary.excerpt ?? "");
  const textCls = muted ? "text-muted-foreground" : "text-foreground/90";

  if (excerptRaw) {
    const excerpt =
      excerptRaw.length > EXCERPT_PREVIEW_MAX_CHARS
        ? `${excerptRaw.slice(0, EXCERPT_PREVIEW_MAX_CHARS - 1).trimEnd()}…`
        : excerptRaw;
    return {
      title,
      summary: (
        <span title={title} className={`block min-w-0 line-clamp-2 text-xs break-words leading-snug ${textCls}`}>
          <span className="text-muted-foreground/70">&ldquo;</span>
          {excerpt}
          <span className="text-muted-foreground/70">&rdquo;</span>
          {rest > 0 && (
            <span className="text-muted-foreground font-normal">{` · +${rest}`}</span>
          )}
        </span>
      ),
    };
  }

  let docLine = primary.document?.trim() || "Source";
  if (typeof primary.page === "number") docLine += ` · p.${primary.page}`;
  if (rest > 0) docLine += ` · +${rest}`;

  return {
    title,
    summary: (
      <span
        title={title}
        className={`block min-w-0 line-clamp-1 text-xs ${muted ? "text-muted-foreground" : "font-medium text-foreground/90"}`}
      >
        {docLine}
      </span>
    ),
  };
}

function rowPassesFilters(row: KYCRow, f: TableFiltersState): boolean {
  const sec = f.sectionNo.trim();
  if (sec) {
    const n = parseInt(sec, 10);
    if (Number.isNaN(n)) return false;
    if (row.sectionNo !== n) return false;
  }
  const sn = f.serialNo.trim();
  if (sn) {
    const n = parseInt(sn, 10);
    if (Number.isNaN(n)) return false;
    if (row.serialNo !== n) return false;
  }
  if (f.question.trim()) {
    if (!row.question.toLowerCase().includes(f.question.trim().toLowerCase())) return false;
  }
  if (f.answer.trim()) {
    if (!row.answer.toLowerCase().includes(f.answer.trim().toLowerCase())) return false;
  }
  if (f.sources.trim()) {
    if (!sourcesToText(row.sources).toLowerCase().includes(f.sources.trim().toLowerCase()))
      return false;
  }
  if (f.aiValidation !== "any") {
    const v = row.validation;
    if (f.aiValidation === "yes" && v !== "Yes") return false;
    if (f.aiValidation === "no" && v !== "No") return false;
    if (f.aiValidation === "empty" && v !== "") return false;
  }
  if (f.aiValidationSources.trim()) {
    const blob = validationSourcesToText(row.validationSources).toLowerCase();
    if (!blob.includes(f.aiValidationSources.trim().toLowerCase())) return false;
  }
  if (f.kycAgentRecon !== "any") {
    const k = row.kycAgentRecon;
    if (f.kycAgentRecon === "yes" && k !== "Yes") return false;
    if (f.kycAgentRecon === "no" && k !== "No") return false;
    if (f.kycAgentRecon === "na" && k !== "NA") return false;
    if (f.kycAgentRecon === "empty" && k !== "") return false;
  }
  if (f.analyst.trim()) {
    if (!row.analystComments.toLowerCase().includes(f.analyst.trim().toLowerCase()))
      return false;
  }
  return true;
}

function rowInReviewQueue(row: KYCRow, escalated: Set<number>): boolean {
  const a = row.answer.trim().toLowerCase();
  const empty = !a || a === "not found";
  if (empty) return true;
  if (row.validation !== "Yes") return true;
  if (escalated.has(row.serialNo)) return true;
  return false;
}

function validationRank(v: ValidationStatus): number {
  if (v === "") return 0;
  if (v === "No") return 1;
  return 2;
}

function reconRank(v: KycAgentReconValue | ""): number {
  if (v === "") return 0;
  if (v === "Yes") return 1;
  if (v === "No") return 2;
  return 3;
}

/** Primary comparison; callers add secondary tie-break via serialNo. */
function cmpByColumn(column: SortColumnId, a: KYCRow, b: KYCRow): number {
  switch (column) {
    case "sectionNo":
      return a.sectionNo !== b.sectionNo
        ? a.sectionNo - b.sectionNo
        : a.serialNo - b.serialNo;
    case "serialNo":
      return a.serialNo - b.serialNo;
    case "question":
      return a.question.localeCompare(b.question, undefined, { sensitivity: "base" });
    case "answer":
      return a.answer.localeCompare(b.answer, undefined, { sensitivity: "base" });
    case "sources":
      return sourcesToText(a.sources).localeCompare(sourcesToText(b.sources), undefined, {
        sensitivity: "base",
      });
    case "validation":
      return validationRank(a.validation) - validationRank(b.validation);
    case "confidenceScore": {
      const ac = a.confidenceScore;
      const bc = b.confidenceScore;
      const av = ac == null || Number.isNaN(Number(ac)) ? -1 : Number(ac);
      const bv = bc == null || Number.isNaN(Number(bc)) ? -1 : Number(bc);
      return av - bv;
    }
    case "validationSources":
      return validationSourcesToText(a.validationSources).localeCompare(
        validationSourcesToText(b.validationSources),
        undefined,
        { sensitivity: "base" }
      );
    case "kycAgentRecon":
      return reconRank(a.kycAgentRecon) - reconRank(b.kycAgentRecon);
    case "analystComments":
      return a.analystComments.localeCompare(b.analystComments, undefined, {
        sensitivity: "base",
      });
    default:
      return 0;
  }
}

function regroupConsecutive(sorted: KYCRow[]): { sectionNo: number; sectionName: string; rows: KYCRow[] }[] {
  const out: { sectionNo: number; sectionName: string; rows: KYCRow[] }[] = [];
  for (const row of sorted) {
    const tail = out[out.length - 1];
    if (tail && tail.sectionNo === row.sectionNo) tail.rows.push(row);
    else out.push({ sectionNo: row.sectionNo, sectionName: row.sectionName, rows: [row] });
  }
  return out;
}

interface SortColumnHeaderProps {
  title: string;
  column: SortColumnId;
  sortColumn: SortColumnId | null;
  sortDir: "asc" | "desc";
  cycleSort: (c: SortColumnId) => void;
  filters: TableFiltersState;
  setFilters: Dispatch<SetStateAction<TableFiltersState>>;
  filterContent: ReactNode;
  className?: string;
}

function SortColumnHeader({
  title,
  column,
  sortColumn,
  sortDir,
  cycleSort,
  filters,
  setFilters,
  filterContent,
  className,
}: SortColumnHeaderProps) {
  const active = filtersAreActive(filters);
  const thisFilterActive =
    (column === "sectionNo" && filters.sectionNo.trim() !== "") ||
    (column === "serialNo" && filters.serialNo.trim() !== "") ||
    (column === "question" && filters.question.trim() !== "") ||
    (column === "answer" && filters.answer.trim() !== "") ||
    (column === "sources" && filters.sources.trim() !== "") ||
    (column === "validation" && filters.aiValidation !== "any") ||
    (column === "confidenceScore" && false) ||
    (column === "validationSources" && filters.aiValidationSources.trim() !== "") ||
    (column === "kycAgentRecon" && filters.kycAgentRecon !== "any") ||
    (column === "analystComments" && filters.analyst.trim() !== "");

  const SortIcon =
    sortColumn === column ? (sortDir === "asc" ? ArrowUp : ArrowDown) : ArrowUpDown;

  return (
    <TableHead className={className}>
      <div className="flex items-center gap-1">
        <button
          type="button"
          className="inline-flex items-center gap-1 text-left font-medium hover:text-foreground/90 mr-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-sm"
          onClick={() => cycleSort(column)}
        >
          <span className="leading-tight">{title}</span>
          <SortIcon className="h-3.5 w-3.5 shrink-0 opacity-70" aria-hidden />
        </button>
        <Popover>
          <PopoverTrigger asChild>
            <Button
              type="button"
              variant={thisFilterActive ? "secondary" : "ghost"}
              size="icon"
              className="h-7 w-7 shrink-0"
              aria-label={`Filter ${title}`}
            >
              <Filter className="h-3.5 w-3.5" />
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-72 space-y-3" align="start">
            <div className="font-medium text-sm">{title}</div>
            {filterContent}
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="w-full"
              onClick={() =>
                setFilters((prev) => {
                  const next = { ...prev };
                  if (column === "sectionNo") next.sectionNo = INITIAL_FILTERS.sectionNo;
                  if (column === "serialNo") next.serialNo = INITIAL_FILTERS.serialNo;
                  if (column === "question") next.question = INITIAL_FILTERS.question;
                  if (column === "answer") next.answer = INITIAL_FILTERS.answer;
                  if (column === "sources") next.sources = INITIAL_FILTERS.sources;
                  if (column === "validation") next.aiValidation = INITIAL_FILTERS.aiValidation;
                  if (column === "validationSources")
                    next.aiValidationSources = INITIAL_FILTERS.aiValidationSources;
                  if (column === "kycAgentRecon")
                    next.kycAgentRecon = INITIAL_FILTERS.kycAgentRecon;
                  if (column === "analystComments") next.analyst = INITIAL_FILTERS.analyst;
                  return next;
                })
              }
            >
              Clear this filter
            </Button>
            {active && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-full"
                onClick={() => setFilters({ ...INITIAL_FILTERS })}
              >
                Clear all filters
              </Button>
            )}
          </PopoverContent>
        </Popover>
      </div>
    </TableHead>
  );
}

interface SimilarMatch {
  submissionId: string;
  companyName: string;
  similarity: number;
}

function PipelineIntelligenceStrip({
  companyName,
  submissionId,
  intelligence,
  rows,
}: {
  companyName: string;
  submissionId?: string | null;
  intelligence: Record<string, unknown> | null;
  rows: KYCRow[];
}) {
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
    } catch (e) {
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

export function ResultsTable({
  companyName,
  rows,
  onReset,
  onRowChange,
  comparisonBaseline = null,
  comparisonLabel = null,
  onClearComparison,
  submissionMeta,
  referenceUrls,
  attachedDocuments,
  analystName = "",
  onAnalystNameChange,
  signOff = false,
  onSignOffChange,
  onAudit,
  initialEscalatedSerials = [],
  pipelineIntelligence = null,
}: ResultsTableProps) {
  const [editing, setEditing] = useState<{ serialNo: number; field: EditingField } | null>(
    null
  );
  const [editValue, setEditValue] = useState("");
  const [filters, setFilters] = useState<TableFiltersState>(INITIAL_FILTERS);
  const [sortColumn, setSortColumn] = useState<SortColumnId | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [showChangedOnly, setShowChangedOnly] = useState(false);
  const [validationPeekRow, setValidationPeekRow] = useState<KYCRow | null>(null);
  const [auditOpen, setAuditOpen] = useState(false);
  const [reviewQueue, setReviewQueue] = useState(false);
  const [selectedSerials, setSelectedSerials] = useState<Set<number>>(() => new Set());
  const [density, setDensity] = useState<"comfortable" | "compact">("comfortable");
  const [splitDetail, setSplitDetail] = useState(false);
  const [evidenceDrawerRow, setEvidenceDrawerRow] = useState<KYCRow | null>(null);
  const [detailFocusSerial, setDetailFocusSerial] = useState<number | null>(null);
  const [escalatedSerials, setEscalatedSerials] = useState<Set<number>>(() => new Set());

  const baselineBySerial = useMemo(() => {
    if (!comparisonBaseline?.length) return null;
    return new Map(comparisonBaseline.map((r) => [r.serialNo, r]));
  }, [comparisonBaseline]);

  useEffect(() => {
    setEscalatedSerials(new Set(initialEscalatedSerials));
  }, [initialEscalatedSerials]);

  const getRowHighlightClass = (row: KYCRow) => {
    const parts: string[] = [];
    if (detailFocusSerial === row.serialNo) parts.push("ring-1 ring-primary/60");
    if (!baselineBySerial) return parts.join(" ");
    const d = classifyRowDelta(row, baselineBySerial.get(row.serialNo));
    if (d.changed) parts.push("bg-amber-500/10 dark:bg-amber-500/15");
    return parts.join(" ");
  };

  const filteredSortedGrouped = useMemo(() => {
    let filtered = rows.filter((row) => rowPassesFilters(row, filters));
    if (reviewQueue) {
      filtered = filtered.filter((row) => rowInReviewQueue(row, escalatedSerials));
    }
    if (showChangedOnly && baselineBySerial) {
      filtered = filtered.filter((row) =>
        classifyRowDelta(row, baselineBySerial.get(row.serialNo)).changed
      );
    }
    let sorted: KYCRow[];
    if (!sortColumn) {
      sorted = [...filtered].sort((a, b) => a.serialNo - b.serialNo);
    } else {
      sorted = [...filtered].sort((a, b) => {
        let c = cmpByColumn(sortColumn, a, b);
        if (sortDir === "desc") c = -c;
        if (c !== 0) return c;
        return a.serialNo - b.serialNo;
      });
    }
    return regroupConsecutive(sorted);
  }, [
    rows,
    filters,
    sortColumn,
    sortDir,
    showChangedOnly,
    baselineBySerial,
    reviewQueue,
    escalatedSerials,
  ]);

  const filteredCount = useMemo(() => {
    let filtered = rows.filter((row) => rowPassesFilters(row, filters));
    if (reviewQueue) {
      filtered = filtered.filter((row) => rowInReviewQueue(row, escalatedSerials));
    }
    if (showChangedOnly && baselineBySerial) {
      filtered = filtered.filter((row) =>
        classifyRowDelta(row, baselineBySerial.get(row.serialNo)).changed
      );
    }
    return filtered.length;
  }, [rows, filters, showChangedOnly, baselineBySerial, reviewQueue, escalatedSerials]);

  const triageSerials = useMemo(() => {
    const serials = rows
      .filter((r) => rowPassesFilters(r, filters) && rowInReviewQueue(r, escalatedSerials))
      .map((r) => r.serialNo)
      .sort((a, b) => a - b);
    return serials;
  }, [rows, filters, escalatedSerials]);

  useEffect(() => {
    if (!reviewQueue) return;
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t?.closest?.("input, textarea, select, [contenteditable=true]")) return;
      if (triageSerials.length === 0) return;
      if (e.key === "ArrowDown" || (e.key === "j" && !e.metaKey && !e.ctrlKey)) {
        e.preventDefault();
        setDetailFocusSerial((prev) => {
          const idx = prev == null ? -1 : triageSerials.indexOf(prev);
          return triageSerials[Math.min(triageSerials.length - 1, idx + 1)] ?? triageSerials[0]!;
        });
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        setDetailFocusSerial((prev) => {
          const idx = prev == null ? triageSerials.length : triageSerials.indexOf(prev);
          return triageSerials[Math.max(0, idx - 1)];
        });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [reviewQueue, triageSerials]);

  const cycleSort = (col: SortColumnId) => {
    if (sortColumn !== col) {
      setSortColumn(col);
      setSortDir("asc");
      return;
    }
    if (sortDir === "asc") {
      setSortDir("desc");
      return;
    }
    setSortColumn(null);
    setSortDir("asc");
  };

  const startEditing = (serialNo: number, field: EditingField, current: string) => {
    setEditing({ serialNo, field });
    setEditValue(current);
  };

  const cancelEdit = () => {
    setEditing(null);
    setEditValue("");
  };

  const saveEdit = () => {
    if (!editing) return;
    const { serialNo, field } = editing;
    if (field === "answer") {
      onRowChange(serialNo, { answer: editValue });
    } else if (field === "analystComments") {
      onRowChange(serialNo, { analystComments: editValue });
    } else if (field === "sources") {
      onRowChange(serialNo, { sources: textToSources(editValue) });
    }
    setEditing(null);
    setEditValue("");
  };

  const renderEditor = (placeholder: string) => (
    <div className="space-y-2 min-w-[220px]">
      <Textarea
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        className="min-h-[80px] text-sm"
        placeholder={placeholder}
        autoFocus
      />
      <div className="flex gap-2">
        <Button size="sm" onClick={saveEdit}>
          <Check className="h-3 w-3 mr-1" /> Save
        </Button>
        <Button size="sm" variant="outline" onClick={cancelEdit}>
          <X className="h-3 w-3 mr-1" /> Cancel
        </Button>
      </div>
    </div>
  );

  const renderAnswerCell = (row: KYCRow) => {
    const isEditing = editing?.serialNo === row.serialNo && editing.field === "answer";
    if (isEditing) {
      return renderEditor("Enter answer...");
    }
    return (
      <div className="group">
        <div className="flex items-start gap-2">
          <div className="flex-1 text-sm whitespace-pre-wrap">
            {row.answer || <span className="text-muted-foreground">Not extracted</span>}
          </div>
          <button
            type="button"
            onClick={() => startEditing(row.serialNo, "answer", row.answer)}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-muted rounded"
            aria-label="Edit answer"
          >
            <Pencil className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>
    );
  };

  const renderSourcesCell = (row: KYCRow) => {
    const isEditing = editing?.serialNo === row.serialNo && editing.field === "sources";
    if (isEditing) {
      return renderEditor("One source per line. Format: Title | https://example.com");
    }
    return (
      <div className="group">
        <div className="flex items-start gap-2">
          <div className="flex-1 space-y-1">
            {row.sources.length === 0 ? (
              <span className="text-muted-foreground text-sm">No sources</span>
            ) : (
              row.sources.map((src, idx) => (
                <a
                  key={idx}
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-start gap-1 text-xs text-primary hover:underline break-all"
                >
                  <ExternalLink className="h-3 w-3 mt-0.5 shrink-0" />
                  <span>{src.title || src.url}</span>
                </a>
              ))
            )}
          </div>
          <button
            type="button"
            onClick={() =>
              startEditing(row.serialNo, "sources", sourcesToText(row.sources))
            }
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-muted rounded"
            aria-label="Edit sources"
          >
            <Pencil className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>
    );
  };

  const renderValidationCell = (row: KYCRow) => {
    const value: ValidationStatus = row.validation;
    return (
      <div className="min-h-[32px] flex items-center">
        {value === "Yes" ? (
          <Badge className="bg-green-500/20 text-green-700 border-green-500/50 text-xs">
            Yes
          </Badge>
        ) : value === "No" ? (
          <Badge className="bg-red-500/20 text-red-700 border-red-500/50 text-xs">No</Badge>
        ) : (
          <span className="text-muted-foreground text-xs">—</span>
        )}
      </div>
    );
  };

  const renderConfidenceCell = (row: KYCRow) => {
    const cs = row.confidenceScore;
    if (cs == null || Number.isNaN(Number(cs))) {
      return <span className="text-muted-foreground text-xs">—</span>;
    }
    const n = Number(cs);
    const variant = n >= 75 ? "default" : n >= 50 ? "secondary" : "destructive";
    const stale = row.stalenessDays;
    const titleHint =
      stale != null ? `Citation freshness heuristic: ~${stale} days from URL years (if detected)` : undefined;
    return (
      <Badge variant={variant} className="font-mono text-xs px-1.5" title={titleHint}>
        {n}
      </Badge>
    );
  };

  const renderValidationSourcesCell = (row: KYCRow) => {
    const delta = baselineBySerial
      ? classifyRowDelta(row, baselineBySerial.get(row.serialNo))
      : null;
    const hasSources = row.validationSources.length > 0;
    const showPeek =
      row.validation === "Yes" || hasSources || Boolean(delta?.changed);

    let summary: ReactNode;
    if (hasSources) {
      const muted = row.validation !== "Yes";
      summary = buildValidationSourcesPreview(row.validationSources, muted).summary;
    } else if (row.validation === "Yes") {
      summary = (
        <span className="text-xs text-muted-foreground italic">No citation extracted</span>
      );
    } else if (delta?.changed) {
      summary = (
        <span className="text-xs text-amber-800 dark:text-amber-200/95">Changed vs prior run</span>
      );
    } else {
      summary = <span className="text-muted-foreground text-xs">—</span>;
    }

    return (
      <div className="flex flex-col gap-1 min-w-0">
        {delta?.changed && (
          <div className="text-[10px] uppercase tracking-wide text-amber-800 dark:text-amber-300 font-medium leading-none">
            Δ {delta.tags.join(" · ")}
          </div>
        )}
        <div className="flex items-start gap-0.5 min-w-0">
          <div className="min-w-0 flex-1 leading-snug">{summary}</div>
          {showPeek && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7 shrink-0 -mr-1 text-muted-foreground hover:text-foreground"
              title="Citation details"
              aria-label={`Citation details for question ${row.serialNo}`}
              onClick={() => setValidationPeekRow(row)}
            >
              <Eye className="h-3.5 w-3.5" aria-hidden />
            </Button>
          )}
        </div>
      </div>
    );
  };

  const renderKycAgentReconCell = (row: KYCRow) => {
    const value = row.kycAgentRecon;
    return (
      <Select
        value={value === "" ? "__blank__" : value}
        onValueChange={(v) => {
          const next: KycAgentReconValue | "" =
            v === "Yes" ? "Yes" : v === "No" ? "No" : v === "NA" ? "NA" : "";
          onRowChange(row.serialNo, { kycAgentRecon: next });
        }}
      >
        <SelectTrigger className="h-8 min-w-[100px] text-xs">
          <SelectValue>
            {value === "Yes" ? (
              <span className="text-xs">Yes</span>
            ) : value === "No" ? (
              <span className="text-xs">No</span>
            ) : value === "NA" ? (
              <span className="text-xs">NA</span>
            ) : (
              <span className="text-muted-foreground text-xs">—</span>
            )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__blank__">—</SelectItem>
          <SelectItem value="Yes">Yes</SelectItem>
          <SelectItem value="No">No</SelectItem>
          <SelectItem value="NA">NA</SelectItem>
        </SelectContent>
      </Select>
    );
  };

  const renderAnalystCommentsCell = (row: KYCRow) => {
    const isEditing =
      editing?.serialNo === row.serialNo && editing.field === "analystComments";
    if (isEditing) {
      return renderEditor("Add analyst comments...");
    }
    return (
      <div className="group">
        <div className="flex items-start gap-2">
          <div className="flex-1 text-sm whitespace-pre-wrap">
            {row.analystComments || (
              <span className="text-muted-foreground">Add comment...</span>
            )}
          </div>
          <button
            type="button"
            onClick={() =>
              startEditing(row.serialNo, "analystComments", row.analystComments)
            }
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-muted rounded"
            aria-label="Edit analyst comments"
          >
            <Pencil className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>
    );
  };

  const anyFilterActive = filtersAreActive(filters);

  const splitRow =
    evidenceDrawerRow ?? rows.find((r) => r.serialNo === detailFocusSerial) ?? null;

  const exportAuditLogJson = () => {
    const data = readAuditLog();
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `kyc_audit_log_${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <KYCStatsBar rows={rows} />
      <KYCCoverageCharts rows={rows} />
      <PipelineIntelligenceStrip
        companyName={companyName}
        submissionId={submissionMeta?.submissionId}
        intelligence={pipelineIntelligence}
        rows={rows}
      />

      <div className="flex flex-wrap gap-2 items-center">
        <Button
          type="button"
          size="sm"
          variant={reviewQueue ? "default" : "outline"}
          onClick={() => {
            setReviewQueue((v) => !v);
            setDetailFocusSerial(null);
          }}
        >
          <ListOrdered className="h-4 w-4 mr-1" />
          Review queue
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => setDensity((d) => (d === "comfortable" ? "compact" : "comfortable"))}
        >
          <LayoutList className="h-4 w-4 mr-1" />
          {density === "compact" ? "Compact" : "Comfortable"}
        </Button>
        <Button
          type="button"
          size="sm"
          variant={splitDetail ? "secondary" : "outline"}
          onClick={() => setSplitDetail((v) => !v)}
        >
          <PanelRight className="h-4 w-4 mr-1" />
          Split view
        </Button>
        {reviewQueue ? (
          <span className="text-xs text-muted-foreground">
            Queue: {triageSerials.length} · j/k or ↑/↓ to step
          </span>
        ) : null}
        {selectedSerials.size > 0 ? (
          <span className="text-xs text-muted-foreground">{selectedSerials.size} selected</span>
        ) : null}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!reviewQueue || triageSerials.length === 0}
          onClick={() => setSelectedSerials(new Set(triageSerials))}
        >
          Select queue
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={selectedSerials.size === 0}
          onClick={() => {
            const next = new Set(escalatedSerials);
            selectedSerials.forEach((s) => next.add(s));
            setEscalatedSerials(next);
            onAudit?.({
              action: "bulk_escalate",
              analyst: analystName?.trim() || undefined,
              detail: { serials: [...selectedSerials] },
            });
          }}
        >
          Mark selected escalated
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setSelectedSerials(new Set())}>
          Clear selection
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => {
            const t =
              rows.find((r) => r.serialNo === detailFocusSerial) ?? rows[0] ?? null;
            if (t) setEvidenceDrawerRow(t);
          }}
        >
          Evidence drawer
        </Button>
      </div>

      <div className="rounded-md border bg-muted/30 p-3 flex flex-wrap gap-4 items-end text-sm">
        {onAnalystNameChange && (
          <div className="space-y-1 min-w-[200px] flex-1">
            <Label htmlFor="analyst-id">Analyst identity (local only)</Label>
            <Input
              id="analyst-id"
              value={analystName}
              onChange={(e) => onAnalystNameChange(e.target.value)}
              placeholder="Name or initials"
              className="h-9"
            />
          </div>
        )}
        {submissionMeta?.submissionId && (
          <div className="space-y-1 text-xs text-muted-foreground min-w-[220px] max-w-md">
            <div className="font-medium text-foreground">Run provenance</div>
            <div className="font-mono break-all">ID: {submissionMeta.submissionId}</div>
            {submissionMeta.savedAt && (
              <div>Saved: {new Date(submissionMeta.savedAt).toLocaleString()}</div>
            )}
          </div>
        )}
        {submissionMeta?.submissionId && onSignOffChange && (
          <div className="flex items-center space-x-2 pb-1">
            <Checkbox
              id="analyst-signoff"
              checked={signOff}
              onCheckedChange={(c) => {
                const next = c === true;
                onSignOffChange(next);
                onAudit?.({
                  action: next ? "sign_off" : "sign_off_revoked",
                  analyst: analystName?.trim() || undefined,
                  detail: { submissionId: submissionMeta.submissionId },
                });
              }}
            />
            <Label htmlFor="analyst-signoff" className="text-sm font-normal cursor-pointer">
              Sign-off (this browser)
            </Label>
          </div>
        )}
        <Button type="button" variant="outline" size="sm" onClick={() => setAuditOpen(true)}>
          Local audit log
        </Button>
      </div>

      {baselineBySerial && (
        <div className="flex flex-wrap items-center gap-3 rounded-md border border-amber-200 dark:border-amber-900 bg-amber-50/40 dark:bg-amber-950/20 px-3 py-2 text-sm">
          <span className="text-muted-foreground">
            Regression vs{" "}
            <span className="font-medium text-foreground">{comparisonLabel ?? "prior run"}</span>
          </span>
          <div className="flex items-center gap-2">
            <Switch
              id="changed-only"
              checked={showChangedOnly}
              onCheckedChange={(c) => setShowChangedOnly(c === true)}
            />
            <Label htmlFor="changed-only" className="text-sm font-normal cursor-pointer">
              Changed rows only
            </Label>
          </div>
          {onClearComparison && (
            <Button type="button" variant="ghost" size="sm" onClick={onClearComparison}>
              Clear comparison
            </Button>
          )}
        </div>
      )}

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">KYC Results: {companyName}</h2>
          <p className="text-sm text-muted-foreground">
            {anyFilterActive
              ? `Showing ${filteredCount} of ${rows.length} questions (${filteredSortedGrouped.length} section groups)`
              : `${rows.length} questions across ${filteredSortedGrouped.length} sections`}
            {sortColumn != null
              ? ` · Sorted by ${SORT_COLUMN_LABELS[sortColumn]} (${sortDir})`
              : ""}
          </p>
        </div>
        <div className="flex gap-2">
          <ExportOptions
            companyName={companyName}
            rows={rows}
            selectedRows={
              selectedSerials.size > 0
                ? rows.filter((r) => selectedSerials.has(r.serialNo))
                : undefined
            }
            submissionId={submissionMeta?.submissionId}
            savedAt={submissionMeta?.savedAt}
            referenceUrls={referenceUrls}
            attachedDocuments={attachedDocuments}
            analystName={analystName}
            onAudit={onAudit}
          />
          <Button variant="outline" onClick={onReset}>
            <RotateCcw className="h-4 w-4 mr-2" />
            Start New
          </Button>
        </div>
      </div>

      <div
        className={`${splitDetail ? "grid gap-4 lg:grid-cols-[1fr_minmax(260px,360px)]" : ""}`}
      >
        <div className="border rounded-lg overflow-hidden min-w-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <SortColumnHeader
                  title="Section No."
                  column="sectionNo"
                  sortColumn={sortColumn}
                  sortDir={sortDir}
                  cycleSort={cycleSort}
                  filters={filters}
                  setFilters={setFilters}
                  filterContent={
                    <>
                      <Label htmlFor="f-sec">Equals</Label>
                      <Input
                        id="f-sec"
                        inputMode="numeric"
                        placeholder="e.g. 2"
                        value={filters.sectionNo}
                        onChange={(e) =>
                          setFilters((f) => ({ ...f, sectionNo: e.target.value }))
                        }
                      />
                    </>
                  }
                  className="w-24"
                />
                <SortColumnHeader
                  title="Question No."
                  column="serialNo"
                  sortColumn={sortColumn}
                  sortDir={sortDir}
                  cycleSort={cycleSort}
                  filters={filters}
                  setFilters={setFilters}
                  filterContent={
                    <>
                      <Label htmlFor="f-ser">Equals</Label>
                      <Input
                        id="f-ser"
                        inputMode="numeric"
                        placeholder="e.g. 12"
                        value={filters.serialNo}
                        onChange={(e) =>
                          setFilters((f) => ({ ...f, serialNo: e.target.value }))
                        }
                      />
                    </>
                  }
                  className="w-28"
                />
                <SortColumnHeader
                  title="Question"
                  column="question"
                  sortColumn={sortColumn}
                  sortDir={sortDir}
                  cycleSort={cycleSort}
                  filters={filters}
                  setFilters={setFilters}
                  filterContent={
                    <>
                      <Label htmlFor="f-q">Contains (case-insensitive)</Label>
                      <Input
                        id="f-q"
                        value={filters.question}
                        onChange={(e) =>
                          setFilters((f) => ({ ...f, question: e.target.value }))
                        }
                      />
                    </>
                  }
                  className="min-w-[200px]"
                />
                <SortColumnHeader
                  title="Answers"
                  column="answer"
                  sortColumn={sortColumn}
                  sortDir={sortDir}
                  cycleSort={cycleSort}
                  filters={filters}
                  setFilters={setFilters}
                  filterContent={
                    <>
                      <Label htmlFor="f-a">Contains</Label>
                      <Input
                        id="f-a"
                        value={filters.answer}
                        onChange={(e) =>
                          setFilters((f) => ({ ...f, answer: e.target.value }))
                        }
                      />
                    </>
                  }
                  className="min-w-[200px] bg-primary/5"
                />
                <SortColumnHeader
                  title="Sources"
                  column="sources"
                  sortColumn={sortColumn}
                  sortDir={sortDir}
                  cycleSort={cycleSort}
                  filters={filters}
                  setFilters={setFilters}
                  filterContent={
                    <>
                      <Label htmlFor="f-src">Contains</Label>
                      <Input
                        id="f-src"
                        value={filters.sources}
                        onChange={(e) =>
                          setFilters((f) => ({ ...f, sources: e.target.value }))
                        }
                      />
                    </>
                  }
                  className="min-w-[180px]"
                />
                <SortColumnHeader
                  title="AI Validation"
                  column="validation"
                  sortColumn={sortColumn}
                  sortDir={sortDir}
                  cycleSort={cycleSort}
                  filters={filters}
                  setFilters={setFilters}
                  filterContent={
                    <>
                      <Label>Value</Label>
                      <Select
                        value={filters.aiValidation}
                        onValueChange={(v) =>
                          setFilters((f) => ({
                            ...f,
                            aiValidation: v as AiValidationFilter,
                          }))
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="any">Any</SelectItem>
                          <SelectItem value="yes">Yes</SelectItem>
                          <SelectItem value="no">No</SelectItem>
                          <SelectItem value="empty">Empty / —</SelectItem>
                        </SelectContent>
                      </Select>
                    </>
                  }
                  className="w-[124px]"
                />
                <SortColumnHeader
                  title="Conf."
                  column="confidenceScore"
                  sortColumn={sortColumn}
                  sortDir={sortDir}
                  cycleSort={cycleSort}
                  filters={filters}
                  setFilters={setFilters}
                  filterContent={
                    <p className="text-xs text-muted-foreground">
                      Confidence is computed server-side; no column filter.
                    </p>
                  }
                  className="w-[72px]"
                />
                <SortColumnHeader
                  title="AI Validation Sources"
                  column="validationSources"
                  sortColumn={sortColumn}
                  sortDir={sortDir}
                  cycleSort={cycleSort}
                  filters={filters}
                  setFilters={setFilters}
                  filterContent={
                    <>
                      <Label htmlFor="f-vs">Contains</Label>
                      <Input
                        id="f-vs"
                        value={filters.aiValidationSources}
                        onChange={(e) =>
                          setFilters((f) => ({
                            ...f,
                            aiValidationSources: e.target.value,
                          }))
                        }
                      />
                    </>
                  }
                  className="min-w-[200px]"
                />
                <SortColumnHeader
                  title="KYC_Agent_Recon"
                  column="kycAgentRecon"
                  sortColumn={sortColumn}
                  sortDir={sortDir}
                  cycleSort={cycleSort}
                  filters={filters}
                  setFilters={setFilters}
                  filterContent={
                    <>
                      <Label>Value</Label>
                      <Select
                        value={filters.kycAgentRecon}
                        onValueChange={(v) =>
                          setFilters((f) => ({
                            ...f,
                            kycAgentRecon: v as KycReconColumnFilter,
                          }))
                        }
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="any">Any</SelectItem>
                          <SelectItem value="yes">Yes</SelectItem>
                          <SelectItem value="no">No</SelectItem>
                          <SelectItem value="na">NA</SelectItem>
                          <SelectItem value="empty">Empty / —</SelectItem>
                        </SelectContent>
                      </Select>
                    </>
                  }
                  className="w-[148px]"
                />
                <SortColumnHeader
                  title="Analyst Comments"
                  column="analystComments"
                  sortColumn={sortColumn}
                  sortDir={sortDir}
                  cycleSort={cycleSort}
                  filters={filters}
                  setFilters={setFilters}
                  filterContent={
                    <>
                      <Label htmlFor="f-an">Contains</Label>
                      <Input
                        id="f-an"
                        value={filters.analyst}
                        onChange={(e) =>
                          setFilters((f) => ({ ...f, analyst: e.target.value }))
                        }
                      />
                    </>
                  }
                  className="min-w-[200px]"
                />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredSortedGrouped.map((section, secIdx) => (
                <SectionRows
                  key={`${section.sectionNo}-${secIdx}`}
                  sectionNo={section.sectionNo}
                  sectionName={section.sectionName}
                  rows={section.rows}
                  compact={density === "compact"}
                  onRowActivate={(sn) => setDetailFocusSerial(sn)}
                  getRowClassName={getRowHighlightClass}
                  renderAnswerCell={renderAnswerCell}
                  renderSourcesCell={renderSourcesCell}
                  renderValidationCell={renderValidationCell}
                  renderConfidenceCell={renderConfidenceCell}
                  renderValidationSourcesCell={renderValidationSourcesCell}
                  renderKycAgentReconCell={renderKycAgentReconCell}
                  renderAnalystCommentsCell={renderAnalystCommentsCell}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {splitDetail && (
        <aside className="border rounded-lg bg-muted/20 p-4 text-sm space-y-4 max-h-[calc(100vh-10rem)] overflow-y-auto lg:sticky lg:top-4 self-start">
          <div className="font-semibold text-foreground">Detail / evidence</div>
          {!splitRow ? (
            <p className="text-muted-foreground">Select a row from the review queue (j/k) or open Evidence drawer.</p>
          ) : (
            <>
              <div>
                <div className="text-xs text-muted-foreground">Q{splitRow.serialNo}</div>
                <p className="font-medium leading-snug">{splitRow.question}</p>
              </div>
              <div>
                <div className="text-xs uppercase text-muted-foreground mb-1">Answer</div>
                <p className="whitespace-pre-wrap leading-relaxed">{splitRow.answer || "—"}</p>
              </div>
              <div>
                <div className="text-xs uppercase text-muted-foreground mb-1">Web sources</div>
                {splitRow.sources.length === 0 ? (
                  <span className="text-muted-foreground">None</span>
                ) : (
                  <ul className="space-y-2">
                    {splitRow.sources.map((s, i) => (
                      <li key={i}>
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary underline break-all text-xs inline-flex gap-1"
                        >
                          <ExternalLink className="h-3 w-3 shrink-0" />
                          {s.title || s.url}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <div className="text-xs uppercase text-muted-foreground mb-1">Document validation</div>
                {splitRow.validationSources.length === 0 ? (
                  <span className="text-muted-foreground">No citations</span>
                ) : (
                  <ul className="space-y-3">
                    {splitRow.validationSources.map((src, idx) => (
                      <li key={idx} className="border rounded-md p-2 space-y-1">
                        <div className="font-medium text-xs">{src.document}</div>
                        {src.url?.trim() && (
                          <a
                            href={src.url.trim()}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-primary underline break-all"
                          >
                            {src.url}
                          </a>
                        )}
                        {src.excerpt && (
                          <blockquote className="text-xs border-l-2 pl-2 italic text-muted-foreground whitespace-pre-wrap">
                            {src.excerpt}
                          </blockquote>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          )}
        </aside>
      )}
    </div>

      <Dialog open={validationPeekRow !== null} onOpenChange={(o) => !o && setValidationPeekRow(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Validation sources — Q{validationPeekRow?.serialNo ?? ""}</DialogTitle>
            {validationPeekRow ? (
              <DialogDescription className="text-left text-muted-foreground text-xs">
                {validationPeekRow.question}
              </DialogDescription>
            ) : null}
          </DialogHeader>
          {validationPeekRow && (
            <div className="space-y-4 text-sm">
              {baselineBySerial && (
                <div className="rounded-md bg-muted/50 p-2 text-xs space-y-1">
                  <div className="font-medium text-foreground">vs prior run</div>
                  <div>
                    Prior answer:{" "}
                    <span className="text-muted-foreground whitespace-pre-wrap">
                      {baselineBySerial.get(validationPeekRow.serialNo)?.answer?.trim() ||
                        "—"}
                    </span>
                  </div>
                  <div>
                    Prior validation:{" "}
                    {baselineBySerial.get(validationPeekRow.serialNo)?.validation || "—"}
                  </div>
                </div>
              )}
              {validationPeekRow.validationSources.length === 0 ? (
                <p className="text-muted-foreground">No structured sources for this row.</p>
              ) : (
                <ul className="space-y-4">
                  {validationPeekRow.validationSources.map((src, idx) => (
                    <li key={idx} className="border rounded-md p-3 space-y-2">
                      <div className="font-medium">{src.document}</div>
                      {typeof src.page === "number" && (
                        <div className="text-xs text-muted-foreground">Page {src.page}</div>
                      )}
                      {src.url?.trim() && (
                        <a
                          href={src.url.trim()}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary text-xs underline break-all inline-flex items-center gap-1"
                        >
                          Open link <ExternalLink className="h-3 w-3 shrink-0" />
                        </a>
                      )}
                      {src.excerpt && (
                        <blockquote className="text-xs border-l-2 pl-2 italic text-muted-foreground whitespace-pre-wrap">
                          {src.excerpt}
                        </blockquote>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setValidationPeekRow(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={auditOpen} onOpenChange={setAuditOpen}>
        <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>Local audit log (browser only)</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground text-left sm:text-left">
              Entries cover exports, sign-offs, and reruns while using this browser. This is not a
              server-side compliance ledger.
            </DialogDescription>
          </DialogHeader>
          <div className="overflow-y-auto text-xs font-mono space-y-1 flex-1 min-h-[200px] border rounded-md p-2 bg-muted/30">
            {readAuditLog()
              .slice()
              .reverse()
              .map((e, i) => (
                <div key={i} className="border-b border-border/50 pb-1 mb-1 break-words">
                  <span className="text-muted-foreground">{e.at}</span>{" "}
                  <span className="text-foreground">{e.action}</span>
                  {e.analyst && <span className="text-primary"> · {e.analyst}</span>}
                  {e.detail && (
                    <pre className="mt-0.5 text-[10px] whitespace-pre-wrap">
                      {JSON.stringify(e.detail)}
                    </pre>
                  )}
                </div>
              ))}
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button type="button" variant="outline" onClick={exportAuditLogJson}>
              Export log JSON
            </Button>
            <Button type="button" onClick={() => setAuditOpen(false)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Sheet
        open={evidenceDrawerRow !== null}
        onOpenChange={(o) => {
          if (!o) setEvidenceDrawerRow(null);
        }}
      >
        <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Evidence — Q{evidenceDrawerRow?.serialNo ?? ""}</SheetTitle>
          </SheetHeader>
          {evidenceDrawerRow && (
            <div className="space-y-4 text-sm mt-4">
              <p className="text-muted-foreground text-xs">{evidenceDrawerRow.question}</p>
              <div>
                <div className="text-xs uppercase text-muted-foreground mb-1">Web sources</div>
                {evidenceDrawerRow.sources.length === 0 ? (
                  <span className="text-muted-foreground">None</span>
                ) : (
                  <ul className="space-y-2">
                    {evidenceDrawerRow.sources.map((s, i) => (
                      <li key={i}>
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary underline break-all text-xs inline-flex gap-1"
                        >
                          <ExternalLink className="h-3 w-3 shrink-0" />
                          {s.title || s.url}
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <div className="text-xs uppercase text-muted-foreground mb-1">
                  Document validation
                </div>
                {evidenceDrawerRow.validationSources.length === 0 ? (
                  <span className="text-muted-foreground">No citations</span>
                ) : (
                  <ul className="space-y-3">
                    {evidenceDrawerRow.validationSources.map((src, idx) => (
                      <li key={idx} className="border rounded-md p-3 space-y-2">
                        <div className="font-medium">{src.document}</div>
                        {typeof src.page === "number" && (
                          <div className="text-xs text-muted-foreground">Page {src.page}</div>
                        )}
                        {src.url?.trim() && (
                          <a
                            href={src.url.trim()}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary text-xs underline break-all inline-flex gap-1"
                          >
                            Open link <ExternalLink className="h-3 w-3 shrink-0" />
                          </a>
                        )}
                        {src.excerpt && (
                          <blockquote className="text-xs border-l-2 pl-2 italic text-muted-foreground whitespace-pre-wrap">
                            {src.excerpt}
                          </blockquote>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

interface SectionRowsProps {
  sectionNo: number;
  sectionName: string;
  rows: KYCRow[];
  compact?: boolean;
  onRowActivate?: (serialNo: number) => void;
  getRowClassName?: (row: KYCRow) => string;
  renderAnswerCell: (row: KYCRow) => ReactNode;
  renderSourcesCell: (row: KYCRow) => ReactNode;
  renderValidationCell: (row: KYCRow) => ReactNode;
  renderConfidenceCell: (row: KYCRow) => ReactNode;
  renderValidationSourcesCell: (row: KYCRow) => ReactNode;
  renderKycAgentReconCell: (row: KYCRow) => ReactNode;
  renderAnalystCommentsCell: (row: KYCRow) => ReactNode;
}

function SectionRows({
  sectionNo,
  sectionName,
  rows,
  compact = false,
  onRowActivate,
  getRowClassName,
  renderAnswerCell,
  renderSourcesCell,
  renderValidationCell,
  renderConfidenceCell,
  renderValidationSourcesCell,
  renderKycAgentReconCell,
  renderAnalystCommentsCell,
}: SectionRowsProps) {
  const cell = compact ? "text-xs py-1.5" : "text-sm py-2.5";
  return (
    <>
      <TableRow className="bg-muted/90 sticky top-0 z-10 shadow-sm backdrop-blur-sm">
        <TableCell colSpan={10} className="font-semibold text-sm">
          Section {sectionNo} &mdash; {sectionName}
        </TableCell>
      </TableRow>
      {rows.map((row) => (
        <TableRow
          key={row.serialNo}
          className={`align-top cursor-pointer ${getRowClassName?.(row) ?? ""}`.trim()}
          tabIndex={0}
          onClick={(e) => {
            if ((e.target as HTMLElement).closest("a,button,input,textarea,select")) return;
            onRowActivate?.(row.serialNo);
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onRowActivate?.(row.serialNo);
            }
          }}
        >
          <TableCell className={`${cell} font-medium align-top`}>{row.sectionNo}</TableCell>
          <TableCell className={`${cell} font-medium align-top`}>{row.serialNo}</TableCell>
          <TableCell className={`${cell} align-top`}>{row.question}</TableCell>
          <TableCell className={`bg-primary/5 align-top ${cell}`}>{renderAnswerCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderSourcesCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderValidationCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderConfidenceCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderValidationSourcesCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderKycAgentReconCell(row)}</TableCell>
          <TableCell className={`align-top ${cell}`}>{renderAnalystCommentsCell(row)}</TableCell>
        </TableRow>
      ))}
    </>
  );
}
