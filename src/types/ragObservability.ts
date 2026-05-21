export interface RagChunkHit {
  chunkId: string;
  documentId: string;
  chunkIndex: number;
  filename: string;
  pageStart?: number | null;
  pageEnd?: number | null;
  contentPreview: string;
  denseScore: number;
  lexicalScore: number;
  fusedScore: number;
  rerankScore: number;
  rank?: number;
  filteredOut?: boolean;
}

export interface RagRetrievalPass {
  recall: boolean;
  query: string;
  retrieveTopK: number;
  rerankTopK: number;
  minRelevance: number;
  hybridCandidateCount: number;
  afterFilterCount: number;
  queryEmbeddingPreview?: number[];
  queryEmbeddingNorm?: number;
  hybridCandidates: RagChunkHit[];
  hits: RagChunkHit[];
}

export interface RagQuestionTrace {
  serialNo: number;
  sectionNo: number;
  sectionName: string;
  question: string;
  answerPreview: string;
  validationPath: string | null;
  validation: string | null;
  retrievalUsed: boolean;
  primaryRetrieval: RagRetrievalPass | null;
  recallRetrieval: RagRetrievalPass | null;
  durationMs: number | null;
}

export interface RagTracePayload {
  version: number;
  submissionId: string | null;
  config: Record<string, unknown>;
  indexing: {
    chunkCount: number;
    documentCount: number;
    documents: Array<{ filename: string; documentId: string; kind?: string }>;
    durationMs: number;
    skipped?: boolean;
    skipReason?: string;
  } | null;
  questions: RagQuestionTrace[];
  pipelineTiming: {
    totalMs: number;
    validationMs: number | null;
    indexingMs: number | null;
  };
}

export interface EmbeddingPoint {
  chunkId?: string;
  documentId?: string;
  chunkIndex?: number;
  filename?: string;
  pageStart?: number | null;
  pageEnd?: number | null;
  contentPreview?: string;
  x: number;
  y: number;
  color: string;
  kind: "chunk" | "query";
  id?: string;
  serialNo?: number;
  pass?: string;
  label?: string;
}

export interface RagObservabilityResponse {
  submissionId: string;
  companyName: string;
  hasTrace: boolean;
  trace: RagTracePayload | null;
  embeddingMap: {
    method: string;
    dimensions: number;
    chunkPoints: EmbeddingPoint[];
    queryPoints: EmbeddingPoint[];
    documents: Array<{ documentId: string; color: string; label: string }>;
    stats: { chunkCount: number; documentCount: number; queryCount: number };
  };
}
