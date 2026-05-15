"""Compliance narrative generation (Gemini)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.db.session import db_session_maker
from app.db.submissions import get_kyc_submission
from app.schemas import KYCRow, NarrativeRequest
from app.services.narrative_summarizer import generate_compliance_narrative

router = APIRouter(prefix="/api", tags=["narrative"])


@router.post("/narrative")
async def post_compliance_narrative(body: NarrativeRequest) -> dict[str, str]:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured on the server",
        )

    rows: list[KYCRow] | None = body.rows
    company = body.company_name.strip()
    if body.submission_id and str(body.submission_id).strip():
        try:
            uid = UUID(str(body.submission_id).strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid submissionId") from None
        maker = db_session_maker()
        if maker is None:
            raise HTTPException(status_code=503, detail="Database is not configured")
        async with maker() as session:
            rec = await get_kyc_submission(session, uid)
        if rec is None:
            raise HTTPException(status_code=404, detail="Submission not found")
        company = (rec.company_name or company).strip()
        rows = [KYCRow.model_validate(item) for item in rec.rows]

    if not rows:
        raise HTTPException(
            status_code=400,
            detail="Provide rows in the request body or a valid submissionId",
        )

    text = await generate_compliance_narrative(company or "Unknown entity", rows)
    return {"narrative": text}
