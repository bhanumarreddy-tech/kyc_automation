"""Assemble sandbox screening, playbook checks, registry hints, and optional LLM extracts."""

from __future__ import annotations

import logging
from typing import Any

from app.schemas import KYCRow
from app.services.documents import ParsedDocument, text_preview
from app.services.playbook_eval import evaluate_playbook
from app.services.registry_hints import hints_for_company
from app.services.screening_stub import evaluate_screening
from app.services.structured_extract import maybe_structured_entity_extract

logger = logging.getLogger(__name__)


def _merge_risk_tier(screening: dict[str, Any], violation_n: int) -> str:
    base = str(screening.get("riskTierSuggested") or "T2_STANDARD")
    if violation_n >= 8 and base == "T2_STANDARD":
        return "T1_EXPANDED_REVIEW"
    if violation_n >= 15:
        return "T1_EXPANDED_REVIEW"
    return base


async def build_pipeline_intelligence(
    company: str,
    rows: list[KYCRow],
    parsed_docs: list[ParsedDocument],
) -> dict[str, Any]:
    screening = evaluate_screening(company)
    violations = evaluate_playbook(rows)
    hints = hints_for_company(company)
    blob_parts: list[str] = []
    for d in parsed_docs:
        blob_parts.append(text_preview(d, max_chars=7000))
    doc_blob = "\n\n".join(blob_parts)
    struct: str | None
    try:
        struct = await maybe_structured_entity_extract(company, doc_blob)
    except Exception as exc:  # pragma: no cover
        logger.warning("structured extract failed: %s", exc)
        struct = None

    tier = _merge_risk_tier(screening, len(violations))
    return {
        "screening": screening,
        "playbookViolations": violations,
        "registryHints": hints,
        "structuredExtractSummary": struct,
        "riskTierSuggested": tier,
    }
