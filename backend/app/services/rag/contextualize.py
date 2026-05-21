"""Contextual Retrieval: prepend document-level context before embedding."""

from __future__ import annotations

import logging

from google.genai import types

from app.config import Settings
from app.services.gemini_client import generate_content_with_overload_retry, get_client
from app.services.rag.chunking import DocumentChunkDraft

logger = logging.getLogger(__name__)


def _template_context(
    company: str,
    draft: DocumentChunkDraft,
) -> str:
    page_hint = ""
    if draft.page_start is not None:
        if draft.page_end is not None and draft.page_end != draft.page_start:
            page_hint = f" pages {draft.page_start}–{draft.page_end}"
        else:
            page_hint = f" page {draft.page_start}"
    return (
        f"This excerpt is from KYC supporting material for {company}: "
        f"document \"{draft.document_id}\"{page_hint}, chunk {draft.chunk_index + 1}. "
    )


async def contextualize_chunks(
    company: str,
    drafts: list[DocumentChunkDraft],
    settings: Settings,
) -> list[str]:
    """Return contextualized text per draft (template or LLM batch)."""
    if not drafts:
        return []

    if not settings.rag_contextualize or not settings.gemini_api_key:
        return [_template_context(company, d) + d.content for d in drafts]

    # Batch contextualization for large corpora; template for small runs.
    if len(drafts) <= 3:
        return [_template_context(company, d) + d.content for d in drafts]

    lines = []
    for i, d in enumerate(drafts[:40]):
        snippet = d.content[:400].replace("\n", " ")
        lines.append(
            f"[{i}] doc={d.document_id!r} chunk={d.chunk_index} snippet={snippet!r}"
        )
    prompt = (
        f"Company: {company}\n\n"
        "For each numbered excerpt below, write ONE short sentence (max 30 words) "
        "that situates the snippet within the document (type, section, page if known). "
        "Return JSON: {\"contexts\": [\"...\", ...]} with the same array length and order.\n\n"
        + "\n".join(lines)
    )
    try:
        client = get_client()
        response = await generate_content_with_overload_retry(
            client,
            settings,
            model=settings.gemini_validation_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)],
                )
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        from app.services.gemini_client import parse_json_response

        parsed = parse_json_response(response)
        contexts = parsed.get("contexts") if isinstance(parsed, dict) else None
        if isinstance(contexts, list) and len(contexts) >= len(drafts):
            out: list[str] = []
            for i, d in enumerate(drafts):
                prefix = str(contexts[i]).strip() if contexts[i] else _template_context(company, d)
                if not prefix.endswith(" "):
                    prefix += " "
                out.append(prefix + d.content)
            return out
    except Exception:
        logger.warning("LLM contextualization failed; using template prefixes", exc_info=True)

    return [_template_context(company, d) + d.content for d in drafts]
