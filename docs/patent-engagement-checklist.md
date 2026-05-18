# Patent counsel engagement checklist (internal)

Use this when moving from **product architecture** to **formal IP strategy**. This is not legal advice.

## 1. Materials to assemble for counsel

- **System architecture**: evidence graph spec ([evidence-graph-spec.md](evidence-graph-spec.md)), deterministic grounding inventory ([deterministic-grounding-inventory.md](deterministic-grounding-inventory.md)).
- **Differentiating algorithms**: policy compiler over structured claims (`backend/app/services/policy_compiler.py`), merge/precedence design as implemented or specified.
- **Benchmarks / evaluation**: regression harness ([backend/benchmarks/README.md](../backend/benchmarks/README.md)) proving technical effect (e.g. false-positive reduction, citation quality).
- **Prior art you already know**: internal literature search, closest competitor products, academic papers cited in design docs.
- **Invention disclosure**: 1–2 page narrative of the **technical problem** (e.g., inconsistent multi-source KYB under policy rules) and **concrete steps** your system uses to solve it on a computer.

## 2. Claim strategy (discussion topics with counsel)

- Prefer **narrow independent claims** tied to: multi-source fusion with **time-aware precedence**, **typed policy compilation** over a claims graph, or **deterministic + LLM-mapped** separation with audit bundles.
- Avoid **abstract ideas** framing (“doing KYC with AI”); anchor in **specific improvements**: audit replay, reduced contradiction rate, enforceable policy constraints.
- Consider **provisionals** only after at least one **reduced-to-practice** embodiment is frozen (code version + benchmark).

## 3. Freedom-to-operate (FTO)

- Commission FTO or landscape search in **your jurisdictions** before public launch or fund-raise if competitors hold broad identity-verification patents.

## 4. Trade secret vs patent

- **Patent**: publicly disclosed in exchange for exclusivity.
- **Trade secret**: proprietary datasets, prompt chains, customer-specific policy packs, fraud corpora — protect with contracts and access control; do not publish.

## 5. Engineering follow-ups before filing

- [ ] Tag a git release candidate associated with the disclosed embodiment.
- [ ] Capture benchmark numbers before/after core algorithms.
- [ ] Document inventors and contribution dates (lab notebooks / commits).

## 6. Next step

Schedule a call with **qualified patent counsel** and bring this checklist plus the architecture PDFs/export of the `docs/` and `backend/app/services/` modules discussed above.
