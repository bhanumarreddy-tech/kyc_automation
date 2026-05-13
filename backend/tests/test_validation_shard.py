"""Validation sharding / merge helpers (no Gemini network calls)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from google.genai import types

import app.config as app_config
from app.config import get_settings
from app.services.document_sharding import (
    expand_large_text_documents,
    pack_validation_shards,
)
from app.services.documents import ParsedDocument
from app.services.gemini_client import parse_json_response
from app.services.validate_section import ValidationResult, _merge_shard_validation_results
from app.questions import KYCQuestion


def _clear_cfg_cache() -> None:
    get_settings.cache_clear()


def _reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _clear_cfg_cache()


def test_defaults_use_distinct_gemini_validation_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_env(monkeypatch)
    s = get_settings()
    assert s.gemini_model == app_config.GEMINI_MODEL_ANSWER
    assert s.gemini_validation_model == app_config.GEMINI_MODEL_VALIDATION
    assert s.gemini_model != s.gemini_validation_model


def test_merge_prefers_any_yes() -> None:
    qs = [
        KYCQuestion(101, 1, "S1", "Question A?"),
        KYCQuestion(102, 1, "S1", "Question B?"),
    ]
    s1_q1_yes = [
        ValidationResult(
            101,
            "Yes",
            [{"document": "foo.pdf · pages 1–2", "page": 1, "excerpt": None}],
        ),
        ValidationResult(102, "No", []),
    ]
    s2_q1_no = [
        ValidationResult(101, "No", []),
        ValidationResult(102, "No", []),
    ]
    merged = _merge_shard_validation_results([s1_q1_yes, s2_q1_no], qs)
    by_no = {m.serial_no: m for m in merged}
    assert by_no[101].validation == "Yes"
    assert len(by_no[101].validation_sources) == 1
    assert by_no[102].validation == "No"


def test_pack_splits_large_native_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setattr(app_config, "VALIDATION_MAX_NATIVE_PARTS_PER_REQUEST", 2)
    _clear_cfg_cache()
    cfg = get_settings()

    blobs = [
        ParsedDocument(
            f"p{i}.pdf",
            "pdf",
            raw_bytes=b"%PDF-1.4 minimal" + bytes([i]) * 20,
            media_type="application/pdf",
            text="",
            pages=1,
        )
        for i in range(3)
    ]

    shards = pack_validation_shards(blobs, cfg, attach_natively=True)
    assert len(shards) == 2
    assert [len(z) for z in shards] == [2, 1]


def test_expand_chunk_huge_plaintext(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_env(monkeypatch)
    monkeypatch.setattr(app_config, "VALIDATION_TEXT_CHUNK_CHARS", 200)
    _clear_cfg_cache()
    cfg = get_settings()

    blob = ParsedDocument(
        "long.txt",
        "other",
        raw_bytes=b"",
        text=("x" * 120_000),
    )
    exploded = expand_large_text_documents([blob], cfg, attach_natively=False)
    assert len(exploded) >= 2
    paths = exploded[1].filename
    assert "text part" in paths


@pytest.mark.asyncio
async def test_parse_json_schema_blob_from_gemini() -> None:
    payload = '{"items": [{"serial_no": 101, "validation": "No", "validation_sources": []}]}'
    part = types.Part(text=payload)
    content = types.Content(role="model", parts=[part])
    candidate = types.Candidate(content=content, finish_reason="STOP")
    response = MagicMock(spec=types.GenerateContentResponse)
    response.candidates = [candidate]

    parsed = parse_json_response(response)
    assert isinstance(parsed, dict)
    assert parsed["items"][0]["serial_no"] == 101
