"""Pydantic models exchanged with the frontend.

Field names use camelCase to match the existing TypeScript types on the
React side (see ``src/data/kycQuestions.ts``).
"""

from __future__ import annotations

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
    rows: list[KYCRow]
