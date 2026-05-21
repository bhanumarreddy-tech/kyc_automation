"""Tests for advanced RAG retrieval helpers."""

from __future__ import annotations

import uuid

from app.services.rag.diversity import mmr_select
from app.services.rag.query_expansion import expand_retrieval_queries
from app.services.rag.retrieve import RetrievedChunk, _filter_by_relevance


def test_expand_retrieval_queries_adds_question_variant() -> None:
    queries = expand_retrieval_queries(
        "What is the CIK?\n0000764478",
        question_text="What is the CIK?",
        enabled=True,
    )
    assert len(queries) >= 2
    assert any("CIK" in q for q in queries)


def test_filter_by_relevance_uses_dense_not_rrf_scale() -> None:
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="10k.pdf",
        chunk_index=0,
        content="CIK 0000764478",
        page_start=1,
        page_end=1,
        filename="10k.pdf",
        dense_score=0.88,
        lexical_score=0.0,
        fused_score=0.016,
        rerank_score=0.0,
    )
    kept, rejected = _filter_by_relevance(
        [chunk],
        min_dense=0.42,
        min_lexical=0.02,
        min_fused=0.012,
    )
    assert len(kept) == 1
    assert not rejected


def test_mmr_reduces_redundant_chunks() -> None:
    base = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="10k.pdf",
        chunk_index=0,
        content="CIK 0000764478 Delaware registration",
        page_start=1,
        page_end=1,
        filename="10k.pdf",
        dense_score=0.9,
        lexical_score=0.1,
        fused_score=0.02,
        rerank_score=0.9,
    )
    dup = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="10k.pdf",
        chunk_index=1,
        content="CIK 0000764478 Delaware registration number",
        page_start=1,
        page_end=1,
        filename="10k.pdf",
        dense_score=0.85,
        lexical_score=0.1,
        fused_score=0.018,
        rerank_score=0.85,
    )
    other = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="bylaws.pdf",
        chunk_index=0,
        content="Board composition and committees",
        page_start=2,
        page_end=2,
        filename="bylaws.pdf",
        dense_score=0.7,
        lexical_score=0.05,
        fused_score=0.015,
        rerank_score=0.7,
    )
    selected = mmr_select([base, dup, other], top_k=2, lambda_mult=0.65)
    assert len(selected) == 2
    ids = {c.chunk_id for c in selected}
    assert base.chunk_id in ids
    assert other.chunk_id in ids
