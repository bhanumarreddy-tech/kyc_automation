# Analyst SOP: evidence tiers, citations, and EDD triggers

This document aligns manual review with the automation defaults in this repository: per-section source hierarchy is injected into the answer model (`backend/app/kyc_evidence_anchors.py`, `backend/app/services/answer_section.py`), and clickable sources are ordered SEC-hub-first, then configured government/regulator domains (`answer_sources_domain_priority_suffixes` in `backend/app/config.py`).

## Tier definitions (quick reference)

| Tier | Meaning | Examples |
|------|---------|----------|
| **1 — Primary / legal** | Government or legally mandated filings | Company registers, SEC EDGAR, official sanctions lists, regulator licensing portals |
| **2 — Certified private** | Applicant or professional-certified documents | Certificate of incorporation, audited financials, certified bank statements, KYB packs |
| **3 — Commercial aggregators** | Useful cross-check; lag / coverage gaps | Credit bureaus, data vendors, reputable press for adverse media *leads* |
| **4 — Self-declared** | Legally important accountability; weak verification alone | Signed questionnaires, consent clauses, management representations |

Stronger tiers have lower numbers. Each questionnaire row has an anchor in `QUESTION_EVIDENCE_ANCHORS`: **minimum_acceptable_tier** is the weakest tier that may clear the fact without escalation when no stronger evidence exists—if you only have weaker tiers, document the gap and trigger follow-up or EDD.

## Citation order (Sources column)

1. Prefer URLs that match **Tier 1** hosts (automation boosts SEC hub overlap first, then suffixes such as `.gov.uk`, `sec.gov`, EU institutional hosts—see config).
2. List **highest-tier evidence first** in analyst notes when narrating file provenance.
3. Never treat Tier 3 or Tier 4 as sufficient for **sanctions hits**, **registration identifiers**, or **UBO identity attributes** unless policy explicitly allows and risk is accepted.

## “Not found” vs “Not relevant”

These literals are contractually important for the LLM output (`backend/app/services/answer_section.py`).

| Sentinel | When to use |
|----------|-------------|
| **Not relevant** | The question does not apply to the subject (e.g. natural-person sub-questions when no UBO is in scope). |
| **Not found** | The fact could exist in registry or applicant materials but was **not** located in public search / uploads—**collect Tier 2 documents**. |

Declarations and forward-looking consents are generally **not public**; Section 8 uses applicant attestation, not web proof.

## When to open EDD (Section 7 workflow)

Open or extend EDD when **any** of the following apply:

- **Ownership**: Complex structures (trusts, nominees) without register extract or certified chart; PEP indicators without list screening artefacts.
- **Financials**: Revenue, net worth, or source-of-funds stated with **only** Tier 3/4 support.
- **Risk**: Material adverse media without primary regulatory or court source; high-risk geography or sector without licence evidence.
- **Mismatch**: Answer grounded on public sources conflicts with uploaded KYB pack or another Tier 1 source.
- **Residual tier gap**: For that serial’s `minimum_acceptable_tier`, you cannot reach evidence at or stronger than that tier.

Document in analyst comments: **what Tier 1/Tier 2 artefact** would remediate each gap.

## Using `QUESTION_EVIDENCE_ANCHORS`

For programmatic checks or QA scripts, import `QUESTION_EVIDENCE_ANCHORS` and `EvidenceTier` from `app.kyc_evidence_anchors`. Each serial maps to:

- **theme** — corporate identity, ownership, operations, financials, risk, EDD, or declarations.
- **minimum_acceptable_tier** — weakest tier still acceptable without escalation under normal policy.

Adjust anchors only with compliance sign-off; they encode policy defaults, not universal law.
