"""RAG retrieval helpers and validation prep integration (mocked)."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.config as app_config
from app.config import get_settings
from app.questions import KYCQuestion
from app.services.answer_section import AnsweredQuestion
from app.services.documents import ParsedDocument
from app.services.rag.rerank import token_rerank
from app.services.rag.retrieve import RetrievedChunk, retrieve_for_query, retrieve_for_question
from app.services.validate_section import _prepare_documents_for_validation_rag


def _clear_cfg_cache() -> None:
    get_settings.cache_clear()


def _reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _clear_cfg_cache()


@pytest.mark.asyncio
async def test_retrieve_for_query_returns_reranked_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_env(monkeypatch)
    sid = uuid.uuid4()
    hit = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="10k.pdf",
        chunk_index=0,
        content="CIK 0000764478 Delaware file number 0764478.",
        page_start=1,
        page_end=1,
        filename="10k.pdf",
        dense_score=0.92,
        lexical_score=0.1,
        fused_score=0.4,
        rerank_score=0.0,
    )

    with (
        patch(
            "app.services.rag.retrieve.embed_query",
            new_callable=AsyncMock,
            return_value=[0.1] * 768,
        ),
        patch(
            "app.services.rag.retrieve._hybrid_retrieve_multi",
            new_callable=AsyncMock,
            return_value=([hit], [0.1] * 768),
        ),
        patch(
            "app.services.rag.rerank.gemini_rerank",
            new_callable=AsyncMock,
            side_effect=lambda q, c, s, **kw: (
                token_rerank(q, c)[: kw.get("top_k") or len(c)],
                "token_overlap",
            ),
        ),
    ):
        results = await retrieve_for_query(sid, "registration number CIK", get_settings())
    assert len(results) == 1
    assert "CIK" in results[0].content
    assert results[0].rerank_score > 0


@pytest.mark.asyncio
async def test_prepare_rag_uses_retrieved_not_full_corpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setattr(app_config, "RAG_SMALL_DOC_FULL_TEXT_CHARS", 100)
    _clear_cfg_cache()
    settings = get_settings()

    long_text = "word " * 5000
    doc = ParsedDocument("big.pdf", "pdf", b"", text=long_text)
    sid = uuid.uuid4()
    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="big.pdf",
        chunk_index=0,
        content="CIK 0000764478",
        page_start=1,
        page_end=1,
        filename="big.pdf",
        dense_score=0.9,
        lexical_score=0.0,
        fused_score=0.5,
        rerank_score=0.6,
    )
    questions = [KYCQuestion(101, 1, "S1", "What is the registration number?")]
    answers = [AnsweredQuestion(101, "CIK 0000764478", [])]

    with (
        patch(
            "app.services.validate_section.rag_indexing_available",
            return_value=True,
        ),
        patch(
            "app.services.validate_section.count_submission_chunks",
            new_callable=AsyncMock,
            return_value=5,
        ),
        patch(
            "app.services.validate_section.retrieve_for_section",
            new_callable=AsyncMock,
            return_value=[chunk],
        ),
    ):
        prepared, used, _fallback = await _prepare_documents_for_validation_rag(
            [doc],
            settings,
            submission_id=sid,
            questions=questions,
            answers=answers,
        )

    assert used is True
    assert prepared is not None
    assert len(prepared) == 1
    assert "CIK" in prepared[0].text
    assert len(prepared[0].text) < len(long_text)


@pytest.mark.asyncio
async def test_retrieve_for_question_caps_at_validation_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_env(monkeypatch)
    sid = uuid.uuid4()
    question = KYCQuestion(1, 1, "S1", "What is the registration number?")
    answer = AnsweredQuestion(1, "CIK 0000764478", [])
    settings = get_settings()
    hits = [
        RetrievedChunk(
            chunk_id=uuid.uuid4(),
            document_id="10k.pdf",
            chunk_index=i,
            content=f"chunk {i}",
            page_start=1,
            page_end=1,
            filename="10k.pdf",
            dense_score=0.9,
            lexical_score=0.0,
            fused_score=0.5,
            rerank_score=0.6 - i * 0.01,
        )
        for i in range(3)
    ]

    with (
        patch(
            "app.services.rag.retrieve.rag_indexing_available",
            return_value=True,
        ),
        patch(
            "app.services.rag.retrieve.retrieve_for_query",
            new_callable=AsyncMock,
            return_value=hits,
        ) as mock_query,
    ):
        results = await retrieve_for_question(sid, question, answer, settings)

    assert len(results) == 3
    mock_query.assert_awaited_once()
    assert mock_query.await_args.kwargs["rerank_top_k"] == settings.validation_chunks_per_question
