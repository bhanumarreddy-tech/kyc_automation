import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Download, FileSpreadsheet, FileText, FileJson, Archive, FileDown, Send } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import type { KYCRow } from "@/data/kycQuestions";
import { apiUrl } from "@/lib/api";
import type { AuditLogEntry } from "@/lib/kycAnalystToolkit";

interface ExportOptionsProps {
  companyName: string;
  rows: KYCRow[];
  /** When set (non-empty), tabular exports use this subset (e.g. bulk-selected rows). */
  selectedRows?: KYCRow[];
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
  selectedRows,
  submissionId,
  savedAt,
  referenceUrls,
  attachedDocuments,
  analystName,
  onAudit,
}: ExportOptionsProps) {
  const { toast } = useToast();
  const [isExporting, setIsExporting] = useState(false);

  const effectiveRows = selectedRows && selectedRows.length > 0 ? selectedRows : rows;

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
      rows: effectiveRows,
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
      detail: { rowCount: effectiveRows.length, submissionId },
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
      questionnaire: effectiveRows.map((row) => ({
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
    for (const row of effectiveRows) {
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
      detail: { rowCount: effectiveRows.length },
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
      printWindow.document.write(generatePDFHTML(companyName, effectiveRows));
      printWindow.document.close();
      printWindow.onload = () => {
        printWindow.print();
      };
      toast({ title: "PDF ready", description: "Use the print dialog to save as PDF" });
      onAudit?.({
        action: "export_pdf",
        analyst: analystName?.trim() || undefined,
        detail: { rowCount: effectiveRows.length },
      });
    } finally {
      setIsExporting(false);
    }
  };

  const exportMemoPdf = async () => {
    setIsExporting(true);
    try {
      const printWindow = window.open("", "_blank");
      if (!printWindow) {
        toast({
          title: "Error",
          description: "Please allow popups for memo export",
          variant: "destructive",
        });
        return;
      }
      printWindow.document.write(generateMemoHTML(companyName, effectiveRows, analystName, submissionId));
      printWindow.document.close();
      printWindow.onload = () => printWindow.print();
      toast({
        title: "Executive memo ready",
        description: "Print to PDF — one-page summary for stakeholders.",
      });
      onAudit?.({
        action: "export_memo_pdf",
        analyst: analystName?.trim() || undefined,
        detail: { rowCount: effectiveRows.length },
      });
    } finally {
      setIsExporting(false);
    }
  };

  const exportZipBundle = async () => {
    setIsExporting(true);
    try {
      const { default: JSZip } = await import("jszip");
      const zip = new JSZip();
      zip.file(
        "README.txt",
        [
          "KYC automation evidence bundle (ZIP)",
          `Company: ${companyName}`,
          `Generated: ${new Date().toISOString()}`,
          submissionId ? `Submission: ${submissionId}` : "",
          "",
          "Contains results.csv and snapshot.json.",
        ].join("\n"),
      );
      const lines = [HEADERS.join(",")];
      for (const row of effectiveRows) {
        lines.push(rowToColumns(row).map(csvEscape).join(","));
      }
      zip.file("results.csv", lines.join("\n"));
      zip.file(
        "snapshot.json",
        JSON.stringify(
          { companyName, submissionId, rows: effectiveRows, exportedAt: new Date().toISOString() },
          null,
          2,
        ),
      );
      const blob = await zip.generateAsync({ type: "blob" });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${(companyName || "KYC").replace(/[^\w-]+/g, "_")}_evidence.zip`;
      a.click();
      window.URL.revokeObjectURL(url);
      toast({ title: "ZIP downloaded", description: "Includes CSV and JSON snapshot." });
      onAudit?.({
        action: "export_zip",
        analyst: analystName?.trim() || undefined,
        detail: { rowCount: effectiveRows.length },
      });
    } catch (e) {
      toast({
        title: "ZIP failed",
        description: e instanceof Error ? e.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setIsExporting(false);
    }
  };

  const pushWebhook = async () => {
    const prev = localStorage.getItem("kyc_export_webhook_url") ?? "";
    const url = window.prompt("POST JSON body to this URL (CORS must allow the browser origin)", prev)?.trim();
    if (!url) return;
    localStorage.setItem("kyc_export_webhook_url", url);
    try {
      const res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          event: "kyc_automation_export",
          companyName: companyName.trim(),
          submissionId: submissionId ?? null,
          analystName: analystName?.trim() ?? null,
          rowCount: effectiveRows.length,
          rows: effectiveRows,
        }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      toast({ title: "Webhook delivered", description: url.slice(0, 48) });
      onAudit?.({
        action: "webhook_push",
        analyst: analystName?.trim() || undefined,
        detail: { url },
      });
    } catch (e) {
      toast({
        title: "Webhook failed",
        description: e instanceof Error ? e.message : "Network error",
        variant: "destructive",
      });
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
          Full table PDF
        </DropdownMenuItem>
        <DropdownMenuItem onClick={exportMemoPdf}>
          <FileDown className="h-4 w-4 mr-2" />
          Executive memo (print PDF)
        </DropdownMenuItem>
        <DropdownMenuItem onClick={exportZipBundle}>
          <Archive className="h-4 w-4 mr-2" />
          Evidence ZIP (CSV + JSON)
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => void pushWebhook()}>
          <Send className="h-4 w-4 mr-2" />
          Push JSON to webhook
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

function generateMemoHTML(
  companyName: string,
  rows: KYCRow[],
  analystName?: string,
  submissionId?: string | null,
): string {
  const answered = rows.filter((r) => {
    const a = r.answer.trim().toLowerCase();
    return Boolean(a && a !== "not found");
  }).length;
  const validationYes = rows.filter((r) => r.validation === "Yes").length;
  const needsReview = rows.filter((r) => r.validation !== "Yes").length;
  const completion = rows.length ? Math.round((answered / rows.length) * 100) : 0;

  return `<!DOCTYPE html>
<html>
<head>
  <title>KYC Memo — ${escapeHtml(companyName)}</title>
  <style>
    body { font-family: Georgia, serif; margin: 48px; max-width: 720px; color: #222; }
    .brand { font-size: 11px; letter-spacing: 0.12em; text-transform: uppercase; color: #666; }
    h1 { font-size: 26px; margin: 8px 0 24px; }
    .metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 24px 0; }
    .metric { border: 1px solid #ddd; padding: 12px; border-radius: 8px; }
    .metric .v { font-size: 22px; font-weight: 700; }
    .footer { margin-top: 40px; font-size: 11px; color: #666; }
  </style>
</head>
<body>
  <div class="brand">Tiger Analytics · KYC Automation</div>
  <h1>${escapeHtml(companyName)}</h1>
  <p><strong>Readiness summary</strong> — generated ${new Date().toLocaleString()}</p>
  ${submissionId ? `<p>Submission ID: <code>${escapeHtml(submissionId)}</code></p>` : ""}
  ${analystName?.trim() ? `<p>Analyst: ${escapeHtml(analystName.trim())}</p>` : ""}
  <div class="metrics">
    <div class="metric"><div>Completion</div><div class="v">${completion}%</div></div>
    <div class="metric"><div>AI validation Yes</div><div class="v">${validationYes}/${rows.length}</div></div>
    <div class="metric"><div>Needs review</div><div class="v">${needsReview}</div></div>
  </div>
  <p>This one-pager summarizes questionnaire coverage. Attach the full CSV export from the app for detailed citations.</p>
  <div class="footer">Print this page to PDF for sharing. Confidential — internal use.</div>
</body>
</html>`;
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
