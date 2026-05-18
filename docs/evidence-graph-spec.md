# Evidence graph and audit bundle — technical specification

This document defines the **claim/evidence model**, **relationship types**, **precedence rules**, and the **audit bundle** attached to each pipeline run. It aligns with the production direction: regulator-defensible, replayable decisions rather than opaque LLM output.

Implementation hooks in this repository:

- Row-level answers and citations are [`KYCRow`](backend/app/schemas.py) objects produced by [`run_pipeline`](backend/app/services/pipeline.py).
- Per-question evidence strength hints live in [`kyc_evidence_anchors`](backend/app/kyc_evidence_anchors.py) (`EvidenceTheme`, `EvidenceTier`).
- A machine-readable **claims snapshot** and **audit bundle** are assembled in [`build_pipeline_intelligence`](backend/app/services/kyc_intelligence.py) via [`claims_snapshot`](backend/app/services/claims_snapshot.py) and [`audit_bundle`](backend/app/services/audit_bundle.py).

---

## 1. Goals

1. **Provenance**: Every surfaced KYC field must trace to **evidence artifacts** (document bytes, URL retrieval, registry record, filing id) with **versioned pipeline** metadata.
2. **Replay**: Given the same **evidence artifact set** + **policy version**, recomputing structured claims and policy violations must be **deterministic** (LLM-assisted synthesis is optional and labeled).
3. **Contradiction handling**: Conflicting evidence is represented explicitly; resolution follows **typed precedence** (§4), not prompt prose.
4. **Audit**: External review receives an **audit bundle** (§6) that is compact, hash-stable where possible, and free of raw secrets.

---

## 2. Core concepts

### 2.1 Claim

A **claim** is a candidate fact the system asserts about the subject entity for a given **question serial** (1–64) or derived slot (e.g. normalized UBO record).

| Field | Description |
|--------|-------------|
| `claim_id` | Stable id: e.g. `Q{serial}::v1` or derived `UBO::{normalized_name}::pct` |
| `serial_no` | Question serial when applicable |
| `statement` | Normalized string or structured value (JSON) |
| `status` | `proposed` \| `supported` \| `disputed` \| `rejected` \| `human_overridden` |
| `extraction` | `deterministic` \| `llm_mapped` \| `human` |

### 2.2 Evidence node

An **evidence node** is an addressable artifact:

| Kind | Examples | Typical identifiers |
|------|----------|---------------------|
| `document` | Uploaded PDF, image | `sha256`, `filename`, `page`, `byte_range` |
| `url_snapshot` | Fetched reference URL | `url`, `fetched_at`, `content_sha256`, `http_status` |
| `registry_record` | Companies House / EDGAR | Registry id, entity number, accession number |
| `model_trace` | LLM call | `model_id`, `prompt_hash`, `response_hash` (no raw prompt in audit bundle by default) |

### 2.3 Edges (claim ↔ evidence)

| Edge | Meaning |
|------|---------|
| `supports` | Evidence increases confidence in the claim |
| `contradicts` | Evidence conflicts with the claim or another evidence node |
| `supersedes` | Newer or higher-precedence evidence replaces an older interpretation |
| `derived_from` | Claim produced by rule/ETL from other claims or raw extraction |

Edge weights (optional): `confidence_0_1`, `source_trust_tier` (align with `EvidenceTier` in code).

---

## 3. Graph operations (logical API)

These are **spec-level** operations; persistence format may be SQL, RDF, or columnar JSON.

1. **IngestArtifacts** — Register documents and URL snapshots with hashes and timestamps.
2. **ExtractDeterministic** — OCR, tables, registry/filing parsers → structured tuples (no LLM).
3. **MapWithLLM** — Optional: map ambiguous text to schema under **strict JSON schema**; output is **`llm_mapped`** claims only.
4. **MergeClaims** — Apply canonicalization (addresses, names, percentages) and dedupe.
5. **ResolveConflicts** — Apply precedence (§4); optional escalate to `disputed`.
6. **EnforcePolicies** — Run playbook + **typed policy compiler** over structured claims (see `kyc_policy_typed.yaml` and `policy_compiler.py`).
7. **EmitAuditBundle** — Serialize bundle (§6) + claims snapshot for the submission.

---

## 4. Precedence rules (time-aware)

When two claims or evidence nodes conflict:

1. **Legal mandate wins**: Statutory filing / government registry (`EvidenceTier.PRIMARY_LEGAL`) overrides commercial aggregators and marketing pages.
2. **Recency**: For the **same tier**, newer **effective_date** (incorporation amendment, new 10-K) supersedes older, unless marked `superseded_by` explicitly.
3. **Applicant-held for sensitive natural-person facts**: Certified / applicant-supplied evidence may be **required** even if public web contradicts (treat web as non-authoritative for DOB, ID, home address).
4. **Self-declared**: Declarations (Section 8) are **`EvidenceTier.SELF_DECLARED`** — they do not disprove registry facts; they create **obligations** not **historical truth**.

Implementations should log the **rule id** applied at merge time for replay.

---

## 5. Claims snapshot (API to policy engine)

The **claims snapshot** is a JSON-safe view of row state used by [`evaluate_typed_policy`](backend/app/services/policy_compiler.py):

- Per-serial: whether answered, truncated answer preview, source URLs and hostnames, validation status, counts.
- Versioned with `"version": 1` for forward compatibility.

This is intentionally **not** the full graph in v1; it is the **bridge** between current `KYCRow[]` and stricter graph storage later.

---

## 6. Audit bundle (per submission)

The audit bundle is attached under `intelligence.auditBundle` in API responses. Fields (v1):

| Field | Purpose |
|-------|---------|
| `version` | Format version |
| `generatedAt` | UTC ISO timestamp |
| `subjectCompany` | Normalized subject string |
| `pipeline` | `geminiAnswerModel`, `geminiValidationModel`, key flags (`validationAttachDocuments`, etc.) |
| `documents` | Per-upload: `filename`, `kind`, `sha256Prefix` (first 16 hex chars), `textChars`, `pages` |
| `rowCount` | Number of questionnaire rows |
| `claimsSnapshotDigest` | SHA-256 hex of canonical JSON claims snapshot (for integrity) |

Future versions may add: `policyPackVersion`, `evidenceGraphDigest`, `urlSnapshotIndex`.

---

## 7. Privacy and retention

- Bundles should default to **hashes** and **truncated** text, not full prompts or PII payloads.
- Raw documents remain in controlled storage (e.g. S3 object keys); the bundle references **fingerprints** only.

---

## 8. Compliance note

This specification describes **system design** for engineering and audit. It is not legal advice. Patent strategy should be pursued with qualified IP counsel; see [patent-engagement-checklist.md](patent-engagement-checklist.md).
