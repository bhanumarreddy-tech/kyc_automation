"""Optional Gemini-powered summary of uploaded document text."""

from __future__ import annotations

import logging

from google.genai import types

from app.config import get_settings
from app.services.gemini_client import extract_text, generate_content_with_overload_retry, get_client

logger = logging.getLogger(__name__)

MAX_CHARS = 14000


async def maybe_structured_entity_extract(company: str, document_blob: str) -> str | None:
    """Return a short bullet facts block or None if skipped / failed."""

    blob = (document_blob or "").strip()
    if len(blob) < 80:
        return None

    settings = get_settings()
    if not settings.gemini_api_key:
        return None

    trimmed = blob[:MAX_CHARS]
    prompt = (
        "You are a KYB document analyst. Given extracted text from filings or contracts, "
        "list the most important structured facts as 5–10 short bullets: legal name, "
        "registration id if present, jurisdiction, key officers, percentages, material "
        "risk flags. Company context: "
        f"{company!r}\n\n---\n{trimmed}\n---"
    )

    try:
        client = get_client()
        resp = await generate_content_with_overload_retry(
            client,
            settings,
            model=settings.gemini_validation_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                ),
            ],
            config=types.GenerateContentConfig(max_output_tokens=1024, temperature=0.2),
        )
        text = extract_text(resp).strip()
        return text[:6000] if text else None
    except Exception as exc:
        logger.warning("structured extract skipped: %s", exc)
        return None
