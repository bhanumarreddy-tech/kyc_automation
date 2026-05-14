import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Download, FileSpreadsheet, FileText, FileJson, Archive } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import type { KYCRow } from "@/data/kycQuestions";
import { apiUrl } from "@/lib/api";
import type { AuditLogEntry } from "@/lib/kycAnalystToolkit";

interface ExportOptionsProps {
  companyName: string;
  rows: KYCRow[];
  submissionId?: string | null;
  savedAt?: string | null;
  referenceUrls?: string[];
  attachedDocuments?: { filename: string; objectKey?: string | null }[];
  analystName?: string;
  onAudit?: (entry: Omit<AuditLogEntry, "at">) => void;
}

const HEADERS = [
  "Section No.",
  "Question No.",
  "Question",
  "Answers",
  "Sources",
  "AI Validation",
  "AI Validation Sources",
  "KYC_Agent_Recon",
  "Analyst Comments",
];

const csvEscape = (value: string): string => `"${value.replace(/"/g, '""')}"`;

const sourcesAsText = (row: KYCRow): string =>
  row.sources
    .map((s) => (s.title && s.title !== s.url ? `${s.title} (${s.url})` : s.url))
    .join("; ");

const validationSourcesAsText = (row: KYCRow): string =>
  row.validationSources
    .map((s) => {
      const parts = [s.document];
      if (s.url?.trim()) parts.push(s.url.trim());
      if (typeof s.page === "number") parts.push(`p.${s.page}`);
      if (s.excerpt) parts.push(`"${s.excerpt}"`);
      return parts.join(" ");
    })
    .join("; ");

const rowToColumns = (row: KYCRow): string[] => [
  String(row.sectionNo),
  String(row.serialNo),
  row.question,
  row.answer,
  sourcesAsText(row),
  row.validation || "",
  validationSourcesAsText(row),
  row.kycAgentRecon || "",
  row.analystComments,
];

export function ExportOptions({
  companyName,
  rows,
  submissionId,
  savedAt,
  referenceUrls,
  attachedDocuments,
  analystName,
  onAudit,
}: ExportOptionsProps) {
  const { toast } = useToast();
  const [isExporting, setIsExporting] = useState(false);

  const downloadFile = (content: string, filename: string, mimeType: string) => {
    const blob = new Blob([content], { type: mimeType });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  const exportDraftSnapshot = () => {
    const bundle = {
      kind: "kyc_automation_draft_v1",
      exportedAt: new Date().toISOString(),
      companyName: companyName.trim(),
      analystName: analystName?.trim() || undefined,
      submissionId: submissionId ?? undefined,
      rows,
    };
    downloadFile(
      JSON.stringify(bundle, null, 2),
      `${companyName || "KYC"}_draft_snapshot.json`,
      "application/json",
    );
    toast({ title: "Draft saved", description: "JSON snapshot downloaded to your device." });
    onAudit?.({
      action: "export_draft_snapshot",
      analyst: analystName?.trim() || undefined,
      detail: { rowCount: rows.length, submissionId },
    });
  };

  const exportEvidenceBundle = () => {
    const sid = submissionId?.trim();
    const attachments =
      attachedDocuments?.map((d) => ({
        filename: d.filename,
        objectKey: d.objectKey ?? null,
        downloadUrl:
          sid && d.objectKey
            ? apiUrl(
                `/api/history/${encodeURIComponent(sid)}/attachments/download?objectKey=${encodeURIComponent(d.objectKey)}`,
              )
            : null,
      })) ?? [];

    const bundle = {
      kind: "kyc_automation_evidence_bundle_v1",
      generatedAt: new Date().toISOString(),
      companyName: companyName.trim(),
      analystName: analystName?.trim() || undefined,
      submissionId: sid || undefined,
      savedAt: savedAt ?? undefined,
      referenceUrls: referenceUrls ?? [],
      attachments,
      questionnaire: rows.map((row) => ({
        sectionNo: row.sectionNo,
        sectionName: row.sectionName,
        serialNo: row.serialNo,
        question: row.question,
        answer: row.answer,
        sources: row.sources,
        validation: row.validation,
        validationSources: row.validationSources,
        kycAgentRecon: row.kycAgentRecon,
        analystComments: row.analystComments,
      })),
    };
    downloadFile(
      JSON.stringify(bundle, null, 2),
      `${companyName || "KYC"}_evidence_bundle.json`,
      "application/json",
    );
    toast({
      title: "Evidence bundle exported",
      description: "Includes questionnaire, citations metadata, and attachment download URLs.",
    });
    onAudit?.({
      action: "export_evidence_bundle",
      analyst: analystName?.trim() || undefined,
      detail: { submissionId: sid, attachmentCount: attachments.length },
    });
  };

  const exportCSV = () => {
    const lines = [HEADERS.join(",")];
    for (const row of rows) {
      lines.push(rowToColumns(row).map(csvEscape).join(","));
    }
    downloadFile(
      lines.join("\n"),
      `${companyName || "KYC"}_Results.csv`,
      "text/csv"
    );
    toast({ title: "Export complete", description: "CSV file downloaded" });
    onAudit?.({
      action: "export_csv",
      analyst: analystName?.trim() || undefined,
      detail: { rowCount: rows.length },
    });
  };

  const exportPDF = async () => {
    setIsExporting(true);
    try {
      const printWindow = window.open("", "_blank");
      if (!printWindow) {
        toast({
          title: "Error",
          description: "Please allow popups to export PDF",
          variant: "destructive",
        });
        return;
      }
      printWindow.document.write(generatePDFHTML(companyName, rows));
      printWindow.document.close();
      printWindow.onload = () => {
        printWindow.print();
      };
      toast({ title: "PDF ready", description: "Use the print dialog to save as PDF" });
      onAudit?.({
        action: "export_pdf",
        analyst: analystName?.trim() || undefined,
        detail: { rowCount: rows.length },
      });
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" disabled={isExporting}>
          <Download className="h-4 w-4 mr-2" />
          {isExporting ? "Exporting..." : "Export"}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={exportDraftSnapshot}>
          <FileJson className="h-4 w-4 mr-2" />
          Save draft snapshot (JSON)
        </DropdownMenuItem>
        <DropdownMenuItem onClick={exportEvidenceBundle}>
          <Archive className="h-4 w-4 mr-2" />
          Evidence bundle (JSON)
        </DropdownMenuItem>
        <DropdownMenuItem onClick={exportCSV}>
          <FileSpreadsheet className="h-4 w-4 mr-2" />
          Export as CSV
        </DropdownMenuItem>
        <DropdownMenuItem onClick={exportPDF}>
          <FileText className="h-4 w-4 mr-2" />
          Export as PDF
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function generatePDFHTML(companyName: string, rows: KYCRow[]): string {
  const bodyRows = rows
    .map(
      (row) => `
      <tr>
        <td>${escapeHtml(String(row.sectionNo))}</td>
        <td>${escapeHtml(String(row.serialNo))}</td>
        <td>${escapeHtml(row.question)}</td>
        <td>${escapeHtml(row.answer)}</td>
        <td>${escapeHtml(sourcesAsText(row))}</td>
        <td>${escapeHtml(row.validation || "")}</td>
        <td>${escapeHtml(validationSourcesAsText(row))}</td>
        <td>${escapeHtml(row.kycAgentRecon || "")}</td>
        <td>${escapeHtml(row.analystComments)}</td>
      </tr>`
    )
    .join("");

  return `<!DOCTYPE html>
<html>
<head>
  <title>KYC Report - ${escapeHtml(companyName)}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 20px; font-size: 11px; }
    h1 { color: #333; }
    table { width: 100%; border-collapse: collapse; margin-top: 20px; }
    th { background-color: #f5f5f5; padding: 8px; border: 1px solid #ddd; text-align: left; }
    td { padding: 6px; border: 1px solid #ddd; vertical-align: top; }
    @media print { body { margin: 0; } }
  </style>
</head>
<body>
  <h1>KYC Report: ${escapeHtml(companyName)}</h1>
  <div>Generated: ${new Date().toLocaleDateString()}</div>
  <table>
    <thead>
      <tr>${HEADERS.map((h) => `<th>${escapeHtml(h)}</th>`).join("")}</tr>
    </thead>
    <tbody>${bodyRows}</tbody>
  </table>
</body>
</html>`;
}
