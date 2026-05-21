"""MLflow tracing helpers (disabled by default in tests)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.config import get_settings
from app.services.mlflow_tracing import chunk_observability_row, is_enabled, pipeline_run
from app.services.rag.retrieve import RetrievedChunk


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def test_is_enabled_false_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("MLFLOW_TRACING_ENABLED", raising=False)
    _clear_settings_cache()
    assert is_enabled() is False


def test_pipeline_run_noops_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("MLFLOW_TRACING_ENABLED", "false")
    _clear_settings_cache()
    with pipeline_run(company="Acme", submission_id=None):
        pass


def test_chunk_observability_row_shape() -> None:
    import uuid

    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="doc.pdf",
        chunk_index=2,
        content="Sample chunk text for observability.",
        page_start=3,
        page_end=4,
        filename="doc.pdf",
        dense_score=0.91,
        lexical_score=0.05,
        fused_score=0.44,
        rerank_score=0.52,
    )
    row = chunk_observability_row(chunk, rank=1)
    assert row["rank"] == 1
    assert row["denseScore"] == 0.91
    assert "Sample chunk" in row["contentPreview"]


def test_log_retrieval_calls_mlflow_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("MLFLOW_TRACING_ENABLED", "true")
    _clear_settings_cache()

    import uuid

    from app.services.mlflow_tracing import log_retrieval

    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id="doc.pdf",
        chunk_index=0,
        content="hello",
        page_start=1,
        page_end=1,
        filename="doc.pdf",
        dense_score=0.5,
        lexical_score=0.1,
        fused_score=0.3,
        rerank_score=0.4,
    )

    mock_span = MagicMock()
    mock_span.__enter__ = MagicMock(return_value=mock_span)
    mock_span.__exit__ = MagicMock(return_value=False)

    with (
        patch("app.services.mlflow_tracing.configure"),
        patch("mlflow.start_span", return_value=mock_span),
        patch("mlflow.log_metric"),
    ):
        log_retrieval(
            query="What is the CIK?",
            recall=False,
            serial_no=1,
            retrieve_top_k=20,
            rerank_top_k=3,
            min_relevance=0.15,
            hybrid_candidates=[chunk],
            filtered_candidates=[chunk],
            hits=[chunk],
            query_embedding=[0.1, 0.2, 0.3],
        )

    mock_span.set_inputs.assert_called_once()
    mock_span.set_outputs.assert_called_once()
