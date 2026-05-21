"""RAG workflow trace collection for end-to-end observability."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.config import Settings
from app.services.rag.retrieve import RetrievedChunk


def _preview_text(text: str, limit: int = 240) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _embedding_preview(vec: list[float], dims: int = 12) -> list[float]:
    if not vec:
        return []
    return [round(float(v), 6) for v in vec[:dims]]


def _embedding_norm(vec: list[float]) -> float:
    if not vec:
        return 0.0
    return round(math.sqrt(sum(float(v) * float(v) for v in vec)), 6)


def chunk_hit_to_dict(
    chunk: RetrievedChunk,
    *,
    rank: int | None = None,
    embedding_preview: list[float] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "chunkId": str(chunk.chunk_id),
        "documentId": chunk.document_id,
        "chunkIndex": chunk.chunk_index,
        "filename": chunk.filename,
        "pageStart": chunk.page_start,
        "pageEnd": chunk.page_end,
        "contentPreview": _preview_text(chunk.content),
        "denseScore": round(chunk.dense_score, 6),
        "lexicalScore": round(chunk.lexical_score, 6),
        "fusedScore": round(chunk.fused_score, 6),
        "rerankScore": round(chunk.rerank_score, 6),
    }
    if rank is not None:
        out["rank"] = rank
    if embedding_preview is not None:
        out["embeddingPreview"] = embedding_preview
    return out


@dataclass
class RagTraceCollector:
    """Accumulates RAG indexing and per-question retrieval/validation traces."""

    settings: Settings
    submission_id: UUID | None = None
    indexing: dict[str, Any] | None = None
    questions: list[dict[str, Any]] = field(default_factory=list)
    _question_index: dict[int, dict[str, Any]] = field(default_factory=dict, repr=False)
    _pipeline_started: float = field(default_factory=time.perf_counter, repr=False)
    _validate_started: float | None = field(default=None, repr=False)

    def config_snapshot(self) -> dict[str, Any]:
        s = self.settings
        return {
            "ragEnabled": s.rag_enabled,
            "embeddingModel": s.rag_embedding_model,
            "embeddingDimensions": s.rag_embedding_dimensions,
            "chunkTargetChars": s.rag_chunk_target_chars,
            "chunkOverlapChars": s.rag_chunk_overlap_chars,
            "contextualizeEnabled": s.rag_contextualize,
            "retrieveTopK": s.rag_retrieve_top_k,
            "rerankTopK": s.rag_rerank_top_k,
            "recallRetrieveTopK": s.rag_recall_retrieve_top_k,
            "recallRerankTopK": s.rag_recall_rerank_top_k,
            "validationChunksPerQuestion": s.validation_chunks_per_question,
            "hybridLexicalWeight": s.rag_hybrid_lexical_weight,
            "rrfK": s.rag_rrf_k,
            "minDenseScore": s.rag_min_dense_score,
            "minLexicalScore": s.rag_min_lexical_score,
            "minFusedScore": s.rag_min_relevance_score,
            "recallMinFusedScore": s.rag_recall_min_relevance_score,
            "multiQueryEnabled": s.rag_multi_query_enabled,
            "geminiRerankEnabled": s.rag_gemini_rerank_enabled,
            "geminiRerankCandidates": s.rag_gemini_rerank_candidates,
            "mmrEnabled": s.rag_mmr_enabled,
            "mmrLambda": s.rag_mmr_lambda,
        }

    def record_indexing(
        self,
        *,
        chunk_count: int,
        document_count: int,
        documents: list[dict[str, Any]],
        duration_ms: int,
        skipped: bool = False,
        skip_reason: str | None = None,
    ) -> None:
        self.indexing = {
            "chunkCount": chunk_count,
            "documentCount": document_count,
            "documents": documents,
            "durationMs": duration_ms,
            "skipped": skipped,
            "skipReason": skip_reason,
        }

    def begin_validation_phase(self) -> None:
        self._validate_started = time.perf_counter()

    def _ensure_question(
        self,
        *,
        serial_no: int,
        section_no: int,
        section_name: str,
        question: str,
        answer_preview: str,
    ) -> dict[str, Any]:
        existing = self._question_index.get(serial_no)
        if existing is not None:
            return existing
        row: dict[str, Any] = {
            "serialNo": serial_no,
            "sectionNo": section_no,
            "sectionName": section_name,
            "question": question,
            "answerPreview": _preview_text(answer_preview, 400),
            "validationPath": None,
            "validation": None,
            "retrievalUsed": False,
            "primaryRetrieval": None,
            "recallRetrieval": None,
            "durationMs": None,
        }
        self._question_index[serial_no] = row
        self.questions.append(row)
        return row

    def record_retrieval(
        self,
        *,
        serial_no: int,
        section_no: int,
        section_name: str,
        question: str,
        answer_preview: str,
        recall: bool,
        trace: dict[str, Any],
    ) -> None:
        row = self._ensure_question(
            serial_no=serial_no,
            section_no=section_no,
            section_name=section_name,
            question=question,
            answer_preview=answer_preview,
        )
        key = "recallRetrieval" if recall else "primaryRetrieval"
        row[key] = trace
        if not recall:
            row["retrievalUsed"] = True

    def record_question_outcome(
        self,
        *,
        serial_no: int,
        section_no: int,
        section_name: str,
        question: str,
        answer_preview: str,
        validation_path: str,
        validation: str,
        retrieval_used: bool,
        duration_ms: int,
    ) -> None:
        row = self._ensure_question(
            serial_no=serial_no,
            section_no=section_no,
            section_name=section_name,
            question=question,
            answer_preview=answer_preview,
        )
        row["validationPath"] = validation_path
        row["validation"] = validation
        row["retrievalUsed"] = retrieval_used
        row["durationMs"] = duration_ms

    def to_dict(self) -> dict[str, Any]:
        validate_ms: int | None = None
        if self._validate_started is not None:
            validate_ms = int((time.perf_counter() - self._validate_started) * 1000)
        total_ms = int((time.perf_counter() - self._pipeline_started) * 1000)
        return {
            "version": 1,
            "submissionId": str(self.submission_id) if self.submission_id else None,
            "config": self.config_snapshot(),
            "indexing": self.indexing,
            "questions": sorted(self.questions, key=lambda q: q["serialNo"]),
            "pipelineTiming": {
                "totalMs": total_ms,
                "validationMs": validate_ms,
                "indexingMs": (self.indexing or {}).get("durationMs"),
            },
        }


def build_retrieval_trace(
    *,
    query: str,
    retrieve_top_k: int,
    rerank_top_k: int,
    min_relevance: float,
    hybrid_candidates: list[RetrievedChunk],
    filtered_candidates: list[RetrievedChunk],
    hits: list[RetrievedChunk],
    recall: bool,
    query_embedding: list[float] | None = None,
    min_dense: float | None = None,
    min_lexical: float | None = None,
    pre_mmr_candidates: list[RetrievedChunk] | None = None,
    expanded_queries: list[str] | None = None,
    techniques: list[str] | None = None,
    rerank_method: str | None = None,
    filter_rejected: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Serialize one retrieval pass for observability."""
    reranked_with_rank = [
        chunk_hit_to_dict(c, rank=i + 1) for i, c in enumerate(hits)
    ]
    pre_mmr = pre_mmr_candidates or hits
    pre_mmr_preview = [
        chunk_hit_to_dict(c, rank=i + 1) for i, c in enumerate(pre_mmr[:retrieve_top_k])
    ]
    fused_preview = [
        {
            **chunk_hit_to_dict(c),
            "filteredOut": c not in filtered_candidates,
            "filterReason": (filter_rejected or {}).get(str(c.chunk_id)),
        }
        for c in hybrid_candidates[:retrieve_top_k]
    ]
    top_hit = hits[0] if hits else None
    score_waterfall = None
    if top_hit is not None:
        score_waterfall = {
            "chunkId": str(top_hit.chunk_id),
            "filename": top_hit.filename,
            "denseScore": round(top_hit.dense_score, 4),
            "lexicalScore": round(top_hit.lexical_score, 4),
            "fusedScore": round(top_hit.fused_score, 4),
            "rerankScore": round(top_hit.rerank_score, 4),
        }
    return {
        "recall": recall,
        "query": _preview_text(query, 2000),
        "expandedQueries": expanded_queries or [query],
        "techniques": techniques or [],
        "rerankMethod": rerank_method,
        "retrieveTopK": retrieve_top_k,
        "rerankTopK": rerank_top_k,
        "minRelevance": min_relevance,
        "minDenseScore": min_dense,
        "minLexicalScore": min_lexical,
        "hybridCandidateCount": len(hybrid_candidates),
        "afterFilterCount": len(filtered_candidates),
        "afterRerankCount": len(pre_mmr),
        "hitCount": len(hits),
        "queryEmbeddingPreview": _embedding_preview(query_embedding or []),
        "queryEmbeddingNorm": _embedding_norm(query_embedding or []),
        "queryEmbedding": (
            [round(float(v), 6) for v in query_embedding] if query_embedding else None
        ),
        "hybridCandidates": fused_preview,
        "preMmrCandidates": pre_mmr_preview,
        "hits": reranked_with_rank,
        "scoreWaterfall": score_waterfall,
    }
