"""Gemini embedding helpers for validation RAG."""

from __future__ import annotations

import logging

from google.genai import types

from app.config import Settings
from app.services.gemini_client import get_client

logger = logging.getLogger(__name__)

_EMBED_BATCH = 32


async def embed_texts(
    texts: list[str],
    settings: Settings,
    *,
    task_type: str,
) -> list[list[float]]:
    """Embed texts with ``gemini-embedding-001`` (or configured model)."""
    if not texts:
        return []

    client = get_client()
    out: list[list[float]] = []
    dims = settings.rag_embedding_dimensions

    for start in range(0, len(texts), _EMBED_BATCH):
        batch = texts[start : start + _EMBED_BATCH]
        response = await client.aio.models.embed_content(
            model=settings.rag_embedding_model,
            contents=batch,
            config=types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=dims,
            ),
        )
        embeddings = getattr(response, "embeddings", None) or []
        for emb in embeddings:
            values = getattr(emb, "values", None) or []
            out.append(list(values))
        if len(out) < start + len(batch):
            logger.warning(
                "Embedding batch returned %d vectors for %d inputs",
                len(out) - start,
                len(batch),
            )
            break

    return out


async def embed_query(query: str, settings: Settings) -> list[float]:
    vecs = await embed_texts([query], settings, task_type="RETRIEVAL_QUERY")
    if not vecs:
        raise RuntimeError("Query embedding returned no vector")
    return vecs[0]
