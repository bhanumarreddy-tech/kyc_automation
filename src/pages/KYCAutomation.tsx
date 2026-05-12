import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Upload, FileText, Home, X, ArrowLeft, Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import ProcessingView from "@/components/kyc/ProcessingView";
import { ResultsTable } from "@/components/kyc/ResultsTable";
import { kycQuestions } from "@/data/kycQuestions";
import type { KYCRow } from "@/data/kycQuestions";
import { apiUrl } from "@/lib/api";

type WorkflowStep = "upload" | "processing" | "results";
type MainTab = "run" | "history";

interface AttachedDocumentItem {
  filename: string;
  sizeBytes?: number | null;
  contentType?: string;
  objectKey?: string | null;
}

function attachmentDownloadUrl(submissionId: string, objectKey: string): string {
  const q = new URLSearchParams({ objectKey });
  return apiUrl(`/api/history/${encodeURIComponent(submissionId)}/attachments/download?${q.toString()}`);
}

function AttachmentNameLink(props: {
  submissionId: string;
  doc: AttachedDocumentItem;
  className?: string;
}) {
  const { submissionId, doc, className } = props;
  if (!doc.objectKey) {
    return <span className={className}>{doc.filename}</span>;
  }
  return (
    <a
      href={attachmentDownloadUrl(submissionId, doc.objectKey)}
      className={`text-primary underline-offset-4 hover:underline font-medium ${className ?? ""}`}
    >
      {doc.filename}
    </a>
  );
}

interface HistoryListItem {
  submissionId: string;
  companyName: string;
  createdAt: string;
  documentCount: number;
  attachedDocuments?: AttachedDocumentItem[];
  durationMs?: number | null;
}

function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms) || ms < 0) {
    return "—";
  }
  if (ms < 1000) {
    return `${ms} ms`;
  }
  const totalSeconds = Math.floor(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes <= 0) {
    return `${seconds}s`;
  }
  return `${minutes}m ${seconds}s`;
}

const API_ENDPOINT = apiUrl("/api/process");
const HISTORY_LIST_ENDPOINT = apiUrl("/api/history");

export default function KYCAutomation() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [step, setStep] = useState<WorkflowStep>("upload");
  const [companyName, setCompanyName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [rows, setRows] = useState<KYCRow[]>([]);
  const [mainTab, setMainTab] = useState<MainTab>("run");
  const [historyDetailId, setHistoryDetailId] = useState<string | null>(null);
  const [historyItems, setHistoryItems] = useState<HistoryListItem[]>([]);
  const [historyListLoading, setHistoryListLoading] = useState(false);
  const [historyListError, setHistoryListError] = useState<string | null>(null);
  const [historyDetailLoading, setHistoryDetailLoading] = useState(false);
  const [historyRunMeta, setHistoryRunMeta] = useState<{
    attachedDocuments: AttachedDocumentItem[];
    durationMs: number | null;
  } | null>(null);
  const [completedRunDownloads, setCompletedRunDownloads] = useState<{
    submissionId: string;
    documents: AttachedDocumentItem[];
  } | null>(null);

  useEffect(() => {
    const preventDefaults = (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
    };

    document.addEventListener("dragenter", preventDefaults);
    document.addEventListener("dragover", preventDefaults);
    document.addEventListener("dragleave", preventDefaults);
    document.addEventListener("drop", preventDefaults);

    return () => {
      document.removeEventListener("dragenter", preventDefaults);
      document.removeEventListener("dragover", preventDefaults);
      document.removeEventListener("dragleave", preventDefaults);
      document.removeEventListener("drop", preventDefaults);
    };
  }, []);

  useEffect(() => {
    if (mainTab !== "history" || historyDetailId !== null) {
      return;
    }
    let cancelled = false;
    const load = async () => {
      setHistoryListLoading(true);
      setHistoryListError(null);
      try {
        const res = await fetch(HISTORY_LIST_ENDPOINT);
        if (!res.ok) {
          throw new Error(`Failed to load history (${res.status})`);
        }
        const data = (await res.json()) as HistoryListItem[];
        if (!cancelled) {
          setHistoryItems(Array.isArray(data) ? data : []);
        }
      } catch (e) {
        if (!cancelled) {
          setHistoryListError(e instanceof Error ? e.message : "Failed to load history");
          setHistoryItems([]);
        }
      } finally {
        if (!cancelled) {
          setHistoryListLoading(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [mainTab, historyDetailId]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files);
      setFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const droppedFiles = Array.from(e.dataTransfer.files);
    const validExt = [".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx"];
    const validFiles = droppedFiles.filter((file) => {
      const ext = "." + (file.name.split(".").pop()?.toLowerCase() ?? "");
      return validExt.includes(ext);
    });

    if (validFiles.length !== droppedFiles.length) {
      toast({
        title: "Invalid file type",
        description: "Some files were skipped. Only PDF, JPG, PNG, DOC, DOCX are allowed.",
        variant: "destructive",
      });
    }

    setFiles((prev) => [...prev, ...validFiles]);
  };

  const handleDragEnter = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const closeHistoryDetail = () => {
    setHistoryDetailId(null);
    setHistoryRunMeta(null);
    setRows([]);
    setCompanyName("");
  };

  const openHistorySubmission = async (submissionId: string) => {
    setHistoryDetailLoading(true);
    setHistoryListError(null);
    try {
      const res = await fetch(apiUrl(`/api/history/${submissionId}`));
      if (res.status === 503) {
        toast({
          title: "History unavailable",
          description: "Database is not configured on the server.",
          variant: "destructive",
        });
        return;
      }
      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `Failed to load submission (${res.status})`);
      }
      const data = (await res.json()) as {
        companyName: string;
        rows: KYCRow[];
        attachedDocuments?: AttachedDocumentItem[];
        durationMs?: number | null;
      };
      if (!data?.rows || !Array.isArray(data.rows)) {
        throw new Error("Invalid submission payload");
      }
      setCompanyName(data.companyName);
      setRows(data.rows);
      setHistoryRunMeta({
        attachedDocuments: Array.isArray(data.attachedDocuments)
          ? data.attachedDocuments
          : [],
        durationMs: data.durationMs ?? null,
      });
      setHistoryDetailId(submissionId);
    } catch (e) {
      console.error(e);
      toast({
        title: "Could not open submission",
        description: e instanceof Error ? e.message : "Unknown error",
        variant: "destructive",
      });
    } finally {
      setHistoryDetailLoading(false);
    }
  };

  const buildEmptyRows = (): KYCRow[] =>
    kycQuestions.map((q) => ({
      sectionNo: q.sectionNo,
      sectionName: q.sectionName,
      serialNo: q.serialNo,
      question: q.question,
      answer: "",
      sources: [],
      validation: "",
      validationSources: [],
      analystComments: "",
    }));

  const handleStartProcessing = async () => {
    if (!companyName.trim()) {
      toast({
        title: "Company name required",
        description: "Please enter a company name",
        variant: "destructive",
      });
      return;
    }

    setStep("processing");
    setCompletedRunDownloads(null);

    try {
      const formData = new FormData();
      formData.append("company_name", companyName.trim());
      for (const file of files) {
        formData.append("files", file, file.name);
      }

      const res = await fetch(API_ENDPOINT, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`Backend error ${res.status}: ${text || res.statusText}`);
      }

      const data = (await res.json()) as {
        rows: KYCRow[];
        submissionId?: string;
        durationMs?: number | null;
        attachedDocuments?: AttachedDocumentItem[];
      };
      if (!data?.rows || !Array.isArray(data.rows)) {
        throw new Error("Backend returned an invalid response");
      }

      setRows(data.rows);
      setStep("results");

      if (
        typeof data.submissionId === "string" &&
        data.submissionId.length > 0 &&
        Array.isArray(data.attachedDocuments) &&
        data.attachedDocuments.length > 0
      ) {
        setCompletedRunDownloads({
          submissionId: data.submissionId,
          documents: data.attachedDocuments,
        });
      } else {
        setCompletedRunDownloads(null);
      }

      const durationLabel =
        typeof data.durationMs === "number" && !Number.isNaN(data.durationMs)
          ? ` Run time ${formatDurationMs(data.durationMs)}.`
          : "";

      toast({
        title: "Processing complete",
        description: data.submissionId
          ? `KYC questionnaire populated for ${companyName.trim()}. Saved to history.${durationLabel}`
          : `KYC questionnaire populated for ${companyName.trim()}.${durationLabel}`,
      });
    } catch (error) {
      console.error("Processing error:", error);
      toast({
        title: "Processing failed",
        description: error instanceof Error ? error.message : "Unknown error occurred",
        variant: "destructive",
      });
      setStep("upload");
    }
  };

  const handleReset = () => {
    setStep("upload");
    setCompanyName("");
    setFiles([]);
    setRows([]);
    setCompletedRunDownloads(null);
  };

  const handleRowChange = (serialNo: number, updates: Partial<KYCRow>) => {
    setRows((prev) =>
      prev.map((row) => (row.serialNo === serialNo ? { ...row, ...updates } : row))
    );
  };

  const handleBack = () => {
    if (mainTab === "history" && historyDetailId) {
      closeHistoryDetail();
      return;
    }
    if (step === "results") {
      setStep("upload");
    } else if (step === "upload") {
      navigate("/");
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <div className="container mx-auto px-4 py-8">
        <div className="mb-8 flex items-start justify-between">
          <div>
            <h1 className="text-4xl font-bold text-foreground mb-2">
              Tiger Analytics KYC Automation
            </h1>
            <p className="text-muted-foreground">Commercial Banking</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              onClick={handleBack}
              className="shrink-0"
              title="Back"
            >
              <ArrowLeft className="h-5 w-5" />
            </Button>
            <Button
              variant="outline"
              size="icon"
              onClick={() => navigate("/")}
              className="shrink-0"
              title="Home"
            >
              <Home className="h-5 w-5" />
            </Button>
          </div>
        </div>

        <Tabs
          value={mainTab}
          onValueChange={(v) => setMainTab(v as MainTab)}
          className="w-full"
        >
          <TabsList>
            <TabsTrigger value="run">New run</TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
          </TabsList>

          <TabsContent value="run" className="mt-6 space-y-6">
            {step === "upload" && (
          <div className="max-w-2xl mx-auto space-y-6">
            <div className="bg-card p-6 rounded-lg border shadow-sm space-y-6">
              <div className="space-y-2">
                <Label htmlFor="companyName">Client Name</Label>
                <Input
                  id="companyName"
                  placeholder='e.g. Best Buy Co., Inc. · add NYSE:BBY or jurisdiction if ambiguous'
                  value={companyName}
                  onChange={(e) => setCompanyName(e.target.value)}
                />
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Web search grounds answers better with the legal name; add exchange:ticker or
                  country when the name is vague.
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="documents">Upload Documents</Label>
                <div
                  className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
                    isDragging
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  }`}
                  onDrop={handleDrop}
                  onDragEnter={handleDragEnter}
                  onDragLeave={handleDragLeave}
                  onDragOver={handleDragOver}
                >
                  <input
                    id="documents"
                    type="file"
                    multiple
                    accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  <label
                    htmlFor="documents"
                    className="cursor-pointer flex flex-col items-center gap-2"
                  >
                    <Upload className="h-12 w-12 text-muted-foreground" />
                    <p className="text-sm text-muted-foreground">
                      {isDragging ? "Drop files here" : "Click to upload or drag and drop"}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      PDF, JPG, PNG, DOC, DOCX (max 50MB each)
                    </p>
                  </label>
                </div>

                {files.length > 0 && (
                  <div className="mt-4 space-y-2">
                    {files.map((file, index) => (
                      <div
                        key={index}
                        className="flex items-center gap-2 p-2 bg-muted rounded group"
                      >
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm flex-1 truncate">{file.name}</span>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {(file.size / 1024 / 1024).toFixed(2)} MB
                        </span>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={() => removeFile(index)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <Button
                onClick={handleStartProcessing}
                className="w-full"
                disabled={!companyName.trim()}
              >
                Start Processing
              </Button>
            </div>
          </div>
            )}

            {step === "processing" && (
          <ProcessingView companyName={companyName} fileCount={files.length} />
            )}

            {step === "results" && (
          <div className="space-y-4">
            {completedRunDownloads && completedRunDownloads.documents.length > 0 && (
              <div className="rounded-md border bg-muted/30 p-4 text-sm space-y-2">
                <div className="text-muted-foreground text-xs uppercase tracking-wide">
                  Stored uploads (click to download)
                </div>
                <ul className="space-y-2">
                  {completedRunDownloads.documents.map((doc, idx) => (
                    <li
                      key={`${doc.objectKey ?? doc.filename}-${idx}`}
                      className="flex flex-wrap items-center gap-2 p-2 bg-background rounded-md border"
                    >
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                      <AttachmentNameLink
                        submissionId={completedRunDownloads.submissionId}
                        doc={doc}
                        className="flex-1 min-w-0 truncate text-left"
                      />
                      {typeof doc.sizeBytes === "number" && doc.sizeBytes >= 0 && (
                        <span className="text-xs text-muted-foreground whitespace-nowrap">
                          {(doc.sizeBytes / 1024 / 1024).toFixed(2)} MB
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <ResultsTable
              companyName={companyName}
              rows={rows}
              onReset={handleReset}
              onRowChange={handleRowChange}
            />
          </div>
            )}
          </TabsContent>

          <TabsContent value="history" className="mt-6 space-y-4">
            {historyDetailLoading && (
              <div className="flex justify-center py-16">
                <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" aria-hidden />
              </div>
            )}

            {!historyDetailLoading && historyDetailId && (
              <>
                <div className="flex flex-wrap gap-2">
                  <Button type="button" variant="outline" onClick={closeHistoryDetail}>
                    Back to list
                  </Button>
                </div>

                {historyRunMeta && (
                  <div className="rounded-md border bg-muted/30 p-4 text-sm space-y-3">
                    <div className="flex flex-wrap gap-x-6 gap-y-1">
                      <div>
                        <span className="text-muted-foreground">Run duration</span>
                        {": "}
                        <span className="font-medium">
                          {formatDurationMs(historyRunMeta.durationMs)}
                        </span>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <div className="text-muted-foreground text-xs uppercase tracking-wide">
                        Attached documents
                      </div>
                      {historyRunMeta.attachedDocuments.length === 0 ? (
                        <p className="text-muted-foreground">No documents were uploaded.</p>
                      ) : (
                        <ul className="space-y-2">
                          {historyRunMeta.attachedDocuments.map((doc, idx) => (
                            <li
                              key={`${doc.filename}-${idx}`}
                              className="flex flex-wrap items-center gap-x-3 gap-y-2 p-2 bg-background rounded-md border"
                            >
                              <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                              <AttachmentNameLink
                                submissionId={historyDetailId}
                                doc={doc}
                                className="flex-1 min-w-0 truncate text-left"
                              />
                              {typeof doc.sizeBytes === "number" && doc.sizeBytes >= 0 && (
                                <span className="text-xs text-muted-foreground whitespace-nowrap">
                                  {(doc.sizeBytes / 1024 / 1024).toFixed(2)} MB
                                </span>
                              )}
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                )}

                <ResultsTable
                  companyName={companyName}
                  rows={rows}
                  onReset={closeHistoryDetail}
                  onRowChange={handleRowChange}
                />
              </>
            )}

            {!historyDetailLoading && !historyDetailId && (
              <>
                {historyListLoading && (
                  <div className="flex justify-center py-16">
                    <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" aria-hidden />
                  </div>
                )}
                {historyListError && (
                  <p className="text-sm text-destructive">{historyListError}</p>
                )}
                {!historyListLoading && !historyListError && historyItems.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    No saved runs yet. Complete a run while the server has{" "}
                    <code className="rounded bg-muted px-1 py-0.5 text-xs">DATABASE_URL</code> set
                    to store results here.
                  </p>
                )}
                {!historyListLoading && historyItems.length > 0 && (
                  <div className="rounded-md border bg-card">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Client</TableHead>
                          <TableHead className="min-w-[140px] max-w-[260px]">Documents</TableHead>
                          <TableHead className="whitespace-nowrap hidden md:table-cell">
                            Duration
                          </TableHead>
                          <TableHead className="whitespace-nowrap">Saved</TableHead>
                          <TableHead className="text-right">Open</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {historyItems.map((item) => {
                          const docs = item.attachedDocuments ?? [];
                          return (
                            <TableRow key={item.submissionId}>
                              <TableCell className="font-medium max-w-[180px]">
                                <div className="truncate" title={item.companyName}>
                                  {item.companyName}
                                </div>
                                <div className="md:hidden text-xs text-muted-foreground mt-1">
                                  {formatDurationMs(item.durationMs)}
                                </div>
                              </TableCell>
                            <TableCell className="text-muted-foreground max-w-[220px] lg:max-w-[320px]">
                                <span className="block truncate">
                                  {docs.length === 0 ? (
                                    <span className="text-muted-foreground">None</span>
                                  ) : (
                                    <>
                                      {docs.map((doc, di) => (
                                        <span key={`${doc.objectKey ?? doc.filename}-${di}`}>
                                          {di > 0 ? ", " : null}
                                          {doc.objectKey ? (
                                            <AttachmentNameLink
                                              submissionId={item.submissionId}
                                              doc={doc}
                                              className="truncate inline-block max-w-full align-bottom"
                                            />
                                          ) : (
                                            <span
                                              title={doc.filename}
                                              className="text-foreground/90"
                                            >
                                              {doc.filename}
                                            </span>
                                          )}
                                        </span>
                                      ))}
                                    </>
                                  )}
                                </span>
                              </TableCell>
                              <TableCell className="hidden md:table-cell text-muted-foreground whitespace-nowrap">
                                {formatDurationMs(item.durationMs)}
                              </TableCell>
                              <TableCell className="text-muted-foreground whitespace-nowrap">
                                {new Date(item.createdAt).toLocaleString()}
                              </TableCell>
                              <TableCell className="text-right">
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="secondary"
                                  onClick={() =>
                                    void openHistorySubmission(item.submissionId)
                                  }
                                >
                                  Open
                                </Button>
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </div>
                )}
              </>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
