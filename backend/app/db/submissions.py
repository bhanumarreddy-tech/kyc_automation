"""Persistence helpers for KYC submissions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KYCSubmission, KYCSubmissionMetadata
from app.schemas import AttachedDocument, KYCRow


async def create_kyc_submission(
    session: AsyncSession,
    *,
    submission_id: UUID,
    company_name: str,
    rows: list[KYCRow],
    attached_documents: list[AttachedDocument],
    duration_ms: int,
    reference_urls: list[str] | None = None,
) -> KYCSubmission:
    payload = [r.model_dump(mode="json", by_alias=True) for r in rows]
    doc_meta = (
        [d.model_dump(mode="json", by_alias=True) for d in attached_documents]
        if attached_documents
        else None
    )
    ref_meta = reference_urls if reference_urls else None
    record = KYCSubmission(
        id=submission_id,
        company_name=company_name,
        rows=payload,
        document_filenames=doc_meta,
        reference_urls=ref_meta,
        duration_ms=duration_ms,
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
) -> KYCSubmissionMetadata:
    row = await get_submission_metadata_row(session, submission_id)
    if row is None:
        row = KYCSubmissionMetadata(
            submission_id=submission_id,
            sign_off=False,
            analyst_notes="",
            audit_log=[],
            escalated_serials=[],
        )
        session.add(row)
        await session.flush()
    if sign_off is not None:
        row.sign_off = sign_off
    if analyst_notes is not None:
        row.analyst_notes = analyst_notes
    if escalated_serials is not None:
        row.escalated_serials = escalated_serials
    return row


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
