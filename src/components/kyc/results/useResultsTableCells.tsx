import { useCallback, useState, type ReactNode } from "react";
import { Check, ExternalLink, Eye, Pencil, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type { KYCRow, KycAgentReconValue, ValidationStatus } from "@/data/kycQuestions";
import { classifyRowDelta } from "@/lib/kycAnalystToolkit";
import type { EditingField } from "./types";
import {
  buildValidationSourcesPreview,
  sourcesToText,
  textToSources,
} from "./utils";

interface UseResultsTableCellsOptions {
  rows: KYCRow[];
  onRowChange: (serialNo: number, updates: Partial<KYCRow>) => void;
  baselineBySerial: Map<number, KYCRow> | null;
  onValidationPeek: (row: KYCRow) => void;
}

export function useResultsTableCells({
  rows,
  onRowChange,
  baselineBySerial,
  onValidationPeek,
}: UseResultsTableCellsOptions) {
  const [editing, setEditing] = useState<{ serialNo: number; field: EditingField } | null>(null);
  const [editValue, setEditValue] = useState("");

  const startEditing = useCallback((serialNo: number, field: EditingField, current: string) => {
    setEditing({ serialNo, field });
    setEditValue(current);
  }, []);

  const cancelEdit = useCallback(() => {
    setEditing(null);
    setEditValue("");
  }, []);

  const saveEdit = useCallback(() => {
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
  }, [editValue, editing, onRowChange]);

  const renderEditor = useCallback(
    (placeholder: string) => (
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
    ),
    [cancelEdit, editValue, saveEdit],
  );

  const renderAnswerCell = useCallback(
    (row: KYCRow) => {
      const isEditing = editing?.serialNo === row.serialNo && editing.field === "answer";
      if (isEditing) return renderEditor("Enter answer...");
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
    },
    [editing, renderEditor, startEditing],
  );

  const renderSourcesCell = useCallback(
    (row: KYCRow) => {
      const isEditing = editing?.serialNo === row.serialNo && editing.field === "sources";
      if (isEditing) return renderEditor("One source per line. Format: Title | https://example.com");
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
              onClick={() => startEditing(row.serialNo, "sources", sourcesToText(row.sources))}
              className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-muted rounded"
              aria-label="Edit sources"
            >
              <Pencil className="h-3 w-3 text-muted-foreground" />
            </button>
          </div>
        </div>
      );
    },
    [editing, renderEditor, startEditing],
  );

  const renderValidationCell = useCallback((row: KYCRow) => {
    const value: ValidationStatus = row.validation;
    return (
      <div className="min-h-[32px] flex items-center">
        {value === "Yes" ? (
          <Badge className="bg-green-500/20 text-green-700 border-green-500/50 text-xs">Yes</Badge>
        ) : value === "No" ? (
          <Badge className="bg-red-500/20 text-red-700 border-red-500/50 text-xs">No</Badge>
        ) : (
          <span className="text-muted-foreground text-xs">—</span>
        )}
      </div>
    );
  }, []);

  const renderConfidenceCell = useCallback((row: KYCRow) => {
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
  }, []);

  const renderValidationSourcesCell = useCallback(
    (row: KYCRow) => {
      const delta = baselineBySerial
        ? classifyRowDelta(row, baselineBySerial.get(row.serialNo))
        : null;
      const hasSources = row.validationSources.length > 0;
      const showPeek = row.validation === "Yes" || hasSources || Boolean(delta?.changed);

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
                onClick={() => onValidationPeek(row)}
              >
                <Eye className="h-3.5 w-3.5" aria-hidden />
              </Button>
            )}
          </div>
        </div>
      );
    },
    [baselineBySerial, onValidationPeek],
  );

  const renderKycAgentReconCell = useCallback(
    (row: KYCRow) => {
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
    },
    [onRowChange],
  );

  const renderAnalystCommentsCell = useCallback(
    (row: KYCRow) => {
      const isEditing =
        editing?.serialNo === row.serialNo && editing.field === "analystComments";
      if (isEditing) return renderEditor("Add analyst comments...");
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
              onClick={() => startEditing(row.serialNo, "analystComments", row.analystComments)}
              className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-muted rounded"
              aria-label="Edit analyst comments"
            >
              <Pencil className="h-3 w-3 text-muted-foreground" />
            </button>
          </div>
        </div>
      );
    },
    [editing, renderEditor, startEditing],
  );

  return {
    renderAnswerCell,
    renderSourcesCell,
    renderValidationCell,
    renderConfidenceCell,
    renderValidationSourcesCell,
    renderKycAgentReconCell,
    renderAnalystCommentsCell,
  };
}
