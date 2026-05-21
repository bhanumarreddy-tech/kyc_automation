import type { KycAgentReconValue } from "@/data/kycQuestions";
import type { AuditLogEntry } from "@/lib/kycAnalystToolkit";
import type { KYCRow } from "@/data/kycQuestions";

export type EditingField = "answer" | "sources" | "analystComments";

export type SortColumnId =
  | "sectionNo"
  | "serialNo"
  | "question"
  | "answer"
  | "sources"
  | "validation"
  | "confidenceScore"
  | "validationSources"
  | "kycAgentRecon"
  | "analystComments";

export type AiValidationFilter = "any" | "yes" | "no" | "empty";

export type KycReconColumnFilter = "any" | "yes" | "no" | "na" | "empty";

export interface TableFiltersState {
  sectionNo: string;
  serialNo: string;
  question: string;
  answer: string;
  sources: string;
  aiValidation: AiValidationFilter;
  aiValidationSources: string;
  kycAgentRecon: KycReconColumnFilter;
  analyst: string;
}

export interface ResultsTableProps {
  companyName: string;
  rows: KYCRow[];
  onReset: () => void;
  onRowChange: (serialNo: number, updates: Partial<KYCRow>) => void;
  comparisonBaseline?: KYCRow[] | null;
  comparisonLabel?: string | null;
  onClearComparison?: () => void;
  submissionMeta?: { submissionId: string | null; savedAt: string | null };
  referenceUrls?: string[];
  attachedDocuments?: { filename: string; objectKey?: string | null }[];
  analystName?: string;
  onAnalystNameChange?: (name: string) => void;
  signOff?: boolean;
  onSignOffChange?: (value: boolean) => void;
  onAudit?: (entry: Omit<AuditLogEntry, "at">) => void;
  pipelineIntelligence?: Record<string, unknown> | null;
  initialEscalatedSerials?: number[];
}

export interface SectionGroup {
  sectionNo: number;
  sectionName: string;
  rows: KYCRow[];
}

export const SORT_COLUMN_LABELS: Record<SortColumnId, string> = {
  sectionNo: "Section No.",
  serialNo: "Question No.",
  question: "Question",
  answer: "Answers",
  sources: "Sources",
  validation: "AI Validation",
  confidenceScore: "Conf.",
  validationSources: "AI Validation Sources",
  kycAgentRecon: "KYC_Agent_Recon",
  analystComments: "Analyst Comments",
};

export const INITIAL_FILTERS: TableFiltersState = {
  sectionNo: "",
  serialNo: "",
  question: "",
  answer: "",
  sources: "",
  aiValidation: "any",
  aiValidationSources: "",
  kycAgentRecon: "any",
  analyst: "",
};

export function filtersAreActive(f: TableFiltersState): boolean {
  return (
    f.sectionNo.trim() !== "" ||
    f.serialNo.trim() !== "" ||
    f.question.trim() !== "" ||
    f.answer.trim() !== "" ||
    f.sources.trim() !== "" ||
    f.aiValidation !== "any" ||
    f.aiValidationSources.trim() !== "" ||
    f.kycAgentRecon !== "any" ||
    f.analyst.trim() !== ""
  );
}
