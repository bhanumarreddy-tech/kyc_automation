"""HTTP handlers for RAG observability and debug views."""

from __future__ import annotations

import uuid as uuid_mod
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.db.session import db_session_maker
from app.db.submissions import get_kyc_submission
from app.services.rag.chunk_boundaries import build_chunk_boundaries
from app.services.rag.embedding_viz import (
    build_embedding_visualization,
    build_similarity_matrix,
)
from app.services.rag.explorer_helpers import analyze_failure_cases, simulate_relevance_filter
from app.services.rag.index import rag_indexing_available
from app.services.rag.retrieve import compare_retrieval_strategies

router = APIRouter(prefix="/api", tags=["rag-observability"])


def _question_trace(rag_trace: dict | None, serial_no: int) -> dict | None:
    if not rag_trace:
        return None
    for q in rag_trace.get("questions") or []:
        if q.get("serialNo") == serial_no:
            return q
    return None


def _pass_for_serial(question: dict, *, recall: bool) -> dict | None:
    key = "recallRetrieval" if recall else "primaryRetrieval"
    val = question.get(key)
    return val if isinstance(val, dict) else None


@router.get("/history/{submission_id}/rag-observability")
async def get_rag_observability(
    submission_id: str,
    serial_no: int | None = Query(None, alias="serialNo", ge=1, le=200),
    recall: bool = Query(False),
) -> dict:
    """Return persisted RAG trace, embedding map, and optional similarity matrix."""
    try:
        uid = UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    async with maker() as session:
        record = await get_kyc_submission(session, uid)

    if record is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    rag_trace = record.rag_trace if isinstance(record.rag_trace, dict) else None
    embedding_map = await build_embedding_visualization(uid, rag_trace)

    similarity_matrix: dict | None = None
    if serial_no is not None and rag_trace:
        question = _question_trace(rag_trace, serial_no)
        retrieval = _pass_for_serial(question, recall=recall) if question else None
        if retrieval:
            hits = retrieval.get("hits") or []
            chunk_ids: list[UUID] = []
            for hit in hits[:12]:
                if not isinstance(hit, dict):
                    continue
                try:
                    chunk_ids.append(UUID(str(hit.get("chunkId"))))
                except (ValueError, TypeError):
                    continue
            query_emb = retrieval.get("queryEmbedding")
            if isinstance(query_emb, list) and chunk_ids:
                similarity_matrix = await build_similarity_matrix(
                    uid,
                    chunk_ids=chunk_ids,
                    query_embedding=[float(v) for v in query_emb],
                )
                similarity_matrix["serialNo"] = serial_no
                similarity_matrix["recall"] = recall

    active_techniques = [
        {
            "id": "contextual_retrieval",
            "name": "Contextual retrieval",
            "description": "Prepends document context before embedding (Anthropic-style).",
            "enabled": bool((rag_trace or {}).get("config", {}).get("contextualizeEnabled")),
        },
        {
            "id": "hybrid_dense_lexical",
            "name": "Hybrid search",
            "description": "Combines pgvector cosine similarity with Postgres full-text ts_rank.",
            "enabled": True,
        },
        {
            "id": "rrf_fusion",
            "name": "Reciprocal Rank Fusion",
            "description": "Merges dense and lexical ranked lists without score normalization.",
            "enabled": True,
        },
        {
            "id": "multi_query",
            "name": "Multi-query retrieval",
            "description": "Runs several query variants and fuses results (question + keywords).",
            "enabled": bool((rag_trace or {}).get("config", {}).get("multiQueryEnabled")),
        },
        {
            "id": "gemini_rerank",
            "name": "Gemini listwise rerank",
            "description": "Cross-encoder-style reranking with a lightweight Gemini listwise prompt.",
            "enabled": bool((rag_trace or {}).get("config", {}).get("geminiRerankEnabled")),
        },
        {
            "id": "mmr_diversity",
            "name": "MMR diversity",
            "description": "Maximal Marginal Relevance reduces redundant chunks from the same passage.",
            "enabled": bool((rag_trace or {}).get("config", {}).get("mmrEnabled")),
        },
    ]

    return {
        "submissionId": str(record.id),
        "companyName": record.company_name,
        "trace": rag_trace,
        "embeddingMap": embedding_map,
        "similarityMatrix": similarity_matrix,
        "activeTechniques": active_techniques,
        "hasTrace": rag_trace is not None,
        "failureCases": analyze_failure_cases(rag_trace),
    }


@router.get("/history/{submission_id}/rag-filter-sandbox")
async def rag_filter_sandbox(
    submission_id: str,
    serial_no: int = Query(..., alias="serialNo", ge=1, le=200),
    min_dense: float = Query(0.42, alias="minDense", ge=0.0, le=1.0),
    min_lexical: float = Query(0.02, alias="minLexical", ge=0.0, le=1.0),
    min_fused: float = Query(0.012, alias="minFused", ge=0.0, le=1.0),
    recall: bool = Query(False),
) -> dict:
    """Replay relevance filter on stored hybrid candidates with custom thresholds."""
    try:
        uid = UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    async with maker() as session:
        record = await get_kyc_submission(session, uid)
    if record is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    rag_trace = record.rag_trace if isinstance(record.rag_trace, dict) else None
    question = _question_trace(rag_trace, serial_no)
    retrieval = _pass_for_serial(question, recall=recall) if question else None
    if not retrieval or not retrieval.get("hybridCandidates"):
        raise HTTPException(status_code=404, detail="No hybrid candidates for this question")

    result = simulate_relevance_filter(
        retrieval["hybridCandidates"],
        min_dense=min_dense,
        min_lexical=min_lexical,
        min_fused=min_fused,
    )
    result["serialNo"] = serial_no
    result["recall"] = recall
    return result


@router.get("/history/{submission_id}/rag-compare")
async def rag_strategy_compare(
    submission_id: str,
    serial_no: int = Query(..., alias="serialNo", ge=1, le=200),
) -> dict:
    """Run dense-only vs hybrid vs hybrid+rerank for one traced question."""
    try:
        uid = UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    settings = get_settings()
    if not rag_indexing_available(settings):
        raise HTTPException(status_code=503, detail="RAG indexing is not available")

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    async with maker() as session:
        record = await get_kyc_submission(session, uid)
    if record is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    rag_trace = record.rag_trace if isinstance(record.rag_trace, dict) else None
    question = _question_trace(rag_trace, serial_no)
    if not question:
        raise HTTPException(status_code=404, detail="Question trace not found")

    query = f"{question.get('question', '')}\n{question.get('answerPreview') or 'Not found'}"
    comparison = await compare_retrieval_strategies(
        uid,
        query,
        settings,
        question_text=str(question.get("question") or ""),
    )
    comparison["serialNo"] = serial_no
    return comparison


@router.get("/history/{submission_id}/chunk-boundaries")
async def rag_chunk_boundaries(
    submission_id: str,
    document_id: str | None = Query(None, alias="documentId"),
) -> dict:
    """Return indexed chunk layout with overlap and boundary diagnostics."""
    try:
        uid = UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    settings = get_settings()
    overlap = settings.rag_chunk_overlap_chars
    return await build_chunk_boundaries(uid, document_id=document_id, overlap_config=overlap)
