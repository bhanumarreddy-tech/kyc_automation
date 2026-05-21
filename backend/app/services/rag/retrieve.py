"""Hybrid dense + lexical retrieval with RRF fusion and reranking."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.config import Settings, get_settings
from app.db.session import db_session_maker
from app.questions import KYCQuestion
from app.services.answer_section import AnsweredQuestion
from app.services.rag.embeddings import embed_query
from app.services.rag.index import rag_indexing_available

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: str
    chunk_index: int
    content: str
    page_start: int | None
    page_end: int | None
    filename: str
    dense_score: float
    lexical_score: float
    fused_score: float
    rerank_score: float


def _rrf(rank: int, k: int) -> float:
    return 1.0 / (k + rank)


def _query_tokens(query: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", query.lower())}


def _rerank_score(query: str, chunk: RetrievedChunk) -> float:
    """Lightweight reranker: fused RRF + token overlap on content."""
    tokens = _query_tokens(query)
    text_l = chunk.content.lower()
    overlap = sum(text_l.count(t) for t in tokens)
    denom = max(8, len(tokens))
    return chunk.fused_score + 0.25 * (overlap / denom)


async def _hybrid_retrieve(
    submission_id: uuid.UUID,
    query: str,
    settings: Settings,
    *,
    top_k: int,
) -> tuple[list[RetrievedChunk], list[float]]:
    maker = db_session_maker()
    if maker is None:
        return [], []

    query_vec = await embed_query(query, settings)
    vec_literal = "[" + ",".join(str(v) for v in query_vec) + "]"
    k = settings.rag_rrf_k
    lexical_w = settings.rag_hybrid_lexical_weight

    dense_sql = text(
        """
        SELECT id, document_id, chunk_index, content, page_start, page_end,
               metadata, 1 - (embedding <=> CAST(:qv AS vector)) AS dense_score
        FROM kyc_document_chunks
        WHERE submission_id = :sid
        ORDER BY embedding <=> CAST(:qv AS vector)
        LIMIT :lim
        """
    )
    lexical_sql = text(
        """
        SELECT id, document_id, chunk_index, content, page_start, page_end,
               metadata,
               ts_rank_cd(content_tsv, plainto_tsquery('english', :q)) AS lexical_score
        FROM kyc_document_chunks
        WHERE submission_id = :sid
          AND content_tsv @@ plainto_tsquery('english', :q)
        ORDER BY lexical_score DESC
        LIMIT :lim
        """
    )

    async with maker() as session:
        dense_rows = (
            await session.execute(
                dense_sql,
                {"sid": submission_id, "qv": vec_literal, "lim": top_k},
            )
        ).mappings().all()
        try:
            lex_rows = (
                await session.execute(
                    lexical_sql,
                    {"sid": submission_id, "q": query[:2000], "lim": top_k},
                )
            ).mappings().all()
        except Exception:
            logger.debug("Lexical retrieval skipped (empty tsquery or DB error)", exc_info=True)
            lex_rows = []

    dense_rank = {row["id"]: i + 1 for i, row in enumerate(dense_rows)}
    lex_rank = {row["id"]: i + 1 for i, row in enumerate(lex_rows)}
    all_ids = set(dense_rank) | set(lex_rank)
    row_by_id: dict[uuid.UUID, dict] = {}
    for row in dense_rows:
        row_by_id[row["id"]] = dict(row)
    for row in lex_rows:
        rid = row["id"]
        if rid not in row_by_id:
            row_by_id[rid] = dict(row)
        else:
            row_by_id[rid]["lexical_score"] = row.get("lexical_score", 0.0)

    fused: list[RetrievedChunk] = []
    for cid in all_ids:
        row = row_by_id[cid]
        dr = dense_rank.get(cid)
        lr = lex_rank.get(cid)
        dense_part = _rrf(dr, k) if dr else 0.0
        lex_part = lexical_w * _rrf(lr, k) if lr else 0.0
        fused_score = dense_part + lex_part
        meta = row.get("metadata") or {}
        if isinstance(meta, str):
            meta = {}
        filename = str(meta.get("filename") or row["document_id"])
        rc = RetrievedChunk(
            chunk_id=cid,
            document_id=str(row["document_id"]),
            chunk_index=int(row["chunk_index"]),
            content=str(row["content"]),
            page_start=row.get("page_start"),
            page_end=row.get("page_end"),
            filename=filename,
            dense_score=float(row.get("dense_score") or 0.0),
            lexical_score=float(row.get("lexical_score") or 0.0),
            fused_score=fused_score,
            rerank_score=0.0,
        )
        fused.append(rc)

    fused.sort(key=lambda c: -c.fused_score)
    return fused[:top_k], query_vec


def _filter_by_relevance(
    chunks: list[RetrievedChunk],
    *,
    min_dense: float,
    min_lexical: float,
    min_fused: float,
) -> tuple[list[RetrievedChunk], dict[str, str]]:
    """Keep chunks passing dense, lexical, or fused RRF thresholds."""
    kept: list[RetrievedChunk] = []
    rejected: dict[str, str] = {}
    for c in chunks:
        if c.dense_score >= min_dense:
            kept.append(c)
        elif c.lexical_score >= min_lexical:
            kept.append(c)
        elif c.fused_score >= min_fused:
            kept.append(c)
        else:
            rejected[str(c.chunk_id)] = (
                f"dense {c.dense_score:.3f} < {min_dense}; "
                f"lexical {c.lexical_score:.3f} < {min_lexical}"
            )
    return kept, rejected


async def _hybrid_retrieve_multi(
    submission_id: uuid.UUID,
    queries: list[str],
    settings: Settings,
    *,
    top_k: int,
) -> tuple[list[RetrievedChunk], list[float]]:
    """Run hybrid search for each query variant and fuse with RRF across queries."""
    if not queries:
        return [], []

    per_query: list[list[RetrievedChunk]] = []
    query_vecs: list[list[float]] = []
    for q in queries:
        cands, qvec = await _hybrid_retrieve(submission_id, q, settings, top_k=top_k)
        per_query.append(cands)
        query_vecs.append(qvec)

    if len(per_query) == 1:
        return per_query[0], query_vecs[0] if query_vecs else []

    k = settings.rag_rrf_k
    fused_scores: dict[uuid.UUID, float] = {}
    best_row: dict[uuid.UUID, RetrievedChunk] = {}
    for cands in per_query:
        for rank, c in enumerate(cands, start=1):
            fused_scores[c.chunk_id] = fused_scores.get(c.chunk_id, 0.0) + _rrf(rank, k)
            prev = best_row.get(c.chunk_id)
            if prev is None or c.dense_score > prev.dense_score:
                best_row[c.chunk_id] = c

    merged: list[RetrievedChunk] = []
    for cid, score in fused_scores.items():
        base = best_row[cid]
        merged.append(
            RetrievedChunk(
                chunk_id=base.chunk_id,
                document_id=base.document_id,
                chunk_index=base.chunk_index,
                content=base.content,
                page_start=base.page_start,
                page_end=base.page_end,
                filename=base.filename,
                dense_score=base.dense_score,
                lexical_score=base.lexical_score,
                fused_score=score,
                rerank_score=0.0,
            )
        )
    merged.sort(key=lambda c: -c.fused_score)
    return merged[:top_k], query_vecs[0] if query_vecs else []


async def retrieve_for_query(
    submission_id: uuid.UUID,
    query: str,
    settings: Settings,
    *,
    retrieve_top_k: int | None = None,
    rerank_top_k: int | None = None,
    min_relevance: float | None = None,
    serial_no: int | None = None,
    recall: bool = False,
    question_ctx: dict[str, Any] | None = None,
) -> list[RetrievedChunk]:
    top_k = retrieve_top_k or settings.rag_retrieve_top_k
    rerank_k = rerank_top_k or settings.rag_rerank_top_k
    min_fused = (
        min_relevance
        if min_relevance is not None
        else (
            settings.rag_recall_min_relevance_score
            if recall
            else settings.rag_min_relevance_score
        )
    )
    min_dense = settings.rag_min_dense_score if not recall else max(
        0.35, settings.rag_min_dense_score - 0.08
    )
    min_lexical = settings.rag_min_lexical_score

    question_text = None
    if question_ctx:
        question_text = str(question_ctx.get("question") or "") or None

    from app.services.rag.query_expansion import expand_retrieval_queries

    expanded = expand_retrieval_queries(
        query,
        question_text=question_text,
        enabled=settings.rag_multi_query_enabled,
    )

    hybrid_candidates, query_embedding = await _hybrid_retrieve_multi(
        submission_id, expanded, settings, top_k=top_k
    )
    filtered_candidates, filter_rejected = _filter_by_relevance(
        hybrid_candidates,
        min_dense=min_dense,
        min_lexical=min_lexical,
        min_fused=min_fused,
    )

    from app.services.rag.rerank import gemini_rerank

    reranked, rerank_method = await gemini_rerank(
        query,
        filtered_candidates,
        settings,
        top_k=min(len(filtered_candidates), settings.rag_gemini_rerank_candidates),
    )

    from app.services.rag.diversity import mmr_select

    if settings.rag_mmr_enabled and len(reranked) > rerank_k:
        hits = mmr_select(
            reranked,
            top_k=rerank_k,
            lambda_mult=settings.rag_mmr_lambda,
        )
    else:
        hits = reranked[:rerank_k]

    techniques = [
        "contextual_retrieval",
        "hybrid_dense_lexical",
        "rrf_fusion",
    ]
    if settings.rag_multi_query_enabled and len(expanded) > 1:
        techniques.append("multi_query")
    if rerank_method == "gemini_listwise":
        techniques.append("gemini_rerank")
    else:
        techniques.append("token_rerank")
    if settings.rag_mmr_enabled:
        techniques.append("mmr_diversity")

    if question_ctx:
        from app.services.rag.observability import build_retrieval_trace
        from app.services.rag.trace_context import get_collector

        collector = get_collector()
        if collector is not None:
            trace = build_retrieval_trace(
                query=query,
                retrieve_top_k=top_k,
                rerank_top_k=rerank_k,
                min_relevance=min_fused,
                min_dense=min_dense,
                min_lexical=min_lexical,
                hybrid_candidates=hybrid_candidates,
                filtered_candidates=filtered_candidates,
                pre_mmr_candidates=reranked,
                hits=hits,
                recall=recall,
                query_embedding=query_embedding,
                expanded_queries=expanded,
                techniques=techniques,
                rerank_method=rerank_method,
                filter_rejected=filter_rejected,
            )
            collector.record_retrieval(
                serial_no=int(question_ctx["serialNo"]),
                section_no=int(question_ctx["sectionNo"]),
                section_name=str(question_ctx["sectionName"]),
                question=str(question_ctx["question"]),
                answer_preview=str(question_ctx.get("answerPreview") or ""),
                recall=recall,
                trace=trace,
            )
    return hits


def _question_retrieval_query(question: KYCQuestion, answer: AnsweredQuestion) -> str:
    answer_text = answer.answer if answer.answer else "Not found"
    return f"{question.question}\n{answer_text}"


async def retrieve_for_question(
    submission_id: uuid.UUID,
    question: KYCQuestion,
    answer: AnsweredQuestion,
    settings: Settings | None = None,
    *,
    recall: bool = False,
) -> list[RetrievedChunk]:
    """Retrieve top evidence chunks for a single validation question."""
    s = settings or get_settings()
    if not rag_indexing_available(s):
        return []

    retrieve_k = s.rag_recall_retrieve_top_k if recall else s.rag_retrieve_top_k
    rerank_k = s.rag_recall_rerank_top_k if recall else s.validation_chunks_per_question
    min_rel = s.rag_recall_min_relevance_score if recall else s.rag_min_relevance_score
    query = _question_retrieval_query(question, answer)

    hits = await retrieve_for_query(
        submission_id,
        query,
        s,
        retrieve_top_k=retrieve_k,
        rerank_top_k=rerank_k,
        min_relevance=min_rel,
        serial_no=question.serial_no,
        recall=recall,
        question_ctx={
            "serialNo": question.serial_no,
            "sectionNo": question.section_no,
            "sectionName": question.section_name,
            "question": question.question,
            "answerPreview": answer.answer if answer.answer else "Not found",
        },
    )
    logger.info(
        "RAG question retrieve submission=%s serial=%d recall=%s chunks=%d",
        submission_id,
        question.serial_no,
        recall,
        len(hits),
    )
    return hits


async def retrieve_for_section(
    submission_id: uuid.UUID,
    questions: list[KYCQuestion],
    answers: list[AnsweredQuestion],
    settings: Settings | None = None,
    *,
    recall: bool = False,
) -> list[RetrievedChunk]:
    """Retrieve evidence chunks for a validation section (per-question or batched)."""
    s = settings or get_settings()
    if not rag_indexing_available(s):
        return []

    by_serial = {a.serial_no: a for a in answers}
    retrieve_k = s.rag_recall_retrieve_top_k if recall else s.rag_retrieve_top_k
    rerank_k = s.rag_recall_rerank_top_k if recall else s.rag_rerank_top_k
    min_rel = s.rag_recall_min_relevance_score if recall else s.rag_min_relevance_score

    seen: set[uuid.UUID] = set()
    merged: list[RetrievedChunk] = []

    if s.rag_per_question:
        queries: list[tuple[int, str]] = []
        for q in questions:
            ans = by_serial.get(q.serial_no)
            answer_text = ans.answer if ans else "Not found"
            queries.append(
                (q.serial_no, f"{q.question}\n{answer_text}")
            )
        for _serial, qtext in queries:
            hits = await retrieve_for_query(
                submission_id,
                qtext,
                s,
                retrieve_top_k=retrieve_k,
                rerank_top_k=rerank_k,
                min_relevance=min_rel,
            )
            for h in hits:
                if h.chunk_id not in seen:
                    seen.add(h.chunk_id)
                    merged.append(h)
    else:
        from app.services.validate_section import build_section_query_fragment

        qtext = build_section_query_fragment(questions, answers)
        merged = await retrieve_for_query(
            submission_id,
            qtext,
            s,
            retrieve_top_k=retrieve_k,
            rerank_top_k=rerank_k,
            min_relevance=min_rel,
        )

    merged.sort(key=lambda c: -c.rerank_score)
    logger.info(
        "RAG section retrieve submission=%s recall=%s unique_chunks=%d",
        submission_id,
        recall,
        len(merged),
    )
    return merged
