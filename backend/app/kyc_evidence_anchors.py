"""Per-question evidence theme and tier anchors for KYC source prioritization.

Maps each questionnaire serial number to (1) a high-level evidence theme aligned
with bank KYB practice and (2) the minimum acceptable evidence tier before an
analyst should treat the fact as verified without escalation — tier 1 is
strongest (government / legally mandated), tier 4 is self-declared / applicant
accountability only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class EvidenceTier(IntEnum):
    """Ordinal strength: lower value = stronger independent verification."""

    PRIMARY_LEGAL = 1
    CERTIFIED_PRIVATE = 2
    COMMERCIAL_AGGREGATOR = 3
    SELF_DECLARED = 4


class EvidenceTheme(StrEnum):
    CORPORATE_IDENTITY = "corporate_identity"
    OWNERSHIP_CONTROL = "ownership_control"
    OPERATIONS_BUSINESS = "operations_business"
    FINANCIALS_SOURCE_OF_FUNDS = "financials_source_of_funds"
    RISK_COMPLIANCE = "risk_compliance"
    EDD = "edd"
    DECLARATIONS_INTENT = "declarations_intent"


@dataclass(frozen=True)
class QuestionEvidenceAnchor:
    theme: EvidenceTheme
    minimum_acceptable_tier: EvidenceTier


def _a(theme: EvidenceTheme, tier: EvidenceTier) -> QuestionEvidenceAnchor:
    return QuestionEvidenceAnchor(theme=theme, minimum_acceptable_tier=tier)


# Keys must cover every serial_no in KYC_QUESTIONS (1..64).
QUESTION_EVIDENCE_ANCHORS: dict[int, QuestionEvidenceAnchor] = {
    # Section 1 — Legal identity (government registry / filings first).
    1: _a(EvidenceTheme.CORPORATE_IDENTITY, EvidenceTier.PRIMARY_LEGAL),
    2: _a(EvidenceTheme.CORPORATE_IDENTITY, EvidenceTier.PRIMARY_LEGAL),
    3: _a(EvidenceTheme.CORPORATE_IDENTITY, EvidenceTier.PRIMARY_LEGAL),
    4: _a(EvidenceTheme.CORPORATE_IDENTITY, EvidenceTier.PRIMARY_LEGAL),
    5: _a(EvidenceTheme.CORPORATE_IDENTITY, EvidenceTier.PRIMARY_LEGAL),
    6: _a(EvidenceTheme.CORPORATE_IDENTITY, EvidenceTier.PRIMARY_LEGAL),
    7: _a(EvidenceTheme.CORPORATE_IDENTITY, EvidenceTier.PRIMARY_LEGAL),
    8: _a(EvidenceTheme.CORPORATE_IDENTITY, EvidenceTier.PRIMARY_LEGAL),
    9: _a(EvidenceTheme.CORPORATE_IDENTITY, EvidenceTier.PRIMARY_LEGAL),
    # Section 2 — UBO / control (registers where public; otherwise certified KYB pack).
    10: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    11: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    12: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    13: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    14: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    15: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    16: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    17: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    18: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    19: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    20: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    21: _a(EvidenceTheme.OWNERSHIP_CONTROL, EvidenceTier.CERTIFIED_PRIVATE),
    # Section 3 — Business activity (ops narrative); revenue/net worth need financial proof.
    22: _a(EvidenceTheme.OPERATIONS_BUSINESS, EvidenceTier.COMMERCIAL_AGGREGATOR),
    23: _a(EvidenceTheme.OPERATIONS_BUSINESS, EvidenceTier.COMMERCIAL_AGGREGATOR),
    24: _a(EvidenceTheme.OPERATIONS_BUSINESS, EvidenceTier.COMMERCIAL_AGGREGATOR),
    25: _a(EvidenceTheme.OPERATIONS_BUSINESS, EvidenceTier.COMMERCIAL_AGGREGATOR),
    26: _a(EvidenceTheme.OPERATIONS_BUSINESS, EvidenceTier.COMMERCIAL_AGGREGATOR),
    27: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    28: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    29: _a(EvidenceTheme.RISK_COMPLIANCE, EvidenceTier.PRIMARY_LEGAL),
    30: _a(EvidenceTheme.RISK_COMPLIANCE, EvidenceTier.PRIMARY_LEGAL),
    31: _a(EvidenceTheme.OPERATIONS_BUSINESS, EvidenceTier.PRIMARY_LEGAL),
    # Section 4 — Financial & banking.
    32: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    33: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    34: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    35: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    36: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    37: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    38: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    39: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    # Section 5 — Risk & compliance (sanctions / regulators primary).
    40: _a(EvidenceTheme.RISK_COMPLIANCE, EvidenceTier.PRIMARY_LEGAL),
    41: _a(EvidenceTheme.RISK_COMPLIANCE, EvidenceTier.PRIMARY_LEGAL),
    42: _a(EvidenceTheme.RISK_COMPLIANCE, EvidenceTier.COMMERCIAL_AGGREGATOR),
    43: _a(EvidenceTheme.RISK_COMPLIANCE, EvidenceTier.CERTIFIED_PRIVATE),
    44: _a(EvidenceTheme.RISK_COMPLIANCE, EvidenceTier.PRIMARY_LEGAL),
    45: _a(EvidenceTheme.RISK_COMPLIANCE, EvidenceTier.COMMERCIAL_AGGREGATOR),
    46: _a(EvidenceTheme.RISK_COMPLIANCE, EvidenceTier.CERTIFIED_PRIVATE),
    47: _a(EvidenceTheme.RISK_COMPLIANCE, EvidenceTier.CERTIFIED_PRIVATE),
    # Section 6 — Source of funds / wealth (certified / audited).
    48: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    49: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    50: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    51: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    52: _a(EvidenceTheme.FINANCIALS_SOURCE_OF_FUNDS, EvidenceTier.CERTIFIED_PRIVATE),
    # Section 7 — EDD (typically curated applicant / FI documentation).
    53: _a(EvidenceTheme.EDD, EvidenceTier.CERTIFIED_PRIVATE),
    54: _a(EvidenceTheme.EDD, EvidenceTier.CERTIFIED_PRIVATE),
    55: _a(EvidenceTheme.EDD, EvidenceTier.CERTIFIED_PRIVATE),
    56: _a(EvidenceTheme.EDD, EvidenceTier.CERTIFIED_PRIVATE),
    57: _a(EvidenceTheme.EDD, EvidenceTier.CERTIFIED_PRIVATE),
    58: _a(EvidenceTheme.EDD, EvidenceTier.CERTIFIED_PRIVATE),
    59: _a(EvidenceTheme.EDD, EvidenceTier.CERTIFIED_PRIVATE),
    # Section 8 — Declarations / consent (self-declared accountability).
    60: _a(EvidenceTheme.DECLARATIONS_INTENT, EvidenceTier.SELF_DECLARED),
    61: _a(EvidenceTheme.DECLARATIONS_INTENT, EvidenceTier.SELF_DECLARED),
    62: _a(EvidenceTheme.DECLARATIONS_INTENT, EvidenceTier.SELF_DECLARED),
    63: _a(EvidenceTheme.DECLARATIONS_INTENT, EvidenceTier.SELF_DECLARED),
    64: _a(EvidenceTheme.DECLARATIONS_INTENT, EvidenceTier.SELF_DECLARED),
}


SECTION_SOURCE_HIERARCHY: dict[int, str] = {
    1: (
        "Section source priority — Legal identity & corporate status:\n"
        "- Tier 1: Official government company registers and statutory filings "
        "(SEC EDGAR for U.S. issuers, Companies House, state Secretary of State, "
        "ACRA, national commercial registers).\n"
        "- Tier 2: Certificate of incorporation, constitutional documents, "
        "tax/VAT portal confirmations (when not fully public).\n"
        "- Tier 3: Reputable commercial aggregators only as cross-check — never "
        "sole proof for registration numbers, dates, legal form, or registered "
        "address.\n"
        "- Tier 4: Company marketing site — consistency check only.\n"
        "Prefer registry/filing URLs over news or Wikipedia."
    ),
    2: (
        "Section source priority — Ownership & beneficial ownership:\n"
        "- Tier 1: Statutory beneficial ownership registers where published; "
        "for listed issuers use definitive proxy (DEF 14A) and 10-K beneficial "
        "ownership / corporate governance disclosures.\n"
        "- Tier 2: Share register excerpts, articles, shareholder agreements, "
        "certified KYB packs (required for ID numbers, DOB, residential address).\n"
        "- Tier 3: Aggregators / databases — corroboration only.\n"
        "- Do not infer UBOs from marketing pages or generic bios alone; use "
        "\"Not found\" when natural-person facts are not on public record."
    ),
    3: (
        "Section source priority — Business activities & operations:\n"
        "- Tier 1: Operating licences and regulator-authored approvals.\n"
        "- Tier 2: Contracts / PO samples when uploaded or cited from primary "
        "counterparties.\n"
        "- Tier 3–4: Corporate website, investor materials, industry profiles — "
        "use for narrative consistency; for revenue/net worth treat audited "
        "financials or certified statements as minimum acceptable (flag if "
        "only third-party estimates).\n"
        "- High-risk activity / jurisdiction questions: cite official sanctions "
        "lists and regulator sources before media."
    ),
    4: (
        "Section source priority — Financial profile & banking:\n"
        "- Tier 1: Audited financial statements filed with regulators or "
        "exchanges where available.\n"
        "- Tier 2: Certified bank statements, management accounts, loan "
        "agreements, facility letters.\n"
        "- Tier 3: Ratings / data vendors — supplementary.\n"
        "Many items here cannot be satisfied from web search alone — prefer "
        "\"Not found\" when applicant-held documents are required."
    ),
    5: (
        "Section source priority — Risk, sanctions & compliance:\n"
        "- Tier 1: Official sanctions lists (OFAC, UN, EU, HMT), regulator "
        "enforcement portals and published orders.\n"
        "- Tier 2: Audited compliance programme descriptions, policies supplied "
        "by applicant.\n"
        "- Tier 3: Adverse media from reputable outlets — label as screening "
        "lead, not definitive legal fact.\n"
        "Do not assert sanctions hits without Tier 1-style list or filing proof."
    ),
    6: (
        "Section source priority — Source of funds / wealth:\n"
        "- Tier 1–2: Audited accounts, certified bank statements, tax returns, "
        "signed investment or loan agreements.\n"
        "- Tier 3–4: Narrative explanations without documentary proof — "
        "insufficient alone; use \"Not found\" where documents must come from "
        "the applicant."
    ),
    7: (
        "Section source priority — Enhanced due diligence:\n"
        "- Expect Tier 2 applicant-provided evidence (references, "
        "detailed narratives, site-visit reports, institution correspondence).\n"
        "- Use Tier 1 public sources to corroborate facts already asserted.\n"
        "Web search alone rarely suffices — prefer \"Not found\" when material "
        "is clearly applicant-held."
    ),
    8: (
        "Section source priority — Declarations & consents:\n"
        "- Tier 4: Signed declarations and contractual undertakings from the "
        "applicant — not discoverable via open web search.\n"
        "Use the prescribed \"Not relevant\" / notice patterns where "
        "appropriate; do not fabricate consent."
    ),
}


def anchor_for_serial(serial_no: int) -> QuestionEvidenceAnchor | None:
    return QUESTION_EVIDENCE_ANCHORS.get(serial_no)


def section_hierarchy_instructions(section_no: int) -> str:
    return SECTION_SOURCE_HIERARCHY.get(section_no, "")


def validate_anchor_coverage(expected_serials: set[int]) -> None:
    """Assert anchors exist for every questionnaire serial (development helper)."""
    missing = expected_serials - set(QUESTION_EVIDENCE_ANCHORS.keys())
    extra = set(QUESTION_EVIDENCE_ANCHORS.keys()) - expected_serials
    if missing or extra:
        msg = []
        if missing:
            msg.append(f"missing serials: {sorted(missing)}")
        if extra:
            msg.append(f"extra serials: {sorted(extra)}")
        raise ValueError("; ".join(msg))
