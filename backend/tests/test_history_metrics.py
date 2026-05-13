"""History list/detail metrics derivations."""

from __future__ import annotations

from app.schemas import history_metrics_from_rows_json


def test_completion_unchanged_review_counts_non_yes_validation() -> None:
    rows = [
        {"answer": "", "validation": ""},
        {"answer": "x", "validation": ""},
        {"answer": "x", "validation": "No"},
        {"answer": "x", "validation": "Yes"},
        {"answer": "not found", "validation": "Yes"},
    ]
    pct, review_n = history_metrics_from_rows_json(rows)
    assert pct == 60  # 3 of 5 answered (not blank, not "not found")
    assert review_n == 3  # validation empty/No; excludes two "Yes" rows

