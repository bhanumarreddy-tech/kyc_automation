"""Structure-aware chunking for validation RAG."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.documents import ParsedDocument


@dataclass(frozen=True)
class DocumentChunkDraft:
    document_id: str
    chunk_index: int
    content: str
    page_start: int | None
    page_end: int | None
    metadata: dict


_PAGE_MARKER_RE = re.compile(r"\[Page (\d+)\]")


def document_stable_id(doc: ParsedDocument) -> str:
    """Stable key for a parsed upload or reference URL document."""
    url = (doc.extra or {}).get("source_url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return doc.filename


def _page_range_from_text(text: str) -> tuple[int | None, int | None]:
    pages = [int(m.group(1)) for m in _PAGE_MARKER_RE.finditer(text)]
    if not pages:
        return None, None
    return min(pages), max(pages)


def _split_with_overlap(text: str, target: int, overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= target:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + target)
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _chunk_plain_with_pages(
    doc: ParsedDocument,
    target: int,
    overlap: int,
) -> list[str]:
    txt = (doc.text or "").strip()
    if not txt:
        return []
    if len(txt) <= target:
        return [txt]

    segments = [p.strip() for p in re.split(r"(?=\[Page \d+\])", txt) if p.strip()]
    if not segments:
        return _split_with_overlap(txt, target, overlap)

    merged: list[str] = []
    buf = ""
    for seg in segments:
        cand = seg if not buf else f"{buf}\n\n{seg}".strip()
        if len(cand) <= target:
            buf = cand
            continue
        if buf:
            merged.append(buf)
            buf = ""
        if len(seg) <= target:
            buf = seg
            continue
        merged.extend(_split_with_overlap(seg, target, overlap))
    if buf:
        merged.append(buf)

    out: list[str] = []
    for m in merged:
        if len(m) <= target:
            out.append(m)
        else:
            out.extend(_split_with_overlap(m, target, overlap))
    return out if out else _split_with_overlap(txt, target, overlap)


def chunk_parsed_documents(
    documents: list[ParsedDocument],
    *,
    target_chars: int,
    overlap_chars: int,
    small_doc_full_text_chars: int,
) -> list[DocumentChunkDraft]:
    """Split text-bearing documents into page-aware overlapping chunks."""
    drafts: list[DocumentChunkDraft] = []
    for doc in documents:
        text = (doc.text or "").strip()
        if not text or doc.error:
            continue
        doc_id = document_stable_id(doc)
        if len(text) <= small_doc_full_text_chars:
            ps, pe = _page_range_from_text(text)
            drafts.append(
                DocumentChunkDraft(
                    document_id=doc_id,
                    chunk_index=0,
                    content=text,
                    page_start=ps,
                    page_end=pe,
                    metadata={
                        "filename": doc.filename,
                        "kind": doc.kind,
                        "small_doc": True,
                    },
                )
            )
            continue

        pieces = _chunk_plain_with_pages(doc, target_chars, overlap_chars)
        for idx, piece in enumerate(pieces):
            ps, pe = _page_range_from_text(piece)
            drafts.append(
                DocumentChunkDraft(
                    document_id=doc_id,
                    chunk_index=idx,
                    content=piece,
                    page_start=ps,
                    page_end=pe,
                    metadata={
                        "filename": doc.filename,
                        "kind": doc.kind,
                        "small_doc": False,
                    },
                )
            )
    return drafts
