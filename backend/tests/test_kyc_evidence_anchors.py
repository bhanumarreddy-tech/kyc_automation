"""Coverage and consistency for QUESTION_EVIDENCE_ANCHORS."""

from __future__ import annotations

from app.kyc_evidence_anchors import (
    QUESTION_EVIDENCE_ANCHORS,
    EvidenceTheme,
    EvidenceTier,
    QuestionEvidenceAnchor,
    section_hierarchy_instructions,
    validate_anchor_coverage,
)
from app.questions import KYC_QUESTIONS


def test_every_question_has_anchor_and_section_hierarchy() -> None:
    serials = {q.serial_no for q in KYC_QUESTIONS}
    validate_anchor_coverage(serials)
    section_nos = {q.section_no for q in KYC_QUESTIONS}
    for sn in sorted(section_nos):
        assert section_hierarchy_instructions(sn).strip()


def test_declarations_use_self_declared_minimum_tier() -> None:
    for serial in range(60, 65):
        anchor = QUESTION_EVIDENCE_ANCHORS[serial]
        assert anchor.theme == EvidenceTheme.DECLARATIONS_INTENT
        assert anchor.minimum_acceptable_tier == EvidenceTier.SELF_DECLARED


def test_anchor_types() -> None:
    for serial, anchor in QUESTION_EVIDENCE_ANCHORS.items():
        assert isinstance(serial, int)
        assert isinstance(anchor, QuestionEvidenceAnchor)
