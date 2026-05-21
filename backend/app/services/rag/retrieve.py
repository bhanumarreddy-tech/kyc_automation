"""Hybrid dense + lexical retrieval with RRF fusion and reranking."""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass

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
) -> list[RetrievedChunk]:
    maker = db_session_maker()
    if maker is None:
        return []

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
    return fused[:top_k]


def _filter_by_relevance(
    chunks: list[RetrievedChunk],
    *,
    min_score: float,
) -> list[RetrievedChunk]:
    return [c for c in chunks if c.fused_score >= min_score or c.lexical_score > 0]


async def retrieve_for_query(
    submission_id: uuid.UUID,
    query: str,
    settings: Settings,
    *,
    retrieve_top_k: int | None = None,
    rerank_top_k: int | None = None,
    min_relevance: float | None = None,
) -> list[RetrievedChunk]:
    top_k = retrieve_top_k or settings.rag_retrieve_top_k
    rerank_k = rerank_top_k or settings.rag_rerank_top_k
    min_rel = (
        min_relevance
        if min_relevance is not None
        else settings.rag_min_relevance_score
    )

    candidates = await _hybrid_retrieve(submission_id, query, settings, top_k=top_k)
    candidates = _filter_by_relevance(candidates, min_score=min_rel)

    reranked: list[RetrievedChunk] = []
    for c in candidates:
        score = _rerank_score(query, c)
        reranked.append(
            RetrievedChunk(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                content=c.content,
                page_start=c.page_start,
                page_end=c.page_end,
                filename=c.filename,
                dense_score=c.dense_score,
                lexical_score=c.lexical_score,
                fused_score=c.fused_score,
                rerank_score=score,
            )
        )
    reranked.sort(key=lambda c: -c.rerank_score)
    return reranked[:rerank_k]


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
