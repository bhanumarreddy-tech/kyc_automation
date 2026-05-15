"""Per-row confidence and citation freshness heuristics (prototype)."""

from __future__ import annotations

import re
from datetime import datetime

from app.schemas import KYCRow

_YEAR_IN_URL = re.compile(r"(20\d{2})")


def _answered(row: KYCRow) -> bool:
    a = row.answer.strip().lower()
    return bool(a and a != "not found")


def _staleness_penalty_days(sources: list) -> tuple[int | None, str]:
    """Return (estimated age in days vs current year filings, rationale)."""

    years: list[int] = []
    for s in sources:
        u = getattr(s, "url", "") or ""
        for y in _YEAR_IN_URL.findall(u):
            try:
                years.append(int(y))
            except ValueError:
                continue
        t = getattr(s, "title", "") or ""
        for y in _YEAR_IN_URL.findall(t):
            try:
                years.append(int(y))
            except ValueError:
                continue

    if not years:
        return None, "no_year_in_urls"

    newest = max(years)
    cy = datetime.utcnow().year
    if newest >= cy - 1:
        return 0, f"recent_{newest}"
    gap = max(0, (cy - newest) * 365)
    return min(gap, 3650), f"oldest_ref_year_{newest}"


def row_confidence_0_100(row: KYCRow) -> int:
    """Higher = more trustworthy for operational triage (heuristic only)."""

    base = 50
    if _answered(row):
        base += 20
    if row.validation == "Yes":
        base += 22
    elif row.validation == "No":
        base -= 10
    if row.sources:
        base += min(15, len(row.sources) * 5)
    if row.validation_sources:
        base += 8

    staleness_days, tag = _staleness_penalty_days(row.sources)
    if staleness_days and staleness_days > 730:
        base -= min(35, staleness_days // 100)

    return max(0, min(100, base))


def annotate_pipeline_rows(rows: list[KYCRow]) -> list[KYCRow]:
    out: list[KYCRow] = []
    for r in rows:
        conf = row_confidence_0_100(r)
        stale_days, _ = _staleness_penalty_days(r.sources)
        out.append(
            r.model_copy(
                update={
                    "confidence_score": conf,
                    "staleness_days": stale_days,
                }
            )
        )
    return out
