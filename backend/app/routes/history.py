"""HTTP handlers for listing and loading persisted KYC submissions."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from app.db.session import db_session_maker
from app.db.submissions import get_kyc_submission, list_kyc_submissions
from app.schemas import (
    HistoryDetailResponse,
    HistoryListItem,
    KYCRow,
    attached_documents_from_stored,
)

router = APIRouter(prefix="/api", tags=["history"])


@router.get("/history", response_model=list[HistoryListItem], response_model_by_alias=True)
async def list_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[HistoryListItem]:
    maker = db_session_maker()
    if maker is None:
        return []

    async with maker() as session:
        records = await list_kyc_submissions(session, limit=limit, offset=offset)

    return [
        HistoryListItem(
            submission_id=str(r.id),
            company_name=r.company_name,
            created_at=r.created_at,
            document_count=len(r.document_filenames or []),
            attached_documents=attached_documents_from_stored(r.document_filenames),
            duration_ms=r.duration_ms,
        )
        for r in records
    ]


@router.get(
    "/history/{submission_id}",
    response_model=HistoryDetailResponse,
    response_model_by_alias=True,
)
async def get_history_detail(submission_id: str) -> HistoryDetailResponse:
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

    rows = [KYCRow.model_validate(item) for item in record.rows]
    return HistoryDetailResponse(
        submission_id=str(record.id),
        company_name=record.company_name,
        created_at=record.created_at,
        attached_documents=attached_documents_from_stored(record.document_filenames),
        duration_ms=record.duration_ms,
        rows=rows,
    )
