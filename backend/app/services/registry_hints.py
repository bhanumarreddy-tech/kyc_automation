"""Heuristic registry / filing shortcuts for analysts."""

from __future__ import annotations

import re
import urllib.parse
from typing import Any

_NAME_SLICE = re.compile(r"NASDAQ|NYSE|\([A-Za-z]+\)")


def hints_for_company(company_name: str) -> list[dict[str, Any]]:
    stripped = company_name.strip()
    if not stripped:
        return []

    head = stripped.split(",")[0].strip()
    head = _NAME_SLICE.sub("", head).strip() or stripped
    esc = urllib.parse.quote(head)

    hints: list[dict[str, Any]] = [
        {
            "label": "SEC EDGAR (name search)",
            "url": f"https://www.sec.gov/edgar/search/#/q={esc}",
        }
    ]

    up = stripped.upper()
    if any(x in up for x in ("LIMITED", "PLC", "LLP", "L.L.P.", "LIMITED COMPANY")):
        hints.append(
            {
                "label": "Companies House (UK heuristic)",
                "url": (
                    "https://find-and-update.company-information.service.gov.uk/search?q=" + esc
                ),
            }
        )

    return hints[:6]
