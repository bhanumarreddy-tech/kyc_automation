"""Maximal Marginal Relevance (MMR) for diverse evidence selection."""

from __future__ import annotations

import re

from app.services.rag.retrieve import RetrievedChunk


def _token_set(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{4,}", text.lower())}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def mmr_select(
    candidates: list[RetrievedChunk],
    *,
    top_k: int,
    lambda_mult: float = 0.65,
) -> list[RetrievedChunk]:
    """Greedy MMR: balance rerank relevance vs. redundancy with prior picks."""
    if len(candidates) <= top_k:
        return list(candidates)

    token_cache = {c.chunk_id: _token_set(c.content) for c in candidates}
    selected: list[RetrievedChunk] = []
    remaining = list(candidates)

    while remaining and len(selected) < top_k:
        best: RetrievedChunk | None = None
        best_score = float("-inf")
        for cand in remaining:
            relevance = cand.rerank_score
            max_sim = 0.0
            if selected:
                cand_tokens = token_cache[cand.chunk_id]
                max_sim = max(
                    _jaccard(cand_tokens, token_cache[s.chunk_id]) for s in selected
                )
            score = lambda_mult * relevance - (1.0 - lambda_mult) * max_sim
            if score > best_score:
                best_score = score
                best = cand
        if best is None:
            break
        selected.append(best)
        remaining.remove(best)

    return selected
