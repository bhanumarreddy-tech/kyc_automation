"""HTTP route handlers for ``POST /api/process``."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime

from typing import Annotated, Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.config import get_settings
from app.db.session import db_session_maker
from app.db.submissions import (
    create_kyc_submission,
    get_intake_token,
    get_kyc_submission,
)
from app.schemas import (
    AttachedDocument,
    PipelineSectionError,
    ProcessResponse,
    attached_documents_from_stored,
)
from app.services.pipeline import run_pipeline
from app.services.pipeline_jobs import (
    apply_progress_payload,
    get_job,
    register_job,
    request_cancel,
)
from app.services.reference_urls import (
    normalize_reference_urls,
    validate_reference_urls_for_request,
)
from app.services.s3_storage import get_object_bytes, upload_submission_files

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["kyc"])


def _errors_from_raw(section_errors: list[dict[str, Any]]) -> list[PipelineSectionError]:
    return [
        PipelineSectionError(
            sectionNo=int(e["sectionNo"]),
            phase=str(e["phase"]),
            message=str(e["message"]),
            errorId=str(e["errorId"]),
        )
        for e in section_errors
    ]


async def _reject_invalid_intake_token(
    maker,
    intake_token: str | None,
) -> None:
    """When present, require Postgres and a matching row in ``kyc_intake_tokens``."""

    if intake_token is None or not str(intake_token).strip():
        return
    if maker is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Database is required to validate intake tokens. "
                "Configure Postgres / DATABASE_PASSWORD."
            ),
        )
    async with maker() as db_session:
        row = await get_intake_token(db_session, str(intake_token).strip())
    if row is None:
        raise HTTPException(status_code=400, detail="Invalid or unknown intake_token")


@router.post("/process", response_model=ProcessResponse, response_model_by_alias=True)
async def process_kyc(
    company_name: str = Form(..., min_length=1),
    files: list[UploadFile] | None = File(default=None),
    reference_urls: Annotated[list[str] | None, Form()] = None,
    intake_token: Annotated[str | None, Form()] = None,
) -> ProcessResponse:
    t0 = time.perf_counter()

    def _elapsed() -> float:
        return time.perf_counter() - t0

    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured on the server",
        )

    company = company_name.strip()
    logger.info(
        "process_kyc: start elapsed=%.3fs company_name_len=%d multipart fields parsed",
        _elapsed(),
        len(company_name),
    )

    if not company:
        raise HTTPException(status_code=400, detail="company_name is required")

    normalized_urls = normalize_reference_urls(reference_urls or [])
    ok_urls, url_err = validate_reference_urls_for_request(
        normalized_urls,
        max_count=settings.reference_url_max_per_request,
    )
    if url_err:
        raise HTTPException(status_code=400, detail=url_err)
    assert ok_urls is not None
    logger.info(
        "process_kyc: reference URLs validated elapsed=%.3fs count=%d",
        _elapsed(),
        len(ok_urls),
    )

    file_list = files or []
    logger.info(
        "process_kyc: reading %d uploaded file(s) into memory elapsed=%.3fs",
        len(file_list),
        _elapsed(),
    )
    uploads: list[tuple[str, bytes, str]] = []
    for idx, upload in enumerate(file_list, start=1):
        read_start = time.perf_counter()
        data = await upload.read()
        read_ms = (time.perf_counter() - read_start) * 1000
        name = upload.filename or "document"
        uploads.append((name, data, upload.content_type or ""))
        logger.info(
            "process_kyc: upload %d/%d read name=%r bytes=%d read_ms=%.0f elapsed=%.3fs",
            idx,
            len(file_list),
            name,
            len(data),
            read_ms,
            _elapsed(),
        )

    total_payload = sum(len(raw) for _, raw, _ in uploads)
    logger.info(
        "Processing KYC submission for '%s' with %d uploaded file(s), %d reference URL(s); "
        "total file payload ~%.2f MiB "
        "(frontend nginx allows 100 MiB for /api/; raise client_max_body_size if you need more)",
        company,
        len(uploads),
        len(ok_urls),
        total_payload / (1024 * 1024),
    )

    maker = db_session_maker()
    submission_id_uuid = uuid.uuid4()
    attached_documents: list[AttachedDocument] = []

    await _reject_invalid_intake_token(maker, intake_token)

    if uploads:
        if not settings.s3_ready():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Object storage is not configured. "
                    "Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, and "
                    "S3_SECRET_ACCESS_KEY (and optionally S3_REGION)."
                ),
            )
        if maker is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Database is required when uploading documents "
                    "(submissions authorize downloads against saved metadata). "
                    "Configure Postgres / DATABASE_PASSWORD as for History."
                ),
            )
        logger.info(
            "process_kyc: storing %d file(s) in object storage elapsed=%.3fs",
            len(uploads),
            _elapsed(),
        )
        attached_documents = await upload_submission_files(
            settings,
            submission_id_uuid,
            uploads,
        )
        logger.info("process_kyc: object storage upload done elapsed=%.3fs", _elapsed())

    logger.info("process_kyc: pipeline starting elapsed=%.3fs", _elapsed())
    pipeline_started = time.perf_counter()
    outcome = await run_pipeline(
        company,
        uploads,
        reference_urls=ok_urls,
        submission_id=submission_id_uuid if maker is not None else None,
    )
    duration_ms = int((time.perf_counter() - pipeline_started) * 1000)
    rows = outcome.rows
    pipe_err = _errors_from_raw(outcome.section_errors)
    logger.info(
        "process_kyc: pipeline finished duration_ms=%d elapsed=%.3fs",
        duration_ms,
        _elapsed(),
    )

    submission_id_out: str | None = None
    saved_at_out: datetime | None = None
    if maker is not None:
        logger.info("process_kyc: saving submission to database elapsed=%.3fs", _elapsed())
        async with maker() as db_session:
            record = await create_kyc_submission(
                db_session,
                submission_id=submission_id_uuid,
                company_name=company,
                rows=rows,
                attached_documents=attached_documents,
                duration_ms=duration_ms,
                reference_urls=ok_urls,
                pipeline_intelligence=outcome.intelligence,
            )
            await db_session.commit()
            submission_id_out = str(record.id)
            saved_at_out = record.created_at
        logger.info(
            "process_kyc: submission saved id=%s elapsed=%.3fs",
            submission_id_out,
            _elapsed(),
        )

    return ProcessResponse(
        rows=rows,
        submission_id=submission_id_out,
        saved_at=saved_at_out,
        duration_ms=duration_ms,
        attached_documents=attached_documents,
        reference_urls=list(ok_urls),
        pipeline_errors=pipe_err,
        intelligence=outcome.intelligence,
    )


def _dedupe_retain_object_keys(raw: list[str] | None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in raw or []:
        key = str(item).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return ordered


@router.post("/process/rerun", response_model=ProcessResponse, response_model_by_alias=True)
async def rerun_process_kyc(
    submission_id: str = Form(..., min_length=1),
    files: list[UploadFile] | None = File(default=None),
    reference_urls: Annotated[list[str] | None, Form()] = None,
    retain_object_keys: Annotated[list[str] | None, Form()] = None,
) -> ProcessResponse:
    """Run the pipeline again for a saved submission with edited URL list and attachments."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured on the server",
        )

    try:
        prior_id = uuid.UUID(submission_id.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(
            status_code=503,
            detail="Database is not configured",
        )

    async with maker() as db_session:
        record = await get_kyc_submission(db_session, prior_id)

    if record is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    company = (record.company_name or "").strip()
    if not company:
        raise HTTPException(
            status_code=400,
            detail="Stored submission has no company name",
        )

    normalized_urls = normalize_reference_urls(reference_urls or [])
    ok_urls, url_err = validate_reference_urls_for_request(
        normalized_urls,
        max_count=settings.reference_url_max_per_request,
    )
    if url_err:
        raise HTTPException(status_code=400, detail=url_err)
    assert ok_urls is not None

    docs = attached_documents_from_stored(record.document_filenames)
    doc_by_key: dict[str, AttachedDocument] = {}
    for d in docs:
        if d.object_key:
            doc_by_key[d.object_key] = d

    retain_keys = _dedupe_retain_object_keys(retain_object_keys)
    for key in retain_keys:
        if key not in doc_by_key:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid retain_object_keys: key does not belong to this submission "
                    f"({key!r})"
                ),
            )

    uploads: list[tuple[str, bytes, str]] = []

    if retain_keys:
        if not settings.s3_ready():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Object storage is not configured. "
                    "Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, and "
                    "S3_SECRET_ACCESS_KEY (and optionally S3_REGION)."
                ),
            )
        for key in retain_keys:
            d = doc_by_key[key]
            try:
                data = await get_object_bytes(settings, key)
            except FileNotFoundError:
                raise HTTPException(
                    status_code=404,
                    detail=f"Attachment is no longer in storage: {d.filename}",
                ) from None
            uploads.append((d.filename, data, d.content_type or ""))

    file_list = files or []
    for idx, upload in enumerate(file_list, start=1):
        data = await upload.read()
        name = upload.filename or "document"
        uploads.append((name, data, upload.content_type or ""))
        logger.info(
            "rerun_process_kyc: new upload %d/%d name=%r bytes=%d",
            idx,
            len(file_list),
            name,
            len(data),
        )

    submission_id_uuid = uuid.uuid4()
    attached_documents: list[AttachedDocument] = []

    if uploads:
        if not settings.s3_ready():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Object storage is not configured. "
                    "Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, and "
                    "S3_SECRET_ACCESS_KEY (and optionally S3_REGION)."
                ),
            )
        attached_documents = await upload_submission_files(
            settings,
            submission_id_uuid,
            uploads,
        )

    pipeline_started = time.perf_counter()
    outcome = await run_pipeline(
        company,
        uploads,
        reference_urls=ok_urls,
        submission_id=submission_id_uuid if maker is not None else None,
    )
    duration_ms = int((time.perf_counter() - pipeline_started) * 1000)
    rows = outcome.rows
    pipe_err = _errors_from_raw(outcome.section_errors)

    submission_id_out: str | None = None
    saved_at_out: datetime | None = None
    async with maker() as db_session:
        rec = await create_kyc_submission(
            db_session,
            submission_id=submission_id_uuid,
            company_name=company,
            rows=rows,
            attached_documents=attached_documents,
            duration_ms=duration_ms,
            reference_urls=ok_urls,
            pipeline_intelligence=outcome.intelligence,
        )
        await db_session.commit()
        submission_id_out = str(rec.id)
        saved_at_out = rec.created_at

    return ProcessResponse(
        rows=rows,
        submission_id=submission_id_out,
        saved_at=saved_at_out,
        duration_ms=duration_ms,
        attached_documents=attached_documents,
        reference_urls=list(ok_urls),
        pipeline_errors=pipe_err,
        intelligence=outcome.intelligence,
    )


@router.post("/process/async")
async def process_kyc_async(
    company_name: str = Form(..., min_length=1),
    files: list[UploadFile] | None = File(default=None),
    reference_urls: Annotated[list[str] | None, Form()] = None,
    intake_token: Annotated[str | None, Form()] = None,
) -> dict[str, str]:
    """Start processing in the background; poll ``GET /api/process/jobs/{jobId}``."""
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured on the server",
        )

    company = company_name.strip()
    if not company:
        raise HTTPException(status_code=400, detail="company_name is required")

    normalized_urls = normalize_reference_urls(reference_urls or [])
    ok_urls, url_err = validate_reference_urls_for_request(
        normalized_urls,
        max_count=settings.reference_url_max_per_request,
    )
    if url_err:
        raise HTTPException(status_code=400, detail=url_err)
    assert ok_urls is not None

    maker = db_session_maker()
    await _reject_invalid_intake_token(maker, intake_token)

    file_list = files or []
    uploads: list[tuple[str, bytes, str]] = []
    for upload in file_list:
        data = await upload.read()
        name = upload.filename or "document"
        uploads.append((name, data, upload.content_type or ""))

    submission_id_uuid = uuid.uuid4()
    attached_documents: list[AttachedDocument] = []

    if uploads:
        if not settings.s3_ready():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Object storage is not configured. "
                    "Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, and "
                    "S3_SECRET_ACCESS_KEY (and optionally S3_REGION)."
                ),
            )
        if maker is None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Database is required when uploading documents "
                    "(submissions authorize downloads against saved metadata). "
                    "Configure Postgres / DATABASE_PASSWORD as for History."
                ),
            )
        attached_documents = await upload_submission_files(
            settings,
            submission_id_uuid,
            uploads,
        )

    st = register_job()
    job_id = st.job_id

    async def work() -> None:
        st.status = "running"
        st.phase = "prep"
        st.detail = "Starting pipeline"
        t0 = time.perf_counter()

        async def on_progress(payload: dict[str, Any]) -> None:
            await apply_progress_payload(job_id, payload)

        try:
            outcome = await run_pipeline(
                company,
                uploads,
                reference_urls=ok_urls,
                submission_id=submission_id_uuid if maker is not None else None,
                on_progress=on_progress,
                cancel_event=st.cancel_event,
            )
            duration_ms = int((time.perf_counter() - t0) * 1000)
            rows = outcome.rows
            pipe_err = _errors_from_raw(outcome.section_errors)
            submission_id_out: str | None = None
            saved_at_out: datetime | None = None
            if maker is not None:
                async with maker() as db_session:
                    record = await create_kyc_submission(
                        db_session,
                        submission_id=submission_id_uuid,
                        company_name=company,
                        rows=rows,
                        attached_documents=attached_documents,
                        duration_ms=duration_ms,
                        reference_urls=ok_urls,
                        pipeline_intelligence=outcome.intelligence,
                    )
                    await db_session.commit()
                    submission_id_out = str(record.id)
                    saved_at_out = record.created_at
            resp = ProcessResponse(
                rows=rows,
                submission_id=submission_id_out,
                saved_at=saved_at_out,
                duration_ms=duration_ms,
                attached_documents=attached_documents,
                reference_urls=list(ok_urls),
                pipeline_errors=pipe_err,
                intelligence=outcome.intelligence,
            )
            st.result_payload = resp.model_dump(mode="json", by_alias=True)
            st.status = "completed"
            st.phase = "done"
            st.detail = "Complete"
        except Exception as exc:
            logger.exception("async process job %s failed", job_id)
            st.status = "failed"
            st.phase = "error"
            st.error_message = f"{type(exc).__name__}: {exc}"

    asyncio.create_task(work())
    return {"jobId": job_id}


@router.post("/process/rerun/async")
async def rerun_process_kyc_async(
    submission_id: str = Form(..., min_length=1),
    files: list[UploadFile] | None = File(default=None),
    reference_urls: Annotated[list[str] | None, Form()] = None,
    retain_object_keys: Annotated[list[str] | None, Form()] = None,
) -> dict[str, str]:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not configured on the server",
        )

    try:
        prior_id = uuid.UUID(submission_id.strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid submission id") from None

    maker = db_session_maker()
    if maker is None:
        raise HTTPException(status_code=503, detail="Database is not configured")

    async with maker() as db_session:
        record = await get_kyc_submission(db_session, prior_id)

    if record is None:
        raise HTTPException(status_code=404, detail="Submission not found")

    company = (record.company_name or "").strip()
    if not company:
        raise HTTPException(status_code=400, detail="Stored submission has no company name")

    normalized_urls = normalize_reference_urls(reference_urls or [])
    ok_urls, url_err = validate_reference_urls_for_request(
        normalized_urls,
        max_count=settings.reference_url_max_per_request,
    )
    if url_err:
        raise HTTPException(status_code=400, detail=url_err)
    assert ok_urls is not None

    docs = attached_documents_from_stored(record.document_filenames)
    doc_by_key: dict[str, AttachedDocument] = {}
    for d in docs:
        if d.object_key:
            doc_by_key[d.object_key] = d

    retain_keys = _dedupe_retain_object_keys(retain_object_keys)
    for key in retain_keys:
        if key not in doc_by_key:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid retain_object_keys: key does not belong to this submission "
                    f"({key!r})"
                ),
            )

    uploads: list[tuple[str, bytes, str]] = []

    if retain_keys:
        if not settings.s3_ready():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Object storage is not configured. "
                    "Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, and "
                    "S3_SECRET_ACCESS_KEY (and optionally S3_REGION)."
                ),
            )
        for key in retain_keys:
            d = doc_by_key[key]
            try:
                data = await get_object_bytes(settings, key)
            except FileNotFoundError:
                raise HTTPException(
                    status_code=404,
                    detail=f"Attachment is no longer in storage: {d.filename}",
                ) from None
            uploads.append((d.filename, data, d.content_type or ""))

    file_list = files or []
    for upload in file_list:
        data = await upload.read()
        name = upload.filename or "document"
        uploads.append((name, data, upload.content_type or ""))

    submission_id_uuid = uuid.uuid4()
    attached_documents: list[AttachedDocument] = []

    if uploads:
        if not settings.s3_ready():
            raise HTTPException(
                status_code=503,
                detail=(
                    "Object storage is not configured. "
                    "Set S3_ENDPOINT_URL, S3_BUCKET, S3_ACCESS_KEY_ID, and "
                    "S3_SECRET_ACCESS_KEY (and optionally S3_REGION)."
                ),
            )
        attached_documents = await upload_submission_files(
            settings,
            submission_id_uuid,
            uploads,
        )

    st = register_job()
    job_id = st.job_id

    async def work() -> None:
        st.status = "running"
        st.phase = "prep"
        st.detail = "Starting pipeline"
        t0 = time.perf_counter()

        async def on_progress(payload: dict[str, Any]) -> None:
            await apply_progress_payload(job_id, payload)

        try:
            outcome = await run_pipeline(
                company,
                uploads,
                reference_urls=ok_urls,
                submission_id=submission_id_uuid,
                on_progress=on_progress,
                cancel_event=st.cancel_event,
            )
            duration_ms = int((time.perf_counter() - t0) * 1000)
            rows = outcome.rows
            pipe_err = _errors_from_raw(outcome.section_errors)
            submission_id_out: str | None = None
            saved_at_out: datetime | None = None
            async with maker() as db_session:
                rec = await create_kyc_submission(
                    db_session,
                    submission_id=submission_id_uuid,
                    company_name=company,
                    rows=rows,
                    attached_documents=attached_documents,
                    duration_ms=duration_ms,
                    reference_urls=ok_urls,
                    pipeline_intelligence=outcome.intelligence,
                )
                await db_session.commit()
                submission_id_out = str(rec.id)
                saved_at_out = rec.created_at
            resp = ProcessResponse(
                rows=rows,
                submission_id=submission_id_out,
                saved_at=saved_at_out,
                duration_ms=duration_ms,
                attached_documents=attached_documents,
                reference_urls=list(ok_urls),
                pipeline_errors=pipe_err,
                intelligence=outcome.intelligence,
            )
            st.result_payload = resp.model_dump(mode="json", by_alias=True)
            st.status = "completed"
            st.phase = "done"
            st.detail = "Complete"
        except Exception as exc:
            logger.exception("async rerun job %s failed", job_id)
            st.status = "failed"
            st.phase = "error"
            st.error_message = f"{type(exc).__name__}: {exc}"

    asyncio.create_task(work())
    return {"jobId": job_id}


@router.get("/process/jobs/{job_id}")
async def get_process_job(job_id: str) -> dict[str, Any]:
    st = await get_job(job_id)
    if st is None:
        raise HTTPException(status_code=404, detail="Job not found")
    out: dict[str, Any] = {"job": st.snapshot()}
    if st.result_payload is not None:
        out["result"] = st.result_payload
    if st.error_message:
        out["error"] = st.error_message
    return out


@router.post("/process/jobs/{job_id}/cancel")
async def cancel_process_job(job_id: str) -> dict[str, bool]:
    ok = await request_cancel(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}
