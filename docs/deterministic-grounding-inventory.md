# Deterministic grounding inventory — 64-question roadmap

This inventory classifies each questionnaire serial by how strongly answers can be grounded in **deterministic** sources (registries, filings, structured extracts) versus **LLM synthesis** or **self-declared** applicant intent. It complements [`kyc_evidence_anchors.py`](../backend/app/kyc_evidence_anchors.py) (`EvidenceTheme`, `EvidenceTier`).

**Legend — `grounding_class`:**

| Class | Meaning |
|-------|---------|
| `registry_primary` | Core legal identity fields: prioritize commercial registers, tax portals, statutory filings |
| `filings_primary` | SEC EDGAR / exchange filings, annual reports, proxies for listings, officers, ownership |
| `licence_regulator` | Operating licences, regulator registers |
| `aggregator_ok` | Public narrative acceptable with Tier-3 corroboration; escalate if sole source for risky facts |
| `certified_private` | Typically **applicant-held** certified docs (UBO IDs, bank statements, cap table) |
| `sanctions_regulator` | Official sanctions / enforcement sources |
| `EDD_pack` | Enhanced diligence: applicant evidence + corroboration |
| `self_declared` | Declarations / consent — not web-discoverable “truth” |

**Determinism roadmap (`extraction_roadmap`):**

| Phase | Capability |
|-------|------------|
| **A — now** | PDF/DOCX text extract, URL ingest, SEC hub hints, playbook + typed policy |
| **B** | Filing parsers (DEF 14A, 10-K beneficial ownership tables), LEI/GLEIF lookup |
| **C** | Registry connectors (Companies House API, OpenCorporates/OFF equivalent per jurisdiction) |
| **D** | Beneficial ownership registers where published; graph construction (ownership paths) |
| **E** | Sanctions / PEP list automated screening with audit trail (replace stubs) |

---

## Section 1 — Legal Identity

| Serial | Topic (short) | grounding_class | extraction_roadmap |
|--------|---------------|-----------------|---------------------|
| 1 | Registration number | registry_primary | A→C |
| 2 | Incorporation date | registry_primary | A→C |
| 3 | Registered address | registry_primary | A→C |
| 4 | Other addresses | registry_primary | A→C (secondary addresses often filing/supplementary) |
| 5 | TIN / VAT | registry_primary | A→C (jurisdiction-dependent) |
| 6 | Group structure | filings_primary | B→D |
| 7 | Legal entity type | registry_primary | A→C |
| 8 | Trade names / DBA | registry_primary | A→C |
| 9 | Listed? exchange/ticker | filings_primary | B (CIK/ticker resolution, exchange filings) |

## Section 2 — Ownership & UBO

| Serial | Topic (short) | grounding_class | extraction_roadmap |
|--------|---------------|-----------------|---------------------|
| 10 | UBO narrative | certified_private | D (public reg) + B (proxies) where listed |
| 11–16 | UBO per-person fields | certified_private | D / applicant IDs — **not** open-web alone |
| 17–18 | Directors / signatories | filings_primary | B |
| 19 | Complex structure / trusts | certified_private | D (graph) |
| 20 | PEP shareholders | sanctions_regulator | E |
| 21 | Recent ownership change | filings_primary | B→D |

## Section 3 — Business activities

| Serial | Topic (short) | grounding_class | extraction_roadmap |
|--------|---------------|-----------------|---------------------|
| 22–26 | Nature, products, geographies, customers, suppliers | aggregator_ok | A (site + news) + licence corroboration for regulated activities |
| 27–28 | Revenue / net worth | certified_private | B (audited) / applicant financials |
| 29–30 | High-risk activity / jurisdiction | sanctions_regulator | E + official lists |
| 31 | Licences / approvals | licence_regulator | A→C |

## Section 4 — Financial & banking

| Serial | Topic (short) | grounding_class | extraction_roadmap |
|--------|---------------|-----------------|---------------------|
| 32–37 | Transaction profile, banking, debt | certified_private | A (filings partial) + applicant |
| 38 | Financial statements | filings_primary | B |
| 39 | Funding structures | certified_private | B |

## Section 5 — Risk & compliance

| Serial | Topic (short) | grounding_class | extraction_roadmap |
|--------|---------------|-----------------|---------------------|
| 40 | Legal/regulatory actions | sanctions_regulator | E + court/regulator portals |
| 41 | Sanctions lists | sanctions_regulator | E |
| 42 | Adverse media | aggregator_ok | E (commercial AM) |
| 43 | AML programme | certified_private | A (policy docs) |
| 44 | Sanctioned-country dealing | sanctions_regulator | E |
| 45 | High-risk industries | aggregator_ok | E |
| 46 | Virtual assets | licence_regulator | C |
| 47 | Prior KYB / documentation | certified_private | applicant |

## Section 6 — Source of funds

| Serial | Topic (short) | grounding_class | extraction_roadmap |
|--------|---------------|-----------------|---------------------|
| 48–52 | SoF / SoW / third-party | certified_private | A→B (audit trail on docs) |

## Section 7 — EDD

| Serial | Topic (short) | grounding_class | extraction_roadmap |
|--------|---------------|-----------------|---------------------|
| 53–59 | EDD narratives & evidence | EDD_pack | A→E |

## Section 8 — Declarations

| Serial | Topic (short) | grounding_class | extraction_roadmap |
|--------|---------------|-----------------|---------------------|
| 60–64 | Consents / signed declaration | self_declared | applicant signature capture |

---

## How to use this with engineering backlogs

1. **Deterministic extractors first** for `registry_primary` and `filings_primary` serials — reduces LLM variance and improves audit.
2. **Policy gates** (YAML playbook + typed policy) enforce **minimum evidence** where automation is known to hallucinate (e.g. listing without filing host).
3. **Benchmarks** (see `backend/benchmarks/`) track regression per section when models or parsers change.
