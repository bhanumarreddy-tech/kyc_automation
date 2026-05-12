import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Upload, FileText, Home, X, ArrowLeft } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import ProcessingView from "@/components/kyc/ProcessingView";
import { ResultsTable } from "@/components/kyc/ResultsTable";
import { kycQuestions } from "@/data/kycQuestions";
import type { KYCRow } from "@/data/kycQuestions";
import { apiUrl } from "@/lib/api";

type WorkflowStep = "upload" | "processing" | "results";

const API_ENDPOINT = apiUrl("/api/process");

export default function KYCAutomation() {
  const navigate = useNavigate();
  const { toast } = useToast();
  const [step, setStep] = useState<WorkflowStep>("upload");
  const [companyName, setCompanyName] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [rows, setRows] = useState<KYCRow[]>([]);

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

      const data = (await res.json()) as { rows: KYCRow[] };
      if (!data?.rows || !Array.isArray(data.rows)) {
        throw new Error("Backend returned an invalid response");
      }

      setRows(data.rows);
      setStep("results");

      toast({
        title: "Processing complete",
        description: `KYC questionnaire populated for ${companyName.trim()}.`,
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
  };

  const handleRowChange = (serialNo: number, updates: Partial<KYCRow>) => {
    setRows((prev) =>
      prev.map((row) => (row.serialNo === serialNo ? { ...row, ...updates } : row))
    );
  };

  const handleBack = () => {
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
                      PDF, JPG, PNG, DOC, DOCX (max 20MB each)
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
          <ResultsTable
            companyName={companyName}
            rows={rows}
            onReset={handleReset}
            onRowChange={handleRowChange}
          />
        )}
      </div>
    </div>
  );
}
