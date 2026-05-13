"""Resolve SEC EDGAR issuer identity and canonical filing URLs for search hints.

Uses ``company_tickers.json`` and ``data.sec.gov`` submissions so the pipeline can
tell the answer model **which CIK/browse page to steer search toward**.

Per-question ``sources`` stay limited to URLs the model actually retrieved for
that question (see answer phase + grounding merge); hub links are never copied
onto every row as synthetic citations.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import httpx

from app.config import Settings
from app.services.gemini_client import normalize_source_url_for_match
from app.services.reference_urls import reference_fetch_user_agent

logger = logging.getLogger(__name__)

SEC_TICKERS_JSON_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"

_TICKERS_CACHE: dict[str, Any] | None = None
_TICKERS_FETCHED_MONO: float = 0.0
_TICKERS_TTL_SECONDS = 86_400

_CORP_TAIL_RE = re.compile(
    r"""
    [,.\s]*(incorporated|corporation|\(inc\.?\)|\binc\b\.?|
    corp\.?|\bco\b\.?|,?\s+ltd\.?|,?\s+llc\.?|,?\s+plc\.?
    |\blp\b\.?|,?\s+limited)\b.*
    $
    """,
    re.X | re.I,
)


def _norm_company_key(name: str) -> str:
    s = name.strip().lower()
    s = s.replace("&", "and")
    s = _CORP_TAIL_RE.sub("", s)
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _match_score(query: str, issuer_title: str) -> float:
    q = _norm_company_key(query)
    t = _norm_company_key(issuer_title)
    if not q or not t:
        return 0.0
    if q == t:
        return 1.0
    if t.startswith(q) or q.startswith(t):
        return 0.93
    if q in t or t in q:
        return 0.88
    return SequenceMatcher(None, q, t).ratio()


def _pick_best_ticker_match(
    company: str, tickers_blob: dict[str, Any]
) -> tuple[str, str] | None:
    """Return ``(zero_padded_cik, issuer_title)`` or ``None`` if unsure."""
    best_cik = ""
    best_title = ""
    best_score = 0.0
    second_score = 0.0

    for _, row in tickers_blob.items():
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "").strip()
        raw_cik = row.get("cik_str")
        if isinstance(raw_cik, int):
            cik_digits = str(raw_cik)
        else:
            cik_digits = str(raw_cik or "").strip()
        if not title or not cik_digits.isdigit():
            continue
        sc = _match_score(company, title)
        if sc > best_score:
            second_score = best_score
            best_score = sc
            best_cik = cik_digits
            best_title = title
        elif sc > second_score:
            second_score = sc

    if best_score < 0.87:
        return None
    if second_score >= best_score - 0.03 and second_score >= 0.84:
        return None

    pad = f"{int(best_cik):010d}"
    return pad, best_title


async def _load_company_tickers(client: httpx.AsyncClient, settings: Settings) -> dict[str, Any]:
    global _TICKERS_CACHE, _TICKERS_FETCHED_MONO
    now = time.monotonic()
    if _TICKERS_CACHE is not None and (now - _TICKERS_FETCHED_MONO) < _TICKERS_TTL_SECONDS:
        return _TICKERS_CACHE

    ua = reference_fetch_user_agent(settings, SEC_TICKERS_JSON_URL)
    headers = {"User-Agent": ua, "Accept-Encoding": "gzip"}
    resp = await client.get(SEC_TICKERS_JSON_URL, headers=headers)
    resp.raise_for_status()
    data = json.loads(resp.text)
    _TICKERS_CACHE = data
    _TICKERS_FETCHED_MONO = now
    return data


def _archives_primary_url(cik_nopad: str, accession: str, primary_document: str) -> str:
    acc_flat = accession.replace("-", "")
    ciki = str(int(cik_nopad))
    doc = primary_document.strip()
    if doc:
        return f"https://www.sec.gov/Archives/edgar/data/{ciki}/{acc_flat}/{doc}"
    return (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK="
        f"{int(ciki):010d}&owner=exclude&count=40"
    )


def _recent_verification_filings(payload: dict[str, Any], cik_pad: str) -> list[dict[str, str]]:
    """First-seen newest rows for priority forms — ``recent`` lists are newest-first."""
    recent = (((payload.get("filings") or {}).get("recent")) or {}) if isinstance(payload, dict) else {}
    forms = recent.get("form") or []
    accs = recent.get("accessionNumber") or []
    dates = recent.get("filingDate") or []
    docs = recent.get("primaryDocument") or []
    target_roots = frozenset({"10-K", "10-Q", "20-F", "40-F", "8-K", "DEF 14A"})
    want = ["10-K", "10-Q", "20-F", "40-F", "DEF 14A", "8-K"]

    picked: dict[str, dict[str, str]] = {}
    cik_nopad = str(int(cik_pad))

    upper_forms = [str(f or "").strip().upper() for f in forms]
    limit = min(len(accs), len(upper_forms), len(dates), len(docs), 1200)

    for i in range(limit):
        form_raw = upper_forms[i]
        root = form_raw.split("/")[0].strip() if "/" in form_raw else form_raw
        if root not in target_roots:
            continue
        acc = str(accs[i]).strip()
        if not acc:
            continue
        dt = str(dates[i]).strip() if i < len(dates) else ""
        doc = str(docs[i]).strip() if i < len(docs) else ""
        key = root
        if key in picked:
            continue
        if not doc:
            continue
        url = _archives_primary_url(cik_nopad, acc, doc)
        title = f"SEC filing: {root} ({dt}) — primary doc"
        picked[key] = {"title": title, "url": url}

    out: list[dict[str, str]] = []
    for form_name in want:
        row = picked.get(form_name)
        if row:
            out.append(row)
        if len(out) >= 3:
            break
    return out


def _dedupe_merge_front(
    front: list[dict[str, str]], existing: list[dict[str, str]]
) -> list[dict[str, str]]:
    seen: set[str] = set()
    merged: list[dict[str, str]] = []
    for r in front + existing:
        u = str(r.get("url") or "").strip()
        if not u:
            continue
        key = normalize_source_url_for_match(u)
        if not key or key in seen:
            continue
        seen.add(key)
        title = str(r.get("title") or "").strip() or u
        merged.append({"title": title, "url": u})
    return merged


@dataclass(frozen=True)
class SecFilingsHub:
    cik_pad: str
    matched_title: str
    hub_sources: list[dict[str, str]]


async def resolve_sec_filings_hub(
    company: str,
    settings: Settings,
) -> SecFilingsHub | None:
    """Resolve EDGAR browse + recent filing URLs, or ``None`` if unmatched / errors."""
    name = (company or "").strip()
    if len(name) < 2:
        return None

    timeout = settings.reference_url_fetch_timeout_seconds

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
        ) as client:
            tickers_blob = await _load_company_tickers(client, settings)
            hit = _pick_best_ticker_match(name, tickers_blob)
            if hit is None:
                logger.info(
                    "SEC filings hub: no confident CIK match for company=%r", name[:80]
                )
                return None
            cik_pad, matched_title = hit

            submissions_url = SEC_SUBMISSIONS_URL.format(cik=cik_pad)
            sub_headers = {
                "User-Agent": reference_fetch_user_agent(settings, submissions_url),
                "Accept-Encoding": "gzip",
            }
            sub_resp = await client.get(submissions_url, headers=sub_headers)
            sub_resp.raise_for_status()
            payload = json.loads(sub_resp.text)
    except Exception as exc:  # noqa: BLE001
        logger.warning("SEC filings hub resolution failed for %r: %s", name[:80], exc)
        return None

    browse = {
        "title": "SEC EDGAR — company filings (official browse)",
        "url": f"https://www.sec.gov/edgar/browse/?CIK={cik_pad}",
    }
    primaries = _recent_verification_filings(payload, cik_pad)
    hub_sources = _dedupe_merge_front([browse], primaries)

    logger.info(
        "SEC filings hub resolved: company=%r cik=%s matched=%r links=%d",
        name[:80],
        cik_pad,
        matched_title[:80] if matched_title else "",
        len(hub_sources),
    )
    return SecFilingsHub(
        cik_pad=cik_pad,
        matched_title=matched_title,
        hub_sources=hub_sources,
    )


def format_issuer_edgar_search_hint(hub: SecFilingsHub | None) -> str:
    """User-message block guiding SEC search — not a citation to paste on every row."""
    if hub is None or not hub.hub_sources:
        return ""
    browse = ""
    for s in hub.hub_sources:
        u = str(s.get("url") or "").strip()
        ul = u.lower()
        if "/edgar/browse" in ul or "/cgi-bin/browse-edgar" in ul:
            browse = u
            break
    if not browse:
        browse = str(hub.hub_sources[0].get("url") or "")
    matched = hub.matched_title.replace("\n", " ").strip()[:240]
    return (
        f"Issuer verified on SEC EDGAR — matched registrant title: {matched}; "
        f"CIK (10-digit): {hub.cik_pad}. Canonical filings browse hub: {browse}\n"
        "Per question you MUST list ONLY `sources` URLs that your searches actually "
        "retrieved THIS TURN and that support THAT question's facts. Do not repeat "
        "the same issuer-wide URLs for every serial_no unless search truly "
        "grounded each answer on those pages. Do not cite the browse hub URL in "
        "`sources` unless it was one of the pages search returned as evidence for "
        "that answer (prefer linking the specific excerpt, e.g. a 10-K or 10-Q "
        "primary document).\n\n"
    )
