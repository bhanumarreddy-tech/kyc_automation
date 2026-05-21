"""End-to-end orchestration for a single ``/api/process`` request.

For each of the 8 sections we make one *answer* Gemini call with Google
Search grounding. Validation then runs per question (64 total): each question
retrieves top document chunks and gets its own validation Gemini call.

The 8 answer calls and 64 validation calls run concurrently (bounded by
semaphores). Results are merged into exactly 64
:class:`~app.schemas.KYCRow` instances ready to be returned to the frontend.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.config import get_settings
from app.questions import KYC_QUESTIONS, KYCQuestion, group_by_section
from app.schemas import KYCRow, SourceLink, ValidationSource
from app.services.answer_section import AnsweredQuestion, answer_section
from app.services.documents import parse_documents
from app.services.kyc_intelligence import build_pipeline_intelligence
from app.services.kyc_row_signals import annotate_pipeline_rows
from app.services.reference_urls import ingest_reference_urls
from app.services.sec_filings_hub import format_issuer_edgar_search_hint, resolve_sec_filings_hub
from app.services.source_urls import (
    prioritize_and_cap_answer_sources,
    sanitize_answer_sources_urls,
)
from app.services.rag.index import index_submission_documents, rag_indexing_available
from app.services.mlflow_tracing import pipeline_run
from app.services.validate_section import ValidationResult, validate_question

logger = logging.getLogger(__name__)

ProgressPayload = dict[str, Any]


class PipelineCancelled(Exception):
    """Raised when ``cancel_event`` is set between major pipeline phases."""


@dataclass
class RunPipelineOutcome:
    rows: list[KYCRow]
    section_errors: list[dict[str, Any]] = field(default_factory=list)
    intelligence: dict[str, Any] | None = None


async def _emit(
    on_progress: Callable[[ProgressPayload], Awaitable[None] | None] | None,
    payload: ProgressPayload,
) -> None:
    if on_progress is None:
        return
    try:
        res = on_progress(payload)
        if asyncio.iscoroutine(res):
            await res
    except Exception:  # pragma: no cover
        logger.warning("on_progress failed", exc_info=True)


def _error_stub_answers(questions: list[KYCQuestion], err_id: str, phase: str) -> list[AnsweredQuestion]:
    msg = (
        f"[Automated {phase} failed for this section — support ref {err_id}. "
        "Retry the run or provide supporting documents.]"
    )
    return [AnsweredQuestion(q.serial_no, msg, []) for q in questions]


def _empty_validation(question: KYCQuestion) -> ValidationResult:
    return ValidationResult(question.serial_no, "", [])


def _empty_validations(questions: list[KYCQuestion]) -> list[ValidationResult]:
    return [_empty_validation(q) for q in questions]


async def run_pipeline(
    company: str,
    uploads: list[tuple[str, bytes, str]],
    reference_urls: list[str] | None = None,
    *,
    submission_id: UUID | None = None,
    on_progress: Callable[[ProgressPayload], Awaitable[None] | None] | None = None,
    cancel_event: asyncio.Event | None = None,
) -> RunPipelineOutcome:
    """Run the full KYC pipeline and return rows plus per-section error metadata."""

    settings = get_settings()
    with pipeline_run(
        company=company,
        submission_id=submission_id,
        settings=settings,
    ):
        return await _run_pipeline_body(
            company,
            uploads,
            reference_urls,
            settings=settings,
            submission_id=submission_id,
            on_progress=on_progress,
            cancel_event=cancel_event,
        )


async def _run_pipeline_body(
    company: str,
    uploads: list[tuple[str, bytes, str]],
    reference_urls: list[str] | None = None,
    *,
    settings: Any,
    submission_id: UUID | None = None,
    on_progress: Callable[[ProgressPayload], Awaitable[None] | None] | None = None,
    cancel_event: asyncio.Event | None = None,
) -> RunPipelineOutcome:
    sections = group_by_section()
    section_errors: list[dict[str, Any]] = []

    await _emit(
        on_progress,
        {"phase": "prep", "status": "started", "detail": "Parsing documents and reference URLs"},
    )

    ref_urls = reference_urls or []
    upload_docs, url_docs, sec_hub = await asyncio.gather(
        parse_documents(uploads),
        ingest_reference_urls(ref_urls, settings),
        resolve_sec_filings_hub(company, settings),
    )
    issuer_sec_hint = format_issuer_edgar_search_hint(sec_hub)
    parsed_docs = [*upload_docs, *url_docs]
    logger.info(
        "Parsed %d uploaded document(s) and %d reference URL document(s)",
        len(upload_docs),
        len(url_docs),
    )

    rag_chunk_count = 0
    if submission_id is not None and rag_indexing_available(settings):
        await _emit(
            on_progress,
            {
                "phase": "prep",
                "status": "indexing",
                "detail": "Indexing documents for validation retrieval",
            },
        )
        try:
            rag_chunk_count = await index_submission_documents(
                submission_id,
                company,
                parsed_docs,
                settings=settings,
            )
        except Exception:
            logger.exception(
                "RAG indexing failed for submission=%s; validation will fall back",
                submission_id,
            )
        logger.info(
            "RAG index submission=%s chunks=%d",
            submission_id,
            rag_chunk_count,
        )

    await _emit(
        on_progress,
        {
            "phase": "prep",
            "status": "complete",
            "detail": (
                f"Loaded {len(upload_docs)} file(s), {len(url_docs)} URL doc(s)"
                + (
                    f"; indexed {rag_chunk_count} chunk(s) for retrieval"
                    if rag_chunk_count
                    else ""
                )
            ),
        },
    )

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

    async def _bounded_answer(section_no: int, section_name: str, questions: list[KYCQuestion]) -> list[AnsweredQuestion]:
        async with answer_sem:
            result = await answer_section(
                company,
                section_no,
                section_name,
                questions,
                issuer_sec_hint=issuer_sec_hint,
            )
            if inter_call_delay > 0:
                await asyncio.sleep(inter_call_delay)
            return result

    n_sec = len(sections)
    n_questions = len(KYC_QUESTIONS)
    answer_lock = asyncio.Lock()
    answer_done = 0

    async def tracked_answer(
        idx: int,
        section_no: int,
        section_name: str,
        questions: list[KYCQuestion],
    ) -> list[AnsweredQuestion]:
        nonlocal answer_done
        if cancel_event and cancel_event.is_set():
            raise PipelineCancelled()
        try:
            result = await _bounded_answer(section_no, section_name, questions)
        except Exception as exc:
            err_id = uuid.uuid4().hex[:12]
            logger.exception("Answer section %s failed: %s", section_no, exc)
            section_errors.append(
                {
                    "sectionNo": section_no,
                    "phase": "answer",
                    "message": f"{type(exc).__name__}: {exc}",
                    "errorId": err_id,
                }
            )
            result = _error_stub_answers(questions, err_id, "web research")
        async with answer_lock:
            answer_done += 1
            done = answer_done
        await _emit(
            on_progress,
            {
                "phase": "answer",
                "status": "section_complete",
                "completedSections": done,
                "totalSections": n_sec,
                "sectionNo": section_no,
                "sectionName": section_name,
                "detail": f"Answer phase {done}/{n_sec}: {section_name}",
            },
        )
        return result

    answer_tasks = [
        tracked_answer(idx, section_no, section_name, questions)
        for idx, (section_no, section_name, questions) in enumerate(sections)
    ]
    answers_per_section: list[list[AnsweredQuestion]] | list[Any] = await asyncio.gather(
        *answer_tasks,
        return_exceptions=True,
    )

    # If any task raised non-Exception list (e.g. PipelineCancelled), handle
    normalized_answers: list[list[AnsweredQuestion]] = []
    for idx, res in enumerate(answers_per_section):
        if isinstance(res, PipelineCancelled):
            section_no, section_name, questions = sections[idx]
            err_id = uuid.uuid4().hex[:12]
            section_errors.append(
                {
                    "sectionNo": section_no,
                    "phase": "answer",
                    "message": "Cancelled",
                    "errorId": err_id,
                }
            )
            normalized_answers.append(_error_stub_answers(questions, err_id, "web research"))
        elif isinstance(res, BaseException):
            section_no, section_name, questions = sections[idx]
            err_id = uuid.uuid4().hex[:12]
            logger.exception("Unexpected answer task failure section=%s", section_no)
            section_errors.append(
                {
                    "sectionNo": section_no,
                    "phase": "answer",
                    "message": f"{type(res).__name__}: {res}",
                    "errorId": err_id,
                }
            )
            normalized_answers.append(_error_stub_answers(questions, err_id, "web research"))
        else:
            normalized_answers.append(res)

    answers_per_section = normalized_answers

    answers_by_serial: dict[int, AnsweredQuestion] = {}
    for section_answers in answers_per_section:
        for item in section_answers:
            answers_by_serial[item.serial_no] = item

    await sanitize_answer_sources_urls(answers_per_section, settings)
    prioritize_and_cap_answer_sources(
        answers_per_section,
        settings,
        verification_hub_sources=sec_hub.hub_sources if sec_hub else None,
    )

    if cancel_event and cancel_event.is_set():
        await _emit(
            on_progress,
            {"phase": "cancelled", "status": "stopping", "detail": "Skipped validation (cancelled)"},
        )
        validation_results = [_empty_validation(q) for q in KYC_QUESTIONS]
    else:
        await _emit(
            on_progress,
            {
                "phase": "validate",
                "status": "started",
                "detail": f"Running document validation ({n_questions} questions)",
            },
        )

        async def _bounded_validate_question(question: KYCQuestion) -> ValidationResult:
            async with validation_sem:
                answer = answers_by_serial.get(question.serial_no)
                if answer is None:
                    return _empty_validation(question)
                return await validate_question(
                    company,
                    question,
                    answer,
                    parsed_docs,
                    submission_id=submission_id,
                )

        val_done_lock = asyncio.Lock()
        val_done = 0

        async def tracked_validate_question(
            _vidx: int,
            question: KYCQuestion,
        ) -> ValidationResult:
            nonlocal val_done
            if cancel_event and cancel_event.is_set():
                raise PipelineCancelled()
            try:
                result = await _bounded_validate_question(question)
            except Exception as exc:
                err_id = uuid.uuid4().hex[:12]
                logger.exception(
                    "Validation question serial=%s failed: %s",
                    question.serial_no,
                    exc,
                )
                section_errors.append(
                    {
                        "sectionNo": question.section_no,
                        "serialNo": question.serial_no,
                        "phase": "validate",
                        "message": f"{type(exc).__name__}: {exc}",
                        "errorId": err_id,
                    }
                )
                result = _empty_validation(question)
            async with val_done_lock:
                val_done += 1
                done = val_done
            await _emit(
                on_progress,
                {
                    "phase": "validate",
                    "status": "question_complete",
                    "completedQuestions": done,
                    "totalQuestions": n_questions,
                    "serialNo": question.serial_no,
                    "sectionNo": question.section_no,
                    "sectionName": question.section_name,
                    "detail": (
                        f"Validation phase {done}/{n_questions}: "
                        f"Q{question.serial_no} ({question.section_name})"
                    ),
                },
            )
            return result

        validation_tasks = [
            tracked_validate_question(idx, question)
            for idx, question in enumerate(KYC_QUESTIONS)
        ]
        raw_vals = await asyncio.gather(*validation_tasks, return_exceptions=True)

        validation_results = []
        for idx, res in enumerate(raw_vals):
            question = KYC_QUESTIONS[idx]
            if isinstance(res, PipelineCancelled):
                validation_results.append(_empty_validation(question))
            elif isinstance(res, BaseException):
                err_id = uuid.uuid4().hex[:12]
                logger.exception(
                    "Unexpected validation task failure serial=%s",
                    question.serial_no,
                )
                section_errors.append(
                    {
                        "sectionNo": question.section_no,
                        "serialNo": question.serial_no,
                        "phase": "validate",
                        "message": f"{type(res).__name__}: {res}",
                        "errorId": err_id,
                    }
                )
                validation_results.append(_empty_validation(question))
            else:
                validation_results.append(res)

    validations_by_serial = {item.serial_no: item for item in validation_results}

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

    intelligence: dict[str, Any] | None = None
    try:
        rows = annotate_pipeline_rows(rows)
        intelligence = await build_pipeline_intelligence(company, rows, parsed_docs)
    except Exception:  # noqa: BLE001 - never fail the pipeline on addons
        logger.exception("pipeline intelligence / row signals skipped")

    logger.info(
        "Pipeline finished for company=%r: %d questionnaire rows, %d section error(s)",
        company,
        len(rows),
        len(section_errors),
    )
    return RunPipelineOutcome(
        rows=rows,
        section_errors=section_errors,
        intelligence=intelligence,
    )
