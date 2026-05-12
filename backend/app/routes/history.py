"""HTTP handlers for listing and loading persisted KYC submissions."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.db.session import db_session_maker
from app.db.submissions import get_kyc_submission, list_kyc_submissions
from app.schemas import (
    HistoryDetailResponse,
    HistoryListItem,
    KYCRow,
    attached_documents_from_stored,
    history_metrics_from_rows_json,
)
from app.services.s3_storage import key_belongs_to_submission, presigned_download_url

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

    items: list[HistoryListItem] = []
    for r in records:
        completion_pct, needs_review_n = history_metrics_from_rows_json(r.rows)
        items.append(
            HistoryListItem(
                submission_id=str(r.id),
                company_name=r.company_name,
                created_at=r.created_at,
                document_count=len(r.document_filenames or []),
                attached_documents=attached_documents_from_stored(r.document_filenames),
                duration_ms=r.duration_ms,
                completion_percent=completion_pct,
                needs_review_count=needs_review_n,
            )
        )
    return items


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


@router.get("/history/{submission_id}/attachments/download")
async def download_submission_attachment(
    submission_id: str,
    object_key: str = Query(..., min_length=1, alias="objectKey"),
):
    """Authorized redirect to a short-lived HTTPS URL served by object storage."""
    try:
        uid = UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    if not key_belongs_to_submission(object_key, uid):
        raise HTTPException(status_code=400, detail="Invalid attachment key") from None

    settings = get_settings()
    if not settings.s3_ready():
        raise HTTPException(status_code=503, detail="Object storage is not configured")

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    async with maker() as session:
        record = await get_kyc_submission(session, uid)

    if record is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    docs = attached_documents_from_stored(record.document_filenames)
    match = None
    for d in docs:
        if d.object_key == object_key:
            match = d
            break
    if match is None:
        raise HTTPException(status_code=404, detail="Attachment not found")

    filename = match.filename or "download"
    try:
        url = presigned_download_url(settings, object_key=object_key, filename=filename)
    except Exception as exc:  # pragma: no cover — provider-specific
        raise HTTPException(
            status_code=502,
            detail=f"Could not prepare download ({exc.__class__.__name__})",
        ) from exc

    return RedirectResponse(url=url, status_code=302)
