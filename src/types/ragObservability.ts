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
  filterReason?: string | null;
}

export interface RagScoreWaterfall {
  chunkId: string;
  filename: string;
  denseScore: number;
  lexicalScore: number;
  fusedScore: number;
  rerankScore: number;
}

export interface RagRetrievalPass {
  recall: boolean;
  query: string;
  expandedQueries?: string[];
  techniques?: string[];
  rerankMethod?: string | null;
  retrieveTopK: number;
  rerankTopK: number;
  minRelevance: number;
  minDenseScore?: number | null;
  minLexicalScore?: number | null;
  hybridCandidateCount: number;
  afterFilterCount: number;
  afterRerankCount?: number;
  queryEmbeddingPreview?: number[];
  queryEmbeddingNorm?: number;
  hybridCandidates: RagChunkHit[];
  preMmrCandidates?: RagChunkHit[];
  hits: RagChunkHit[];
  scoreWaterfall?: RagScoreWaterfall | null;
  stageTiming?: RagStageTiming | null;
}

export interface RagStageTiming {
  hybridMs?: number;
  filterMs?: number;
  rerankMs?: number;
  mmrMs?: number;
  totalMs?: number;
  primaryRetrieveMs?: number;
  validationMs?: number;
  recallRetrieveMs?: number;
  recallValidationMs?: number;
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
  stageTiming?: RagStageTiming | null;
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
    skipReason?: string | null;
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

export interface RagTechnique {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
}

export interface SimilarityMatrix {
  labels: string[];
  queryRow: number[];
  rows: number[][];
  serialNo?: number;
  recall?: boolean;
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
  similarityMatrix?: SimilarityMatrix | null;
  activeTechniques?: RagTechnique[];
  failureCases?: RagFailureCase[];
}

export interface RagFailureCase {
  serialNo: number;
  sectionNo: number;
  sectionName: string;
  question: string;
  answerPreview: string;
  validationPath: string;
  validation: string;
  tags: string[];
  reasons: string[];
  hitCount: number;
  durationMs: number | null;
}

export interface RagFilterSandboxResult {
  serialNo: number;
  recall: boolean;
  minDenseScore: number;
  minLexicalScore: number;
  minFusedScore: number;
  totalCandidates: number;
  survivorCount: number;
  rejectedCount: number;
  candidates: Array<RagChunkHit & { wouldPass?: boolean }>;
}

export interface RagStrategyCompareResult {
  serialNo: number;
  query: string;
  expandedQueries: string[];
  strategies: Record<
    string,
    {
      label: string;
      description: string;
      hitCount: number;
      hits: RagChunkHit[];
      durationMs: number;
    }
  >;
  diff: {
    sharedChunkIds: string[];
    uniqueByStrategy: Record<string, string[]>;
    allChunkIds: string[];
  };
}

export interface ChunkBoundaryChunk {
  chunkId: string;
  chunkIndex: number;
  filename: string;
  pageStart?: number | null;
  pageEnd?: number | null;
  charLength: number;
  contentPreview: string;
  smallDoc?: boolean;
  overlapWithNext: number;
  boundaryIssues: string[];
}

export interface ChunkBoundariesResponse {
  submissionId: string;
  config: { overlapChars: number };
  documents: Array<{
    documentId: string;
    filename: string;
    chunkCount: number;
    chunks: ChunkBoundaryChunk[];
  }>;
  totalChunks: number;
}
