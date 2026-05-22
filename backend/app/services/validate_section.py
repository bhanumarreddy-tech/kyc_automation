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
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

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
from app.services.rag.index import count_submission_chunks, rag_indexing_available
from app.services.rag.pack import (
    chunks_to_parsed_documents,
    should_use_full_corpus_fallback,
)
from app.services.rag.retrieve import retrieve_for_question, retrieve_for_section

logger = logging.getLogger(__name__)

# Gemini ignores ``cache_control`` on blocks.
_CACHE_MIN_CHARS = 4_500
_QUESTION_EVIDENCE_CHAR_BUDGET = 35_000


_SYSTEM_PROMPT = (
    "You are a meticulous KYC document reviewer. Given a set of proposed "
    "answers about a company and the user's materials (uploaded files and/or "
    "content fetched from user-supplied web URLs), decide, for each answer, "
    "whether those materials directly support it. Be strict: only answer "
    "'Yes' when there is clear, on-page evidence in the materials. "
    "When 'Yes', cite the specific document filename (or web URL title/filename "
    "exactly as provided), the full source link for user-fetched web pages in "
    "the \"url\" field when applicable, and (where possible) a page number and "
    "short verbatim excerpt that supports the answer.\n"
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
    '          "excerpt": <short verbatim quote or null>,\n'
    '          "url": <full http(s) link when evidence is from a user-supplied reference URL; otherwise null>\n'
    "        }\n"
    "      ]\n"
    "    }\n"
    "  ]\n"
    "}\n"
    "Include exactly one entry per question. When validation is 'No', the "
    "validation_sources list must be empty. Use the exact document / URL "
    "identifier strings as provided in this request (filenames, URLs, or "
    "web-* placeholders). When evidence is from content fetched from a "
    "user-supplied reference URL, include that full URL in the \"url\" field "
    "(and the matching \"document\" label from the materials).\n"
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
    header = (
        f"Company: {company}\n\nSupporting materials (uploaded files and/or "
        "reference URL excerpts; extracted text):"
    )
    if not text_only_documents:
        return header + "\n\n(no extracted text in supporting materials)"

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
        return header + "\n\n(no extractable text in supporting materials)"
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
        "Proposed answers to validate against the materials above:\n"
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
        url_raw = src.get("url")
        url_val = (
            url_raw.strip()
            if isinstance(url_raw, str) and url_raw.strip()
            else None
        )
        out.append(
            {
                "document": document,
                "page": page,
                "excerpt": excerpt,
                "url": url_val,
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
                        (s.get("url") or "")[:500],
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


def _source_url_index(*doc_lists: list[ParsedDocument]) -> dict[str, str]:
    """Map material labels (filename, chunk labels, orig_filename) to fetched URL."""
    idx: dict[str, str] = {}
    for docs in doc_lists:
        for d in docs:
            u = (d.extra or {}).get("source_url")
            if not isinstance(u, str) or not u.strip():
                continue
            u = u.strip()
            idx[d.filename] = u
            orig = (d.extra or {}).get("orig_filename")
            if isinstance(orig, str) and orig.strip():
                idx.setdefault(orig.strip(), u)
    return idx


def _enrich_validation_results_urls(
    results: list[ValidationResult],
    url_by_document: dict[str, str],
) -> list[ValidationResult]:
    if not url_by_document:
        return results
    enriched: list[ValidationResult] = []
    for vr in results:
        if vr.validation != "Yes":
            enriched.append(vr)
            continue
        new_sources: list[dict[str, Any]] = []
        for s in vr.validation_sources:
            dct = dict(s)
            u = dct.get("url")
            if not (isinstance(u, str) and u.strip()):
                key = str(dct.get("document") or "").strip()
                fb = url_by_document.get(key)
                if fb:
                    dct["url"] = fb
            new_sources.append(dct)
        enriched.append(ValidationResult(vr.serial_no, vr.validation, new_sources))
    return enriched


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


async def _prepare_documents_for_validation_rag(
    documents: list[ParsedDocument],
    settings: Settings,
    *,
    submission_id: UUID,
    questions: list[KYCQuestion],
    answers: list[AnsweredQuestion],
    recall: bool = False,
) -> tuple[list[ParsedDocument], bool, list[ParsedDocument]] | None:
    """Semantic RAG path. Returns ``None`` when indexing/retrieval is unavailable."""
    if not rag_indexing_available(settings):
        return None

    indexed = await count_submission_chunks(submission_id)
    if indexed <= 0:
        return None

    attach = settings.validation_attach_documents
    pdf_expanded = expand_all_documents(documents, settings)
    chunked = expand_large_text_documents(
        pdf_expanded, settings, attach_natively=attach
    )
    textual_pool_pre = [
        d
        for d in chunked
        if (
            not is_native_validation_part(d, settings, attach_natively=attach)
            and bool(d.text and d.text.strip())
        )
    ]
    corpus_chars = (
        estimated_text_budget(chunked, settings, attach_natively=attach)
        if textual_pool_pre
        else 0
    )
    fallback_corpus = list(textual_pool_pre)

    if should_use_full_corpus_fallback(indexed, corpus_chars, settings):
        return None

    hits = await retrieve_for_section(
        submission_id,
        questions,
        answers,
        settings,
        recall=recall,
    )
    if not hits:
        return None

    retrieved_docs = chunks_to_parsed_documents(
        hits,
        max_total_chars=settings.validation_max_total_text_chars,
    )
    natives = [
        d
        for d in chunked
        if is_native_validation_part(d, settings, attach_natively=attach)
    ]
    return natives + retrieved_docs, True, fallback_corpus


async def validate_question(
    company: str,
    question: KYCQuestion,
    answer: AnsweredQuestion,
    documents: list[ParsedDocument],
    *,
    submission_id: UUID | None = None,
) -> ValidationResult:
    """Validate one KYC answer against top retrieved document chunks."""

    if not documents:
        return ValidationResult(question.serial_no, "", [])

    started = time.perf_counter()
    settings = get_settings()
    client = get_client()
    attach = settings.validation_attach_documents
    query = f"{question.question}\n{answer.answer or 'Not found'}"

    pdf_expanded = expand_all_documents(documents, settings)
    chunked = expand_large_text_documents(
        pdf_expanded, settings, attach_natively=attach
    )
    textual_pool = [
        d
        for d in chunked
        if (
            not is_native_validation_part(d, settings, attach_natively=attach)
            and bool(d.text and d.text.strip())
        )
    ]
    corpus_chars = (
        estimated_text_budget(chunked, settings, attach_natively=attach)
        if textual_pool
        else 0
    )
    fallback_corpus = list(textual_pool)
    natives = [
        d
        for d in chunked
        if is_native_validation_part(d, settings, attach_natively=attach)
    ]

    prepared: list[ParsedDocument] = []
    retrieval_used = False
    recall_docs_for_url_index: list[ParsedDocument] = []
    validation_path = "unknown"
    recall_used = False
    stage_timing: dict[str, int] = {}

    use_rag = submission_id is not None and rag_indexing_available(settings)
    indexed = 0
    if use_rag and submission_id is not None:
        indexed = await count_submission_chunks(submission_id)

    if (
        use_rag
        and indexed > 0
        and not should_use_full_corpus_fallback(indexed, corpus_chars, settings)
    ):
        t_retrieve = time.perf_counter()
        hits = await retrieve_for_question(
            submission_id,
            question,
            answer,
            settings,
            recall=False,
        )
        stage_timing["primaryRetrieveMs"] = int((time.perf_counter() - t_retrieve) * 1000)
        if hits:
            retrieved_docs = chunks_to_parsed_documents(
                hits,
                max_total_chars=_QUESTION_EVIDENCE_CHAR_BUDGET,
            )
            prepared = natives + retrieved_docs
            retrieval_used = True
            validation_path = "rag"

    if not prepared:
        if corpus_chars <= settings.rag_small_doc_full_text_chars:
            prepared = chunked
            validation_path = "full_corpus"
        elif textual_pool:
            retrieved = retrieval_selected_documents(
                textual_pool,
                query,
                settings,
                top_k=settings.validation_chunks_per_question,
            )
            prepared = natives + retrieved
            retrieval_used = bool(retrieved)
            validation_path = "keyword"
        else:
            prepared = natives
            validation_path = "natives_only"

    if not prepared:
        return ValidationResult(question.serial_no, "", [])

    known_documents = {d.filename for d in prepared}
    questions = [question]
    answers = [answer]

    t_validate = time.perf_counter()
    shard_results: list[list[ValidationResult]] = [
        await _invoke_validation_gemini_once(
            client=client,
            settings=settings,
            company=company,
            section_no=question.section_no,
            shard_docs=prepared,
            questions=questions,
            answers=answers,
            known_documents=known_documents,
            shard_hint="",
            max_total_chars=settings.validation_max_total_text_chars,
            max_preview_chars=settings.validation_max_text_preview_chars,
        )
    ]
    stage_timing["validationMs"] = int((time.perf_counter() - t_validate) * 1000)

    if retrieval_used and not _globally_has_yes(shard_results[0]):
        recall_prepared: list[ParsedDocument] | None = None
        if use_rag and submission_id is not None and indexed > 0:
            t_recall_retrieve = time.perf_counter()
            recall_hits = await retrieve_for_question(
                submission_id,
                question,
                answer,
                settings,
                recall=True,
            )
            stage_timing["recallRetrieveMs"] = int(
                (time.perf_counter() - t_recall_retrieve) * 1000
            )
            if recall_hits:
                recall_prepared = natives + chunks_to_parsed_documents(
                    recall_hits,
                    max_total_chars=_QUESTION_EVIDENCE_CHAR_BUDGET,
                )
        elif textual_pool:
            wider = retrieval_selected_documents(
                fallback_corpus,
                query,
                settings,
                top_k=settings.rag_recall_rerank_top_k,
            )
            recall_prepared = natives + wider

        if recall_prepared:
            recall_known = {d.filename for d in recall_prepared}
            t_recall_validate = time.perf_counter()
            shard_results.append(
                await _invoke_validation_gemini_once(
                    client=client,
                    settings=settings,
                    company=company,
                    section_no=question.section_no,
                    shard_docs=recall_prepared,
                    questions=questions,
                    answers=answers,
                    known_documents=recall_known,
                    shard_hint="recall",
                    max_total_chars=settings.validation_max_total_text_chars,
                    max_preview_chars=settings.validation_max_text_preview_chars,
                )
            )
            stage_timing["recallValidationMs"] = int(
                (time.perf_counter() - t_recall_validate) * 1000
            )
            recall_docs_for_url_index = recall_prepared
            recall_used = True

    merged = _merge_shard_validation_results(shard_results, questions)[0]
    url_idx = _source_url_index(documents, prepared, recall_docs_for_url_index)
    enriched = _enrich_validation_results_urls([merged], url_idx)
    result = enriched[0]

    from app.services.rag.trace_context import get_collector

    collector = get_collector()
    if collector is not None:
        collector.record_question_outcome(
            serial_no=question.serial_no,
            section_no=question.section_no,
            section_name=question.section_name,
            question=question.question,
            answer_preview=answer.answer if answer.answer else "Not found",
            validation_path=validation_path,
            validation=result.validation,
            retrieval_used=retrieval_used,
            duration_ms=int((time.perf_counter() - started) * 1000),
            stage_timing=stage_timing or None,
        )

    logger.info(
        "Validation question serial=%d section=%d for '%s' finished model=%s retrieval=%s",
        question.serial_no,
        question.section_no,
        company,
        settings.gemini_validation_model,
        retrieval_used,
    )
    return result


async def validate_section(
    company: str,
    section_no: int,
    section_name: str,
    questions: list[KYCQuestion],
    answers: list[AnsweredQuestion],
    documents: list[ParsedDocument],
    *,
    submission_id: UUID | None = None,
) -> list[ValidationResult]:
    """Run the validation Gemini calls for one section (possibly sharded)."""

    if not documents:
        return _empty_results(questions)

    settings = get_settings()
    client = get_client()
    attach = settings.validation_attach_documents

    retrieval_query = build_section_query_fragment(questions, answers)
    rag_prepared: tuple[list[ParsedDocument], bool, list[ParsedDocument]] | None = None
    if submission_id is not None:
        rag_prepared = await _prepare_documents_for_validation_rag(
            documents,
            settings,
            submission_id=submission_id,
            questions=questions,
            answers=answers,
            recall=False,
        )

    if rag_prepared is not None:
        prepared, retrieval_used_flag, textual_fallback_pool = rag_prepared
    else:
        keyword_query = (
            retrieval_query if settings.validation_use_chunk_retrieval else None
        )
        prepared, retrieval_used_flag, textual_fallback_pool = (
            _prepare_documents_for_validation(
                documents,
                settings,
                section_query=keyword_query,
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
    recall_docs_for_url_index: list[ParsedDocument] = []

    if retrieval_used_flag and not _globally_has_yes(merged):
        recall_prepared: list[ParsedDocument] | None = None
        if submission_id is not None:
            rag_recall = await _prepare_documents_for_validation_rag(
                documents,
                settings,
                submission_id=submission_id,
                questions=questions,
                answers=answers,
                recall=True,
            )
            if rag_recall is not None:
                recall_prepared, _, _ = rag_recall

        if recall_prepared is not None:
            wider = [
                d
                for d in recall_prepared
                if not is_native_validation_part(
                    d, settings, attach_natively=attach
                )
            ]
        else:
            wider = retrieval_selected_documents(
                textual_fallback_pool,
                retrieval_query,
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
        recall_docs_for_url_index = natives_recall + wider

    url_idx = _source_url_index(documents, prepared, recall_docs_for_url_index)
    merged = _enrich_validation_results_urls(merged, url_idx)

    logger.info(
        "Validation section %d (%s) finished with merged model=%s shards=%s",
        section_no,
        section_name,
        settings.gemini_validation_model,
        len(shard_results),
    )

    return merged

