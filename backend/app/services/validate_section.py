"""Per-section "validate against uploaded documents" Claude call.

For each KYC section we send Claude the answers produced by
:mod:`app.services.answer_section` together with the user's uploaded
documents (PDFs and images attached natively, DOCX/other as extracted
text) and ask whether each answer is supported by the documents. When
``Yes``, we also collect the document filename, page and optional
excerpt that supports the answer.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.questions import KYCQuestion
from app.services.answer_section import AnsweredQuestion
from app.services.claude_client import get_client, parse_json_response
from app.services.documents import ParsedDocument, text_preview

logger = logging.getLogger(__name__)

# Per-file caps to keep prompts manageable.
_MAX_PDF_BYTES = 8 * 1024 * 1024
_MAX_IMAGE_BYTES = 4 * 1024 * 1024
_MAX_TEXT_PREVIEW_CHARS = 6000
# Hard ceiling on the combined extracted-text payload sent to Claude (across
# all documents) per validation call. Keeps a single call well below the
# 30k-token tier limit even with several large PDFs uploaded.
_MAX_TOTAL_TEXT_CHARS = 20_000
# Anthropic prompt caching requires a cacheable block of at least ~1024
# tokens. ~4 chars per token is a safe rule of thumb -> require ~4500 chars
# in the stable prefix before bothering to mark it for caching.
_CACHE_MIN_CHARS = 4_500


_SYSTEM_PROMPT = (
    "You are a meticulous KYC document reviewer. Given a set of proposed "
    "answers about a company and the user's uploaded documents, decide, for "
    "each answer, whether the documents directly support it. Be strict: only "
    "answer 'Yes' when there is clear, on-page evidence in the documents. "
    "When 'Yes', cite the specific document filename and (where possible) a "
    "page number and short verbatim excerpt that supports the answer.\n"
    "\n"
    "Matching rules:\n"
    "- Fact-style answers (registration numbers, TINs, addresses, dates, "
    "tickers, percentages, named individuals): require a near-verbatim "
    "match in the document text. A digit or character difference, a "
    "different address, or a different person's name means 'No'.\n"
    "- Prose answers (business description, ownership structure, risk "
    "commentary): a paraphrase in the document is acceptable as long as it "
    "asserts the same fact.\n"
    "- If the proposed_answer is the literal string 'Not found' (or is "
    "empty), there is nothing to support - return 'No' and an empty "
    "validation_sources list. Do not invent or infer evidence."
)


_RESPONSE_FORMAT_INSTRUCTIONS = (
    "Respond with a single JSON object and nothing else (no prose, no markdown "
    "fences). The schema is:\n"
    "{\n"
    '  "items": [\n'
    "    {\n"
    '      "serial_no": <integer matching the question>,\n'
    '      "validation": "Yes" | "No",\n'
    '      "validation_sources": [\n'
    "        {\n"
    '          "document": <string, original filename>,\n'
    '          "page": <integer or null>,\n'
    '          "excerpt": <short verbatim quote or null>\n'
    "        }\n"
    "      ]\n"
    "    }\n"
    "  ]\n"
    "}\n"
    "Include exactly one entry per question. When validation is 'No', the "
    "validation_sources list must be empty. Use the exact filename strings "
    "as provided in the attachments."
)


@dataclass
class ValidationResult:
    serial_no: int
    validation: str  # "Yes" or "No" (empty string means we couldn't decide)
    validation_sources: list[dict[str, Any]]


def _empty_results(questions: list[KYCQuestion]) -> list[ValidationResult]:
    return [ValidationResult(q.serial_no, "", []) for q in questions]


def _build_stable_prefix(
    company: str,
    text_only_documents: list[ParsedDocument],
) -> str:
    """Build the per-submission, section-agnostic text block.

    This block (company name + extracted document text) is identical across
    all 8 validation calls in a single submission, which makes it the ideal
    candidate for Anthropic prompt caching: the first call writes the
    cache, the remaining 7 read it at ~10% of the input-token cost and a
    correspondingly lower hit on the per-minute rate limit.
    """
    header = f"Company: {company}\n\nUploaded supporting documents (extracted text):"
    if not text_only_documents:
        return header + "\n\n(no documents uploaded)"

    extra_blocks: list[str] = []
    remaining_budget = _MAX_TOTAL_TEXT_CHARS
    per_doc_cap = min(
        _MAX_TEXT_PREVIEW_CHARS,
        max(800, _MAX_TOTAL_TEXT_CHARS // max(1, len(text_only_documents))),
    )
    for doc in text_only_documents:
        if remaining_budget <= 0:
            break
        snippet = text_preview(doc, min(per_doc_cap, remaining_budget))
        if not snippet.strip():
            continue
        extra_blocks.append(
            f"--- BEGIN DOCUMENT: {doc.filename} ---\n{snippet}\n--- END DOCUMENT ---"
        )
        remaining_budget -= len(snippet)

    if not extra_blocks:
        return header + "\n\n(no extractable text in uploaded documents)"
    return header + "\n\n" + "\n\n".join(extra_blocks)


def _build_section_text(
    questions: list[KYCQuestion],
    answers: list[AnsweredQuestion],
) -> str:
    """Build the per-section, variable part of the user message."""
    by_serial = {a.serial_no: a for a in answers}
    qa_lines: list[str] = []
    for q in questions:
        proposed = by_serial.get(q.serial_no)
        answer_text = proposed.answer if proposed else ""
        qa_lines.append(
            f"  - serial_no={q.serial_no}\n"
            f"    question: {q.question}\n"
            f"    proposed_answer: {answer_text or 'Not found'}"
        )
    return (
        "Proposed answers to validate against the documents above:\n"
        + "\n".join(qa_lines)
        + "\n\n"
        + _RESPONSE_FORMAT_INSTRUCTIONS
    )


def _build_attachments(
    documents: list[ParsedDocument],
    *,
    attach_natively: bool,
) -> tuple[list[dict[str, Any]], list[ParsedDocument]]:
    """Split documents into native Claude content blocks vs. text-only previews.

    When ``attach_natively`` is ``False`` (the default, controlled via
    ``VALIDATION_ATTACH_DOCUMENTS``), every document is sent as extracted
    text only. This drastically reduces input-token usage because the same
    document otherwise gets re-encoded as base64 once per section, which
    will trivially exceed low rate-limit tiers (e.g. 30k tokens/min on the
    starter Anthropic plan).
    """
    blocks: list[dict[str, Any]] = []
    text_only: list[ParsedDocument] = []

    for doc in documents:
        if attach_natively and doc.kind == "pdf" and doc.raw_bytes and len(doc.raw_bytes) <= _MAX_PDF_BYTES and not doc.error:
            blocks.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(doc.raw_bytes).decode("ascii"),
                    },
                    "title": doc.filename,
                }
            )
            continue
        if attach_natively and doc.kind == "image" and doc.raw_bytes and len(doc.raw_bytes) <= _MAX_IMAGE_BYTES:
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": doc.media_type or "image/png",
                        "data": base64.standard_b64encode(doc.raw_bytes).decode("ascii"),
                    },
                }
            )
            continue
        # All other cases (and the default text-only path): include extracted text.
        if doc.text.strip():
            text_only.append(doc)

    return blocks, text_only


def _normalise_validation(value: Any) -> str:
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"yes", "y", "true", "supported"}:
            return "Yes"
        if v in {"no", "n", "false", "unsupported", "not supported"}:
            return "No"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return ""


def _normalise_sources(raw: Any, known_documents: set[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for src in raw:
        if not isinstance(src, dict):
            continue
        document = str(src.get("document") or "").strip()
        if not document:
            continue
        page_raw = src.get("page")
        page: int | None
        if isinstance(page_raw, bool):
            page = None
        elif isinstance(page_raw, int):
            page = page_raw
        elif isinstance(page_raw, str) and page_raw.strip().isdigit():
            page = int(page_raw.strip())
        else:
            page = None
        excerpt_raw = src.get("excerpt")
        excerpt = (
            excerpt_raw.strip()
            if isinstance(excerpt_raw, str) and excerpt_raw.strip()
            else None
        )
        # If the model hallucinated a doc that wasn't attached, keep it
        # but it will be obvious in the UI. We don't filter aggressively.
        out.append(
            {
                "document": document,
                "page": page,
                "excerpt": excerpt,
                "_known": document in known_documents,
            }
        )
    # Strip the helper flag before returning - we kept it for future filtering.
    for item in out:
        item.pop("_known", None)
    return out


async def validate_section(
    company: str,
    section_no: int,
    section_name: str,
    questions: list[KYCQuestion],
    answers: list[AnsweredQuestion],
    documents: list[ParsedDocument],
) -> list[ValidationResult]:
    """Run the validation Claude call for a single section."""

    if not documents:
        return _empty_results(questions)

    settings = get_settings()
    client = get_client()

    attachments, text_only = _build_attachments(
        documents, attach_natively=settings.validation_attach_documents
    )
    stable_text = _build_stable_prefix(company, text_only)
    section_text = _build_section_text(questions, answers)

    # The stable prefix (company name + extracted documents) is identical
    # across all 8 validation calls for a single submission. Marking the last
    # block of that prefix with cache_control makes Anthropic cache the
    # whole prefix (including any native PDF/image attachments that come
    # before it) so the remaining 7 calls read it instead of re-uploading.
    stable_block: dict[str, Any] = {"type": "text", "text": stable_text}
    cache_enabled = (
        settings.enable_prompt_caching
        and (len(stable_text) >= _CACHE_MIN_CHARS or bool(attachments))
    )
    if cache_enabled:
        stable_block["cache_control"] = {"type": "ephemeral"}

    user_content: list[dict[str, Any]] = [
        *attachments,
        stable_block,
        {"type": "text", "text": section_text},
    ]

    # No assistant prefill: some models reject a final assistant turn ("This
    # model does not support assistant message prefill"). JSON-only output is
    # still enforced via _RESPONSE_FORMAT_INSTRUCTIONS; parse_json_response
    # extracts the object from the reply.
    messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]

    logger.info(
        "Validating section %d (%s) for '%s' against %d document(s) "
        "(%d native attachments, %d text previews, cache=%s)",
        section_no,
        section_name,
        company,
        len(documents),
        len(attachments),
        len(text_only),
        "on" if cache_enabled else "off",
    )

    try:
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=2048,
            system=_SYSTEM_PROMPT,
            messages=messages,
        )
    except Exception as exc:  # noqa: BLE001 - surface failure as blank validation
        logger.exception(
            "Claude validation call failed for section %d: %s", section_no, exc
        )
        return _empty_results(questions)

    usage = getattr(response, "usage", None)
    if usage is not None:
        logger.info(
            "section %d usage: input=%s, output=%s, cache_create=%s, cache_read=%s",
            section_no,
            getattr(usage, "input_tokens", None),
            getattr(usage, "output_tokens", None),
            getattr(usage, "cache_creation_input_tokens", None),
            getattr(usage, "cache_read_input_tokens", None),
        )

    try:
        data = parse_json_response(response)
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Could not parse JSON from validation call for section %d", section_no
        )
        return _empty_results(questions)

    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        logger.warning(
            "Validation response for section %d missing 'items' list", section_no
        )
        return _empty_results(questions)

    known_docs = {doc.filename for doc in documents}
    by_serial: dict[int, ValidationResult] = {}
    for raw in items:
        if not isinstance(raw, dict):
            continue
        try:
            serial_no = int(raw.get("serial_no"))
        except (TypeError, ValueError):
            continue
        validation = _normalise_validation(raw.get("validation"))
        sources = _normalise_sources(raw.get("validation_sources"), known_docs)
        if validation != "Yes":
            sources = []
        by_serial[serial_no] = ValidationResult(
            serial_no=serial_no,
            validation=validation,
            validation_sources=sources,
        )

    return [
        by_serial.get(q.serial_no, ValidationResult(q.serial_no, "", []))
        for q in questions
    ]
