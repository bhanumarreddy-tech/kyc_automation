"""Expose indexed chunk boundaries for RAG Explorer visualization."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from app.db.session import db_session_maker
from app.services.rag.explorer_helpers import detect_boundary_issues


def _overlap_chars(prev: str, nxt: str, *, max_scan: int = 512) -> int:
    limit = min(len(prev), len(nxt), max_scan)
    for size in range(limit, 0, -1):
        if prev[-size:] == nxt[:size]:
            return size
    return 0


async def build_chunk_boundaries(
    submission_id: uuid.UUID,
    *,
    document_id: str | None = None,
    overlap_config: int = 256,
) -> dict[str, Any]:
    """Return per-document chunk layout with overlap and boundary issue hints."""
    maker = db_session_maker()
    if maker is None:
        return {"documents": [], "config": {"overlapChars": overlap_config}}

    sql = text(
        """
        SELECT id, document_id, chunk_index, content, page_start, page_end, metadata,
               char_length(content) AS char_len
        FROM kyc_document_chunks
        WHERE submission_id = :sid
          AND (:doc_id IS NULL OR document_id = :doc_id)
        ORDER BY document_id, chunk_index
        """
    )

    async with maker() as session:
        rows = (
            await session.execute(
                sql,
                {"sid": submission_id, "doc_id": document_id},
            )
        ).mappings().all()

    by_doc: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        doc_id = str(row["document_id"])
        meta = row.get("metadata") or {}
        if isinstance(meta, str):
            meta = {}
        content = str(row["content"] or "")
        by_doc.setdefault(doc_id, []).append(
            {
                "chunkId": str(row["id"]),
                "chunkIndex": int(row["chunk_index"]),
                "filename": str(meta.get("filename") or doc_id),
                "pageStart": row.get("page_start"),
                "pageEnd": row.get("page_end"),
                "charLength": int(row.get("char_len") or len(content)),
                "contentPreview": content[:400] + ("…" if len(content) > 400 else ""),
                "fullContent": content,
                "smallDoc": bool(meta.get("small_doc")),
                "overlapWithNext": 0,
                "boundaryIssues": [],
            }
        )

    documents: list[dict[str, Any]] = []
    for doc_id, chunks in by_doc.items():
        for i in range(len(chunks) - 1):
            prev_full = chunks[i]["fullContent"]
            next_full = chunks[i + 1]["fullContent"]
            overlap = _overlap_chars(prev_full, next_full)
            chunks[i]["overlapWithNext"] = overlap
            issues = detect_boundary_issues(prev_full, next_full)
            if overlap > 0 and overlap < overlap_config // 2:
                issues.append("short_overlap")
            chunks[i]["boundaryIssues"] = issues

        for c in chunks:
            del c["fullContent"]

        documents.append(
            {
                "documentId": doc_id,
                "filename": chunks[0]["filename"] if chunks else doc_id,
                "chunkCount": len(chunks),
                "chunks": chunks,
            }
        )

    return {
        "submissionId": str(submission_id),
        "config": {"overlapChars": overlap_config},
        "documents": documents,
        "totalChunks": sum(d["chunkCount"] for d in documents),
    }
