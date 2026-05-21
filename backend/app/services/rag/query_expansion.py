"""Multi-query expansion for hybrid retrieval (query variants fused via RRF)."""

from __future__ import annotations

import re


def expand_retrieval_queries(
    query: str,
    *,
    question_text: str | None = None,
    enabled: bool = True,
) -> list[str]:
    """Return deduplicated query variants for multi-query hybrid search."""
    base = query.strip()
    if not base or not enabled:
        return [base] if base else []

    variants: list[str] = [base]

    if question_text:
        q_only = question_text.strip()
        if q_only and q_only.lower() not in base.lower():
            variants.append(q_only)

    # Keyword-focused variant: entities, numbers, acronyms (helps lexical + dense).
    tokens = re.findall(r"[A-Z]{2,}(?:[0-9]+)?|\b\d{4,}\b|[A-Za-z]{4,}", base)
    if tokens:
        keyword_query = " ".join(dict.fromkeys(tokens))[:500]
        if keyword_query and keyword_query.lower() not in base.lower():
            variants.append(keyword_query)

    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        key = v.lower()
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out
