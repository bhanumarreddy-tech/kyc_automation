"""2D embedding projections for RAG observability UI."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

import numpy as np
from sqlalchemy import select

from app.db.models import KYCDocumentChunk
from app.db.session import db_session_maker


def _document_color(document_id: str) -> str:
    digest = hashlib.sha256(document_id.encode()).hexdigest()
    hue = int(digest[:8], 16) % 360
    return f"hsl({hue} 62% 48%)"


def _pca_2d(vectors: list[list[float]]) -> list[tuple[float, float]]:
    if not vectors:
        return []
    if len(vectors) == 1:
        return [(0.0, 0.0)]
    matrix = np.asarray(vectors, dtype=np.float64)
    matrix = matrix - matrix.mean(axis=0)
    _, _, vt = np.linalg.svd(matrix, full_matrices=False)
    coords = matrix @ vt[:2].T
    return [(round(float(x), 5), round(float(y), 5)) for x, y in coords]


def _collect_query_points(rag_trace: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not rag_trace:
        return []
    points: list[dict[str, Any]] = []
    for question in rag_trace.get("questions") or []:
        serial_no = question.get("serialNo")
        for pass_name, label in (
            ("primaryRetrieval", "primary"),
            ("recallRetrieval", "recall"),
        ):
            retrieval = question.get(pass_name)
            if not isinstance(retrieval, dict):
                continue
            embedding = retrieval.get("queryEmbedding")
            if not isinstance(embedding, list) or not embedding:
                continue
            points.append(
                {
                    "id": f"q{serial_no}-{label}",
                    "serialNo": serial_no,
                    "pass": label,
                    "label": f"Q{serial_no} ({label})",
                    "embedding": [float(v) for v in embedding],
                }
            )
    return points


async def build_embedding_visualization(
    submission_id: uuid.UUID,
    rag_trace: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Project chunk and query embeddings into 2D for scatter visualization."""
    maker = db_session_maker()
    if maker is None:
        return {
            "method": "pca",
            "dimensions": 2,
            "chunkPoints": [],
            "queryPoints": [],
            "documents": [],
            "stats": {"chunkCount": 0, "documentCount": 0, "queryCount": 0},
        }

    async with maker() as session:
        result = await session.execute(
            select(
                KYCDocumentChunk.id,
                KYCDocumentChunk.document_id,
                KYCDocumentChunk.chunk_index,
                KYCDocumentChunk.page_start,
                KYCDocumentChunk.page_end,
                KYCDocumentChunk.content,
                KYCDocumentChunk.chunk_metadata,
                KYCDocumentChunk.embedding,
            ).where(KYCDocumentChunk.submission_id == submission_id)
        )
        rows = result.all()

    chunk_rows: list[dict[str, Any]] = []
    vectors: list[list[float]] = []
    document_ids: set[str] = set()

    for row in rows:
        chunk_id, document_id, chunk_index, page_start, page_end, content, meta, embedding = row
        if embedding is None:
            continue
        vec = [float(v) for v in embedding]
        filename = ""
        if isinstance(meta, dict):
            filename = str(meta.get("filename") or "")
        chunk_rows.append(
            {
                "chunkId": str(chunk_id),
                "documentId": document_id,
                "chunkIndex": chunk_index,
                "filename": filename or document_id,
                "pageStart": page_start,
                "pageEnd": page_end,
                "contentPreview": (content or "").strip()[:240],
            }
        )
        vectors.append(vec)
        document_ids.add(document_id)

    query_meta = _collect_query_points(rag_trace)
    query_vectors = [item["embedding"] for item in query_meta]

    all_vectors = vectors + query_vectors
    coords = _pca_2d(all_vectors)
    chunk_coords = coords[: len(vectors)]
    query_coords = coords[len(vectors) :]

    documents = [
        {
            "documentId": doc_id,
            "color": _document_color(doc_id),
            "label": doc_id.split("/")[-1][:48] or doc_id[:48],
        }
        for doc_id in sorted(document_ids)
    ]
    doc_color = {d["documentId"]: d["color"] for d in documents}

    chunk_points = []
    for row, (x, y) in zip(chunk_rows, chunk_coords, strict=False):
        chunk_points.append(
            {
                **row,
                "x": x,
                "y": y,
                "color": doc_color.get(row["documentId"], "hsl(220 10% 55%)"),
                "kind": "chunk",
            }
        )

    query_points = []
    for meta, (x, y) in zip(query_meta, query_coords, strict=False):
        query_points.append(
            {
                "id": meta["id"],
                "serialNo": meta["serialNo"],
                "pass": meta["pass"],
                "label": meta["label"],
                "x": x,
                "y": y,
                "kind": "query",
            }
        )

    return {
        "method": "pca",
        "dimensions": 2,
        "chunkPoints": chunk_points,
        "queryPoints": query_points,
        "documents": documents,
        "stats": {
            "chunkCount": len(chunk_points),
            "documentCount": len(documents),
            "queryCount": len(query_points),
        },
    }
