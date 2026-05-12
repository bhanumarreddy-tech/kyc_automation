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


ValidationStatus = Literal["Yes", "No", ""]


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


class ProcessResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    rows: list[KYCRow]
    submission_id: str | None = Field(default=None, alias="submissionId")
    saved_at: datetime | None = Field(default=None, alias="savedAt")


class HistoryListItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    submission_id: str = Field(alias="submissionId")
    company_name: str = Field(alias="companyName")
    created_at: datetime = Field(alias="createdAt")
    document_count: int = Field(default=0, alias="documentCount")


class HistoryDetailResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    submission_id: str = Field(alias="submissionId")
    company_name: str = Field(alias="companyName")
    created_at: datetime = Field(alias="createdAt")
    document_filenames: list[str] = Field(
        default_factory=list,
        alias="documentFilenames",
    )
    rows: list[KYCRow]
