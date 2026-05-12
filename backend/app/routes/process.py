"""HTTP route handlers for ``POST /api/process``."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.db.session import db_session_maker
from app.db.submissions import create_kyc_submission
from app.schemas import AttachedDocument, ProcessResponse
from app.services.pipeline import run_pipeline
from app.services.s3_storage import upload_submission_files

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["kyc"])


@router.post("/process", response_model=ProcessResponse, response_model_by_alias=True)
async def process_kyc(
    company_name: str = Form(..., min_length=1),
    files: list[UploadFile] | None = File(default=None),
) -> ProcessResponse:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured on the server",
        )

    company = company_name.strip()
    if not company:
        raise HTTPException(status_code=400, detail="company_name is required")

    uploads: list[tuple[str, bytes, str]] = []
    for upload in files or []:
        data = await upload.read()
        uploads.append((upload.filename or "document", data, upload.content_type or ""))

    total_payload = sum(len(raw) for _, raw, _ in uploads)
    logger.info(
        "Processing KYC submission for '%s' with %d uploaded file(s); total payload ~%.2f MiB "
        "(frontend nginx allows 100 MiB for /api/; raise client_max_body_size if you need more)",
        company,
        len(uploads),
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
        attached_documents = await upload_submission_files(
            settings,
            submission_id_uuid,
            uploads,
        )

    pipeline_started = time.perf_counter()
    rows = await run_pipeline(company, uploads)
    duration_ms = int((time.perf_counter() - pipeline_started) * 1000)

    submission_id_out: str | None = None
    saved_at_out: datetime | None = None
    if maker is not None:
        async with maker() as db_session:
            record = await create_kyc_submission(
                db_session,
                submission_id=submission_id_uuid,
                company_name=company,
                rows=rows,
                attached_documents=attached_documents,
                duration_ms=duration_ms,
            )
            await db_session.commit()
            submission_id_out = str(record.id)
            saved_at_out = record.created_at

    return ProcessResponse(
        rows=rows,
        submission_id=submission_id_out,
        saved_at=saved_at_out,
        duration_ms=duration_ms,
        attached_documents=attached_documents,
    )
