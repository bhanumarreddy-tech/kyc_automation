"""YAML-driven playbook violations for reviewer triage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.schemas import KYCRow

_loaded: dict[str, Any] | None = None


def load_playbook() -> dict[str, Any]:
    global _loaded
    if _loaded is not None:
        return _loaded
    path = Path(__file__).resolve().parent.parent.parent / "config" / "kyc_playbook.yaml"
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            _loaded = yaml.safe_load(f) or {}
    else:
        _loaded = {}
    return _loaded


def _answered(row: KYCRow) -> bool:
    a = row.answer.strip().lower()
    return bool(a and a != "not found")


def evaluate_playbook(rows: list[KYCRow]) -> list[dict[str, Any]]:
    data = load_playbook()
    rules = data.get("rules") if isinstance(data, dict) else None
    if not isinstance(rules, list):
        return []

    violations: list[dict[str, Any]] = []
    by_serial = {r.serial_no: r for r in rows}

    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rid = str(rule.get("id", ""))
        serials_raw = rule.get("match_serial_numbers") or []
        try:
            serials = [int(x) for x in serials_raw]
        except (TypeError, ValueError):
            continue
        msg = str(rule.get("message", rid))

        for sn in serials:
            row = by_serial.get(sn)
            if row is None:
                continue
            if not _answered(row):
                continue

            neg = rule.get("when_answer_not_contains")
            if isinstance(neg, str) and neg and neg.lower() in row.answer.lower():
                continue

            min_src = rule.get("min_sources_when_answered")
            if isinstance(min_src, int) and min_src > 0 and len(row.sources) < min_src:
                violations.append(
                    {"ruleId": rid, "serialNo": sn, "message": msg, "severity": "policy"}
                )
                continue

            if rule.get("require_min_sources_when_non_empty_answer"):
                ms = int(rule.get("min_sources", 1))
                if len(row.sources) < ms:
                    violations.append(
                        {"ruleId": rid, "serialNo": sn, "message": msg, "severity": "policy"}
                    )

    return violations
