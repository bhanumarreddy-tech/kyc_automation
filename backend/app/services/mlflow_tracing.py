"""MLflow GenAI tracing for the KYC RAG validation pipeline.

Enable with ``MLFLOW_TRACING_ENABLED=true`` and optionally set
``MLFLOW_TRACKING_URI`` (defaults to local ``file:./mlruns``). View traces::

    mlflow ui --port 5000
"""

from __future__ import annotations

import contextlib
import logging
import math
from collections.abc import AsyncIterator, Iterator
from typing import Any
from uuid import UUID

from app.config import Settings, get_settings
from app.services.rag.retrieve import RetrievedChunk

logger = logging.getLogger(__name__)

_CONFIGURED = False


def _preview(text: str, limit: int = 240) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _embedding_preview(vec: list[float] | None, dims: int = 12) -> list[float]:
    if not vec:
        return []
    return [round(float(v), 6) for v in vec[:dims]]


def _embedding_norm(vec: list[float] | None) -> float:
    if not vec:
        return 0.0
    return round(math.sqrt(sum(float(v) * float(v) for v in vec)), 6)


def chunk_observability_row(
    chunk: RetrievedChunk,
    *,
    rank: int | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "chunkId": str(chunk.chunk_id),
        "documentId": chunk.document_id,
        "chunkIndex": chunk.chunk_index,
        "filename": chunk.filename,
        "pageStart": chunk.page_start,
        "pageEnd": chunk.page_end,
        "contentPreview": _preview(chunk.content),
        "denseScore": round(chunk.dense_score, 6),
        "lexicalScore": round(chunk.lexical_score, 6),
        "fusedScore": round(chunk.fused_score, 6),
        "rerankScore": round(chunk.rerank_score, 6),
    }
    if rank is not None:
        row["rank"] = rank
    return row


def is_enabled(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.mlflow_tracing_enabled)


def configure(settings: Settings | None = None) -> None:
    """Idempotent MLflow setup (tracking URI, experiment, async logging)."""
    global _CONFIGURED
    s = settings or get_settings()
    if _CONFIGURED or not s.mlflow_tracing_enabled:
        return
    try:
        import mlflow

        mlflow.set_tracking_uri(s.mlflow_tracking_uri)
        mlflow.config.enable_async_logging()
        exp = mlflow.get_experiment_by_name(s.mlflow_experiment_name)
        if exp is None:
            mlflow.create_experiment(s.mlflow_experiment_name)
        mlflow.set_experiment(s.mlflow_experiment_name)
        _CONFIGURED = True
        logger.info(
            "MLflow tracing enabled uri=%s experiment=%s",
            s.mlflow_tracking_uri,
            s.mlflow_experiment_name,
        )
    except Exception:
        logger.exception("MLflow tracing setup failed; tracing disabled for this process")
        _CONFIGURED = False


@contextlib.contextmanager
def pipeline_run(
    *,
    company: str,
    submission_id: UUID | None,
    settings: Settings | None = None,
) -> Iterator[None]:
    """Top-level MLflow run for one ``/api/process`` pipeline execution."""
    s = settings or get_settings()
    if not is_enabled(s):
        yield
        return

    configure(s)
    import mlflow

    run_name = company.strip() or "kyc-run"
    if submission_id is not None:
        run_name = f"{run_name}-{str(submission_id)[:8]}"

    tags = {"company": company[:512]}
    if submission_id is not None:
        tags["submission_id"] = str(submission_id)

    params = {
        "rag_enabled": str(s.rag_enabled),
        "embedding_model": s.rag_embedding_model,
        "embedding_dimensions": s.rag_embedding_dimensions,
        "retrieve_top_k": s.rag_retrieve_top_k,
        "rerank_top_k": s.rag_rerank_top_k,
        "validation_chunks_per_question": s.validation_chunks_per_question,
        "validation_concurrency": s.validation_concurrency,
        "gemini_validation_model": s.gemini_validation_model,
    }

    with mlflow.start_run(run_name=run_name[:250], tags=tags) as run:
        mlflow.log_params(params)
        yield
        if run.info.run_id:
            mlflow.set_tag("run_id", run.info.run_id)


@contextlib.asynccontextmanager
async def pipeline_run_async(
    *,
    company: str,
    submission_id: UUID | None,
    settings: Settings | None = None,
) -> AsyncIterator[None]:
    with pipeline_run(
        company=company,
        submission_id=submission_id,
        settings=settings,
    ):
        yield


def log_indexing(
    *,
    chunk_count: int,
    document_count: int,
    duration_ms: int,
    skipped: bool = False,
    skip_reason: str | None = None,
) -> None:
    if not is_enabled():
        return
    configure()
    import mlflow
    from mlflow.entities.span import SpanType

    with mlflow.start_span(name="rag_index_documents", span_type=SpanType.TOOL) as span:
        span.set_inputs(
            {
                "documentCount": document_count,
                "skipped": skipped,
                "skipReason": skip_reason,
            }
        )
        span.set_outputs(
            {
                "chunkCount": chunk_count,
                "durationMs": duration_ms,
            }
        )
    mlflow.log_metric("rag_index_chunk_count", chunk_count)
    mlflow.log_metric("rag_index_duration_ms", duration_ms)


def log_retrieval(
    *,
    query: str,
    recall: bool,
    serial_no: int | None,
    retrieve_top_k: int,
    rerank_top_k: int,
    min_relevance: float,
    hybrid_candidates: list[RetrievedChunk],
    filtered_candidates: list[RetrievedChunk],
    hits: list[RetrievedChunk],
    query_embedding: list[float] | None = None,
) -> None:
    if not is_enabled():
        return
    configure()
    import mlflow
    from mlflow.entities.span import SpanType

    span_name = "rag_recall_retrieve" if recall else "rag_retrieve"
    with mlflow.start_span(name=span_name, span_type=SpanType.RETRIEVER) as span:
        span.set_inputs(
            {
                "serialNo": serial_no,
                "recall": recall,
                "query": _preview(query, 2000),
                "retrieveTopK": retrieve_top_k,
                "rerankTopK": rerank_top_k,
                "minRelevance": min_relevance,
                "queryEmbeddingPreview": _embedding_preview(query_embedding),
                "queryEmbeddingNorm": _embedding_norm(query_embedding),
            }
        )
        span.set_outputs(
            {
                "hybridCandidateCount": len(hybrid_candidates),
                "afterFilterCount": len(filtered_candidates),
                "hitCount": len(hits),
                "hybridCandidates": [
                    {
                        **chunk_observability_row(c),
                        "filteredOut": c not in filtered_candidates,
                    }
                    for c in hybrid_candidates
                ],
                "hits": [
                    chunk_observability_row(c, rank=i + 1) for i, c in enumerate(hits)
                ],
            }
        )

    if serial_no is not None:
        mlflow.log_metric(
            f"q{serial_no}_retrieval_hits",
            len(hits),
            step=serial_no,
        )


def log_rerank_pass(
    *,
    query: str,
    serial_no: int | None,
    candidates: list[RetrievedChunk],
    hits: list[RetrievedChunk],
) -> None:
    if not is_enabled():
        return
    configure()
    import mlflow
    from mlflow.entities.span import SpanType

    with mlflow.start_span(name="rag_rerank", span_type=SpanType.RERANKER) as span:
        span.set_inputs(
            {
                "serialNo": serial_no,
                "query": _preview(query, 500),
                "candidateCount": len(candidates),
            }
        )
        span.set_outputs(
            {
                "hits": [
                    chunk_observability_row(c, rank=i + 1) for i, c in enumerate(hits)
                ],
            }
        )


def log_validation_question(
    *,
    serial_no: int,
    section_no: int,
    validation_path: str,
    validation: str,
    retrieval_used: bool,
    duration_ms: int,
    recall_used: bool = False,
) -> None:
    if not is_enabled():
        return
    configure()
    import mlflow
    from mlflow.entities.span import SpanType

    with mlflow.start_span(
        name=f"validate_q{serial_no}",
        span_type=SpanType.CHAIN,
    ) as span:
        span.set_inputs(
            {
                "serialNo": serial_no,
                "sectionNo": section_no,
                "validationPath": validation_path,
                "retrievalUsed": retrieval_used,
                "recallUsed": recall_used,
            }
        )
        span.set_outputs(
            {
                "validation": validation,
                "durationMs": duration_ms,
            }
        )
    mlflow.log_metric("validation_duration_ms", duration_ms, step=serial_no)
    if validation == "Yes":
        mlflow.log_metric("validation_yes", 1, step=serial_no)
    elif validation == "No":
        mlflow.log_metric("validation_no", 1, step=serial_no)


def log_gemini_validation_call(
    *,
    serial_no: int,
    section_no: int,
    model: str,
    shard_hint: str,
    doc_count: int,
    validation: str,
    source_count: int,
) -> None:
    if not is_enabled():
        return
    configure()
    import mlflow
    from mlflow.entities.span import SpanType

    with mlflow.start_span(
        name=f"gemini_validate_q{serial_no}",
        span_type=SpanType.CHAT_MODEL,
    ) as span:
        span.set_inputs(
            {
                "serialNo": serial_no,
                "sectionNo": section_no,
                "model": model,
                "shardHint": shard_hint or "primary",
                "documentCount": doc_count,
            }
        )
        span.set_outputs(
            {
                "validation": validation,
                "sourceCount": source_count,
            }
        )


def log_embedding_batch(*, text_count: int, vector_count: int, task_type: str) -> None:
    if not is_enabled():
        return
    configure()
    import mlflow
    from mlflow.entities.span import SpanType

    with mlflow.start_span(name="embed_texts", span_type=SpanType.EMBEDDING) as span:
        span.set_inputs({"textCount": text_count, "taskType": task_type})
        span.set_outputs({"vectorCount": vector_count})
