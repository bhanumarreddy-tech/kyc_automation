"""SQLAlchemy models for persisted KYC runs."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for application tables."""


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
    document_filenames: Mapped[list | None] = mapped_column(JSONB, nullable=True)
