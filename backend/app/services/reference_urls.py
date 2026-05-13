"""Fetch user-supplied HTTP(S) URLs and convert them into :class:`ParsedDocument` for validation.

SSRF hygiene: only http/https, block hosts that resolve to private / loopback / link-local / multicast.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import re
import socket
from urllib.parse import urldefrag, urlparse

import httpx
import trafilatura

from app.config import Settings
from app.services.documents import ParsedDocument, parse_pdf_bytes

logger = logging.getLogger(__name__)

_PDF_MAGIC = b"%PDF"


def normalize_reference_urls(raw: list[str]) -> list[str]:
    """Strip, drop empties, preserve first-seen order."""
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        u = (item or "").strip()
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def validate_reference_urls_for_request(
    urls: list[str],
    *,
    max_count: int,
) -> tuple[list[str] | None, str | None]:
    """Return ``(urls, None)`` or ``(None, error_message)``."""
    if len(urls) > max_count:
        return None, f"At most {max_count} reference URLs are allowed"
    for u in urls:
        parsed = urlparse(u)
        if parsed.scheme not in ("http", "https"):
            return None, f"Invalid URL scheme (only http/https): {u[:120]!r}"
        if not parsed.hostname:
            return None, f"URL has no host: {u[:120]!r}"
    return urls, None


def _host_blocked_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return bool(
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def assert_url_safe_for_ssrf(url: str) -> tuple[bool, str]:
    """Return ``(ok, reason)`` after scheme/host and DNS checks."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "unsupported scheme"
    host = parsed.hostname
    if not host:
        return False, "missing host"

    try:
        host_addr = ipaddress.ip_address(host)
    except ValueError:
        host_addr = None

    if host_addr is not None:
        if _host_blocked_ip(host_addr):
            return False, "literal IP in blocked range"
        return True, ""

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return False, f"DNS failed: {exc}"

    for _fam, _type, _proto, _canon, sockaddr in infos:
        if not sockaddr:
            continue
        ip_str = sockaddr[0]
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _host_blocked_ip(addr):
            return False, "host resolves to blocked network"
    return True, ""


def _citation_filename(url: str) -> str:
    """Stable, reasonably short filename for validation citations."""
    if len(url) <= 240:
        return url
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"web-{digest}"


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n... [truncated]"


async def _fetch_body_capped(
    client: httpx.AsyncClient,
    url: str,
    max_bytes: int,
) -> tuple[int, dict[str, str], bytes]:
    """GET ``url`` and return ``(status, headers_lower, body)`` with body capped."""
    async with client.stream("GET", url, follow_redirects=True) as response:
        status = response.status_code
        headers = {k.lower(): v for k, v in response.headers.items()}
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            if not chunk:
                continue
            remaining = max_bytes - total
            if remaining <= 0:
                break
            take = chunk[:remaining]
            chunks.append(take)
            total += len(take)
            if total >= max_bytes:
                break
        body = b"".join(chunks)
        return status, headers, body


def _content_type_from_headers(headers: dict[str, str]) -> str:
    ct = (headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    return ct


def _html_to_text(html: bytes, url: str) -> str:
    try:
        extracted = trafilatura.extract(
            html.decode("utf-8", errors="replace"),
            url=url,
            include_comments=False,
            include_tables=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("trafilatura extract failed for %s: %s", url, exc)
        extracted = None
    text = (extracted or "").strip()
    if text:
        return text
    # Minimal fallback: strip tags crudely
    raw = html.decode("utf-8", errors="replace")
    raw = re.sub(r"(?is)<script.*?>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style.*?>.*?</style>", " ", raw)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw).strip()


async def fetch_one_reference_url(url: str, settings: Settings) -> ParsedDocument:
    """Fetch a single URL and return a :class:`ParsedDocument` (never raises for network errors)."""
    display = _citation_filename(url)
    prefix_lines = [f"Source URL: {url}"] if display != url else []

    safe, reason = assert_url_safe_for_ssrf(url)
    if not safe:
        msg = f"URL blocked ({reason})"
        logger.info("reference URL rejected %s: %s", url, msg)
        return ParsedDocument(
            filename=display,
            kind="other",
            raw_bytes=b"",
            text=_truncate_text(
                "\n".join(prefix_lines + [f"[Fetch error] {msg}"]),
                settings.reference_url_max_text_chars,
            ),
            error=msg,
        )

    timeout = httpx.Timeout(settings.reference_url_fetch_timeout_seconds)
    limits = httpx.Limits(max_keepalive_connections=5, max_connections=10)
    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            max_redirects=settings.reference_url_max_redirects,
            headers={
                "User-Agent": "KYC-Automation-Validator/1.0",
                "Accept": "text/html,application/pdf,text/plain;q=0.9,*/*;q=0.1",
            },
        ) as client:
            status, headers, body = await _fetch_body_capped(
                client,
                url,
                settings.reference_url_max_response_bytes,
            )
    except httpx.HTTPError as exc:
        logger.warning("reference URL fetch failed %s: %s", url, exc)
        msg = f"HTTP error: {exc}"
        return ParsedDocument(
            filename=display,
            kind="other",
            raw_bytes=b"",
            text="\n".join(prefix_lines + [f"[Fetch error] {msg}"]),
            error=msg,
        )

    if status >= 400:
        msg = f"HTTP status {status}"
        logger.info("reference URL bad status %s: %s", url, msg)
        return ParsedDocument(
            filename=display,
            kind="other",
            raw_bytes=body,
            text="\n".join(prefix_lines + [f"[Fetch error] {msg}"]),
            error=msg,
        )

    ctype = _content_type_from_headers(headers)
    if body.startswith(_PDF_MAGIC) or ctype == "application/pdf":
        pdf_name = display if display.lower().endswith(".pdf") else f"{display}.pdf"
        doc = parse_pdf_bytes(pdf_name, body)
        # Help model tie citation to original URL when hash-named
        if prefix_lines and doc.text:
            doc.text = "\n".join(prefix_lines) + "\n\n" + doc.text
        elif prefix_lines and not doc.text.strip():
            doc.text = "\n".join(prefix_lines)
        return doc

    if ctype in ("text/plain", "text/markdown") or "text/" in ctype:
        text = body.decode("utf-8", errors="replace").strip()
        text = _truncate_text(text, settings.reference_url_max_text_chars)
        if prefix_lines:
            text = "\n".join(prefix_lines) + "\n\n" + text
        return ParsedDocument(
            filename=display,
            kind="other",
            raw_bytes=body,
            text=text,
        )

    # HTML and unknown types: try HTML extraction
    text = _html_to_text(body, url)
    text = _truncate_text(text, settings.reference_url_max_text_chars)
    if prefix_lines:
        text = "\n".join(prefix_lines) + "\n\n" + text
    return ParsedDocument(
        filename=display,
        kind="other",
        raw_bytes=body,
        text=text,
    )


async def ingest_reference_urls(urls: list[str], settings: Settings) -> list[ParsedDocument]:
    """Fetch each URL (sequential to limit blast radius); order matches ``urls``."""
    out: list[ParsedDocument] = []
    for u in urls:
        # Strip fragment (server-side fetch should ignore it)
        clean, _frag = urldefrag(u)
        out.append(await fetch_one_reference_url(clean, settings))
    return out
