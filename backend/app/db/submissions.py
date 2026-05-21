"""Persistence helpers for KYC submissions."""

from __future__ import annotations

import secrets
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KYCIntakeToken, KYCSubmission, KYCSubmissionMetadata
from app.schemas import AttachedDocument, KYCRow


async def ensure_submission_stub(
    session: AsyncSession,
    *,
    submission_id: UUID,
    company_name: str,
) -> KYCSubmission:
    """Insert a placeholder row so RAG chunks can reference ``submission_id`` before the pipeline finishes."""
    existing = await get_kyc_submission(session, submission_id)
    if existing is not None:
        return existing
    record = KYCSubmission(
        id=submission_id,
        company_name=company_name,
        rows=[],
        document_filenames=None,
        reference_urls=None,
        duration_ms=None,
        pipeline_intelligence=None,
        rag_trace=None,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def create_kyc_submission(
    session: AsyncSession,
    *,
    submission_id: UUID,
    company_name: str,
    rows: list[KYCRow],
    attached_documents: list[AttachedDocument],
    duration_ms: int,
    reference_urls: list[str] | None = None,
    pipeline_intelligence: dict | None = None,
    rag_trace: dict | None = None,
) -> KYCSubmission:
    payload = [r.model_dump(mode="json", by_alias=True) for r in rows]
    doc_meta = (
        [d.model_dump(mode="json", by_alias=True) for d in attached_documents]
        if attached_documents
        else None
    )
    ref_meta = reference_urls if reference_urls else None
    existing = await get_kyc_submission(session, submission_id)
    if existing is not None:
        existing.company_name = company_name
        existing.rows = payload
        existing.document_filenames = doc_meta
        existing.reference_urls = ref_meta
        existing.duration_ms = duration_ms
        existing.pipeline_intelligence = pipeline_intelligence
        existing.rag_trace = rag_trace
        await session.flush()
        await session.refresh(existing)
        return existing
    record = KYCSubmission(
        id=submission_id,
        company_name=company_name,
        rows=payload,
        document_filenames=doc_meta,
        reference_urls=ref_meta,
        duration_ms=duration_ms,
        pipeline_intelligence=pipeline_intelligence,
        rag_trace=rag_trace,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def list_kyc_submissions(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
) -> list[KYCSubmission]:
    stmt = (
        select(KYCSubmission)
        .order_by(KYCSubmission.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.scalars(stmt)
    return list(result.all())


async def get_kyc_submission(
    session: AsyncSession,
    submission_id: UUID,
) -> KYCSubmission | None:
    stmt = select(KYCSubmission).where(KYCSubmission.id == submission_id)
    return await session.scalar(stmt)


async def get_submission_metadata_row(
    session: AsyncSession,
    submission_id: UUID,
) -> KYCSubmissionMetadata | None:
    stmt = select(KYCSubmissionMetadata).where(KYCSubmissionMetadata.submission_id == submission_id)
    return await session.scalar(stmt)


async def upsert_submission_metadata(
    session: AsyncSession,
    submission_id: UUID,
    *,
    sign_off: bool | None = None,
    analyst_notes: str | None = None,
    escalated_serials: list[int] | None = None,
    workflow_state: dict[str, object] | None = None,
) -> KYCSubmissionMetadata:
    row = await get_submission_metadata_row(session, submission_id)
    if row is None:
        row = KYCSubmissionMetadata(
            submission_id=submission_id,
            sign_off=False,
            analyst_notes="",
            audit_log=[],
            escalated_serials=[],
            workflow_state={},
        )
        session.add(row)
        await session.flush()
    if sign_off is not None:
        row.sign_off = sign_off
    if analyst_notes is not None:
        row.analyst_notes = analyst_notes
    if escalated_serials is not None:
        row.escalated_serials = escalated_serials
    if workflow_state is not None:
        merged = dict(row.workflow_state or {})
        merged.update(workflow_state)
        row.workflow_state = merged
    return row


async def similar_company_matches(
    session: AsyncSession,
    company_name: str,
    *,
    exclude_submission_id: UUID | None = None,
    pool_limit: int = 350,
    result_limit: int = 15,
    min_similarity: float = 0.42,
) -> list[dict[str, object]]:
    """Lightweight fuzzy match over recent submissions (no dedicated search index yet)."""

    stmt = (
        select(KYCSubmission.id, KYCSubmission.company_name)
        .order_by(KYCSubmission.created_at.desc())
        .limit(pool_limit)
    )
    result = await session.execute(stmt)
    pairs = result.all()

    needle = company_name.strip().lower()
    if not needle:
        return []

    scored: list[tuple[float, UUID, str]] = []
    for sid, cname in pairs:
        if exclude_submission_id is not None and sid == exclude_submission_id:
            continue
        label = (cname or "").strip()
        if not label:
            continue
        low = label.lower()
        ratio = SequenceMatcher(None, needle, low).ratio()
        if ratio >= min_similarity or needle in low or low in needle:
            scored.append((ratio, sid, label))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: list[dict[str, object]] = []
    for ratio, sid, label in scored[:result_limit]:
        out.append(
            {
                "submissionId": str(sid),
                "companyName": label,
                "similarity": round(ratio, 3),
            }
        )
    return out


async def mint_intake_token(session: AsyncSession, label: str = "") -> str:
    raw = secrets.token_urlsafe(32)
    tok = raw[:96]
    row = KYCIntakeToken(token=tok, label=(label or "")[:512])
    session.add(row)
    await session.flush()
    return tok


async def get_intake_token(session: AsyncSession, token: str) -> KYCIntakeToken | None:
    if not token.strip():
        return None
    stmt = select(KYCIntakeToken).where(KYCIntakeToken.token == token.strip())
    return await session.scalar(stmt)


async def append_metadata_audit(
    session: AsyncSession,
    submission_id: UUID,
    entry: dict,
) -> KYCSubmissionMetadata:
    row = await upsert_submission_metadata(session, submission_id)
    log = list(row.audit_log or [])
    log.append(entry)
    row.audit_log = log
    return row
