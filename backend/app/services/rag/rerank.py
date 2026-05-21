"""Cross-encoder-style reranking via Gemini listwise scoring + lexical fallback."""

from __future__ import annotations

import logging
import re

from google.genai import types

from app.config import Settings
from app.services.gemini_client import (
    generate_content_with_overload_retry,
    get_client,
    parse_json_response,
)
from app.services.rag.retrieve import RetrievedChunk, _query_tokens, _rerank_score

logger = logging.getLogger(__name__)


def token_rerank(query: str, candidates: list[RetrievedChunk]) -> list[RetrievedChunk]:
    """Lightweight fallback: fused RRF + token overlap."""
    reranked: list[RetrievedChunk] = []
    for c in candidates:
        score = _rerank_score(query, c)
        reranked.append(
            RetrievedChunk(
                chunk_id=c.chunk_id,
                document_id=c.document_id,
                chunk_index=c.chunk_index,
                content=c.content,
                page_start=c.page_start,
                page_end=c.page_end,
                filename=c.filename,
                dense_score=c.dense_score,
                lexical_score=c.lexical_score,
                fused_score=c.fused_score,
                rerank_score=score,
            )
        )
    reranked.sort(key=lambda x: -x.rerank_score)
    return reranked


async def gemini_rerank(
    query: str,
    candidates: list[RetrievedChunk],
    settings: Settings,
    *,
    top_k: int | None = None,
) -> tuple[list[RetrievedChunk], str]:
    """Listwise rerank with Gemini; falls back to token overlap on failure."""
    if not candidates:
        return [], "none"

    limit = top_k or len(candidates)
    if not settings.rag_gemini_rerank_enabled or not settings.gemini_api_key:
        return token_rerank(query, candidates)[:limit], "token_overlap"

    max_candidates = min(len(candidates), settings.rag_gemini_rerank_candidates)
    pool = candidates[:max_candidates]

    lines = []
    for i, c in enumerate(pool):
        preview = re.sub(r"\s+", " ", c.content.strip())[:320]
        lines.append(f"[{i}] ({c.filename}) {preview}")

    prompt = (
        "You are a retrieval reranker for KYC document validation.\n"
        f"Query:\n{query[:1500]}\n\n"
        "Rank the excerpts below by how well they help answer the query "
        "(most relevant first). Return JSON only:\n"
        '{"ranking": [0, 2, 1, ...]}\n'
        "Use each index 0..N-1 exactly once.\n\n"
        + "\n".join(lines)
    )

    try:
        client = get_client()
        response = await generate_content_with_overload_retry(
            client,
            settings,
            model=settings.gemini_validation_model,
            contents=[types.Content(role="user", parts=[types.Part(text=prompt)])],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        parsed = parse_json_response(response)
        ranking = parsed.get("ranking") if isinstance(parsed, dict) else None
        if not isinstance(ranking, list):
            raise ValueError("missing ranking array")

        order: list[int] = []
        seen: set[int] = set()
        for raw in ranking:
            idx = int(raw)
            if 0 <= idx < len(pool) and idx not in seen:
                order.append(idx)
                seen.add(idx)
        for i in range(len(pool)):
            if i not in seen:
                order.append(i)

        out: list[RetrievedChunk] = []
        for rank, idx in enumerate(order, start=1):
            c = pool[idx]
            # Normalize rank to (0, 1] for downstream MMR relevance signal.
            gemini_score = 1.0 - (rank - 1) / max(len(pool), 1)
            token_bonus = 0.15 * (
                sum(c.content.lower().count(t) for t in _query_tokens(query))
                / max(8, len(_query_tokens(query)))
            )
            out.append(
                RetrievedChunk(
                    chunk_id=c.chunk_id,
                    document_id=c.document_id,
                    chunk_index=c.chunk_index,
                    content=c.content,
                    page_start=c.page_start,
                    page_end=c.page_end,
                    filename=c.filename,
                    dense_score=c.dense_score,
                    lexical_score=c.lexical_score,
                    fused_score=c.fused_score,
                    rerank_score=round(gemini_score + token_bonus, 6),
                )
            )
        return out[:limit], "gemini_listwise"
    except Exception:
        logger.warning("Gemini rerank failed; using token overlap", exc_info=True)
        return token_rerank(query, candidates)[:limit], "token_overlap"
