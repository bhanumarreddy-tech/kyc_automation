"""End-to-end orchestration for a single ``/api/process`` request.

For each of the 8 sections we make:

1. one *answer* Gemini call with Google Search grounding, and
2. one *validation* Gemini call with the user's documents attached.

The 8 answer calls run concurrently via :func:`asyncio.gather`. The 8
validation calls then run concurrently as well. Results are merged into
exactly 64 :class:`~app.schemas.KYCRow` instances ready to be returned
to the frontend.
"""

from __future__ import annotations

import asyncio
import logging

from app.config import get_settings
from app.questions import KYC_QUESTIONS, group_by_section
from app.schemas import KYCRow, SourceLink, ValidationSource
from app.services.answer_section import AnsweredQuestion, answer_section
from app.services.documents import parse_documents
from app.services.reference_urls import ingest_reference_urls
from app.services.sec_filings_hub import inject_sec_hub_into_answers, resolve_sec_filings_hub
from app.services.source_urls import (
    prioritize_and_cap_answer_sources,
    sanitize_answer_sources_urls,
)
from app.services.validate_section import ValidationResult, validate_section

logger = logging.getLogger(__name__)


async def run_pipeline(
    company: str,
    uploads: list[tuple[str, bytes, str]],
    reference_urls: list[str] | None = None,
) -> list[KYCRow]:
    """Run the full KYC pipeline and return the populated questionnaire rows."""

    settings = get_settings()
    sections = group_by_section()

    ref_urls = reference_urls or []
    sec_hub_task = asyncio.create_task(resolve_sec_filings_hub(company, settings))

    # Uploads first, then user-supplied URLs (same order as in the run form).
    upload_docs, url_docs = await asyncio.gather(
        parse_documents(uploads),
        ingest_reference_urls(ref_urls, settings),
    )
    parsed_docs = [*upload_docs, *url_docs]
    logger.info(
        "Parsed %d uploaded document(s) and %d reference URL document(s)",
        len(upload_docs),
        len(url_docs),
    )

    # Throttle concurrency so we stay under Gemini API quota. Both phases use
    # independent semaphores configured via env (ANSWER_CONCURRENCY,
    # VALIDATION_CONCURRENCY).
    answer_sem = asyncio.Semaphore(settings.answer_concurrency)
    validation_sem = asyncio.Semaphore(settings.validation_concurrency)
    inter_call_delay = settings.answer_inter_call_delay_seconds
    logger.info(
        "Running pipeline with answer_concurrency=%d, "
        "answer_inter_call_delay_seconds=%.1f, validation_concurrency=%d, "
        "validation_attach_documents=%s, gemini_validation_model=%s",
        settings.answer_concurrency,
        inter_call_delay,
        settings.validation_concurrency,
        settings.validation_attach_documents,
        settings.gemini_validation_model,
    )

    async def _bounded_answer(section_no: int, section_name: str, questions: list) -> list[AnsweredQuestion]:
        async with answer_sem:
            result = await answer_section(company, section_no, section_name, questions)
            # Hold the semaphore across the post-call sleep so the next queued
            # answer call doesn't fire while we're still waiting for the
            # rolling per-minute token window to free up. Skip the sleep on
            # the conceptually "last" call - we don't know which one that
            # is here, so we always sleep and accept a tiny tail latency.
            if inter_call_delay > 0:
                await asyncio.sleep(inter_call_delay)
            return result

    async def _bounded_validate(
        section_no: int,
        section_name: str,
        questions: list,
        answers: list[AnsweredQuestion],
    ) -> list[ValidationResult]:
        async with validation_sem:
            return await validate_section(
                company, section_no, section_name, questions, answers, parsed_docs
            )

    answer_tasks = [
        _bounded_answer(section_no, section_name, questions)
        for section_no, section_name, questions in sections
    ]
    answers_per_section: list[list[AnsweredQuestion]] = await asyncio.gather(
        *answer_tasks, return_exceptions=False
    )

    try:
        sec_hub = await sec_hub_task
    except Exception as exc:  # noqa: BLE001
        logger.warning("SEC filings hub task failed: %s", exc)
        sec_hub = None
    inject_sec_hub_into_answers(answers_per_section, sec_hub)

    await sanitize_answer_sources_urls(answers_per_section, settings)
    prioritize_and_cap_answer_sources(
        answers_per_section,
        settings,
        verification_hub_sources=sec_hub.hub_sources if sec_hub else None,
    )

    validation_tasks = [
        _bounded_validate(
            section_no,
            section_name,
            questions,
            answers_per_section[idx],
        )
        for idx, (section_no, section_name, questions) in enumerate(sections)
    ]
    validations_per_section: list[list[ValidationResult]] = await asyncio.gather(
        *validation_tasks, return_exceptions=False
    )

    answers_by_serial: dict[int, AnsweredQuestion] = {}
    validations_by_serial: dict[int, ValidationResult] = {}

    for section_answers in answers_per_section:
        for item in section_answers:
            answers_by_serial[item.serial_no] = item
    for section_validations in validations_per_section:
        for item in section_validations:
            validations_by_serial[item.serial_no] = item

    rows: list[KYCRow] = []
    for q in KYC_QUESTIONS:
        answer = answers_by_serial.get(q.serial_no)
        validation = validations_by_serial.get(q.serial_no)

        sources = [
            SourceLink(title=src.get("title") or src.get("url") or "", url=src.get("url") or "")
            for src in (answer.sources if answer else [])
        ]
        validation_sources = [
            ValidationSource(
                document=src.get("document") or "",
                page=src.get("page"),
                excerpt=src.get("excerpt"),
                url=src.get("url"),
            )
            for src in (validation.validation_sources if validation else [])
        ]

        rows.append(
            KYCRow(
                sectionNo=q.section_no,
                sectionName=q.section_name,
                serialNo=q.serial_no,
                question=q.question,
                answer=(answer.answer if answer else ""),
                sources=sources,
                validation=(validation.validation if validation else ""),  # type: ignore[arg-type]
                validationSources=validation_sources,
                analystComments="",
                kyc_agent_recon="",
            )
        )

    logger.info(
        "Pipeline finished for company=%r: %d questionnaire rows returned",
        company,
        len(rows),
    )
    return rows
