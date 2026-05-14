"""Normalize and optionally verify Gemini citation URLs (SEC EDGAR mirrors).

Wrong exhibit paths fail with ``NoSuchKey`` / 404 even under ``www.sec.gov``
because the edge serves the same archive objects; only the hostname differs
from ``sec-archives.s3.amazonaws.com``. We rewrite known S3 mirrors to
``www.sec.gov/Archives/edgar/`` and optionally HEAD-check URLs, replacing a
verified-missing exhibit with that filing's ``{accession}-index.htm`` page.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.config import Settings
from app.services.gemini_client import normalize_source_url_for_match
from app.services.reference_urls import (
    assert_url_safe_for_ssrf,
    reference_fetch_user_agent,
)

logger = logging.getLogger(__name__)


def hostname_domain_priority_rank(url: str, suffixes: tuple[str, ...]) -> int:
    """Return the best (lowest) matching index into *suffixes*, or len(suffixes) if none."""
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    if not host:
        return len(suffixes)
    best = len(suffixes)
    for i, suf in enumerate(suffixes):
        s = suf.lower().strip().lstrip(".")
        if not s:
            continue
        if host == s or host.endswith("." + s):
            best = min(best, i)
    return best


SEC_DATA_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_ARCHIVES_DOC_PATH_RE = re.compile(
    r"/Archives/edgar/data/\d+/[^/?#]+/[^/?#]+", re.I
)

_S3_NOSUCHKEY_RE = re.compile(br"<Code>\s*NoSuchKey\s*</Code>", re.I)
_SUBMISSIONS_CACHE: dict[str, tuple[float, Any]] = {}
_SUBMISSIONS_TTL_S = 3600.0


def normalize_sec_edgar_source_url(url: str) -> str:
    """Rewrite SEC EDGAR S3 mirrors to canonical www.sec.gov Archives URLs."""
    raw = (url or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    if parsed.scheme not in ("http", "https"):
        return raw

    host = (parsed.hostname or "").lower()
    path = parsed.path or ""

    def _canonical_archives_url(new_path: str) -> str:
        np = new_path if new_path.startswith("/") else "/" + new_path
        return urlunparse(
            ("https", "www.sec.gov", np, "", parsed.query, parsed.fragment)
        )

    if _is_sec_archives_virtual_host(host):
        if path.startswith("/edgar/data/"):
            return _canonical_archives_url("/Archives" + path)

    if _is_amazonaws_s3_style_host(host):
        segs = [s for s in path.strip("/").split("/") if s]
        if len(segs) >= 2 and segs[0] == "sec-archives":
            rest = "/" + "/".join(segs[1:])
            if rest.startswith("/edgar/data/"):
                return _canonical_archives_url("/Archives" + rest)

    if host in ("www.sec.gov", "sec.gov"):
        if path.startswith("/edgar/data/") and not path.startswith("/Archives/"):
            return _canonical_archives_url("/Archives" + path)

    return raw


def _is_sec_archives_virtual_host(host: str) -> bool:
    return host == "sec-archives.s3.amazonaws.com" or (
        host.startswith("sec-archives.s3.") and host.endswith(".amazonaws.com")
    )


def _is_amazonaws_s3_style_host(host: str) -> bool:
    return host == "s3.amazonaws.com" or (
        host.startswith("s3.") and host.endswith(".amazonaws.com")
    )


def _edgar_data_parts(path: str) -> tuple[list[str], int] | None:
    """Locate ``.../edgar/data/`` and return ``(path_segments, index_of_edgar)``."""
    parts = [p for p in path.split("/") if p]
    try:
        i_edgar = parts.index("edgar")
    except ValueError:
        return None
    if i_edgar + 1 >= len(parts) or parts[i_edgar + 1] != "data":
        return None
    return parts, i_edgar


def edgar_filing_index_fallback_url(url: str) -> str | None:
    """If ``url`` points at an exhibit under EDGAR Archives, return ``*-index.htm`` URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if host not in ("www.sec.gov", "sec.gov"):
        return None

    parsed_parts = _edgar_data_parts(parsed.path or "")
    if not parsed_parts:
        return None
    parts, i_edgar = parsed_parts
    i_data = i_edgar + 1
    # segments after "data": cik, accession, exhibit filename
    if len(parts) < i_data + 4:
        return None
    accession = parts[i_data + 2]
    doc_name = parts[i_data + 3]
    if doc_name.endswith("-index.htm"):
        return None
    index_name = f"{accession}-index.htm"
    new_parts = parts[: i_data + 3] + [index_name]
    new_path = "/" + "/".join(new_parts)
    return urlunparse(("https", "www.sec.gov", new_path, "", "", ""))


def parse_sec_archives_primary_path(url: str) -> tuple[str, str, str] | None:
    """Return ``(CIK_digits, accession_folder_no_dash, filename)`` for Archives/edgar/data URLs."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if host not in ("www.sec.gov", "sec.gov"):
        return None
    if not _ARCHIVES_DOC_PATH_RE.search(parsed.path or ""):
        return None
    parsed_parts = _edgar_data_parts(parsed.path or "")
    if not parsed_parts:
        return None
    parts, i_edgar = parsed_parts
    i_data = i_edgar + 1
    if len(parts) < i_data + 4:
        return None
    cik_seg = parts[i_data + 1]
    acc_flat = parts[i_data + 2]
    doc = parts[i_data + 3]
    if not cik_seg.isdigit() or not acc_flat or not doc:
        return None
    return cik_seg, acc_flat, doc


def is_sec_archives_edgar_verify_target(url: str) -> bool:
    """Whether this citation is a SEC Archives path eligible for HTTP probing."""
    return parse_sec_archives_primary_path(normalize_sec_edgar_source_url(url)) is not None


def edgar_filing_stem_index_fallback_url(url: str) -> str | None:
    """Map ``basename.ext`` exhibit to ``basename-index.htm``."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return None
    host = (parsed.hostname or "").lower()
    if host not in ("www.sec.gov", "sec.gov"):
        return None
    parsed_parts = _edgar_data_parts(parsed.path or "")
    if not parsed_parts:
        return None
    parts, i_edgar = parsed_parts
    i_data = i_edgar + 1
    if len(parts) < i_data + 4:
        return None
    doc_name = parts[i_data + 3]
    if "-index.htm" in doc_name.lower():
        return None
    chunks = doc_name.rsplit(".", 1)
    if len(chunks) != 2:
        return None
    stem, ext = chunks[0], chunks[1].lower()
    if ext not in ("htm", "html", "txt", "xml", "pdf", "xhtml"):
        return None
    index_name = f"{stem}-index.htm"
    new_parts = parts[: i_data + 3] + [index_name]
    new_path = "/" + "/".join(new_parts)
    return urlunparse(("https", "www.sec.gov", new_path, "", "", ""))


def edgar_filing_fallback_candidates(url: str) -> list[str]:
    """Stem-index first, then accession-folder ``{flat}-index.htm``."""
    seen: set[str] = set()
    out: list[str] = []
    for cand in (
        edgar_filing_stem_index_fallback_url(url),
        edgar_filing_index_fallback_url(url),
    ):
        if not cand or cand in seen:
            continue
        seen.add(cand)
        out.append(cand)
    return out


async def _get_range_snippet(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = 4096,
) -> tuple[int, bytes]:
    rng_last = max(0, max_bytes - 1)
    try:
        async with client.stream(
            "GET",
            url,
            follow_redirects=True,
            headers={"Range": f"bytes=0-{rng_last}"},
        ) as stream_resp:
            chunks: list[bytes] = []
            total = 0
            async for chunk in stream_resp.aiter_bytes():
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total >= max_bytes:
                    break
            body = b"".join(chunks)
            return stream_resp.status_code, body
    except httpx.HTTPError:
        return 598, b""


async def _fetch_submissions_json_cached(
    client: httpx.AsyncClient,
    settings: Settings,
    cik_padded: str,
) -> Any | None:
    now = time.monotonic()
    hit = _SUBMISSIONS_CACHE.get(cik_padded)
    if hit is not None and (now - hit[0]) < _SUBMISSIONS_TTL_S:
        return hit[1]
    sub_url = SEC_DATA_SUBMISSIONS_URL.format(cik=cik_padded)
    ua = reference_fetch_user_agent(settings, sub_url)
    headers = {"User-Agent": ua, "Accept-Encoding": "gzip"}
    try:
        r = await client.get(sub_url, headers=headers)
        r.raise_for_status()
        data = json.loads(r.text)
        _SUBMISSIONS_CACHE[cik_padded] = (now, data)
        return data
    except Exception as exc:  # noqa: BLE001
        logger.warning("submissions lookup failed CIK=%s: %s", cik_padded, exc)
        return None


def _authority_primary_document_url(data: Any, *, cik_seg: str, acc_flat: str) -> str | None:
    filings = (((data or {}).get("filings")) or {}).get("recent") or {}
    accs_raw = filings.get("accessionNumber") or []
    docs = filings.get("primaryDocument") or []
    needle = "".join(acc_flat.split("-"))
    for idx, raw_acc in enumerate(accs_raw):
        if idx >= len(docs):
            break
        a = "".join(str(raw_acc).split("-")).strip().lower()
        if a != needle.lower():
            continue
        primary = str(docs[idx]).strip()
        if not primary:
            return None
        ciki = str(int(cik_seg))
        return normalize_sec_edgar_source_url(
            f"https://www.sec.gov/Archives/edgar/data/{ciki}/{needle}/{primary}"
        )
    return None


async def submissions_canonical_archive_url(
    client: httpx.AsyncClient,
    normalized_url: str,
    settings: Settings,
) -> str | None:
    pts = parse_sec_archives_primary_path(normalized_url)
    if pts is None:
        return None
    cik_seg, acc_flat, _ = pts
    cik_pad = f"{int(cik_seg):010d}"
    payload = await _fetch_submissions_json_cached(client, settings, cik_pad)
    if payload is None:
        return None
    return _authority_primary_document_url(payload, cik_seg=cik_seg, acc_flat=acc_flat)


def _probe_verdict(status: int, body_snip: bytes, *, snippet_checked: bool) -> bool | None:
    if _S3_NOSUCHKEY_RE.search(body_snip):
        return False

    if snippet_checked:
        if status in (404, 410):
            return False
        if status in (429, 502, 503, 504, 598, 599):
            return None
        if status == 403:
            return None
        if 200 <= status < 400:
            if len(body_snip.strip()) < 32:
                return None
            return True
        if status >= 400:
            return False
        return None

    if 200 <= status < 400:
        return True
    if status in (404, 410):
        return False
    if status in (429, 502, 503, 504, 598, 599):
        return None
    if status == 403:
        return None
    if status >= 400:
        return False
    return None


async def _probe_url(client: httpx.AsyncClient, url: str) -> tuple[int, bytes]:
    """GET snippet for Archives primary paths so S3/XML errors show in body."""
    normalized = normalize_sec_edgar_source_url(url)
    if parse_sec_archives_primary_path(normalized) is not None:
        return await _get_range_snippet(client, normalized)

    try:
        resp = await client.head(normalized, follow_redirects=True)
    except httpx.HTTPError:
        return 599, b""

    if resp.status_code == 405:
        try:
            return await _get_range_snippet(client, normalized)
        except httpx.HTTPError:
            return 598, b""

    return resp.status_code, b""


def _snippet_check_for_normalized(normalized_url: str) -> bool:
    return parse_sec_archives_primary_path(normalized_url) is not None


async def verify_or_repair_source_url(url: str, settings: Settings) -> str | None:
    """Normalize, probe Archives with GET-snippet semantics, repair via submissions or index URLs."""
    normalized = normalize_sec_edgar_source_url(url)
    safe, reason = assert_url_safe_for_ssrf(normalized)
    if not safe:
        logger.info("source URL rejected (SSRF): %s (%s)", normalized[:120], reason)
        return None

    timeout = httpx.Timeout(settings.source_url_verify_timeout_seconds)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    headers = {
        "Accept-Encoding": "gzip, deflate",
        "User-Agent": reference_fetch_user_agent(settings, normalized),
        "Accept": "*/*",
    }

    async with httpx.AsyncClient(
        timeout=timeout,
        limits=limits,
        max_redirects=settings.reference_url_max_redirects,
        headers=headers,
    ) as client:
        async def classify(u: str) -> bool | None:
            u_n = normalize_sec_edgar_source_url(u)
            st, snip = await _probe_url(client, u_n)
            return _probe_verdict(
                st,
                snip,
                snippet_checked=_snippet_check_for_normalized(u_n),
            )

        v0 = await classify(normalized)
        if v0 is True or v0 is None:
            return normalized

        canonical = await submissions_canonical_archive_url(
            client, normalized, settings
        )
        if canonical and canonical != normalized:
            v_can = await classify(canonical)
            if v_can is True:
                logger.info(
                    "source URL repaired via submissions primaryDocument: %s -> %s",
                    normalized[:80],
                    canonical[:80],
                )
                return canonical

        folder_index = edgar_filing_index_fallback_url(normalized)
        for fb in edgar_filing_fallback_candidates(normalized):
            if fb == normalized or (canonical and fb == canonical):
                continue
            fb_safe, _fb_reason = assert_url_safe_for_ssrf(fb)
            if not fb_safe:
                continue
            v_fb = await classify(fb)
            if v_fb is True:
                logger.info(
                    "source URL repaired via EDGAR fallback: %s -> %s",
                    normalized[:80],
                    fb[:80],
                )
                return fb
            if (
                v_fb is None
                and folder_index
                and fb.rstrip("/") == folder_index.rstrip("/")
            ):
                logger.info(
                    "source URL repaired via EDGAR folder-index (ambiguous probe): "
                    "%s -> %s",
                    normalized[:80],
                    fb[:80],
                )
                return fb

        logger.info(
            "source URL missing after repair ladder: %s", normalized[:120]
        )
        return None


async def sanitize_answer_sources_urls(
    sections: list[list[Any]],
    settings: Settings,
) -> None:
    """Normalize URLs on answer rows; optionally verify (deduped, budget-capped)."""
    for sec in sections:
        for aq in sec:
            sources = getattr(aq, "sources", None)
            if not isinstance(sources, list):
                continue
            cleaned: list[dict[str, str]] = []
            for src in sources:
                if not isinstance(src, dict):
                    continue
                u = str(src.get("url") or "").strip()
                if not u:
                    continue
                title = str(src.get("title") or "").strip() or u
                nu = normalize_sec_edgar_source_url(u)
                cleaned.append({"title": title, "url": nu})
            aq.sources = cleaned

    if not settings.source_url_verify_enabled:
        return

    cache: dict[str, str | None] = {}
    max_n = settings.source_url_verify_max_urls
    remaining = {"n": max_n}

    async def resolve_budgeted(u: str) -> str | None:
        if u in cache:
            return cache[u]
        if max_n > 0 and remaining["n"] <= 0:
            cache[u] = u
            return u
        if max_n > 0:
            remaining["n"] -= 1
        out = await verify_or_repair_source_url(u, settings)
        cache[u] = out
        return out

    for sec in sections:
        for aq in sec:
            sources = getattr(aq, "sources", None)
            if not isinstance(sources, list):
                continue
            new_sources: list[dict[str, str]] = []
            for src in sources:
                if not isinstance(src, dict):
                    continue
                u = str(src.get("url") or "").strip()
                if not u:
                    continue
                title = str(src.get("title") or "").strip() or u
                nu = normalize_sec_edgar_source_url(u)
                probe_this = settings.source_url_verify_enabled and (
                    not settings.source_url_verify_edgar_only
                    or is_sec_archives_edgar_verify_target(nu)
                )
                if probe_this:
                    final = await resolve_budgeted(u)
                    if final:
                        new_sources.append({"title": title, "url": final})
                else:
                    new_sources.append({"title": title, "url": nu})
            aq.sources = new_sources


def prioritize_and_cap_answer_sources(
    sections: list[list[Any]],
    settings: Settings,
    *,
    verification_hub_sources: list[dict[str, str]] | None,
) -> None:
    """Reorder URLs already cited per row so SEC issuer hub matches come first,

    then government/regulator host suffixes in ``answer_sources_domain_priority_suffixes``,
    then remaining URLs in original row order; dedupe; cap length. Hub links only
    appear when the model or grounding actually cited them (never injected wholesale
    per row).
    """
    max_n = max(1, settings.answer_sources_max_count)
    domain_suffixes = settings.answer_sources_domain_priority_suffixes

    hub_norm_order: list[str] = []
    if verification_hub_sources:
        seenhub: set[str] = set()
        for hs in verification_hub_sources:
            if not isinstance(hs, dict):
                continue
            u = normalize_sec_edgar_source_url(str(hs.get("url") or "").strip())
            if not u:
                continue
            nk = normalize_source_url_for_match(u)
            if not nk or nk in seenhub:
                continue
            seenhub.add(nk)
            hub_norm_order.append(nk)

    for sec in sections:
        for aq in sec:
            sources = getattr(aq, "sources", None)
            if not isinstance(sources, list) or not sources:
                continue

            first_by_norm: dict[str, dict[str, str]] = {}
            norm_order: list[str] = []
            first_index_by_norm: dict[str, int] = {}
            for idx, src in enumerate(sources):
                if not isinstance(src, dict):
                    continue
                u = str(src.get("url") or "").strip()
                if not u:
                    continue
                nk = normalize_source_url_for_match(u)
                if not nk:
                    continue
                if nk not in first_by_norm:
                    title = str(src.get("title") or "").strip() or u
                    first_by_norm[nk] = {"title": title, "url": u}
                    norm_order.append(nk)
                    first_index_by_norm[nk] = idx

            out: list[dict[str, str]] = []
            used: set[str] = set()

            for nk in hub_norm_order:
                if len(out) >= max_n:
                    break
                row = first_by_norm.get(nk)
                if row is None:
                    continue
                out.append(dict(row))
                used.add(nk)

            if len(out) < max_n:
                remainder: list[tuple[int, int, str, dict[str, str]]] = []
                for nk in norm_order:
                    if nk in used:
                        continue
                    row = first_by_norm[nk]
                    dom_rank = hostname_domain_priority_rank(
                        row["url"], domain_suffixes
                    )
                    remainder.append(
                        (dom_rank, first_index_by_norm[nk], nk, row)
                    )
                remainder.sort(key=lambda t: (t[0], t[1]))
                for _dr, _fi, nk, row in remainder:
                    if len(out) >= max_n:
                        break
                    if nk in used:
                        continue
                    out.append(dict(row))
                    used.add(nk)

            aq.sources = out
