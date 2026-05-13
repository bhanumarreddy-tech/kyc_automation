"""Tests for Gemini Google Search grounding URL extraction and citation merge."""

from __future__ import annotations

from google.genai import types

from app.services.answer_section import AnsweredQuestion
from app.services.gemini_client import (
    extract_grounding_web_sources_from_chunks,
    grounding_sources_by_serial_no,
    merge_answer_sources_with_grounding_metadata,
    normalize_source_url_for_match,
)


def _resp_with(
    *,
    json_text: str,
    chunks: list[types.GroundingChunk],
    supports: list[types.GroundingSupport],
) -> types.GenerateContentResponse:
    part = types.Part(text=json_text)
    content = types.Content(role="model", parts=[part])
    gm = types.GroundingMetadata(
        grounding_chunks=chunks,
        grounding_supports=supports,
    )
    cand = types.Candidate(content=content, grounding_metadata=gm)
    return types.GenerateContentResponse(candidates=[cand])


def test_normalize_source_url_for_match_trailing_slash() -> None:
    a = normalize_source_url_for_match("HTTPS://Example.COM/foo/")
    b = normalize_source_url_for_match("https://example.com/foo")
    assert a == b


def test_extract_chunks_unique_order() -> None:
    chunks = [
        types.GroundingChunk(
            web=types.GroundingChunkWeb(uri="https://a.example/x", title="A"),
        ),
        types.GroundingChunk(
            web=types.GroundingChunkWeb(uri="https://a.example/x", title="A2"),
        ),
        types.GroundingChunk(
            web=types.GroundingChunkWeb(uri="https://b.example/y", title="B"),
        ),
    ]
    resp = _resp_with(json_text="{}", chunks=chunks, supports=[])
    out = extract_grounding_web_sources_from_chunks(resp)
    assert len(out) == 2
    assert out[0]["url"] == "https://a.example/x"


def test_grounding_sources_by_serial_no_offset() -> None:
    json_text = '{"items":[{"serial_no":101,"answer":"Hello","sources":[]}]}'
    si = json_text.index("Hello")
    chunks = [
        types.GroundingChunk(
            web=types.GroundingChunkWeb(uri="https://good.example/doc", title="G"),
        ),
    ]
    supports = [
        types.GroundingSupport(
            grounding_chunk_indices=[0],
            segment=types.Segment(start_index=si),
        ),
    ]
    resp = _resp_with(json_text=json_text, chunks=chunks, supports=supports)
    by_s = grounding_sources_by_serial_no(resp)
    assert 101 in by_s
    assert by_s[101][0]["url"] == "https://good.example/doc"


def test_merge_filters_uncorroborated_model_urls() -> None:
    chunks = [
        types.GroundingChunk(
            web=types.GroundingChunkWeb(uri="https://allowed.example/z", title="Z"),
        ),
    ]
    resp = _resp_with(json_text="{}", chunks=chunks, supports=[])
    answered = [
        AnsweredQuestion(
            serial_no=1,
            answer="Fact",
            sources=[
                {"title": "bad", "url": "https://evil.com/no"},
                {"title": "ok", "url": "https://allowed.example/z"},
            ],
        ),
    ]
    out = merge_answer_sources_with_grounding_metadata(
        answered, resp, enabled=True
    )
    assert len(out[0].sources) == 1
    assert out[0].sources[0]["url"] == "https://allowed.example/z"


def test_merge_fallback_uses_chunks_when_model_urls_all_bad() -> None:
    chunks = [
        types.GroundingChunk(
            web=types.GroundingChunkWeb(uri="https://fallback.example/a", title="A"),
        ),
        types.GroundingChunk(
            web=types.GroundingChunkWeb(uri="https://fallback.example/b", title="B"),
        ),
    ]
    resp = _resp_with(json_text="{}", chunks=chunks, supports=[])
    answered = [
        AnsweredQuestion(
            serial_no=1,
            answer="Fact",
            sources=[{"title": "x", "url": "https://bad.com"}],
        ),
    ]
    out = merge_answer_sources_with_grounding_metadata(
        answered, resp, enabled=True
    )
    assert len(out[0].sources) >= 1
    assert out[0].sources[0]["url"].startswith("https://fallback.example/")


def test_merge_sentinel_clears_sources() -> None:
    chunks = [
        types.GroundingChunk(
            web=types.GroundingChunkWeb(uri="https://allowed.example/z", title="Z"),
        ),
    ]
    resp = _resp_with(json_text="{}", chunks=chunks, supports=[])
    answered = [
        AnsweredQuestion(
            serial_no=1,
            answer="Not found",
            sources=[{"title": "x", "url": "https://allowed.example/z"}],
        ),
    ]
    out = merge_answer_sources_with_grounding_metadata(
        answered, resp, enabled=True
    )
    assert out[0].sources == []


def test_merge_no_chunks_passthrough() -> None:
    part = types.Part(text="{}")
    content = types.Content(role="model", parts=[part])
    gm = types.GroundingMetadata(grounding_chunks=[], grounding_supports=[])
    cand = types.Candidate(content=content, grounding_metadata=gm)
    resp = types.GenerateContentResponse(candidates=[cand])
    answered = [
        AnsweredQuestion(
            serial_no=1,
            answer="x",
            sources=[{"title": "u", "url": "https://any.com"}],
        ),
    ]
    out = merge_answer_sources_with_grounding_metadata(
        answered, resp, enabled=True
    )
    assert out[0].sources == answered[0].sources


def test_merge_disabled_passthrough() -> None:
    chunks = [
        types.GroundingChunk(
            web=types.GroundingChunkWeb(uri="https://allowed.example/z", title="Z"),
        ),
    ]
    resp = _resp_with(json_text="{}", chunks=chunks, supports=[])
    answered = [
        AnsweredQuestion(
            serial_no=1,
            answer="Fact",
            sources=[{"title": "x", "url": "https://bad.com"}],
        ),
    ]
    out = merge_answer_sources_with_grounding_metadata(
        answered, resp, enabled=False
    )
    assert out[0].sources == answered[0].sources
