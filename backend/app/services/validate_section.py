"""Per-section "validate against uploaded documents" Gemini call.

For each KYC section we send Gemini the answers produced by
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

from google.genai import types

from app.config import Settings, get_settings
from app.questions import KYCQuestion
from app.services.answer_section import AnsweredQuestion
from app.services.documents import ParsedDocument, text_preview
from app.services.document_sharding import (
    expand_all_documents,
    expand_large_text_documents,
    estimated_text_budget,
    is_native_validation_part,
    pack_validation_shards,
    retrieval_selected_documents,
)
from app.services.gemini_client import (
    generate_content_with_overload_retry,
    get_client,
    parse_json_response,
    user_content_blocks_to_gemini_parts,
)
from app.services.gemini_schemas import KYC_VALIDATION_RESPONSE_JSON_SCHEMA

logger = logging.getLogger(__name__)

# Gemini ignores ``cache_control`` on blocks.
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
    "validation_sources list. Do not invent or infer evidence.\n"
    "- If the proposed_answer is exactly 'Not relevant' (case-sensitive), "
    "or (after stripping leading/trailing space) starts with "
    "'Not applicable' — case-insensitive — the answer means the question "
    "does not apply to this entity or context (not a missing fact). There "
    "is no verbatim quote to match in the documents; return validation "
    "'Yes' with an empty validation_sources list."
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
    *,
    max_total_chars: int,
    max_preview_chars: int,
) -> str:
    """Build the stable text block containing company + extracted text."""
    header = f"Company: {company}\n\nUploaded supporting documents (extracted text):"
    if not text_only_documents:
        return header + "\n\n(no documents uploaded)"

    extra_blocks: list[str] = []
    remaining_budget = max_total_chars
    per_doc_cap = min(
        max_preview_chars,
        max(800, max_total_chars // max(1, len(text_only_documents))),
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


def build_section_query_fragment(
    questions: list[KYCQuestion],
    answers: list[AnsweredQuestion],
) -> str:
    """Compact section text useful for retrieval query construction."""
    by_serial = {a.serial_no: a for a in answers}
    blobs: list[str] = []
    for q in questions:
        ans = by_serial.get(q.serial_no)
        blobs.append(q.question + " ")
        blobs.append(ans.answer if ans else "Not found")
    return "".join(blobs)


def _build_attachments(
    documents: list[ParsedDocument],
    *,
    attach_natively: bool,
    max_pdf_bytes: int,
    max_image_bytes: int,
) -> tuple[list[dict[str, Any]], list[ParsedDocument]]:
    """Split documents into native PDF/image blocks vs. text-only previews."""
    blocks: list[dict[str, Any]] = []
    text_only: list[ParsedDocument] = []

    for doc in documents:
        if (
            attach_natively
            and doc.kind == "pdf"
            and doc.raw_bytes
            and len(doc.raw_bytes) <= max_pdf_bytes
            and not doc.error
        ):
            blocks.append(
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": base64.standard_b64encode(doc.raw_bytes).decode(
                            "ascii"
                        ),
                    },
                    "title": doc.filename,
                }
            )
            continue
        if (
            attach_natively
            and doc.kind == "image"
            and doc.raw_bytes
            and len(doc.raw_bytes) <= max_image_bytes
        ):
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": doc.media_type or "image/png",
                        "data": base64.standard_b64encode(doc.raw_bytes).decode(
                            "ascii"
                        ),
                    },
                }
            )
            continue
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
        out.append(
            {
                "document": document,
                "page": page,
                "excerpt": excerpt,
                "_known": document in known_documents,
            }
        )
    for item in out:
        item.pop("_known", None)
    return out


def _merge_shard_validation_results(
    shard_outputs: list[list[ValidationResult]],
    questions: list[KYCQuestion],
) -> list[ValidationResult]:
    """OR-merge: any shard ``Yes`` wins; citations union with dedupe."""
    by_serial: dict[int, list[ValidationResult]] = {q.serial_no: [] for q in questions}
    for shard in shard_outputs:
        for vr in shard:
            by_serial.setdefault(vr.serial_no, []).append(vr)

    merged: list[ValidationResult] = []
    for q in questions:
        parts = by_serial[q.serial_no]
        yes_candidates = [p for p in parts if p.validation == "Yes"]
        if yes_candidates:
            seen: set[tuple[Any, Any, Any]] = set()
            combined_sources: list[dict[str, Any]] = []
            for p in yes_candidates:
                for s in p.validation_sources:
                    key = (
                        s.get("document"),
                        s.get("page"),
                        (s.get("excerpt") or "")[:200],
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    combined_sources.append(dict(s))
            merged.append(
                ValidationResult(
                    serial_no=q.serial_no,
                    validation="Yes",
                    validation_sources=combined_sources,
                )
            )
        elif any(p.validation == "No" for p in parts):
            merged.append(
                ValidationResult(serial_no=q.serial_no, validation="No", validation_sources=[])
            )
        else:
            merged.append(
                ValidationResult(serial_no=q.serial_no, validation="", validation_sources=[])
            )
    return merged


def _parse_validation_payload(
    data: dict[str, Any] | Any,
    known_docs: set[str],
    questions: list[KYCQuestion],
) -> dict[int, ValidationResult]:
    items = data.get("items") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return {}

    out: dict[int, ValidationResult] = {}
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
        out[serial_no] = ValidationResult(
            serial_no=serial_no,
            validation=validation,
            validation_sources=[dict(s) for s in sources],
        )
    return out


def _gather_validation_results_placeholder(
    by_serial: dict[int, ValidationResult],
    questions: list[KYCQuestion],
) -> list[ValidationResult]:
    return [
        by_serial.get(q.serial_no, ValidationResult(q.serial_no, "", []))
        for q in questions
    ]


def _globally_has_yes(rows: list[ValidationResult]) -> bool:
    return any(r.validation == "Yes" for r in rows)


async def _invoke_validation_gemini_once(
    *,
    client: Any,
    settings: Settings,
    company: str,
    section_no: int,
    shard_docs: list[ParsedDocument],
    questions: list[KYCQuestion],
    answers: list[AnsweredQuestion],
    known_documents: set[str],
    shard_hint: str,
    max_total_chars: int,
    max_preview_chars: int,
) -> list[ValidationResult]:
    attachments, text_only = _build_attachments(
        shard_docs,
        attach_natively=settings.validation_attach_documents,
        max_pdf_bytes=settings.validation_max_pdf_bytes,
        max_image_bytes=settings.validation_max_image_bytes,
    )

    stable_text = _build_stable_prefix(
        company,
        text_only,
        max_total_chars=max_total_chars,
        max_preview_chars=max_preview_chars,
    )

    instruction_note = ""
    if shard_hint:
        instruction_note = (
            f"\n(This request includes document subset [{shard_hint}]; citations "
            "must use the exact filenames attached in this subset.)\n"
        )

    section_text = instruction_note + _build_section_text(questions, answers)

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

    gemini_parts = user_content_blocks_to_gemini_parts(user_content)
    gemini_contents = [types.Content(role="user", parts=gemini_parts)]

    logger.info(
        "%s validating section %d for '%s' (%d shard doc(s)), "
        "native_parts=%d, text_doc_previews=%d",
        shard_hint or "Merged",
        section_no,
        company,
        len(shard_docs),
        len(attachments),
        len(text_only),
    )

    try:
        response = await generate_content_with_overload_retry(
            client,
            settings,
            model=settings.gemini_validation_model,
            contents=gemini_contents,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_PROMPT,
                max_output_tokens=8192,
                response_mime_type="application/json",
                response_json_schema=KYC_VALIDATION_RESPONSE_JSON_SCHEMA,
            ),
        )
    except Exception as exc:  # noqa: BLE001 - surface failure as blank shard
        logger.exception(
            "Gemini validation shard failed section %d: %s",
            section_no,
            exc,
        )
        return _empty_results(questions)

    try:
        data = parse_json_response(response)
    except (json.JSONDecodeError, ValueError):
        logger.warning(
            "Could not parse JSON from validation shard section %d", section_no
        )
        return _empty_results(questions)

    if not isinstance(data, dict):
        return _empty_results(questions)

    by_serial = _parse_validation_payload(data, known_documents, questions)
    out = _gather_validation_results_placeholder(by_serial, questions)
    return out


def _prepare_documents_for_validation(
    documents: list[ParsedDocument],
    settings: Settings,
    *,
    section_query: str | None,
) -> tuple[list[ParsedDocument], bool, list[ParsedDocument]]:
    """Returns (documents_for_sharding, retrieval_used_flag, textual_corpus_fallback).

    ``textual_corpus_fallback`` is every non-native text-bearing slice from the
    expanded corpus (even when retrieval replaced it in ``documents_for_sharding``)
    so the recall path can widen from the whole submission.
    """

    attach = settings.validation_attach_documents

    pdf_expanded = expand_all_documents(documents, settings)

    chunked = expand_large_text_documents(
        pdf_expanded, settings, attach_natively=attach
    )

    use_retrieval = settings.validation_use_chunk_retrieval

    natives = [
        d
        for d in chunked
        if is_native_validation_part(d, settings, attach_natively=attach)
    ]
    textual_pool_pre = [
        d
        for d in chunked
        if (
            not is_native_validation_part(d, settings, attach_natively=attach)
            and bool(d.text and d.text.strip())
        )
    ]
    corpus_chars = (
        estimated_text_budget(
            chunked,
            settings,
            attach_natively=attach,
        )
        if textual_pool_pre
        else 0
    )

    fallback_corpus = list(textual_pool_pre)

    if (
        use_retrieval
        and corpus_chars > settings.validation_max_total_text_chars
        and textual_pool_pre
        and section_query
    ):
        retrieved = retrieval_selected_documents(
            textual_pool_pre,
            section_query,
            settings,
            top_k=settings.validation_retrieval_top_chunks,
        )
        return natives + retrieved, True, fallback_corpus

    return chunked, False, fallback_corpus


async def validate_section(
    company: str,
    section_no: int,
    section_name: str,
    questions: list[KYCQuestion],
    answers: list[AnsweredQuestion],
    documents: list[ParsedDocument],
) -> list[ValidationResult]:
    """Run the validation Gemini calls for one section (possibly sharded)."""

    if not documents:
        return _empty_results(questions)

    settings = get_settings()
    client = get_client()
    attach = settings.validation_attach_documents

    retrieval_query = (
        build_section_query_fragment(questions, answers)
        if settings.validation_use_chunk_retrieval
        else None
    )
    prepared, retrieval_used_flag, textual_fallback_pool = (
        _prepare_documents_for_validation(
            documents,
            settings,
            section_query=retrieval_query,
        )
    )

    shards = pack_validation_shards(
        prepared,
        settings,
        attach_natively=attach,
    )
    shard_descriptors = enumerate(shards)
    shard_results: list[list[ValidationResult]] = []

    known_documents = {d.filename for d in prepared}

    for shard_idx, shard_docs in shard_descriptors:
        hint = f"shard {shard_idx + 1}/{len(shards)}" if len(shards) > 1 else ""
        shard_results.append(
            await _invoke_validation_gemini_once(
                client=client,
                settings=settings,
                company=company,
                section_no=section_no,
                shard_docs=shard_docs,
                questions=questions,
                answers=answers,
                known_documents=known_documents,
                shard_hint=hint,
                max_total_chars=settings.validation_max_total_text_chars,
                max_preview_chars=settings.validation_max_text_preview_chars,
            )
        )

    merged = _merge_shard_validation_results(shard_results, questions)

    if retrieval_used_flag and not _globally_has_yes(merged):
        wider = retrieval_selected_documents(
            textual_fallback_pool,
            retrieval_query or build_section_query_fragment(questions, answers),
            settings,
            top_k=settings.validation_retrieval_recall_chunks,
        )

        natives_recall = [
            d
            for d in prepared
            if is_native_validation_part(d, settings, attach_natively=attach)
        ]

        recall_shards = pack_validation_shards(
            natives_recall + wider,
            settings,
            attach_natively=attach,
        )
        recall_known = {d.filename for d in natives_recall} | {d.filename for d in wider}
        recall_outputs: list[list[ValidationResult]] = []
        for ridx, r_docs in enumerate(recall_shards):
            recall_outputs.append(
                await _invoke_validation_gemini_once(
                    client=client,
                    settings=settings,
                    company=company,
                    section_no=section_no,
                    shard_docs=r_docs,
                    questions=questions,
                    answers=answers,
                    known_documents=recall_known,
                    shard_hint=(
                        f"recall shard {ridx + 1}/{len(recall_shards)}"
                        if len(recall_shards) > 1
                        else "recall shard"
                    ),
                    max_total_chars=settings.validation_max_total_text_chars,
                    max_preview_chars=settings.validation_max_text_preview_chars,
                )
            )

        merged = _merge_shard_validation_results(
            shard_results + recall_outputs,
            questions,
        )

    logger.info(
        "Validation section %d (%s) finished with merged model=%s shards=%s",
        section_no,
        section_name,
        settings.gemini_validation_model,
        len(shard_results),
    )

    return merged

