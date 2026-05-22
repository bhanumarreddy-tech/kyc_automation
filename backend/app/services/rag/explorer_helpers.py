"""Helpers for RAG Explorer: filter replay, failure analysis, strategy labels."""

from __future__ import annotations

import re
from typing import Any

from app.services.rag.observability import chunk_hit_to_dict
from app.services.rag.retrieve import RetrievedChunk, _filter_by_relevance

_ENTITY_SPLIT_RE = re.compile(
    r"(?:CIK|EIN|SSN|File\s+No\.?|Registration\s+No\.?)\s*[:\s]*\d{0,9}$",
    re.IGNORECASE,
)


def simulate_relevance_filter(
    hybrid_candidates: list[dict[str, Any]],
    *,
    min_dense: float,
    min_lexical: float,
    min_fused: float,
) -> dict[str, Any]:
    """Replay relevance filter on stored hybrid candidate scores (client sandbox)."""
    chunks: list[RetrievedChunk] = []
    for row in hybrid_candidates:
        try:
            import uuid as uuid_mod

            chunks.append(
                RetrievedChunk(
                    chunk_id=uuid_mod.UUID(str(row["chunkId"])),
                    document_id=str(row.get("documentId") or ""),
                    chunk_index=int(row.get("chunkIndex") or 0),
                    content=str(row.get("contentPreview") or ""),
                    page_start=row.get("pageStart"),
                    page_end=row.get("pageEnd"),
                    filename=str(row.get("filename") or ""),
                    dense_score=float(row.get("denseScore") or 0.0),
                    lexical_score=float(row.get("lexicalScore") or 0.0),
                    fused_score=float(row.get("fusedScore") or 0.0),
                    rerank_score=float(row.get("rerankScore") or 0.0),
                )
            )
        except (ValueError, TypeError, KeyError):
            continue

    kept, rejected = _filter_by_relevance(
        chunks,
        min_dense=min_dense,
        min_lexical=min_lexical,
        min_fused=min_fused,
    )
    kept_ids = {str(c.chunk_id) for c in kept}
    survivors = []
    for row in hybrid_candidates:
        cid = str(row.get("chunkId") or "")
        survivors.append(
            {
                **row,
                "wouldPass": cid in kept_ids,
                "filterReason": rejected.get(cid),
            }
        )
    return {
        "minDenseScore": min_dense,
        "minLexicalScore": min_lexical,
        "minFusedScore": min_fused,
        "totalCandidates": len(chunks),
        "survivorCount": len(kept),
        "rejectedCount": len(chunks) - len(kept),
        "candidates": survivors,
    }


def hits_to_compare_rows(chunks: list[RetrievedChunk], *, limit: int = 12) -> list[dict[str, Any]]:
    return [chunk_hit_to_dict(c, rank=i + 1) for i, c in enumerate(chunks[:limit])]


def diff_hit_lists(
    *lists: tuple[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Compare chunk-id sets across named strategy hit lists."""
    by_name: dict[str, set[str]] = {}
    for name, rows in lists:
        by_name[name] = {str(r.get("chunkId")) for r in rows if r.get("chunkId")}

    all_ids: set[str] = set()
    for s in by_name.values():
        all_ids |= s

    only: dict[str, list[str]] = {}
    names = list(by_name.keys())
    for name in names:
        others = set()
        for other in names:
            if other != name:
                others |= by_name[other]
        only[name] = sorted(by_name[name] - others)

    shared = set.intersection(*by_name.values()) if by_name else set()
    return {
        "sharedChunkIds": sorted(shared),
        "uniqueByStrategy": only,
        "allChunkIds": sorted(all_ids),
    }


def analyze_failure_cases(trace: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Surface questions that did not use RAG or had weak retrieval with root-cause tags."""
    if not trace:
        return []

    config = trace.get("config") or {}
    indexing = trace.get("indexing") or {}
    chunk_count = int(indexing.get("chunkCount") or 0)
    cases: list[dict[str, Any]] = []

    for q in trace.get("questions") or []:
        path = q.get("validationPath") or "unknown"
        primary = q.get("primaryRetrieval") if isinstance(q.get("primaryRetrieval"), dict) else None
        recall = q.get("recallRetrieval") if isinstance(q.get("recallRetrieval"), dict) else None
        validation = (q.get("validation") or "").strip()
        tags: list[str] = []
        reasons: list[str] = []

        if path == "full_corpus":
            tags.append("full_corpus_fallback")
            reasons.append("Small corpus — validator received full document text instead of chunks.")
        elif path == "keyword":
            tags.append("keyword_fallback")
            if chunk_count == 0:
                tags.append("no_index")
                reasons.append("No vector index for this submission.")
            elif primary is None:
                tags.append("rag_not_traced")
                reasons.append("RAG path skipped or section-level retrieval without per-question trace.")
            elif int(primary.get("hitCount") or 0) == 0:
                tags.append("zero_hits")
                reasons.append("Hybrid retrieval returned no chunks after filter/rerank.")
            elif int(primary.get("afterFilterCount") or 0) == 0:
                tags.append("filter_too_strict")
                reasons.append(
                    f"All {primary.get('hybridCandidateCount', 0)} hybrid candidates filtered "
                    f"(dense ≥ {primary.get('minDenseScore')}, lexical ≥ {primary.get('minLexicalScore')})."
                )
            else:
                reasons.append("RAG retrieval did not produce usable evidence; keyword search used.")
        elif path == "natives_only":
            tags.append("natives_only")
            reasons.append("No textual corpus — only native PDF attachments validated.")
        elif path == "rag":
            hit_count = int((primary or {}).get("hitCount") or 0)
            if hit_count == 0:
                tags.append("rag_empty_hits")
                reasons.append("Marked RAG path but retrieval trace shows zero hits.")
            if validation and validation.lower() != "yes" and recall:
                tags.append("recall_pass")
                reasons.append("Primary retrieval insufficient; wider recall pass ran.")
                if int(recall.get("hitCount") or 0) == 0:
                    tags.append("recall_zero_hits")
                    reasons.append("Recall pass also returned no chunks.")
            if validation and validation.lower() != "yes" and not recall:
                tags.append("validation_miss")
                reasons.append("RAG evidence did not satisfy validator on first pass.")
        elif path == "unknown":
            tags.append("unknown_path")
            reasons.append("Validation path was not recorded.")

        if indexing.get("skipped"):
            tags.append("indexing_skipped")
            reasons.append(str(indexing.get("skipReason") or "Indexing was skipped for this run."))

        is_failure = path != "rag" or any(
            t in tags
            for t in (
                "rag_empty_hits",
                "recall_zero_hits",
                "validation_miss",
                "recall_pass",
            )
        )
        if not is_failure:
            continue

        cases.append(
            {
                "serialNo": q.get("serialNo"),
                "sectionNo": q.get("sectionNo"),
                "sectionName": q.get("sectionName"),
                "question": q.get("question"),
                "answerPreview": q.get("answerPreview"),
                "validationPath": path,
                "validation": validation,
                "tags": tags,
                "reasons": reasons,
                "hitCount": int((primary or {}).get("hitCount") or 0),
                "durationMs": q.get("durationMs"),
            }
        )

    return sorted(cases, key=lambda c: (c.get("serialNo") or 0))


def detect_boundary_issues(prev_content: str, next_content: str) -> list[str]:
    """Heuristic tags for problematic chunk boundaries."""
    issues: list[str] = []
    if not prev_content or not next_content:
        return issues

    prev_tail = prev_content.rstrip()
    next_head = next_content.lstrip()
    if prev_tail and next_head:
        if prev_tail[-1].isalnum() and next_head[0].isalnum():
            tail_word = re.findall(r"[a-zA-Z0-9]+$", prev_tail)
            head_word = re.findall(r"^[a-zA-Z0-9]+", next_head)
            if tail_word and head_word and tail_word[0] != head_word[0]:
                issues.append("word_split")

    window = prev_content[-80:] + "|||" + next_content[:80]
    if _ENTITY_SPLIT_RE.search(prev_content[-60:]) or re.search(
        r"\d{5,}\s*\|\|\|\s*\d", window
    ):
        issues.append("entity_split")

    if "[Page " in next_head[:20] and prev_tail and not prev_tail.endswith("]"):
        issues.append("page_marker_at_boundary")

    return issues
