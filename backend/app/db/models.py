"""SQLAlchemy models for persisted KYC runs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import RAG_EMBEDDING_DIMENSIONS


class Base(DeclarativeBase):
    """Declarative base for application tables."""


class KYCSubmissionMetadata(Base):
    """Analyst workflow metadata persisted per submission (sign-off, notes, audit)."""

    __tablename__ = "kyc_submission_metadata"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kyc_submissions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    sign_off: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    analyst_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    audit_log: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    escalated_serials: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    workflow_state: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class KYCSubmission(Base):
    """One completed pipeline run: full questionnaire rows (answers + validation) as JSONB."""

    __tablename__ = "kyc_submissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    company_name: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    rows: Mapped[list] = mapped_column(JSONB, nullable=False)
    # Legacy: list[str]. Current: list[{"filename", "sizeBytes", "contentType"}].
    document_filenames: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # User-supplied reference URLs (http(s)), same order as submitted.
    reference_urls: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pipeline_intelligence: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    rag_trace: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class KYCDocumentChunk(Base):
    """Per-submission text chunks with embeddings for validation RAG."""

    __tablename__ = "kyc_document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kyc_submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[str] = mapped_column(String(2048), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    contextualized_content: Mapped[str] = mapped_column(Text, nullable=False)
    content_tsv = mapped_column(TSVECTOR, nullable=True)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(RAG_EMBEDDING_DIMENSIONS),
        nullable=False,
    )
    chunk_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
    )


class KYCIntakeToken(Base):
    """Opaque token letting a client reuse the public SPA for a gated intake URL."""

    __tablename__ = "kyc_intake_tokens"

    token: Mapped[str] = mapped_column(String(96), primary_key=True)
    label: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
