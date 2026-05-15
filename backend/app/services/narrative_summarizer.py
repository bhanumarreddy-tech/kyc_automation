"""Compliance narrative memo via Gemini."""

from __future__ import annotations

from google.genai import types

from app.config import get_settings
from app.schemas import KYCRow
from app.services.gemini_client import extract_text, generate_content_with_overload_retry, get_client


async def generate_compliance_narrative(company_name: str, rows: list[KYCRow]) -> str:
    settings = get_settings()
    client = get_client()

    answered = sum(
        1 for r in rows if r.answer.strip().lower() and r.answer.strip().lower() != "not found"
    )
    n = len(rows) or 1
    val_ok = sum(1 for r in rows if r.validation == "Yes")
    review = sum(1 for r in rows if r.validation != "Yes")

    low_conf = sorted(
        (r for r in rows if getattr(r, "confidence_score", None) is not None),
        key=lambda x: getattr(x, "confidence_score") or 0,
    )[:12]

    lines = [
        f"- Q{r.serial_no}: {(r.answer or '').strip()[:280]}..."
        if len(r.answer or "") > 280
        else f"- Q{r.serial_no}: {(r.answer or '').strip()}"
        for r in low_conf
        if r.answer.strip()
    ]

    prompt = (
        "Write a professional 2–4 paragraph KYC / KYB analyst narrative for a commercial bank file. "
        "Cover: coverage summary, document validation posture, open items for review, "
        "and citation quality. Do NOT invent facts.\n\n"
        f"Legal name: {company_name}\n"
        f"Completion: {answered}/{n} answered. AI validation Yes: {val_ok}/{n}. Rows not Yes: {review}/{n}.\n"
        f"Low-confidence sample (heuristic): \n" + "\n".join(lines)
    )

    resp = await generate_content_with_overload_retry(
        client,
        settings,
        model=settings.gemini_validation_model,
        contents=[types.Content(role="user", parts=[types.Part.from_text(text=prompt)])],
        config=types.GenerateContentConfig(max_output_tokens=2048, temperature=0.3),
    )
    return extract_text(resp).strip()
