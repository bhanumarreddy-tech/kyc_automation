import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import { AttachmentNameLink } from "@/components/kyc/AttachmentNameLink";
import { MetadataCollapsible } from "@/components/kyc/MetadataCollapsible";
import ProcessingView from "@/components/kyc/ProcessingView";
import { ResultsTable } from "@/components/kyc/ResultsTable";
import {
  Upload,
  FileText,
  Home,
  X,
  ArrowLeft,
  Loader2,
  Link2,
  RefreshCw,
  ListFilter,
} from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { kycQuestions, hydrateKycRows } from "@/data/kycQuestions";
import type { KYCRow } from "@/data/kycQuestions";
import { apiUrl } from "@/lib/api";
import { formatDurationMs, parseReferenceUrlsFromText } from "@/lib/kycPageUtils";
import type {
  AttachedDocumentItem,
  HistoryListItem,
  RerunEditState,
} from "@/types/kycHistory";
import {
  cancelProcessJob,
  startProcessJob,
  startRerunJob,
  subscribeProcessJob,
  type JobSnapshot,
} from "@/lib/processJobApi";
import {
  appendAuditLog,
  cloneRowsBaseline,
  getAnalystName,
  setAnalystName,
  getSignOff,
  setSignOff,
  loadUrlPresets,
  addUrlPreset,
  deleteUrlPreset,
  type UrlPreset,
} from "@/lib/kycAnalystToolkit";

type WorkflowStep = "upload" | "processing" | "results";
type MainTab = "run" | "history";

const HISTORY_LIST_ENDPOINT = apiUrl("/api/history");

export default function KYCAutomation() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [step, setStep] = useState<WorkflowStep>("upload");
  const [companyName, setCompanyName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [referenceUrlsText, setReferenceUrlsText] = useState("");
  const [isDragging, setIsDragging] = useState(false);
  const [rows, setRows] = useState<KYCRow[]>([]);
  const [mainTab, setMainTab] = useState<MainTab>("run");
  const [historyDetailId, setHistoryDetailId] = useState<string | null>(null);
  const [historyItems, setHistoryItems] = useState<HistoryListItem[]>([]);
  const [historyListLoading, setHistoryListLoading] = useState(false);
  const [historyListError, setHistoryListError] = useState<string | null>(null);
  /** From ``GET /api/health`` when the history list is empty (explains missing saves). */
  const [historyDatabaseStatus, setHistoryDatabaseStatus] = useState<string | null>(null);
  const [historyDetailLoading, setHistoryDetailLoading] = useState(false);
  const [historyRunMeta, setHistoryRunMeta] = useState<{
    attachedDocuments: AttachedDocumentItem[];
    durationMs: number | null;
    referenceUrls: string[];
  } | null>(null);
  const [lastRunMeta, setLastRunMeta] = useState<{
    durationMs: number | null;
    referenceUrls: string[];
  } | null>(null);
  const [completedRunDownloads, setCompletedRunDownloads] = useState<{
    submissionId: string;
    documents: AttachedDocumentItem[];
  } | null>(null);
  /** During processing, doc/url counts for the loading screen (used for history reruns). */
  const [processingCounts, setProcessingCounts] = useState<{ files: number; urls: number } | null>(
    null,
  );
  const [rerunInFlight, setRerunInFlight] = useState(false);
  const [rerunEdit, setRerunEdit] = useState<RerunEditState | null>(null);
  const rerunFileInputRef = useRef<HTMLInputElement>(null);
  const processAbortRef = useRef<AbortController | null>(null);

  const [comparisonBaseline, setComparisonBaseline] = useState<KYCRow[] | null>(null);
  const [comparisonLabel, setComparisonLabel] = useState<string | null>(null);
  const [lastSubmissionMeta, setLastSubmissionMeta] = useState<{
    submissionId: string | null;
    savedAt: string | null;
  }>({ submissionId: null, savedAt: null });
  const [historyDetailCreatedAt, setHistoryDetailCreatedAt] = useState<string | null>(null);
  const [analystName, setAnalystNameState] = useState(() => getAnalystName());
  const [signOffChecked, setSignOffChecked] = useState(false);

  const [urlPresetName, setUrlPresetName] = useState("");
  const [urlPresets, setUrlPresets] = useState<UrlPreset[]>(() => loadUrlPresets());
  const [urlPresetApplyId, setUrlPresetApplyId] = useState<string>("");

  const [historyFilterCompany, setHistoryFilterCompany] = useState("");
  const [historyFilterMinCompletion, setHistoryFilterMinCompletion] = useState("");
  const [historyFilterNeedsReviewOnly, setHistoryFilterNeedsReviewOnly] = useState(false);
  const [historyFilterDateFrom, setHistoryFilterDateFrom] = useState("");
  const [historyFilterDateTo, setHistoryFilterDateTo] = useState("");

  const [jobProgress, setJobProgress] = useState<JobSnapshot | null>(null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [pipelineSectionErrors, setPipelineSectionErrors] = useState<
    { sectionNo: number; phase: string; message: string; errorId: string }[]
  >([]);
  const [pipelineIntelligence, setPipelineIntelligence] = useState<
    Record<string, unknown> | null
  >(null);
  const [searchParams] = useSearchParams();
  const intakeTokenFromUrl = searchParams.get("intakeToken");

  const [serverEscalatedSerials, setServerEscalatedSerials] = useState<number[]>([]);

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
      setHistoryDatabaseStatus(null);
      try {
        const res = await fetch(HISTORY_LIST_ENDPOINT);
        if (!res.ok) {
          throw new Error(`Failed to load history (${res.status})`);
        }
        const data = (await res.json()) as HistoryListItem[];
        const items = Array.isArray(data) ? data : [];
        if (!cancelled) {
          setHistoryItems(items);
          if (items.length === 0) {
            try {
              const healthRes = await fetch(apiUrl("/api/health"));
              if (healthRes.ok) {
                const health = (await healthRes.json()) as { database?: string };
                setHistoryDatabaseStatus(health.database ?? null);
              }
            } catch {
              setHistoryDatabaseStatus(null);
            }
          }
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

  const filteredHistoryItems = useMemo(() => {
    const companyQ = historyFilterCompany.trim().toLowerCase();
    const minC = historyFilterMinCompletion.trim();
    const minNum = minC === "" ? null : parseInt(minC, 10);
    const fromTs = historyFilterDateFrom ? new Date(historyFilterDateFrom).getTime() : null;
    const toTs = historyFilterDateTo ? new Date(historyFilterDateTo).getTime() : null;

    return historyItems.filter((item) => {
      if (companyQ && !item.companyName.toLowerCase().includes(companyQ)) return false;
      if (minNum !== null && !Number.isNaN(minNum)) {
        if ((item.completionPercent ?? 0) < minNum) return false;
      }
      if (historyFilterNeedsReviewOnly && (item.needsReviewCount ?? 0) <= 0) return false;
      const t = new Date(item.createdAt).getTime();
      if (fromTs !== null && !Number.isNaN(fromTs) && t < fromTs) return false;
      if (toTs !== null && !Number.isNaN(toTs)) {
        const end = toTs + 86400000;
        if (t >= end) return false;
      }
      return true;
    });
  }, [
    historyItems,
    historyFilterCompany,
    historyFilterMinCompletion,
    historyFilterNeedsReviewOnly,
    historyFilterDateFrom,
    historyFilterDateTo,
  ]);

  const activeSubmissionId = historyDetailId ?? lastSubmissionMeta.submissionId;
  const activeSavedAt = historyDetailCreatedAt ?? lastSubmissionMeta.savedAt;

  useEffect(() => {
    if (activeSubmissionId) setSignOffChecked(getSignOff(activeSubmissionId));
    else setSignOffChecked(false);
  }, [activeSubmissionId]);

  const recordAudit = useCallback(
    (e: { action: string; analyst?: string; detail?: Record<string, unknown> }) => {
      appendAuditLog({
        ...e,
        analyst: e.analyst ?? (analystName.trim() || undefined),
      });
    },
    [analystName],
  );

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

  const finalizeSuccessfulProcess = (
    data: {
      rows: KYCRow[];
      submissionId?: string;
      savedAt?: string | null;
      durationMs?: number | null;
      attachedDocuments?: AttachedDocumentItem[];
      referenceUrls?: string[];
      pipelineErrors?: { sectionNo: number; phase: string; message: string; errorId: string }[];
      intelligence?: Record<string, unknown> | null;
    },
    companyLabel: string,
  ) => {
    const hydrated = hydrateKycRows(data.rows);
    setRows(hydrated);
    setPipelineSectionErrors(data.pipelineErrors ?? []);
    setPipelineIntelligence(
      data.intelligence && typeof data.intelligence === "object" ? data.intelligence : null,
    );
    setStep("results");

    const answeredN = hydrated.filter((r) => {
      const a = r.answer.trim().toLowerCase();
      return Boolean(a && a !== "not found");
    }).length;
    const completionPct =
      hydrated.length === 0 ? 0 : Math.round((answeredN / hydrated.length) * 100);

    setLastSubmissionMeta({
      submissionId:
        typeof data.submissionId === "string" && data.submissionId.length > 0
          ? data.submissionId
          : null,
      savedAt: data.savedAt ?? null,
    });

    setLastRunMeta({
      durationMs:
        typeof data.durationMs === "number" && !Number.isNaN(data.durationMs)
          ? data.durationMs
          : null,
      referenceUrls: Array.isArray(data.referenceUrls) ? data.referenceUrls : [],
    });

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

    const pe = data.pipelineErrors?.length ?? 0;
    toast({
      title:
        completionPct === 100 ? "Processing complete — full coverage" : "Processing complete",
      description:
        pe > 0
          ? `${pe} section(s) used recovery placeholders — review the alert below. ${
              data.submissionId
                ? `Saved to history for ${companyLabel.trim()}.${durationLabel}`
                : durationLabel.trim()
            }`
          : data.submissionId
            ? `KYC questionnaire populated for ${companyLabel.trim()}. Saved to history.${durationLabel}`
            : `KYC questionnaire populated for ${companyLabel.trim()}.${durationLabel}`,
    });
  };

  const runRerunWithFormData = async (
    companyLabel: string,
    formData: FormData,
    displayCounts: { files: number; urls: number },
  ) => {
    setCompanyName(companyLabel.trim());
    setRerunInFlight(true);
    setProcessingCounts(displayCounts);
    setMainTab("run");
    setHistoryDetailId(null);
    setHistoryRunMeta(null);
    setCompletedRunDownloads(null);
    setStep("processing");
    setJobProgress(null);
    processAbortRef.current?.abort();
    processAbortRef.current = new AbortController();

    try {
      const jobId = await startRerunJob(formData);
      setActiveJobId(jobId);
      const data = await subscribeProcessJob(
        jobId,
        (snap) => setJobProgress(snap),
        { signal: processAbortRef.current.signal },
      );

      if (!data?.rows || !Array.isArray(data.rows)) {
        throw new Error("Backend returned an invalid response");
      }

      finalizeSuccessfulProcess(
        {
          rows: data.rows,
          submissionId: data.submissionId ?? undefined,
          savedAt: data.savedAt ?? null,
          durationMs: data.durationMs ?? null,
          attachedDocuments: data.attachedDocuments,
          referenceUrls: data.referenceUrls,
          pipelineErrors: data.pipelineErrors,
          intelligence: data.intelligence,
        },
        companyLabel.trim(),
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      console.error("Rerun error:", error);
      toast({
        title: "Rerun failed",
        description: error instanceof Error ? error.message : "Unknown error occurred",
        variant: "destructive",
      });
      setStep("upload");
      setLastRunMeta(null);
    } finally {
      setRerunInFlight(false);
      setProcessingCounts(null);
      setActiveJobId(null);
      setJobProgress(null);
    }
  };

  const requestRerunFromHistoryDetail = () => {
    if (!historyDetailId || !historyRunMeta) {
      return;
    }
    const keys = historyRunMeta.attachedDocuments
      .map((d) => d.objectKey)
      .filter((k): k is string => Boolean(k));
    setRerunEdit({
      submissionId: historyDetailId,
      companyLabel: companyName.trim(),
      retainedObjectKeys: keys,
      referenceUrlsText: historyRunMeta.referenceUrls.join("\n"),
      newFiles: [],
    });
  };

  const confirmRerun = () => {
    const edit = rerunEdit;
    setRerunEdit(null);
    if (!edit?.companyLabel) {
      return;
    }
    setComparisonBaseline(cloneRowsBaseline(rows));
    setComparisonLabel(`Submission ${edit.submissionId.slice(0, 8)}…`);
    recordAudit({
      action: "rerun_started",
      detail: {
        priorSubmissionId: edit.submissionId,
        retainedKeys: edit.retainedObjectKeys.length,
        newFiles: edit.newFiles.length,
      },
    });

    const refUrls = parseReferenceUrlsFromText(edit.referenceUrlsText);
    const formData = new FormData();
    formData.append("submission_id", edit.submissionId);
    for (const u of refUrls) {
      formData.append("reference_urls", u);
    }
    for (const k of edit.retainedObjectKeys) {
      formData.append("retain_object_keys", k);
    }
    for (const f of edit.newFiles) {
      formData.append("files", f, f.name);
    }
    if (intakeTokenFromUrl?.trim()) {
      formData.append("intake_token", intakeTokenFromUrl.trim());
    }
    void runRerunWithFormData(edit.companyLabel, formData, {
      files: edit.retainedObjectKeys.length + edit.newFiles.length,
      urls: refUrls.length,
    });
  };

  const closeHistoryDetail = () => {
    setHistoryDetailId(null);
    setServerEscalatedSerials([]);
    setHistoryRunMeta(null);
    setHistoryDetailCreatedAt(null);
    setRows([]);
    setCompanyName("");
    setLastRunMeta(null);
    setPipelineIntelligence(null);
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
        createdAt: string;
        attachedDocuments?: AttachedDocumentItem[];
        durationMs?: number | null;
        referenceUrls?: string[];
        pipelineIntelligence?: Record<string, unknown> | null;
      };
      if (!data?.rows || !Array.isArray(data.rows)) {
        throw new Error("Invalid submission payload");
      }
      setCompanyName(data.companyName);
      setRows(hydrateKycRows(data.rows));
      setPipelineIntelligence(
        data.pipelineIntelligence && typeof data.pipelineIntelligence === "object"
          ? data.pipelineIntelligence
          : null,
      );
      setHistoryDetailCreatedAt(data.createdAt ?? null);
      setHistoryRunMeta({
        attachedDocuments: Array.isArray(data.attachedDocuments)
          ? data.attachedDocuments
          : [],
        durationMs: data.durationMs ?? null,
        referenceUrls: Array.isArray(data.referenceUrls) ? data.referenceUrls : [],
      });
      setHistoryDetailId(submissionId);
      try {
        const mres = await fetch(apiUrl(`/api/history/${encodeURIComponent(submissionId)}/metadata`));
        if (mres.ok) {
          const meta = (await mres.json()) as { escalatedSerials?: unknown[] };
          const esc = Array.isArray(meta.escalatedSerials)
            ? meta.escalatedSerials
                .map((x) => Number(x))
                .filter((n) => Number.isFinite(n) && n >= 1 && n <= 64)
            : [];
          setServerEscalatedSerials(esc);
        } else {
          setServerEscalatedSerials([]);
        }
      } catch {
        setServerEscalatedSerials([]);
      }
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
      kycAgentRecon: "",
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

    setComparisonBaseline(null);
    setComparisonLabel(null);

    const refUrls = parseReferenceUrlsFromText(referenceUrlsText);
    setProcessingCounts({ files: files.length, urls: refUrls.length });
    setStep("processing");
    setCompletedRunDownloads(null);
    setJobProgress(null);
    processAbortRef.current?.abort();
    processAbortRef.current = new AbortController();

    try {
      const formData = new FormData();
      formData.append("company_name", companyName.trim());
      for (const file of files) {
        formData.append("files", file, file.name);
      }
      for (const u of refUrls) {
        formData.append("reference_urls", u);
      }
      if (intakeTokenFromUrl?.trim()) {
        formData.append("intake_token", intakeTokenFromUrl.trim());
      }

      const jobId = await startProcessJob(formData);
      setActiveJobId(jobId);
      const data = await subscribeProcessJob(
        jobId,
        (snap) => setJobProgress(snap),
        { signal: processAbortRef.current.signal },
      );

      finalizeSuccessfulProcess(
        {
          rows: data.rows,
          submissionId: data.submissionId ?? undefined,
          savedAt: data.savedAt ?? null,
          durationMs: data.durationMs ?? null,
          attachedDocuments: data.attachedDocuments,
          referenceUrls: data.referenceUrls,
          pipelineErrors: data.pipelineErrors,
          intelligence: data.intelligence,
        },
        companyName.trim(),
      );
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      console.error("Processing error:", error);
      toast({
        title: "Processing failed",
        description: error instanceof Error ? error.message : "Unknown error occurred",
        variant: "destructive",
      });
      setStep("upload");
      setLastRunMeta(null);
    } finally {
      setProcessingCounts(null);
      setActiveJobId(null);
      setJobProgress(null);
    }
  };

  const handleReset = () => {
    processAbortRef.current?.abort();
    setStep("upload");
    setCompanyName("");
    setFiles([]);
    setReferenceUrlsText("");
    setRows([]);
    setCompletedRunDownloads(null);
    setLastRunMeta(null);
    setLastSubmissionMeta({ submissionId: null, savedAt: null });
    setHistoryDetailCreatedAt(null);
    setComparisonBaseline(null);
    setComparisonLabel(null);
    setProcessingCounts(null);
    setRerunInFlight(false);
    setRerunEdit(null);
    setPipelineSectionErrors([]);
    setPipelineIntelligence(null);
    setJobProgress(null);
    setActiveJobId(null);
    setServerEscalatedSerials([]);
  };

  const handleCancelActiveJob = () => {
    if (activeJobId) void cancelProcessJob(activeJobId);
    processAbortRef.current?.abort();
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

  const evidenceAttached =
    historyDetailId && historyRunMeta
      ? historyRunMeta.attachedDocuments
      : completedRunDownloads?.documents ?? [];
  const evidenceRefs =
    historyDetailId && historyRunMeta
      ? historyRunMeta.referenceUrls
      : lastRunMeta?.referenceUrls ?? [];

  const openNextNeedingReview = () => {
    const candidates = [...filteredHistoryItems]
      .filter((i) => (i.needsReviewCount ?? 0) > 0)
      .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
    const next = candidates[0];
    if (next) void openHistorySubmission(next.submissionId);
    else {
      toast({
        title: "No matching runs",
        description: "Try loosening filters or pick an item from the table.",
        variant: "destructive",
      });
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
            {intakeTokenFromUrl?.trim() ? (
              <Alert>
                <AlertTitle>Client intake link</AlertTitle>
                <AlertDescription>
                  This session uses a gated intake token. Submissions here are validated server-side against
                  the token you opened.
                </AlertDescription>
              </Alert>
            ) : null}
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

              <div className="space-y-2">
                <Label htmlFor="referenceUrls">Reference URLs (optional)</Label>
                <Textarea
                  id="referenceUrls"
                  placeholder={
                    "https://data.sec.gov/submissions/CIK##########.json\n" +
                    "https://www.sec.gov/edgar/browse/?CIK=... (browse URLs rewrite to submissions JSON)\n" +
                    "One http(s) URL per line"
                  }
                  value={referenceUrlsText}
                  onChange={(e) => setReferenceUrlsText(e.target.value)}
                  className="min-h-[100px] resize-y font-mono text-sm"
                />
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Content from these pages is fetched by the server and included when validating answers
                  against your materials (in addition to any uploaded files).
                </p>
              </div>

              <Accordion type="single" collapsible className="w-full border rounded-md px-3">
                <AccordionItem value="url-presets" className="border-0">
                  <AccordionTrigger className="text-sm py-3 hover:no-underline">
                    URL bundles &amp; issuer checklist (local)
                  </AccordionTrigger>
                  <AccordionContent className="space-y-4 pb-4 text-sm">
                    <div className="space-y-2">
                      <div className="font-medium text-xs text-muted-foreground uppercase tracking-wide">
                        Saved URL bundles
                      </div>
                      <div className="flex flex-wrap gap-2 items-end">
                        <div className="flex-1 min-w-[160px] space-y-1">
                          <Label className="text-xs">Apply bundle</Label>
                          <select
                            className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                            value={urlPresetApplyId}
                            onChange={(e) => setUrlPresetApplyId(e.target.value)}
                          >
                            <option value="">Select…</option>
                            {urlPresets.map((p) => (
                              <option key={p.id} value={p.id}>
                                {p.name} ({p.urls.length} URLs)
                              </option>
                            ))}
                          </select>
                        </div>
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          disabled={!urlPresetApplyId}
                          onClick={() => {
                            const p = urlPresets.find((x) => x.id === urlPresetApplyId);
                            if (!p) return;
                            const merged = parseReferenceUrlsFromText(
                              `${referenceUrlsText}\n${p.urls.join("\n")}`,
                            );
                            setReferenceUrlsText(merged.join("\n"));
                            toast({ title: "URLs merged", description: p.name });
                          }}
                        >
                          Merge into list
                        </Button>
                      </div>
                      <div className="flex flex-wrap gap-2 items-end">
                        <div className="flex-1 min-w-[140px] space-y-1">
                          <Label htmlFor="preset-name" className="text-xs">
                            Save current list as
                          </Label>
                          <Input
                            id="preset-name"
                            value={urlPresetName}
                            onChange={(e) => setUrlPresetName(e.target.value)}
                            placeholder="e.g. US bank EDGAR pack"
                            className="h-9"
                          />
                        </div>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="shrink-0"
                          onClick={() => {
                            const urls = parseReferenceUrlsFromText(referenceUrlsText);
                            if (urls.length === 0) {
                              toast({
                                title: "Nothing to save",
                                description: "Add at least one URL first.",
                                variant: "destructive",
                              });
                              return;
                            }
                            addUrlPreset(urlPresetName, urls);
                            setUrlPresets(loadUrlPresets());
                            toast({ title: "Bundle saved", description: "Stored in this browser." });
                          }}
                        >
                          Save bundle
                        </Button>
                      </div>
                      {urlPresets.length > 0 && (
                        <ul className="text-xs space-y-1 text-muted-foreground">
                          {urlPresets.map((p) => (
                            <li key={p.id} className="flex items-center justify-between gap-2">
                              <span>
                                {p.name}{" "}
                                <button
                                  type="button"
                                  className="text-destructive hover:underline"
                                  onClick={() => {
                                    deleteUrlPreset(p.id);
                                    setUrlPresets(loadUrlPresets());
                                    if (urlPresetApplyId === p.id) setUrlPresetApplyId("");
                                  }}
                                >
                                  Delete
                                </button>
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                    <div className="space-y-2 border-t pt-3">
                      <div className="font-medium text-xs text-muted-foreground uppercase tracking-wide">
                        Typical document checklist
                      </div>
                      <ul className="list-disc pl-5 space-y-1 text-muted-foreground text-xs">
                        <li>
                          <span className="font-medium text-foreground">Commercial bank:</span> FFIEC
                          call report link, BHC structure (if applicable), annual report / 10-K, UCC
                          or charter references.
                        </li>
                        <li>
                          <span className="font-medium text-foreground">Fund / asset manager:</span>
                          Form ADV Part 2, prospectus or PPM, audited financials, regulatory register
                          (e.g. SEC IAPD) where relevant.
                        </li>
                      </ul>
                    </div>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>

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
          <ProcessingView
            companyName={companyName}
            fileCount={processingCounts?.files ?? files.length}
            referenceUrlCount={
              processingCounts?.urls ?? parseReferenceUrlsFromText(referenceUrlsText).length
            }
            jobId={activeJobId}
            phase={jobProgress?.phase ?? ""}
            detail={jobProgress?.detail ?? ""}
            answerCompleted={jobProgress?.answerCompleted ?? 0}
            answerTotal={jobProgress?.answerTotal ?? 8}
            validateCompleted={jobProgress?.validateCompleted ?? 0}
            validateTotal={jobProgress?.validateTotal ?? 8}
            onCancelRequest={handleCancelActiveJob}
          />
            )}

            {step === "results" && (
          <div className="space-y-4">
            {pipelineSectionErrors.length > 0 && (
              <Alert variant="destructive">
                <AlertTitle>Partial section recovery</AlertTitle>
                <AlertDescription>
                  <p className="mb-2 text-sm">
                    One or more sections hit an API error; placeholder text may appear for those
                    rows. Use the error id when reporting issues.
                  </p>
                  <ul className="list-disc pl-4 space-y-1 text-sm font-mono">
                    {pipelineSectionErrors.map((e) => (
                      <li key={`${e.errorId}-${e.sectionNo}-${e.phase}`}>
                        Section {e.sectionNo} ({e.phase}): {e.message} — ref {e.errorId}
                      </li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}
            {lastRunMeta && (
              <div className="rounded-md border bg-muted/30 p-4 text-sm space-y-3">
                <div className="flex flex-wrap gap-x-6 gap-y-1">
                  <div>
                    <span className="text-muted-foreground">Run duration</span>
                    {": "}
                    <span className="font-medium">
                      {formatDurationMs(lastRunMeta.durationMs)}
                    </span>
                  </div>
                </div>
                <div className="space-y-2">
                  <MetadataCollapsible
                    label="Attached documents"
                    count={
                      files.length > 0
                        ? files.length
                        : completedRunDownloads?.documents.length ?? 0
                    }
                    emptyHint="No documents were uploaded for this run."
                  >
                    {files.length > 0 ? (
                      <ul className="space-y-2">
                        {files.map((f, idx) => (
                          <li
                            key={`${f.name}-${idx}`}
                            className="flex flex-wrap items-center gap-x-3 gap-y-2 p-2 bg-background rounded-md border"
                          >
                            <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                            <span title={f.name} className="flex-1 min-w-0 truncate font-medium">
                              {f.name}
                            </span>
                            <span className="text-xs text-muted-foreground whitespace-nowrap">
                              {(f.size / 1024 / 1024).toFixed(2)} MB
                            </span>
                          </li>
                        ))}
                      </ul>
                    ) : completedRunDownloads && completedRunDownloads.documents.length > 0 ? (
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
                              className="flex-1 min-w-0 truncate text-left font-medium"
                            />
                            {typeof doc.sizeBytes === "number" && doc.sizeBytes >= 0 && (
                              <span className="text-xs text-muted-foreground whitespace-nowrap">
                                {(doc.sizeBytes / 1024 / 1024).toFixed(2)} MB
                              </span>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </MetadataCollapsible>
                  <MetadataCollapsible
                    label="Reference URLs"
                    count={lastRunMeta.referenceUrls.length}
                    emptyHint="No reference URLs were provided."
                  >
                    {lastRunMeta.referenceUrls.length > 0 ? (
                      <ul className="space-y-2">
                        {lastRunMeta.referenceUrls.map((url, idx) => (
                          <li
                            key={`${url}-${idx}`}
                            className="flex flex-wrap items-start gap-x-3 gap-y-1 p-2 bg-background rounded-md border"
                          >
                            <Link2 className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                            <a
                              href={url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-primary underline break-all font-medium flex-1 min-w-0"
                            >
                              {url}
                            </a>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </MetadataCollapsible>
                </div>
              </div>
            )}
            {completedRunDownloads &&
              completedRunDownloads.documents.length > 0 &&
              files.length > 0 && (
              <MetadataCollapsible
                label="Stored uploads"
                count={completedRunDownloads.documents.length}
                emptyHint=""
              >
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
              </MetadataCollapsible>
            )}
            <ResultsTable
              companyName={companyName}
              rows={rows}
              onReset={handleReset}
              onRowChange={handleRowChange}
              comparisonBaseline={comparisonBaseline}
              comparisonLabel={comparisonLabel}
              onClearComparison={() => {
                setComparisonBaseline(null);
                setComparisonLabel(null);
              }}
              submissionMeta={{
                submissionId: activeSubmissionId,
                savedAt: activeSavedAt,
              }}
              referenceUrls={evidenceRefs}
              attachedDocuments={evidenceAttached}
              analystName={analystName}
              onAnalystNameChange={(name) => {
                setAnalystNameState(name);
                setAnalystName(name);
              }}
              signOff={signOffChecked}
              onSignOffChange={(v) => {
                if (activeSubmissionId) setSignOff(activeSubmissionId, v);
                setSignOffChecked(v);
              }}
              onAudit={recordAudit}
              initialEscalatedSerials={serverEscalatedSerials}
              pipelineIntelligence={pipelineIntelligence}
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
                  <Button
                    type="button"
                    variant="default"
                    className="gap-2"
                    disabled={rerunInFlight || !historyRunMeta}
                    title="Run again with optional edits to stored documents and reference URLs"
                    onClick={requestRerunFromHistoryDetail}
                  >
                    {rerunInFlight ? (
                      <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
                    ) : (
                      <RefreshCw className="h-4 w-4" aria-hidden />
                    )}
                    Rerun
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
                      <MetadataCollapsible
                        label="Attached documents"
                        count={historyRunMeta.attachedDocuments.length}
                        emptyHint="No documents were uploaded."
                      >
                        {historyRunMeta.attachedDocuments.length > 0 ? (
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
                        ) : null}
                      </MetadataCollapsible>
                      <MetadataCollapsible
                        label="Reference URLs"
                        count={historyRunMeta.referenceUrls.length}
                        emptyHint="None."
                      >
                        {historyRunMeta.referenceUrls.length > 0 ? (
                          <ul className="space-y-2">
                            {historyRunMeta.referenceUrls.map((url, idx) => (
                              <li
                                key={`${url}-${idx}`}
                                className="flex flex-wrap items-start gap-x-3 gap-y-1 p-2 bg-background rounded-md border"
                              >
                                <Link2 className="h-4 w-4 text-muted-foreground shrink-0 mt-0.5" />
                                <a
                                  href={url}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="text-primary underline break-all font-medium flex-1 min-w-0"
                                >
                                  {url}
                                </a>
                              </li>
                            ))}
                          </ul>
                        ) : null}
                      </MetadataCollapsible>
                    </div>
                  </div>
                )}

                <ResultsTable
                  companyName={companyName}
                  rows={rows}
                  onReset={closeHistoryDetail}
                  onRowChange={handleRowChange}
                  comparisonBaseline={comparisonBaseline}
                  comparisonLabel={comparisonLabel}
                  onClearComparison={() => {
                    setComparisonBaseline(null);
                    setComparisonLabel(null);
                  }}
                  submissionMeta={{
                    submissionId: activeSubmissionId,
                    savedAt: activeSavedAt,
                  }}
                  referenceUrls={evidenceRefs}
                  attachedDocuments={evidenceAttached}
                  analystName={analystName}
                  onAnalystNameChange={(name) => {
                    setAnalystNameState(name);
                    setAnalystName(name);
                  }}
                  signOff={signOffChecked}
                  onSignOffChange={(v) => {
                    if (activeSubmissionId) setSignOff(activeSubmissionId, v);
                    setSignOffChecked(v);
                  }}
                  onAudit={recordAudit}
                  initialEscalatedSerials={serverEscalatedSerials}
                  pipelineIntelligence={pipelineIntelligence}
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
                    {historyDatabaseStatus === "disabled" ? (
                      <>
                        This API is not connected to Postgres, so completed runs are not saved to
                        History. On Railway staging, link the Postgres plugin to the API service and
                        set{" "}
                        <code className="rounded bg-muted px-1 py-0.5 text-xs">DATABASE_URL</code> or{" "}
                        <code className="rounded bg-muted px-1 py-0.5 text-xs">
                          DATABASE_PUBLIC_URL
                        </code>
                        , then redeploy.
                      </>
                    ) : historyDatabaseStatus === "error" ? (
                      <>
                        Postgres is configured but the API cannot reach it (health check failed).
                        Fix database credentials or networking, then redeploy.
                      </>
                    ) : (
                      <>
                        No saved runs yet. After a successful run you should see a submission ID in
                        the results toast (&quot;Saved to history&quot;). If runs complete without
                        that message, the server is not persisting submissions.
                      </>
                    )}
                  </p>
                )}
                {!historyListLoading &&
                  historyItems.length > 0 &&
                  filteredHistoryItems.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                      No runs match the current filters. Clear filters to see all{" "}
                      {historyItems.length} run(s).
                    </p>
                  )}
                {!historyListLoading && filteredHistoryItems.length > 0 && (
                  <div className="space-y-3">
                    <div className="rounded-md border bg-muted/20 p-3 space-y-3 text-sm">
                      <div className="flex flex-wrap items-center gap-2 text-foreground font-medium">
                        <ListFilter className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden />
                        Review queue filters
                        <span className="text-xs font-normal text-muted-foreground">
                          ({filteredHistoryItems.length} of {historyItems.length})
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-3 items-end">
                        <div className="space-y-1 min-w-[160px] flex-1">
                          <Label htmlFor="hist-co" className="text-xs">
                            Client contains
                          </Label>
                          <Input
                            id="hist-co"
                            value={historyFilterCompany}
                            onChange={(e) => setHistoryFilterCompany(e.target.value)}
                            placeholder="Company name"
                            className="h-9"
                          />
                        </div>
                        <div className="space-y-1 w-24">
                          <Label htmlFor="hist-minc" className="text-xs">
                            Min % done
                          </Label>
                          <Input
                            id="hist-minc"
                            inputMode="numeric"
                            value={historyFilterMinCompletion}
                            onChange={(e) => setHistoryFilterMinCompletion(e.target.value)}
                            placeholder="0"
                            className="h-9"
                          />
                        </div>
                        <div className="space-y-1 w-[140px]">
                          <Label htmlFor="hist-from" className="text-xs">
                            From date
                          </Label>
                          <Input
                            id="hist-from"
                            type="date"
                            value={historyFilterDateFrom}
                            onChange={(e) => setHistoryFilterDateFrom(e.target.value)}
                            className="h-9"
                          />
                        </div>
                        <div className="space-y-1 w-[140px]">
                          <Label htmlFor="hist-to" className="text-xs">
                            To date
                          </Label>
                          <Input
                            id="hist-to"
                            type="date"
                            value={historyFilterDateTo}
                            onChange={(e) => setHistoryFilterDateTo(e.target.value)}
                            className="h-9"
                          />
                        </div>
                        <div className="flex items-center space-x-2 pb-1">
                          <Checkbox
                            id="hist-rev"
                            checked={historyFilterNeedsReviewOnly}
                            onCheckedChange={(c) => setHistoryFilterNeedsReviewOnly(c === true)}
                          />
                          <Label htmlFor="hist-rev" className="text-xs font-normal cursor-pointer">
                            Needs review only
                          </Label>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="secondary"
                          size="sm"
                          onClick={() => void openNextNeedingReview()}
                        >
                          Open next needing review
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setHistoryFilterCompany("");
                            setHistoryFilterMinCompletion("");
                            setHistoryFilterNeedsReviewOnly(false);
                            setHistoryFilterDateFrom("");
                            setHistoryFilterDateTo("");
                          }}
                        >
                          Clear filters
                        </Button>
                      </div>
                    </div>
                    <div className="rounded-md border bg-card">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Client</TableHead>
                          <TableHead className="min-w-[140px] max-w-[260px]">Documents</TableHead>
                          <TableHead className="text-right whitespace-nowrap w-[104px]">
                            Completion
                          </TableHead>
                          <TableHead className="text-right whitespace-nowrap w-[118px]">
                            Needs review
                          </TableHead>
                          <TableHead className="whitespace-nowrap hidden md:table-cell">
                            Duration
                          </TableHead>
                          <TableHead className="whitespace-nowrap">Saved</TableHead>
                          <TableHead className="text-right">Open</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {filteredHistoryItems.map((item) => {
                          const docs = item.attachedDocuments ?? [];
                          return (
                            <TableRow key={item.submissionId}>
                              <TableCell className="font-medium max-w-[180px]">
                                <div className="truncate" title={item.companyName}>
                                  {item.companyName}
                                </div>
                                <div className="md:hidden text-xs text-muted-foreground mt-1 flex flex-wrap gap-x-2 gap-y-0.5">
                                  <span>{formatDurationMs(item.durationMs)}</span>
                                  {typeof item.completionPercent === "number" ? (
                                    <span>{item.completionPercent}% complete</span>
                                  ) : null}
                                  {typeof item.needsReviewCount === "number" ? (
                                    <span
                                      className={
                                        item.needsReviewCount > 0
                                          ? "text-amber-700 dark:text-amber-400"
                                          : ""
                                      }
                                    >
                                      {item.needsReviewCount} review
                                      {item.needsReviewCount === 1 ? "" : "s"}
                                    </span>
                                  ) : null}
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
                              <TableCell className="text-right tabular-nums align-top">
                                <span title="Answered vs total questions">
                                  {typeof item.completionPercent === "number"
                                    ? `${item.completionPercent}%`
                                    : "—"}
                                </span>
                              </TableCell>
                              <TableCell className="text-right tabular-nums align-top">
                                <span
                                  title={
                                    (item.needsReviewCount ?? 0) > 0
                                      ? "Missing answers or AI validation No"
                                      : "Nothing flagged"
                                  }
                                  className={
                                    (item.needsReviewCount ?? 0) > 0
                                      ? "text-amber-700 dark:text-amber-400 font-medium"
                                      : "text-muted-foreground"
                                  }
                                >
                                  {typeof item.needsReviewCount === "number"
                                    ? item.needsReviewCount
                                    : "—"}
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
                  </div>
                )}
              </>
            )}
          </TabsContent>
        </Tabs>

        <AlertDialog
          open={rerunEdit !== null}
          onOpenChange={(open) => {
            if (!open) setRerunEdit(null);
          }}
        >
          <AlertDialogContent className="max-w-lg max-h-[min(90vh,720px)] flex flex-col overflow-hidden gap-0 p-0">
            <AlertDialogHeader className="p-6 pb-2 shrink-0">
              <AlertDialogTitle>Rerun with inputs</AlertDialogTitle>
              <AlertDialogDescription asChild>
                <span className="sr-only">
                  Adjust which stored documents and reference URLs to use for this pipeline
                  rerun, add new files, then confirm.
                </span>
              </AlertDialogDescription>
            </AlertDialogHeader>
            {rerunEdit && historyRunMeta ? (
              <div className="px-6 pb-4 overflow-y-auto flex-1 min-h-0 text-sm space-y-4">
                <p className="text-muted-foreground">
                  New run for{" "}
                  <span className="font-medium text-foreground">{rerunEdit.companyLabel}</span>.
                  Uncheck documents to drop them, add files or URLs as needed. A new history entry is
                  created when processing completes.
                </p>
                {rerunEdit.retainedObjectKeys.length +
                  rerunEdit.newFiles.length +
                  parseReferenceUrlsFromText(rerunEdit.referenceUrlsText).length ===
                  0 && (
                  <p className="text-amber-700 dark:text-amber-400 text-xs border border-amber-200 dark:border-amber-900 rounded-md p-2 bg-amber-50/80 dark:bg-amber-950/30">
                    No documents or reference URLs selected. The run will rely on web search and
                    other defaults only—consider adding at least one source.
                  </p>
                )}
                <div className="space-y-2">
                  <div className="text-muted-foreground text-xs uppercase tracking-wide">
                    Stored documents
                  </div>
                  {historyRunMeta.attachedDocuments.length === 0 ? (
                    <p className="text-muted-foreground">None for this submission.</p>
                  ) : (
                    <ul className="space-y-2">
                      {historyRunMeta.attachedDocuments.map((doc, idx) => {
                        const key = doc.objectKey ?? "";
                        if (!key) {
                          return (
                            <li
                              key={`legacy-${doc.filename}-${idx}`}
                              className="flex gap-2 items-start p-2 rounded-md border border-amber-200 dark:border-amber-900 bg-amber-50/50 dark:bg-amber-950/20 text-xs text-amber-800 dark:text-amber-200"
                            >
                              <FileText className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
                              <span>
                                <span className="font-medium text-foreground">{doc.filename}</span>{" "}
                                — not kept in storage for rerun. Upload a replacement below or start
                                a new run from the Run tab.
                              </span>
                            </li>
                          );
                        }
                        return (
                          <li
                            key={key}
                            className="flex items-start gap-3 p-2 bg-muted/40 rounded-md border"
                          >
                            <Checkbox
                              id={`rerun-doc-${key}`}
                              className="mt-0.5"
                              checked={rerunEdit.retainedObjectKeys.includes(key)}
                              onCheckedChange={(checked) => {
                                setRerunEdit((prev) => {
                                  if (!prev) return prev;
                                  const next = new Set(prev.retainedObjectKeys);
                                  if (checked === true) next.add(key);
                                  else next.delete(key);
                                  return { ...prev, retainedObjectKeys: [...next] };
                                });
                              }}
                            />
                            <Label
                              htmlFor={`rerun-doc-${key}`}
                              className="text-left font-normal cursor-pointer flex-1 min-w-0 leading-snug"
                            >
                              <span className="font-medium text-foreground break-words">
                                {doc.filename}
                              </span>
                            </Label>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </div>
                <div className="space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="text-muted-foreground text-xs uppercase tracking-wide">
                      New files
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="gap-1"
                      onClick={() => rerunFileInputRef.current?.click()}
                    >
                      <Upload className="h-3.5 w-3.5" aria-hidden />
                      Add files
                    </Button>
                  </div>
                  <input
                    ref={rerunFileInputRef}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={(e) => {
                      const list = e.target.files;
                      if (!list?.length) return;
                      setRerunEdit((prev) => {
                        if (!prev) return prev;
                        return { ...prev, newFiles: [...prev.newFiles, ...Array.from(list)] };
                      });
                      e.target.value = "";
                    }}
                  />
                  {rerunEdit.newFiles.length === 0 ? (
                    <p className="text-muted-foreground text-xs">No additional files.</p>
                  ) : (
                    <ul className="space-y-1">
                      {rerunEdit.newFiles.map((f, fi) => (
                        <li
                          key={`${f.name}-${fi}-${f.size}`}
                          className="flex items-center gap-2 text-xs border rounded-md px-2 py-1 bg-background"
                        >
                          <span className="truncate flex-1" title={f.name}>
                            {f.name}
                          </span>
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 shrink-0"
                            aria-label={`Remove ${f.name}`}
                            onClick={() =>
                              setRerunEdit((prev) =>
                                prev
                                  ? {
                                      ...prev,
                                      newFiles: prev.newFiles.filter((_, i) => i !== fi),
                                    }
                                  : prev,
                            )}
                          >
                            <X className="h-3.5 w-3.5" />
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="rerun-reference-urls">Reference URLs (one per line)</Label>
                  <Textarea
                    id="rerun-reference-urls"
                    value={rerunEdit.referenceUrlsText}
                    onChange={(e) =>
                      setRerunEdit((prev) =>
                        prev ? { ...prev, referenceUrlsText: e.target.value } : prev,
                      )
                    }
                    rows={5}
                    className="font-mono text-xs"
                    placeholder="https://..."
                  />
                </div>
              </div>
            ) : null}
            <AlertDialogFooter className="p-6 pt-2 border-t shrink-0 bg-background">
              <AlertDialogCancel disabled={rerunInFlight}>Cancel</AlertDialogCancel>
              <Button type="button" disabled={rerunInFlight} onClick={confirmRerun}>
                {rerunInFlight ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin mr-2" aria-hidden />
                    Starting…
                  </>
                ) : (
                  "Start rerun"
                )}
              </Button>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    </div>
  );
}
