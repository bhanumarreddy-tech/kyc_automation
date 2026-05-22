"""Tests for RAG Explorer helper utilities."""

from __future__ import annotations

import uuid

from app.services.rag.explorer_helpers import (
    analyze_failure_cases,
    detect_boundary_issues,
    simulate_relevance_filter,
)


def test_simulate_relevance_filter_respects_dense_gate() -> None:
    cid = str(uuid.uuid4())
    result = simulate_relevance_filter(
        [
            {
                "chunkId": cid,
                "documentId": "10k.pdf",
                "chunkIndex": 0,
                "filename": "10k.pdf",
                "contentPreview": "CIK",
                "denseScore": 0.9,
                "lexicalScore": 0.0,
                "fusedScore": 0.01,
                "rerankScore": 0.0,
            }
        ],
        min_dense=0.42,
        min_lexical=0.02,
        min_fused=0.012,
    )
    assert result["survivorCount"] == 1
    assert result["candidates"][0]["wouldPass"] is True


def test_analyze_failure_cases_surfaces_keyword_fallback() -> None:
    trace = {
        "config": {},
        "indexing": {"chunkCount": 10},
        "questions": [
            {
                "serialNo": 1,
                "sectionNo": 1,
                "sectionName": "S1",
                "question": "What is the CIK?",
                "answerPreview": "123",
                "validationPath": "keyword",
                "validation": "No",
                "primaryRetrieval": {
                    "hitCount": 0,
                    "hybridCandidateCount": 5,
                    "afterFilterCount": 0,
                    "minDenseScore": 0.42,
                    "minLexicalScore": 0.02,
                },
            }
        ],
    }
    cases = analyze_failure_cases(trace)
    assert len(cases) == 1
    assert "keyword_fallback" in cases[0]["tags"]
    assert "zero_hits" in cases[0]["tags"] or "filter_too_strict" in cases[0]["tags"]


def test_detect_boundary_issues_flags_entity_split() -> None:
    issues = detect_boundary_issues(
        "Company CIK 0000764",
        "4478 Delaware incorporation",
    )
    assert "entity_split" in issues or "word_split" in issues
