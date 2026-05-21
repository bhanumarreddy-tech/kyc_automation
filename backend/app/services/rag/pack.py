"""Pack retrieved chunks into ParsedDocument list for validation prompts."""

from __future__ import annotations

from app.config import Settings
from app.services.documents import ParsedDocument
from app.services.rag.retrieve import RetrievedChunk


def _chunk_label(chunk: RetrievedChunk) -> str:
    page_hint = ""
    if chunk.page_start is not None:
        if chunk.page_end is not None and chunk.page_end != chunk.page_start:
            page_hint = f" · pages {chunk.page_start}–{chunk.page_end}"
        else:
            page_hint = f" · page {chunk.page_start}"
    return f"{chunk.filename} · chunk {chunk.chunk_index + 1}{page_hint}"


def chunks_to_parsed_documents(
    chunks: list[RetrievedChunk],
    *,
    max_total_chars: int,
) -> list[ParsedDocument]:
    """Convert retrieved chunks to text-only ParsedDocuments under a char budget."""
    out: list[ParsedDocument] = []
    remaining = max_total_chars - 2000
    for chunk in chunks:
        body = chunk.content.strip()
        if not body or remaining <= 0:
            continue
        if len(body) > remaining:
            body = body[:remaining]
        label = _chunk_label(chunk)
        extra: dict[str, str] = {
            "rag_chunk_id": str(chunk.chunk_id),
            "document_id": chunk.document_id,
        }
        if chunk.page_start is not None:
            extra["page_start"] = str(chunk.page_start)
        out.append(
            ParsedDocument(
                filename=label,
                kind="other",
                raw_bytes=b"",
                text=body,
                extra=extra,
            )
        )
        remaining -= len(body) + 64
    return out


def should_use_full_corpus_fallback(
    chunk_count: int,
    corpus_chars: int,
    settings: Settings,
) -> bool:
    """Use legacy full-text path when RAG index is empty or corpus is tiny."""
    if chunk_count <= 0:
        return True
    return corpus_chars <= settings.rag_small_doc_full_text_chars
