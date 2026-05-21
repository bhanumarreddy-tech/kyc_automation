"""HTTP handlers for RAG observability and debug views."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.db.session import db_session_maker
from app.db.submissions import get_kyc_submission
from app.services.rag.embedding_viz import build_embedding_visualization

router = APIRouter(prefix="/api", tags=["rag-observability"])


@router.get("/history/{submission_id}/rag-observability")
async def get_rag_observability(submission_id: str) -> dict:
    """Return persisted RAG trace plus 2D embedding projection for visualization."""
    try:
        uid = UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    async with maker() as session:
        record = await get_kyc_submission(session, uid)

    if record is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    rag_trace = record.rag_trace if isinstance(record.rag_trace, dict) else None
    embedding_map = await build_embedding_visualization(uid, rag_trace)

    return {
        "submissionId": str(record.id),
        "companyName": record.company_name,
        "trace": rag_trace,
        "embeddingMap": embedding_map,
        "hasTrace": rag_trace is not None,
    }
