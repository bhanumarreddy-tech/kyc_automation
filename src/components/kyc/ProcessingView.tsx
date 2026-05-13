import { Loader2, FileSearch, Brain, CheckCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";

interface ProcessingViewProps {
  companyName: string;
  fileCount: number;
  referenceUrlCount?: number;
}

const ProcessingView = ({
  companyName,
  fileCount,
  referenceUrlCount = 0,
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

  return (
    <div className="max-w-3xl mx-auto animate-fade-in">
      <Card className="p-8 border-border/50 bg-card/50 backdrop-blur-sm">
        <div className="space-y-8">
          <div className="text-center space-y-2">
            <h2 className="text-2xl font-bold">Processing Documents</h2>
            <p className="text-muted-foreground">
              Analyzing {docPart}
              {urlPart} for {companyName}
            </p>
          </div>

          {/* Animated progress indicator */}
          <div className="space-y-4">
            <div className="flex justify-center">
              <div className="relative">
                <div className="h-24 w-24 rounded-full bg-gradient-to-br from-[hsl(var(--gradient-start))] to-[hsl(var(--gradient-mid-1))] flex items-center justify-center animate-pulse">
                  <Loader2 className="h-12 w-12 text-white animate-spin" />
                </div>
              </div>
            </div>

            <Progress value={66} className="h-2" />
          </div>

          {/* Processing steps */}
          <div className="space-y-4">
            <ProcessingStep
              icon={<FileSearch className="h-5 w-5" />}
              title="Scanning Documents"
              description={
                referenceUrlCount > 0
                  ? "Reading uploaded files and fetching reference URLs"
                  : "Reading and parsing uploaded files"
              }
              status="complete"
            />
            <ProcessingStep
              icon={<Brain className="h-5 w-5" />}
              title="Extracting Data"
              description="Using AI to identify and extract KYC information"
              status="active"
            />
            <ProcessingStep
              icon={<CheckCircle className="h-5 w-5" />}
              title="Organizing Results"
              description="Preparing data for review and editing"
              status="pending"
            />
          </div>
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
    <div className={`flex items-start gap-4 p-4 rounded-lg border ${
      status === "complete" ? "bg-success/10 border-success/50" :
      status === "active" ? "bg-primary/10 border-primary/50" :
      "bg-muted/50 border-border/50"
    }`}>
      <div className={`h-10 w-10 rounded-full flex items-center justify-center ${
        status === "complete" ? "bg-success text-success-foreground" :
        status === "active" ? "bg-primary text-primary-foreground" :
        "bg-muted text-muted-foreground"
      }`}>
        {icon}
      </div>
      <div className="flex-1">
        <h3 className="font-semibold">{title}</h3>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>
      {status === "complete" && (
        <CheckCircle className="h-5 w-5 text-success" />
      )}
      {status === "active" && (
        <Loader2 className="h-5 w-5 text-primary animate-spin" />
      )}
    </div>
  );
};

export default ProcessingView;
