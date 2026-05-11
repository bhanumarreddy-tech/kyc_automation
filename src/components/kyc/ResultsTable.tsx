import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
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
import { Check, ExternalLink, Pencil, RotateCcw, X } from "lucide-react";
import type {
  KYCRow,
  SourceLink,
  ValidationSource,
  ValidationStatus,
} from "@/data/kycQuestions";
import { ExportOptions } from "@/components/kyc/ExportOptions";
import { KYCStatsBar } from "@/components/kyc/KYCStatsBar";

type EditingField = "answer" | "sources" | "validationSources" | "analystComments";

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

const textToValidationSources = (text: string): ValidationSource[] => {
  return text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split("|").map((p) => p.trim()).filter(Boolean);
      const doc = parts[0] ?? line;
      let page: number | undefined;
      let excerpt: string | undefined;
      for (let i = 1; i < parts.length; i++) {
        const part = parts[i];
        const pageMatch = part.match(/^p\.?\s*(\d+)$/i);
        if (pageMatch) {
          page = parseInt(pageMatch[1], 10);
        } else {
          excerpt = excerpt ? `${excerpt} | ${part}` : part;
        }
      }
      return { document: doc, page, excerpt };
    });
};

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

  const grouped = useMemo(() => {
    const map = new Map<number, { sectionName: string; rows: KYCRow[] }>();
    for (const row of rows) {
      if (!map.has(row.sectionNo)) {
        map.set(row.sectionNo, { sectionName: row.sectionName, rows: [] });
      }
      map.get(row.sectionNo)!.rows.push(row);
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => a - b)
      .map(([sectionNo, value]) => ({ sectionNo, ...value }));
  }, [rows]);

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
    } else if (field === "validationSources") {
      onRowChange(serialNo, { validationSources: textToValidationSources(editValue) });
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
      <Select
        value={value === "" ? "__blank__" : value}
        onValueChange={(v) => {
          const next: ValidationStatus =
            v === "Yes" ? "Yes" : v === "No" ? "No" : "";
          const updates: Partial<KYCRow> = { validation: next };
          if (next !== "Yes") {
            updates.validationSources = [];
          }
          onRowChange(row.serialNo, updates);
        }}
      >
        <SelectTrigger className="h-8 w-[100px] text-xs">
          <SelectValue>
            {value === "Yes" ? (
              <Badge className="bg-green-500/20 text-green-700 border-green-500/50 text-xs">
                Yes
              </Badge>
            ) : value === "No" ? (
              <Badge className="bg-red-500/20 text-red-700 border-red-500/50 text-xs">
                No
              </Badge>
            ) : (
              <span className="text-muted-foreground text-xs">—</span>
            )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__blank__">—</SelectItem>
          <SelectItem value="Yes">Yes</SelectItem>
          <SelectItem value="No">No</SelectItem>
        </SelectContent>
      </Select>
    );
  };

  const renderValidationSourcesCell = (row: KYCRow) => {
    const isEditing =
      editing?.serialNo === row.serialNo && editing.field === "validationSources";
    if (isEditing) {
      return renderEditor(
        "One per line. Format: document.pdf | p.3 | optional excerpt"
      );
    }
    if (row.validation !== "Yes") {
      return <span className="text-muted-foreground text-xs">—</span>;
    }
    return (
      <div className="group">
        <div className="flex items-start gap-2">
          <div className="flex-1 space-y-1">
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
          <button
            onClick={() =>
              startEditing(
                row.serialNo,
                "validationSources",
                validationSourcesToText(row.validationSources)
              )
            }
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-muted rounded"
            aria-label="Edit validation sources"
          >
            <Pencil className="h-3 w-3 text-muted-foreground" />
          </button>
        </div>
      </div>
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

  return (
    <div className="space-y-4">
      <KYCStatsBar rows={rows} />

      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">KYC Results: {companyName}</h2>
          <p className="text-sm text-muted-foreground">
            {rows.length} questions across {grouped.length} sections
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
                <TableHead className="w-20">Section No.</TableHead>
                <TableHead className="w-24">Question No.</TableHead>
                <TableHead className="min-w-[260px]">Question</TableHead>
                <TableHead className="min-w-[240px] bg-primary/5">Answers</TableHead>
                <TableHead className="min-w-[220px]">Sources</TableHead>
                <TableHead className="w-[120px]">Validation</TableHead>
                <TableHead className="min-w-[220px]">Validation Sources</TableHead>
                <TableHead className="min-w-[200px]">Analyst Comments</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {grouped.map((section) => (
                <SectionRows
                  key={section.sectionNo}
                  sectionNo={section.sectionNo}
                  sectionName={section.sectionName}
                  rows={section.rows}
                  renderAnswerCell={renderAnswerCell}
                  renderSourcesCell={renderSourcesCell}
                  renderValidationCell={renderValidationCell}
                  renderValidationSourcesCell={renderValidationSourcesCell}
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
  renderAnswerCell: (row: KYCRow) => React.ReactNode;
  renderSourcesCell: (row: KYCRow) => React.ReactNode;
  renderValidationCell: (row: KYCRow) => React.ReactNode;
  renderValidationSourcesCell: (row: KYCRow) => React.ReactNode;
  renderAnalystCommentsCell: (row: KYCRow) => React.ReactNode;
}

function SectionRows({
  sectionNo,
  sectionName,
  rows,
  renderAnswerCell,
  renderSourcesCell,
  renderValidationCell,
  renderValidationSourcesCell,
  renderAnalystCommentsCell,
}: SectionRowsProps) {
  return (
    <>
      <TableRow className="bg-muted/40">
        <TableCell colSpan={8} className="font-semibold text-sm">
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
          <TableCell className="align-top">{renderAnalystCommentsCell(row)}</TableCell>
        </TableRow>
      ))}
    </>
  );
}
