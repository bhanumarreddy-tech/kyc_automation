"""Persistence helpers for KYC submissions."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KYCSubmission
from app.schemas import AttachedDocument, KYCRow


async def create_kyc_submission(
    session: AsyncSession,
    *,
    submission_id: UUID,
    company_name: str,
    rows: list[KYCRow],
    attached_documents: list[AttachedDocument],
    duration_ms: int,
) -> KYCSubmission:
    payload = [r.model_dump(mode="json", by_alias=True) for r in rows]
    doc_meta = (
        [d.model_dump(mode="json", by_alias=True) for d in attached_documents]
        if attached_documents
        else None
    )
    record = KYCSubmission(
        id=submission_id,
        company_name=company_name,
        rows=payload,
        document_filenames=doc_meta,
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
