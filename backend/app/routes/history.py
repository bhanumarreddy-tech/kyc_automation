"""HTTP handlers for listing and loading persisted KYC submissions."""

from __future__ import annotations

import random
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.config import get_settings
from app.db.session import db_session_maker
from app.db.submissions import (
    append_metadata_audit,
    get_kyc_submission,
    get_submission_metadata_row,
    list_kyc_submissions,
    similar_company_matches,
    upsert_submission_metadata,
)
from app.schemas import (
    AuditAppendRequest,
    HistoryDetailResponse,
    HistoryListItem,
    KYCRow,
    SubmissionMetadataResponse,
    SubmissionMetadataUpdate,
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
        ref_urls = r.reference_urls if isinstance(r.reference_urls, list) else []
        ref_n = sum(
            1 for u in ref_urls if u is not None and str(u).strip()
        )
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
                reference_url_count=ref_n,
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
    raw_refs = record.reference_urls
    ref_urls: list[str] = []
    if isinstance(raw_refs, list):
        ref_urls = [str(u).strip() for u in raw_refs if u is not None and str(u).strip()]
    intel = getattr(record, "pipeline_intelligence", None)
    pipeline_intel = intel if isinstance(intel, dict) else None
    return HistoryDetailResponse(
        submission_id=str(record.id),
        company_name=record.company_name,
        created_at=record.created_at,
        attached_documents=attached_documents_from_stored(record.document_filenames),
        duration_ms=record.duration_ms,
        reference_urls=ref_urls,
        rows=rows,
        pipeline_intelligence=pipeline_intel,
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


def _meta_to_response(submission_id: str, row) -> SubmissionMetadataResponse:
    return SubmissionMetadataResponse(
        submission_id=submission_id,
        sign_off=bool(row.sign_off),
        analyst_notes=str(row.analyst_notes or ""),
        audit_log=list(row.audit_log or []),
        escalated_serials=[int(x) for x in (row.escalated_serials or []) if str(x).isdigit()],
        workflow_state=dict(row.workflow_state or {}),
    )


@router.get(
    "/history/{submission_id}/metadata",
    response_model=SubmissionMetadataResponse,
    response_model_by_alias=True,
)
async def get_submission_metadata(submission_id: str) -> SubmissionMetadataResponse:
    try:
        uid = UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    async with maker() as session:
        rec = await get_kyc_submission(session, uid)
        if rec is None:
            raise HTTPException(status_code=404, detail="Submission not found")
        meta = await get_submission_metadata_row(session, uid)
        if meta is None:
            return SubmissionMetadataResponse(
                submission_id=submission_id,
                sign_off=False,
                analyst_notes="",
                audit_log=[],
                escalated_serials=[],
                workflow_state={},
            )
        return _meta_to_response(submission_id, meta)


@router.put(
    "/history/{submission_id}/metadata",
    response_model=SubmissionMetadataResponse,
    response_model_by_alias=True,
)
async def put_submission_metadata(
    submission_id: str,
    body: SubmissionMetadataUpdate,
) -> SubmissionMetadataResponse:
    try:
        uid = UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    async with maker() as session:
        rec = await get_kyc_submission(session, uid)
        if rec is None:
            raise HTTPException(status_code=404, detail="Submission not found")
        row = await upsert_submission_metadata(
            session,
            uid,
            sign_off=body.sign_off,
            analyst_notes=body.analyst_notes,
            escalated_serials=body.escalated_serials,
            workflow_state=body.workflow_state,
        )
        await session.commit()
        await session.refresh(row)
    return _meta_to_response(submission_id, row)


@router.post(
    "/history/{submission_id}/metadata/audit",
    response_model=SubmissionMetadataResponse,
    response_model_by_alias=True,
)
async def post_submission_audit(
    submission_id: str,
    body: AuditAppendRequest,
) -> SubmissionMetadataResponse:
    try:
        uid = UUID(submission_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    from datetime import datetime, timezone

    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "action": body.action,
        "analyst": body.analyst,
        "detail": body.detail,
    }

    async with maker() as session:
        rec = await get_kyc_submission(session, uid)
        if rec is None:
            raise HTTPException(status_code=404, detail="Submission not found")
        row = await append_metadata_audit(session, uid, entry)
        await session.commit()
        await session.refresh(row)
    return _meta_to_response(submission_id, row)


@router.get("/entity-resolution/similar")
async def entity_resolution_similar(
    company_name: str = Query(..., min_length=2, alias="companyName"),
    exclude_submission_id: str | None = Query(default=None, alias="excludeSubmissionId"),
    limit: int = Query(default=12, ge=1, le=50),
) -> list[dict[str, object]]:
    """Cheap fuzzy match over recent submissions (SequenceMatcher on company name)."""

    maker = db_session_maker()
    if maker is None:
        return []

    ex_uid: UUID | None = None
    if exclude_submission_id and exclude_submission_id.strip():
        try:
            ex_uid = UUID(exclude_submission_id.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid excludeSubmissionId") from None

    async with maker() as session:
        return await similar_company_matches(
            session,
            company_name.strip(),
            exclude_submission_id=ex_uid,
            result_limit=limit,
        )


@router.get("/history/{submission_id}/qa-sample")
async def qa_sample_serials(
    submission_id: str,
    n: int = Query(default=5, ge=1, le=40),
) -> dict[str, object]:
    """Random serial numbers for rows where AI validation is not ``Yes`` (QA spot-checks)."""

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

    rows_json = record.rows if isinstance(record.rows, list) else []
    candidates: list[int] = []
    for item in rows_json:
        if not isinstance(item, dict):
            continue
        v = str(item.get("validation", "") or "").strip()
        if v == "Yes":
            continue
        raw_sn = item.get("serialNo", item.get("serial_no", 0))
        try:
            sn = int(raw_sn)
        except (TypeError, ValueError):
            continue
        if 1 <= sn <= 512:
            candidates.append(sn)

    if not candidates:
        return {"serials": [], "poolSize": 0}
    k = min(n, len(candidates))
    sampled = random.sample(candidates, k=k)
    sampled.sort()
    return {"serials": sampled, "poolSize": len(set(candidates))}
