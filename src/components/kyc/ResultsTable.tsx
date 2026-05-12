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
}: ResultsTableProps) {
  const [editing, setEditing] = useState<{ serialNo: number; field: EditingField } | null>(
    null
  );
  const [editValue, setEditValue] = useState("");
  const [filters, setFilters] = useState<TableFiltersState>(INITIAL_FILTERS);
  const [sortColumn, setSortColumn] = useState<SortColumnId | null>(null);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const filteredSortedGrouped = useMemo(() => {
    const filtered = rows.filter((row) => rowPassesFilters(row, filters));
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
  }, [rows, filters, sortColumn, sortDir]);

  const filteredCount = useMemo(
    () => rows.filter((row) => rowPassesFilters(row, filters)).length,
    [rows, filters]
  );

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
    if (row.validation !== "Yes") {
      return <span className="text-muted-foreground text-xs">—</span>;
    }
    return (
      <div className="space-y-1">
        {row.validationSources.length === 0 ? (
          <span className="text-muted-foreground text-xs">No document source</span>
        ) : (
          row.validationSources.map((src, idx) => (
            <div key={idx} className="text-xs">
              <span className="font-medium">{src.document}</span>
              {typeof src.page === "number" && (
                <span className="text-muted-foreground"> (p.{src.page})</span>
              )}
              {src.excerpt && (
                <div className="text-muted-foreground italic mt-0.5">
                  &ldquo;{src.excerpt}&rdquo;
                </div>
              )}
            </div>
          ))
        )}
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

  return (
    <div className="space-y-4">
      <KYCStatsBar rows={rows} />

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
          <ExportOptions companyName={companyName} rows={rows} />
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
    </div>
  );
}

interface SectionRowsProps {
  sectionNo: number;
  sectionName: string;
  rows: KYCRow[];
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
        <TableRow key={row.serialNo} className="align-top">
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
