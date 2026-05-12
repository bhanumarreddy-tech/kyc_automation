"""HTTP route handlers for ``POST /api/process``."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.db.session import db_session_maker
from app.db.submissions import create_kyc_submission
from app.schemas import ProcessResponse
from app.services.pipeline import run_pipeline

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

    rows = await run_pipeline(company, uploads)

    submission_id_out: str | None = None
    saved_at_out: datetime | None = None
    maker = db_session_maker()
    if maker is not None:
        doc_names = [fn for fn, _, _ in uploads]
        async with maker() as db_session:
            record = await create_kyc_submission(
                db_session,
                company_name=company,
                rows=rows,
                document_filenames=doc_names,
            )
            await db_session.commit()
            submission_id_out = str(record.id)
            saved_at_out = record.created_at

    return ProcessResponse(
        rows=rows,
        submission_id=submission_id_out,
        saved_at=saved_at_out,
    )
