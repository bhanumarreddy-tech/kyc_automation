"""Per-question validation with top-15 chunk retrieval."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.config import get_settings
from app.questions import KYCQuestion
from app.services.answer_section import AnsweredQuestion
from app.services.documents import ParsedDocument
from app.services.rag.retrieve import RetrievedChunk
from app.services.validate_section import ValidationResult, validate_question


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def _sample_chunk(idx: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="10k.pdf",
        chunk_index=idx,
        content=f"Evidence chunk {idx} CIK 0000764478.",
        page_start=1,
        page_end=1,
        filename="10k.pdf",
        dense_score=0.9,
        lexical_score=0.1,
        fused_score=0.5,
        rerank_score=0.6,
    )


@pytest.mark.asyncio
async def test_validate_question_uses_retrieved_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _clear_settings_cache()

    question = KYCQuestion(1, 1, "Legal Identity", "What is the CIK?")
    answer = AnsweredQuestion(1, "CIK 0000764478", [])
    doc = ParsedDocument("10k.pdf", "pdf", b"", text="full corpus " * 5000)
    sid = uuid.uuid4()
    chunks = [_sample_chunk(i) for i in range(15)]
    invoke_calls: list[list[ParsedDocument]] = []

    async def _fake_invoke(**kwargs):  # noqa: ANN003
        invoke_calls.append(kwargs["shard_docs"])
        return [
            ValidationResult(
                serial_no=question.serial_no,
                validation="Yes",
                validation_sources=[{"document": "10k.pdf", "page": 1, "excerpt": "CIK"}],
            )
        ]

    with (
        patch(
            "app.services.validate_section.rag_indexing_available",
            return_value=True,
        ),
        patch(
            "app.services.validate_section.count_submission_chunks",
            new_callable=AsyncMock,
            return_value=12,
        ),
        patch(
            "app.services.validate_section.retrieve_for_question",
            new_callable=AsyncMock,
            return_value=chunks,
        ) as mock_retrieve,
        patch(
            "app.services.validate_section._invoke_validation_gemini_once",
            new_callable=AsyncMock,
            side_effect=_fake_invoke,
        ),
    ):
        result = await validate_question(
            "Acme Corp",
            question,
            answer,
            [doc],
            submission_id=sid,
        )

    assert result.validation == "Yes"
    mock_retrieve.assert_awaited_once()
    assert mock_retrieve.await_args.kwargs.get("recall") is False
    assert len(invoke_calls) == 1
    assert len(invoke_calls[0]) == 15


@pytest.mark.asyncio
async def test_validate_question_recall_when_initial_no(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _clear_settings_cache()

    question = KYCQuestion(2, 1, "Legal Identity", "What is the TIN?")
    answer = AnsweredQuestion(2, "12-3456789", [])
    doc = ParsedDocument("10k.pdf", "pdf", b"", text="full corpus " * 5000)
    sid = uuid.uuid4()
    invoke_results = [
        [ValidationResult(serial_no=2, validation="No", validation_sources=[])],
        [
            ValidationResult(
                serial_no=2,
                validation="Yes",
                validation_sources=[{"document": "10k.pdf", "page": 2, "excerpt": "TIN"}],
            )
        ],
    ]

    async def _fake_retrieve(*_args, **kwargs):  # noqa: ANN002
        if kwargs.get("recall"):
            return [_sample_chunk(10), _sample_chunk(11)]
        return [_sample_chunk(0)]

    with (
        patch(
            "app.services.validate_section.rag_indexing_available",
            return_value=True,
        ),
        patch(
            "app.services.validate_section.count_submission_chunks",
            new_callable=AsyncMock,
            return_value=12,
        ),
        patch(
            "app.services.validate_section.retrieve_for_question",
            new_callable=AsyncMock,
            side_effect=_fake_retrieve,
        ) as mock_retrieve,
        patch(
            "app.services.validate_section._invoke_validation_gemini_once",
            new_callable=AsyncMock,
            side_effect=invoke_results,
        ),
    ):
        result = await validate_question(
            "Acme Corp",
            question,
            answer,
            [doc],
            submission_id=sid,
        )

    assert result.validation == "Yes"
    assert mock_retrieve.await_count == 2
    assert mock_retrieve.await_args_list[1].kwargs.get("recall") is True
