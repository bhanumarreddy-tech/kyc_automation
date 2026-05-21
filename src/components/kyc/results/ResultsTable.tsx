import { useEffect, useMemo, useState } from "react";
import {
  LayoutList,
  ListOrdered,
  PanelRight,
  RotateCcw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody } from "@/components/ui/table";
import { ExportOptions } from "@/components/kyc/ExportOptions";
import { KYCStatsBar } from "@/components/kyc/KYCStatsBar";
import { KYCCoverageCharts } from "@/components/kyc/KYCCoverageCharts";
import type { KYCRow } from "@/data/kycQuestions";
import { classifyRowDelta } from "@/lib/kycAnalystToolkit";
import { AuditLogDialog } from "./AuditLogDialog";
import { EvidenceDrawer } from "./EvidenceDrawer";
import { SplitDetailPanel } from "./EvidencePanel";
import { PipelineIntelligenceStrip } from "./PipelineIntelligenceStrip";
import { ResultsTableFilters } from "./ResultsTableFilters";
import { SectionRows } from "./SectionRows";
import {
  filtersAreActive,
  INITIAL_FILTERS,
  SORT_COLUMN_LABELS,
  type ResultsTableProps,
  type SortColumnId,
  type TableFiltersState,
} from "./types";
import { useResultsTableCells } from "./useResultsTableCells";
import { ValidationPeekDialog } from "./ValidationPeekDialog";
import {
  cmpByColumn,
  regroupConsecutive,
  rowInReviewQueue,
  rowPassesFilters,
} from "./utils";

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

  const cellRenderers = useResultsTableCells({
    rows,
    onRowChange,
    baselineBySerial,
    onValidationPeek: setValidationPeekRow,
  });

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
        classifyRowDelta(row, baselineBySerial.get(row.serialNo)).changed,
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
        classifyRowDelta(row, baselineBySerial.get(row.serialNo)).changed,
      );
    }
    return filtered.length;
  }, [rows, filters, showChangedOnly, baselineBySerial, reviewQueue, escalatedSerials]);

  const triageSerials = useMemo(() => {
    return rows
      .filter((r) => rowPassesFilters(r, filters) && rowInReviewQueue(r, escalatedSerials))
      .map((r) => r.serialNo)
      .sort((a, b) => a - b);
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

  const anyFilterActive = filtersAreActive(filters);
  const splitRow =
    evidenceDrawerRow ?? rows.find((r) => r.serialNo === detailFocusSerial) ?? null;

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
            const t = rows.find((r) => r.serialNo === detailFocusSerial) ?? rows[0] ?? null;
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

      <div className={`${splitDetail ? "grid gap-4 lg:grid-cols-[1fr_minmax(260px,360px)]" : ""}`}>
        <div className="border rounded-lg overflow-hidden min-w-0">
          <div className="overflow-x-auto">
            <Table>
              <ResultsTableFilters
                sortColumn={sortColumn}
                sortDir={sortDir}
                cycleSort={cycleSort}
                filters={filters}
                setFilters={setFilters}
              />
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
                    {...cellRenderers}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
        </div>

        {splitDetail && <SplitDetailPanel row={splitRow} />}
      </div>

      <ValidationPeekDialog
        row={validationPeekRow}
        baselineBySerial={baselineBySerial}
        onClose={() => setValidationPeekRow(null)}
      />
      <AuditLogDialog open={auditOpen} onOpenChange={setAuditOpen} />
      <EvidenceDrawer row={evidenceDrawerRow} onClose={() => setEvidenceDrawerRow(null)} />
    </div>
  );
}
