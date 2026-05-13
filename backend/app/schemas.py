"""Pydantic models exchanged with the frontend.

Field names use camelCase to match the existing TypeScript types on the
React side (see ``src/data/kycQuestions.ts``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SourceLink(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = ""
    url: str = ""


class ValidationSource(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document: str = ""
    excerpt: str | None = None
    page: int | None = None
    url: str | None = None


ValidationStatus = Literal["Yes", "No", ""]
KycAgentReconStatus = Literal["Yes", "No", "NA", ""]


class KYCRow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    section_no: int = Field(alias="sectionNo")
    section_name: str = Field(alias="sectionName")
    serial_no: int = Field(alias="serialNo")
    question: str
    answer: str = ""
    sources: list[SourceLink] = Field(default_factory=list)
    validation: ValidationStatus = ""
    validation_sources: list[ValidationSource] = Field(
        default_factory=list, alias="validationSources"
    )
    analyst_comments: str = Field(default="", alias="analystComments")
    kyc_agent_recon: KycAgentReconStatus = Field(
        default="",
        alias="KYC_Agent_Recon",
    )


class AttachedDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    filename: str
    size_bytes: int | None = Field(default=None, alias="sizeBytes")
    content_type: str = Field(default="", alias="contentType")
    object_key: str | None = Field(default=None, alias="objectKey")


class RerunProcessRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    submission_id: str = Field(alias="submissionId", min_length=1)


class ProcessResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rows: list[KYCRow]
    submission_id: str | None = Field(default=None, alias="submissionId")
    saved_at: datetime | None = Field(default=None, alias="savedAt")
    duration_ms: int | None = Field(default=None, alias="durationMs")
    attached_documents: list[AttachedDocument] = Field(
        default_factory=list,
        alias="attachedDocuments",
    )
    reference_urls: list[str] = Field(default_factory=list, alias="referenceUrls")


def history_metrics_from_rows_json(rows: list) -> tuple[int, int]:
    """Completion % answered; needs_review = AI validation is not ``Yes`` (pending, ``No``, or empty)."""

    def _answered(row: dict) -> bool:
        a = str(row.get("answer", "") or "").strip().lower()
        return bool(a and a != "not found")

    def _needs_review(row: dict) -> bool:
        v = str(row.get("validation", "") or "").strip()
        return v != "Yes"

    total = len(rows)
    if total == 0:
        return 0, 0
    answered_n = sum(1 for item in rows if isinstance(item, dict) and _answered(item))
    review_n = sum(1 for item in rows if isinstance(item, dict) and _needs_review(item))
    completion = round(100 * answered_n / total)
    return completion, review_n


def attached_documents_from_stored(raw: list | None) -> list[AttachedDocument]:
    """Accept legacy JSONB values: list[str] or list[object]."""
    if not raw:
        return []
    out: list[AttachedDocument] = []
    for item in raw:
        if isinstance(item, str):
            out.append(AttachedDocument(filename=item))
        elif isinstance(item, dict):
            out.append(AttachedDocument.model_validate(item))
    return out


class HistoryListItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    submission_id: str = Field(alias="submissionId")
    company_name: str = Field(alias="companyName")
    created_at: datetime = Field(alias="createdAt")
    document_count: int = Field(default=0, alias="documentCount")
    attached_documents: list[AttachedDocument] = Field(
        default_factory=list,
        alias="attachedDocuments",
    )
    duration_ms: int | None = Field(default=None, alias="durationMs")
    completion_percent: int = Field(default=0, alias="completionPercent")
    needs_review_count: int = Field(default=0, alias="needsReviewCount")
    reference_url_count: int = Field(default=0, alias="referenceUrlCount")


class HistoryDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    submission_id: str = Field(alias="submissionId")
    company_name: str = Field(alias="companyName")
    created_at: datetime = Field(alias="createdAt")
    attached_documents: list[AttachedDocument] = Field(
        default_factory=list,
        alias="attachedDocuments",
    )
    duration_ms: int | None = Field(default=None, alias="durationMs")
    reference_urls: list[str] = Field(default_factory=list, alias="referenceUrls")
    rows: list[KYCRow]
