"""HTTP route handlers for ``POST /api/process``."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.db.session import db_session_maker
from app.db.submissions import create_kyc_submission, get_kyc_submission
from app.schemas import (
    AttachedDocument,
    ProcessResponse,
    RerunProcessRequest,
    attached_documents_from_stored,
)
from app.services.pipeline import run_pipeline
from app.services.reference_urls import (
    normalize_reference_urls,
    validate_reference_urls_for_request,
)
from app.services.s3_storage import get_object_bytes, upload_submission_files

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["kyc"])


@router.post("/process", response_model=ProcessResponse, response_model_by_alias=True)
async def process_kyc(
    company_name: str = Form(..., min_length=1),
    files: list[UploadFile] | None = File(default=None),
    reference_urls: Annotated[list[str] | None, Form()] = None,
) -> ProcessResponse:
    t0 = time.perf_counter()

    def _elapsed() -> float:
        return time.perf_counter() - t0

    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured on the server",
        )

    company = company_name.strip()
    logger.info(
        "process_kyc: start elapsed=%.3fs company_name_len=%d multipart fields parsed",
        _elapsed(),
        len(company_name),
    )

    if not company:
        raise HTTPException(status_code=400, detail="company_name is required")

    normalized_urls = normalize_reference_urls(reference_urls or [])
    ok_urls, url_err = validate_reference_urls_for_request(
        normalized_urls,
        max_count=settings.reference_url_max_per_request,
    )
    if url_err:
        raise HTTPException(status_code=400, detail=url_err)
    assert ok_urls is not None
    logger.info(
        "process_kyc: reference URLs validated elapsed=%.3fs count=%d",
        _elapsed(),
        len(ok_urls),
    )

    file_list = files or []
    logger.info(
        "process_kyc: reading %d uploaded file(s) into memory elapsed=%.3fs",
        len(file_list),
        _elapsed(),
    )
    uploads: list[tuple[str, bytes, str]] = []
    for idx, upload in enumerate(file_list, start=1):
        read_start = time.perf_counter()
        data = await upload.read()
        read_ms = (time.perf_counter() - read_start) * 1000
        name = upload.filename or "document"
        uploads.append((name, data, upload.content_type or ""))
        logger.info(
            "process_kyc: upload %d/%d read name=%r bytes=%d read_ms=%.0f elapsed=%.3fs",
            idx,
            len(file_list),
            name,
            len(data),
            read_ms,
            _elapsed(),
        )

    total_payload = sum(len(raw) for _, raw, _ in uploads)
    logger.info(
        "Processing KYC submission for '%s' with %d uploaded file(s), %d reference URL(s); "
        "total file payload ~%.2f MiB "
        "(frontend nginx allows 100 MiB for /api/; raise client_max_body_size if you need more)",
        company,
        len(uploads),
        len(ok_urls),
        total_payload / (1024 * 1024),
    )

    maker = db_session_maker()
    submission_id_uuid = uuid.uuid4()
    attached_documents: list[AttachedDocument] = []

    if uploads:
        if not settings.s3_ready():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Object storage is not configured. "
                    "Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, and "
                    "S3_SECRET_ACCESS_KEY (and optionally S3_REGION)."
                ),
            )
        if maker is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Database is required when uploading documents "
                    "(submissions authorize downloads against saved metadata). "
                    "Configure Postgres / DATABASE_PASSWORD as for History."
                ),
            )
        logger.info(
            "process_kyc: storing %d file(s) in object storage elapsed=%.3fs",
            len(uploads),
            _elapsed(),
        )
        attached_documents = await upload_submission_files(
            settings,
            submission_id_uuid,
            uploads,
        )
        logger.info("process_kyc: object storage upload done elapsed=%.3fs", _elapsed())

    logger.info("process_kyc: pipeline starting elapsed=%.3fs", _elapsed())
    pipeline_started = time.perf_counter()
    rows = await run_pipeline(company, uploads, reference_urls=ok_urls)
    duration_ms = int((time.perf_counter() - pipeline_started) * 1000)
    logger.info(
        "process_kyc: pipeline finished duration_ms=%d elapsed=%.3fs",
        duration_ms,
        _elapsed(),
    )

    submission_id_out: str | None = None
    saved_at_out: datetime | None = None
    if maker is not None:
        logger.info("process_kyc: saving submission to database elapsed=%.3fs", _elapsed())
        async with maker() as db_session:
            record = await create_kyc_submission(
                db_session,
                submission_id=submission_id_uuid,
                company_name=company,
                rows=rows,
                attached_documents=attached_documents,
                duration_ms=duration_ms,
                reference_urls=ok_urls,
            )
            await db_session.commit()
            submission_id_out = str(record.id)
            saved_at_out = record.created_at
        logger.info(
            "process_kyc: submission saved id=%s elapsed=%.3fs",
            submission_id_out,
            _elapsed(),
        )

    return ProcessResponse(
        rows=rows,
        submission_id=submission_id_out,
        saved_at=saved_at_out,
        duration_ms=duration_ms,
        attached_documents=attached_documents,
        reference_urls=list(ok_urls),
    )


@router.post("/process/rerun", response_model=ProcessResponse, response_model_by_alias=True)
async def rerun_process_kyc(body: RerunProcessRequest) -> ProcessResponse:
    """Run the pipeline again using a saved submission's company, files, and reference URLs."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured on the server",
        )

    try:
        prior_id = uuid.UUID(body.submission_id.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(
            status_code=503,
            detail="Database is not configured",
        )

    async with maker() as db_session:
        record = await get_kyc_submission(db_session, prior_id)

    if record is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    company = (record.company_name or "").strip()
    if not company:
        raise HTTPException(
            status_code=400,
            detail="Stored submission has no company name",
        )

    raw_refs = record.reference_urls
    stored_url_strings: list[str] = []
    if isinstance(raw_refs, list):
        stored_url_strings = [
            str(u).strip() for u in raw_refs if u is not None and str(u).strip()
        ]

    normalized_urls = normalize_reference_urls(stored_url_strings)
    ok_urls, url_err = validate_reference_urls_for_request(
        normalized_urls,
        max_count=settings.reference_url_max_per_request,
    )
    if url_err:
        raise HTTPException(status_code=400, detail=url_err)
    assert ok_urls is not None

    docs = attached_documents_from_stored(record.document_filenames)
    uploads: list[tuple[str, bytes, str]] = []

    if docs:
        missing_keys = [d for d in docs if not d.object_key]
        if missing_keys:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Cannot rerun: one or more saved attachments have no storage key "
                    "(older submissions). Start a new run and upload the documents again."
                ),
            )
        if not settings.s3_ready():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Object storage is not configured. "
                    "Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, and "
                    "S3_SECRET_ACCESS_KEY (and optionally S3_REGION)."
                ),
            )
        for d in docs:
            key = d.object_key
            assert key is not None
            try:
                data = await get_object_bytes(settings, key)
            except FileNotFoundError:
                raise HTTPException(
                    status_code=404,
                    detail=f"Attachment is no longer in storage: {d.filename}",
                ) from None
            uploads.append((d.filename, data, d.content_type or ""))

    submission_id_uuid = uuid.uuid4()
    attached_documents: list[AttachedDocument] = []

    if uploads:
        attached_documents = await upload_submission_files(
            settings,
            submission_id_uuid,
            uploads,
        )

    pipeline_started = time.perf_counter()
    rows = await run_pipeline(company, uploads, reference_urls=ok_urls)
    duration_ms = int((time.perf_counter() - pipeline_started) * 1000)

    submission_id_out: str | None = None
    saved_at_out: datetime | None = None
    async with maker() as db_session:
        rec = await create_kyc_submission(
            db_session,
            submission_id=submission_id_uuid,
            company_name=company,
            rows=rows,
            attached_documents=attached_documents,
            duration_ms=duration_ms,
            reference_urls=ok_urls,
        )
        await db_session.commit()
        submission_id_out = str(rec.id)
        saved_at_out = rec.created_at

    return ProcessResponse(
        rows=rows,
        submission_id=submission_id_out,
        saved_at=saved_at_out,
        duration_ms=duration_ms,
        attached_documents=attached_documents,
        reference_urls=list(ok_urls),
    )
