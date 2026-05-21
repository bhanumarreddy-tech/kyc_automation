/** Shared types for submission history and rerun flows. */

export interface AttachedDocumentItem {
  filename: string;
  sizeBytes?: number | null;
  contentType?: string;
  objectKey?: string | null;
}

export interface HistoryListItem {
  submissionId: string;
  companyName: string;
  createdAt: string;
  documentCount: number;
  attachedDocuments?: AttachedDocumentItem[];
  durationMs?: number | null;
  completionPercent?: number;
  needsReviewCount?: number;
  referenceUrlCount?: number;
}

export interface RerunEditState {
  submissionId: string;
  companyLabel: string;
  retainedObjectKeys: string[];
  referenceUrlsText: string;
  newFiles: File[];
}
