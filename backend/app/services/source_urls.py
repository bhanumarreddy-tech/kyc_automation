"""Normalize and optionally verify Gemini citation URLs (SEC EDGAR mirrors).

Wrong exhibit paths fail with ``NoSuchKey`` / 404 even under ``www.sec.gov``
because the edge serves the same archive objects; only the hostname differs
from ``sec-archives.s3.amazonaws.com``. We rewrite known S3 mirrors to
``www.sec.gov/Archives/edgar/`` and optionally HEAD-check URLs, replacing a
verified-missing exhibit with that filing's ``{accession}-index.htm`` page.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from app.config import Settings
from app.services.reference_urls import (
    assert_url_safe_for_ssrf,
    reference_fetch_user_agent,
)

logger = logging.getLogger(__name__)

_S3_NOSUCHKEY_RE = re.compile(br"<Code>\s*NoSuchKey\s*</Code>", re.I)


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


def _probe_verdict(status: int, body_snip: bytes) -> bool | None:
    """Whether URL exists: True / False / None (inconclusive: rate-limit, maintenance, …)."""
    if _S3_NOSUCHKEY_RE.search(body_snip):
        return False
    if 200 <= status < 400:
        return True
    if status in (404, 410):
        return False
    if status in (429, 502, 503, 504):
        return None
    if status in (598, 599):
        return None
    if status == 403:
        return None
    if status >= 400:
        return False
    return None


async def _probe_url(client: httpx.AsyncClient, url: str) -> tuple[int, bytes]:
    """Return HTTP status and a short body snippet (empty when HEAD suffices)."""
    try:
        resp = await client.head(url, follow_redirects=True)
    except httpx.HTTPError:
        return 599, b""

    if resp.status_code == 405:
        try:
            async with client.stream(
                "GET",
                url,
                follow_redirects=True,
                headers={"Range": "bytes=0-4095"},
            ) as stream_resp:
                chunks: list[bytes] = []
                total = 0
                async for chunk in stream_resp.aiter_bytes():
                    if not chunk:
                        continue
                    chunks.append(chunk)
                    total += len(chunk)
                    if total >= 4096:
                        break
                body = b"".join(chunks)
                return stream_resp.status_code, body
        except httpx.HTTPError:
            return 598, b""

    return resp.status_code, b""


async def verify_or_repair_source_url(url: str, settings: Settings) -> str | None:
    """HEAD-check ``url`` (after normalization); EDGAR index fallback or drop.

    Returns a usable URL, or ``None`` if the link should be removed from sources.
    """
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
        status, snip = await _probe_url(client, normalized)
        v0 = _probe_verdict(status, snip)
        if v0 is True or v0 is None:
            # OK, or SEC throttling / maintenance — keep the link we were given.
            return normalized

        fb = edgar_filing_index_fallback_url(normalized)
        if fb and fb != normalized:
            fb_safe, fb_reason = assert_url_safe_for_ssrf(fb)
            if fb_safe:
                st2, sn2 = await _probe_url(client, fb)
                v1 = _probe_verdict(st2, sn2)
                # Exhibit was verified missing (404 / NoSuchKey). Prefer filing index even
                # when index probe is inconclusive (503 maintenance): better URL than a dead exhibit.
                if v1 is True or v1 is None:
                    logger.info(
                        "source URL repaired via EDGAR index: %s -> %s",
                        normalized[:80],
                        fb[:80],
                    )
                    return fb

        logger.info(
            "source URL missing and no usable EDGAR index (status=%s): %s",
            status,
            normalized[:120],
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
                final = await resolve_budgeted(u)
                if final:
                    new_sources.append({"title": title, "url": final})
            aq.sources = new_sources
