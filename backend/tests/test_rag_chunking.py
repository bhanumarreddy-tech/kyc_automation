"""RAG chunking and packing unit tests (no Postgres)."""

from __future__ import annotations

import uuid

from app.config import get_settings
from app.services.documents import ParsedDocument
from app.services.rag.chunking import chunk_parsed_documents, document_stable_id
from app.services.rag.pack import chunks_to_parsed_documents
from app.services.rag.retrieve import RetrievedChunk, _rerank_score, _rrf


def _clear_cfg_cache() -> None:
    get_settings.cache_clear()


def test_document_stable_id_prefers_source_url() -> None:
    doc = ParsedDocument(
        "local.pdf",
        "pdf",
        b"",
        text="x",
        extra={"source_url": "https://example.com/filing.pdf"},
    )
    assert document_stable_id(doc) == "https://example.com/filing.pdf"


def test_chunking_splits_large_pdf_text_with_page_markers() -> None:
    pages = "\n\n".join(f"[Page {i}]\nCIK 0000123456 fact {i}." for i in range(1, 8))
    doc = ParsedDocument("10k.pdf", "pdf", b"", text=pages)
    drafts = chunk_parsed_documents(
        [doc],
        target_chars=80,
        overlap_chars=10,
        small_doc_full_text_chars=50,
    )
    assert len(drafts) > 1
    assert any("CIK" in d.content for d in drafts)
    assert drafts[0].page_start == 1


def test_pack_respects_char_budget() -> None:
    chunks = [
        RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id="10k.pdf",
            chunk_index=0,
            content="A" * 5000,
            page_start=1,
            page_end=1,
            filename="10k.pdf",
            dense_score=0.9,
            lexical_score=0.0,
            fused_score=0.5,
            rerank_score=0.6,
        ),
        RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id="10k.pdf",
            chunk_index=1,
            content="B" * 5000,
            page_start=2,
            page_end=2,
            filename="10k.pdf",
            dense_score=0.8,
            lexical_score=0.0,
            fused_score=0.4,
            rerank_score=0.5,
        ),
    ]
    packed = chunks_to_parsed_documents(chunks, max_total_chars=6000)
    total = sum(len(d.text) for d in packed)
    assert total <= 6000
    assert len(packed) >= 1


def test_rrf_and_rerank_prefer_lexical_overlap() -> None:
    _clear_cfg_cache()
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="reg.pdf",
        chunk_index=0,
        content="Principal office: 7601 Penn Avenue South, Richfield, MN 55423.",
        page_start=3,
        page_end=3,
        filename="reg.pdf",
        dense_score=0.5,
        lexical_score=0.2,
        fused_score=_rrf(1, 60),
        rerank_score=0.0,
    )
    q = "registered address Richfield MN 55423"
    assert _rerank_score(q, chunk) > _rerank_score(q, RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="other.pdf",
        chunk_index=0,
        content="unrelated marketing copy",
        page_start=None,
        page_end=None,
        filename="other.pdf",
        dense_score=0.5,
        lexical_score=0.0,
        fused_score=_rrf(2, 60),
        rerank_score=0.0,
    ))
