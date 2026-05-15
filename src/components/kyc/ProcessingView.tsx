import { Loader2, FileSearch, Brain, CheckCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";
import { cn } from "@/lib/utils";

interface ProcessingViewProps {
  companyName: string;
  fileCount: number;
  referenceUrlCount?: number;
  jobId?: string | null;
  phase?: string;
  detail?: string;
  answerCompleted?: number;
  answerTotal?: number;
  validateCompleted?: number;
  validateTotal?: number;
  onCancelRequest?: () => void;
}

const ProcessingView = ({
  companyName,
  fileCount,
  referenceUrlCount = 0,
  jobId,
  phase = "",
  detail = "",
  answerCompleted = 0,
  answerTotal = 8,
  validateCompleted = 0,
  validateTotal = 8,
  onCancelRequest,
}: ProcessingViewProps) => {
  const urlPart =
    referenceUrlCount > 0
      ? `, ${referenceUrlCount} reference ${referenceUrlCount === 1 ? "URL" : "URLs"}`
      : "";
  const docPart =
    fileCount > 0
      ? `${fileCount} ${fileCount === 1 ? "document" : "documents"}`
      : referenceUrlCount > 0
        ? "reference pages only"
        : "no uploads";

  const [reduceMotion, setReduceMotion] = useState(false);
  useEffect(() => {
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduceMotion(m.matches);
    const handler = () => setReduceMotion(m.matches);
    m.addEventListener("change", handler);
    return () => m.removeEventListener("change", handler);
  }, []);

  const prep = phase === "prep";
  const answering = phase === "answer" || (phase === "" && !prep);
  const validating = phase === "validate";
  const cancelling = phase === "cancelling" || detail.toLowerCase().includes("cancel");

  let progressValue = 8;
  if (prep) progressValue = 5;
  else if (answering && answerTotal > 0)
    progressValue = Math.min(45, 8 + Math.round((answerCompleted / answerTotal) * 37));
  else if (validating && validateTotal > 0)
    progressValue = Math.min(
      96,
      45 + Math.round((validateCompleted / validateTotal) * 50),
    );
  else if (phase === "done") progressValue = 100;

  const scanComplete = prep || answering || validating || phase === "done";
  const extractActive = answering && !prep;
  const organizeActive = validating;
  const organizeComplete = phase === "done";

  const spinnerClass = reduceMotion ? "" : "animate-spin";

  return (
    <div className="max-w-3xl mx-auto animate-fade-in">
      <Card className="p-8 border-border/50 bg-card/50 backdrop-blur-sm">
        <div className="space-y-8">
          <div aria-live="polite" className="text-center space-y-2">
            <h2 className="text-2xl font-bold">Processing</h2>
            <p className="text-muted-foreground">
              Analyzing {docPart}
              {urlPart} for {companyName}
            </p>
            {detail ? <p className="text-sm text-foreground/90 font-medium">{detail}</p> : null}
            {jobId ? (
              <p className="text-xs font-mono text-muted-foreground break-all">
                Job {jobId.slice(0, 8)}…{" "}
                {cancelling ? <span className="text-amber-600">Cancellation requested</span> : null}
              </p>
            ) : null}
          </div>

          <div className="space-y-4">
            <div className="flex justify-center">
              <div className="relative">
                <div
                  className={cn(
                    "h-24 w-24 rounded-full bg-gradient-to-br from-[hsl(var(--gradient-start))] to-[hsl(var(--gradient-mid-1))] flex items-center justify-center",
                    reduceMotion ? "" : "animate-pulse",
                  )}
                >
                  <Loader2
                    className={cn("h-12 w-12 text-white", spinnerClass)}
                    aria-hidden
                  />
                </div>
              </div>
            </div>

            <Progress value={progressValue} className="h-2" />
            <p className="text-center text-xs text-muted-foreground">
              {phase === "prep"
                ? "Preparing documents"
                : answering
                  ? `Researching sections (${answerCompleted}/${answerTotal})`
                  : validating
                    ? `Validating against uploads (${validateCompleted}/${validateTotal})`
                    : "Working…"}
            </p>
          </div>

          <div className="space-y-4">
            <ProcessingStep
              icon={<FileSearch className="h-5 w-5" />}
              title="Scanning Documents"
              description={
                referenceUrlCount > 0
                  ? "Reading uploaded files and fetching reference URLs"
                  : "Reading and parsing uploaded files"
              }
              status={scanComplete ? "complete" : "pending"}
            />
            <ProcessingStep
              icon={<Brain className="h-5 w-5" />}
              title="Extracting Data"
              description="Using AI with web research to answer each section"
              status={extractActive ? "active" : prep ? "pending" : answering ? "complete" : "pending"}
            />
            <ProcessingStep
              icon={<CheckCircle className="h-5 w-5" />}
              title="Validating & organizing"
              description="Cross-checking answers against your documents"
              status={
                organizeComplete
                  ? "complete"
                  : organizeActive
                    ? "active"
                    : validating
                      ? "active"
                      : "pending"
              }
            />
          </div>

          {onCancelRequest ? (
            <div className="flex justify-center pt-2">
              <Button type="button" variant="outline" size="sm" onClick={onCancelRequest}>
                Cancel run
              </Button>
              <span className="sr-only">
                Stops after the current phase completes; partial results may still be returned.
              </span>
            </div>
          ) : null}
        </div>
      </Card>
    </div>
  );
};

interface ProcessingStepProps {
  icon: React.ReactNode;
  title: string;
  description: string;
  status: "complete" | "active" | "pending";
}

const ProcessingStep = ({ icon, title, description, status }: ProcessingStepProps) => {
  return (
    <div
      className={`flex items-start gap-4 p-4 rounded-lg border ${
        status === "complete"
          ? "bg-success/10 border-success/50"
          : status === "active"
            ? "bg-primary/10 border-primary/50"
            : "bg-muted/50 border-border/50"
      }`}
    >
      <div
        className={`h-10 w-10 rounded-full flex items-center justify-center ${
          status === "complete"
            ? "bg-success text-success-foreground"
            : status === "active"
              ? "bg-primary text-primary-foreground"
              : "bg-muted text-muted-foreground"
        }`}
      >
        {icon}
      </div>
      <div className="flex-1">
        <h3 className="font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      {status === "complete" && <CheckCircle className="h-5 w-5 text-success" aria-hidden />}
      {status === "active" && (
        <Loader2 className="h-5 w-5 text-primary animate-spin" aria-hidden />
      )}
    </div>
  );
};

export default ProcessingView;
