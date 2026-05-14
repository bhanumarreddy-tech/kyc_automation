import {
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
  Filter,
  Pencil,
  RotateCcw,
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
import { Switch } from "@/components/ui/switch";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { classifyRowDelta, readAuditLog, type AuditLogEntry } from "@/lib/kycAnalystToolkit";

type EditingField = "answer" | "sources" | "analystComments";

export type SortColumnId =
  | "sectionNo"
  | "serialNo"
  | "question"
  | "answer"
  | "sources"
  | "validation"
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
          className="inline-flex items-center gap-1 text-left font-medium hover:text-foreground/90 mr-auto"
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

  const baselineBySerial = useMemo(() => {
    if (!comparisonBaseline?.length) return null;
    return new Map(comparisonBaseline.map((r) => [r.serialNo, r]));
  }, [comparisonBaseline]);

  const getRowHighlightClass = (row: KYCRow) => {
    if (!baselineBySerial) return "";
    const d = classifyRowDelta(row, baselineBySerial.get(row.serialNo));
    return d.changed ? "bg-amber-500/10 dark:bg-amber-500/15" : "";
  };

  const filteredSortedGrouped = useMemo(() => {
    let filtered = rows.filter((row) => rowPassesFilters(row, filters));
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
  }, [rows, filters, sortColumn, sortDir, showChangedOnly, baselineBySerial]);

  const filteredCount = useMemo(() => {
    let filtered = rows.filter((row) => rowPassesFilters(row, filters));
    if (showChangedOnly && baselineBySerial) {
      filtered = filtered.filter((row) =>
        classifyRowDelta(row, baselineBySerial.get(row.serialNo)).changed
      );
    }
    return filtered.length;
  }, [rows, filters, showChangedOnly, baselineBySerial]);

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

  const renderValidationSourcesCell = (row: KYCRow) => {
    const delta = baselineBySerial
      ? classifyRowDelta(row, baselineBySerial.get(row.serialNo))
      : null;
    const body =
      row.validation !== "Yes" ? (
        <span className="text-muted-foreground text-xs">—</span>
      ) : row.validationSources.length === 0 ? (
        <span className="text-muted-foreground text-xs">No document source</span>
      ) : (
        <div className="space-y-1">
          {row.validationSources.map((src, idx) => (
            <div key={idx} className="text-xs">
              <span className="font-medium">{src.document}</span>
              {src.url?.trim() && (
                <div className="mt-0.5">
                  <a
                    href={src.url.trim()}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary underline break-all"
                  >
                    {src.url.trim()}
                  </a>
                </div>
              )}
              {typeof src.page === "number" && (
                <span className="text-muted-foreground"> (p.{src.page})</span>
              )}
              {src.excerpt && (
                <div className="text-muted-foreground italic mt-0.5 line-clamp-2">
                  &ldquo;{src.excerpt}&rdquo;
                </div>
              )}
            </div>
          ))}
        </div>
      );

    return (
      <div className="space-y-1.5">
        {delta?.changed && (
          <div className="text-[10px] uppercase tracking-wide text-amber-800 dark:text-amber-300 font-medium">
            Δ {delta.tags.join(" · ")}
          </div>
        )}
        {body}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="h-7 text-xs w-full max-w-[140px]"
          onClick={() => setValidationPeekRow(row)}
        >
          Source peek
        </Button>
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

      <div className="border rounded-lg overflow-hidden">
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
                  getRowClassName={getRowHighlightClass}
                  renderAnswerCell={renderAnswerCell}
                  renderSourcesCell={renderSourcesCell}
                  renderValidationCell={renderValidationCell}
                  renderValidationSourcesCell={renderValidationSourcesCell}
                  renderKycAgentReconCell={renderKycAgentReconCell}
                  renderAnalystCommentsCell={renderAnalystCommentsCell}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <Dialog open={validationPeekRow !== null} onOpenChange={(o) => !o && setValidationPeekRow(null)}>
        <DialogContent className="max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Validation sources — Q{validationPeekRow?.serialNo ?? ""}</DialogTitle>
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
              <p className="text-muted-foreground text-xs">{validationPeekRow.question}</p>
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
          </DialogHeader>
          <p className="text-xs text-muted-foreground">
            Entries cover exports, sign-offs, and reruns while using this browser. This is not a
            server-side compliance ledger.
          </p>
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
    </div>
  );
}

interface SectionRowsProps {
  sectionNo: number;
  sectionName: string;
  rows: KYCRow[];
  getRowClassName?: (row: KYCRow) => string;
  renderAnswerCell: (row: KYCRow) => ReactNode;
  renderSourcesCell: (row: KYCRow) => ReactNode;
  renderValidationCell: (row: KYCRow) => ReactNode;
  renderValidationSourcesCell: (row: KYCRow) => ReactNode;
  renderKycAgentReconCell: (row: KYCRow) => ReactNode;
  renderAnalystCommentsCell: (row: KYCRow) => ReactNode;
}

function SectionRows({
  sectionNo,
  sectionName,
  rows,
  getRowClassName,
  renderAnswerCell,
  renderSourcesCell,
  renderValidationCell,
  renderValidationSourcesCell,
  renderKycAgentReconCell,
  renderAnalystCommentsCell,
}: SectionRowsProps) {
  return (
    <>
      <TableRow className="bg-muted/40">
        <TableCell colSpan={9} className="font-semibold text-sm">
          Section {sectionNo} &mdash; {sectionName}
        </TableCell>
      </TableRow>
      {rows.map((row) => (
        <TableRow
          key={row.serialNo}
          className={`align-top ${getRowClassName?.(row) ?? ""}`.trim()}
        >
          <TableCell className="text-sm font-medium align-top">{row.sectionNo}</TableCell>
          <TableCell className="text-sm font-medium align-top">{row.serialNo}</TableCell>
          <TableCell className="text-sm align-top">{row.question}</TableCell>
          <TableCell className="bg-primary/5 align-top">{renderAnswerCell(row)}</TableCell>
          <TableCell className="align-top">{renderSourcesCell(row)}</TableCell>
          <TableCell className="align-top">{renderValidationCell(row)}</TableCell>
          <TableCell className="align-top">{renderValidationSourcesCell(row)}</TableCell>
          <TableCell className="align-top">{renderKycAgentReconCell(row)}</TableCell>
          <TableCell className="align-top">{renderAnalystCommentsCell(row)}</TableCell>
        </TableRow>
      ))}
    </>
  );
}
