"""Sandbox screening model for prototype KYC tooling.

Production systems should integrate a sanctioned screening vendor API;
this stub returns deterministic, explainable placeholders so UI and
workflows can be built end‑to‑end without credentials.
"""

from __future__ import annotations

import hashlib
from typing import Any


def evaluate_screening(company_name: str) -> dict[str, Any]:
    """Return PEP / sanctions‑style placeholders.

    Activate demo PEP hit by including ``sandbox:pep`` (case insensitive) in
    the client name field. Activate sanctions demo with ``sandbox:san``.
    """

    cn = company_name.strip()
    low = cn.lower()
    alerts: list[dict[str, Any]] = []

    if "sandbox:pep" in low:
        alerts.append(
            {
                "type": "PEP_WATCHLIST_PROXY",
                "severity": "high",
                "summary": "(Demo) Possible PEP-linked name heuristic — escalate per policy.",
            }
        )
    if "sandbox:san" in low:
        alerts.append(
            {
                "type": "SANCTIONS_PROXY",
                "severity": "critical",
                "summary": "(Demo) Simulated sanctions list keyword — block / escalate.",
            }
        )

    digest = hashlib.sha256(low.encode()).hexdigest()
    if not alerts and int(digest[:2], 16) < 6:  # ~2.3 % low-only informational
        alerts.append(
            {
                "type": "ADVERSE_MEDIA_PROXY",
                "severity": "low",
                "summary": "(Demo informational) Routine media scan artifact — informational only.",
            }
        )

    if any(a.get("severity") == "critical" for a in alerts):
        tier = "T0_BLOCK"
        overall = "blocked"
    elif any(a.get("severity") == "high" for a in alerts):
        tier = "T1_EXPANDED_REVIEW"
        overall = "escalated"
    elif alerts:
        tier = "T2_STANDARD"
        overall = "alerted"
    else:
        tier = "T2_STANDARD"
        overall = "clear"

    return {
        "provider": "sandbox_stub_v1",
        "overall": overall,
        "riskTierSuggested": tier,
        "alerts": alerts,
        "rawScore": round(int(digest[:8], 16) / 0xFFFFFFFF, 4),
    }
