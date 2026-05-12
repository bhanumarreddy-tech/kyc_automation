"""HTTP route handlers for ``POST /api/process``."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
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

    max_bytes = settings.max_file_mb * 1024 * 1024
    uploads: list[tuple[str, bytes, str]] = []
    for upload in files or []:
        data = await upload.read()
        if len(data) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File '{upload.filename}' exceeds the {settings.max_file_mb} MB limit",
            )
        uploads.append((upload.filename or "document", data, upload.content_type or ""))

    logger.info(
        "Processing KYC submission for '%s' with %d uploaded file(s)",
        company,
        len(uploads),
    )

    rows = await run_pipeline(company, uploads)
    return ProcessResponse(rows=rows)
