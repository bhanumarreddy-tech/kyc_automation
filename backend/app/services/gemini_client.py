"""Gemini (Google AI) async client helpers used by answer and validation."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import re
from dataclasses import replace
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse, urlunparse

from google import genai
from google.genai import errors, types

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_SERIAL_NO_JSON_RE = re.compile(r'"serial_no"\s*:\s*(\d+)')
_GROUNDING_FALLBACK_CHUNK_CAP = 8


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=settings.gemini_api_key)


def google_search_tools() -> list[types.Tool]:
    return [types.Tool(google_search=types.GoogleSearch())]


async def generate_content_with_overload_retry(
    client: genai.Client,
    settings: Settings,
    *,
    model: str,
    contents: list[types.Content],
    config: types.GenerateContentConfig | None = None,
) -> types.GenerateContentResponse:
    """Call ``generate_content``, retrying transient quota / overload errors."""
    extra = settings.overload_extra_attempts
    base = settings.overload_base_delay_seconds
    for attempt in range(extra + 1):
        try:
            return await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )
        except errors.APIError as exc:
            code = int(getattr(exc, "code", None) or 0)
            if code not in {408, 429, 500, 503, 529} or attempt >= extra:
                raise
            delay = min(120.0, base * (2**attempt))
            delay += random.uniform(0.0, max(0.5, delay * 0.15))
            logger.warning(
                "Gemini API error %s; backing off %.1fs (%d/%d extra rounds)",
                code,
                delay,
                attempt + 1,
                extra,
            )
            await asyncio.sleep(delay)
    raise RuntimeError("generate_content overload retry loop exited without result")


def extract_text(response: types.GenerateContentResponse) -> str:
    """Concatenate text parts from all candidates (first candidate can be empty)."""
    chunks: list[str] = []
    for cand in response.candidates or []:
        content = cand.content
        if content is None:
            continue
        for part in content.parts or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)
    return "".join(chunks)


def _first_balanced_json_object(text: str) -> str | None:
    """Return the substring of the first top-level `{ ... }` balanced for JSON strings.

    Handles `{` / `}` inside quoted strings; ignores braces in strings."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                in_string = False
            continue
        if c == '"':
            in_string = True
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def log_blocked_generation(response: types.GenerateContentResponse) -> None:
    """Log prompt blocking or empty candidates when JSON parsing fails."""
    pf = getattr(response, "prompt_feedback", None)
    if pf is not None:
        br = getattr(pf, "block_reason", None)
        if br is not None:
            logger.warning("Gemini prompt_feedback block_reason=%s", br)
    for idx, cand in enumerate(response.candidates or []):
        finish = getattr(cand, "finish_reason", None)
        sr = getattr(cand, "safety_ratings", None) or []
        n_parts = len(cand.content.parts) if cand.content and cand.content.parts else 0
        if finish is not None and (n_parts == 0 or finish != types.FinishReason.STOP):
            logger.debug(
                "candidate[%d] finish_reason=%s parts=%d safety_ratings=%s",
                idx,
                finish,
                n_parts,
                sr,
            )


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text).strip()


def parse_json_response(
    response: types.GenerateContentResponse, prefill: str = ""
) -> Any:
    """Parse model output as JSON (same heuristics as the prior Claude path)."""

    def _try_parse_segment(segment: str) -> Any | None:
        stripped = segment.strip()
        cleaned = _strip_code_fences(stripped)
        if not cleaned.strip():
            return None
        body = cleaned.strip()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            balanced = _first_balanced_json_object(body)
            if balanced:
                try:
                    return json.loads(balanced)
                except json.JSONDecodeError:
                    pass
            decoder = json.JSONDecoder()
            for idx in range(len(body)):
                if body[idx] != "{":
                    continue
                try:
                    obj, _end = decoder.raw_decode(body, idx)
                    return obj
                except json.JSONDecodeError:
                    continue
            return None

    sdk_parsed = getattr(response, "parsed", None)
    if sdk_parsed is not None:
        return sdk_parsed

    raw_concat = extract_text(response)
    combined = (prefill + raw_concat) if prefill else raw_concat

    parsed = _try_parse_segment(combined)
    if parsed is not None:
        return parsed

    stripped_segments = [
        t.strip() for t in _assistant_text_segments(response) if t.strip()
    ]

    for seg in reversed(stripped_segments):
        candidate = (prefill + seg) if prefill else seg
        if candidate.strip() == combined.strip():
            continue
        parsed_seg = _try_parse_segment(candidate)
        if parsed_seg is not None:
            return parsed_seg

    log_blocked_generation(response)
    logger.debug("Model response did not contain parsable JSON")
    logger.debug("Combined text (prefix 4000 chars): %s", combined[:4000])
    raise json.JSONDecodeError("no JSON object decoded", combined, 0)


def _assistant_text_segments(response: types.GenerateContentResponse) -> list[str]:
    out: list[str] = []
    for cand in response.candidates or []:
        content = cand.content
        if content is None:
            continue
        for part in content.parts or []:
            text = getattr(part, "text", None)
            if text:
                out.append(text)
    return out


def user_content_blocks_to_gemini_parts(
    blocks: list[dict[str, Any]],
) -> list[types.Part]:
    """Map Anthropic-style content blocks to Gemini parts (PDF/image/text)."""
    parts: list[types.Part] = []

    for block in blocks:
        btype = block.get("type")
        if btype == "text":
            parts.append(types.Part.from_text(text=str(block.get("text") or "")))
            continue
        if btype == "document":
            src = block.get("source") or {}
            if isinstance(src, dict) and src.get("type") == "base64":
                raw = base64.standard_b64decode(src.get("data") or b"")
                mime = str(src.get("media_type") or "application/pdf")
                parts.append(types.Part.from_bytes(data=raw, mime_type=mime))
            continue
        if btype == "image":
            src = block.get("source") or {}
            if isinstance(src, dict) and src.get("type") == "base64":
                raw = base64.standard_b64decode(src.get("data") or b"")
                mime = str(src.get("media_type") or "image/png")
                parts.append(types.Part.from_bytes(data=raw, mime_type=mime))
            continue
    return parts


def count_grounding_web_queries(response: types.GenerateContentResponse) -> int:
    candidates = response.candidates or []
    if not candidates:
        return 0
    gm = getattr(candidates[0], "grounding_metadata", None)
    if gm is None:
        return 0
    queries = getattr(gm, "web_search_queries", None)
    if isinstance(queries, list):
        return len(queries)
    return 0


def normalize_source_url_for_match(url: str) -> str:
    """Normalize HTTP(S) URLs for allowlist comparisons."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((scheme, host, path, "", "", "")).lower()


def _dedupe_web_sources(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for r in rows:
        u = str(r.get("url") or "").strip()
        if not u:
            continue
        key = normalize_source_url_for_match(u)
        if not key or key in seen:
            continue
        seen.add(key)
        title = str(r.get("title") or "").strip() or u
        out.append({"title": title, "url": u})
    return out


def extract_grounding_web_sources_from_chunks(
    response: types.GenerateContentResponse,
) -> list[dict[str, str]]:
    """Ordered unique ``{title, url}`` pairs from ``grounding_chunks`` web URIs."""
    candidates = response.candidates or []
    if not candidates:
        return []
    gm = getattr(candidates[0], "grounding_metadata", None)
    if gm is None:
        return []
    chunks = getattr(gm, "grounding_chunks", None) or []
    rows: list[dict[str, str]] = []
    for ch in chunks:
        web = getattr(ch, "web", None)
        if web is None:
            continue
        uri = str(getattr(web, "uri", None) or "").strip()
        if not uri:
            continue
        title = str(getattr(web, "title", None) or "").strip() or uri
        rows.append({"title": title, "url": uri})
    return _dedupe_web_sources(rows)


def grounding_sources_by_serial_no(
    response: types.GenerateContentResponse,
    *,
    lookback_chars: int = 6000,
) -> dict[int, list[dict[str, str]]]:
    """Infer ``serial_no`` from JSON offsets in grounding_support segments."""
    out: dict[int, list[dict[str, str]]] = {}
    candidates = response.candidates or []
    if not candidates:
        return out
    gm = getattr(candidates[0], "grounding_metadata", None)
    if gm is None:
        return out
    chunks = getattr(gm, "grounding_chunks", None) or []
    supports = getattr(gm, "grounding_supports", None) or []
    full_text = extract_text(response)
    if not full_text.strip():
        return out

    def urls_for_chunk_indices(indices: object) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        if not isinstance(indices, list):
            return rows
        for raw_idx in indices:
            try:
                idx = int(raw_idx)
            except (TypeError, ValueError):
                continue
            if idx < 0 or idx >= len(chunks):
                continue
            web = getattr(chunks[idx], "web", None)
            if web is None:
                continue
            uri = str(getattr(web, "uri", None) or "").strip()
            if not uri:
                continue
            title = str(getattr(web, "title", None) or "").strip() or uri
            rows.append({"title": title, "url": uri})
        return rows

    for sup in supports:
        seg = getattr(sup, "segment", None)
        start_raw = getattr(seg, "start_index", None) if seg is not None else None
        if start_raw is None:
            continue
        try:
            si = int(start_raw)
        except (TypeError, ValueError):
            continue
        prefix_start = max(0, si - lookback_chars)
        prefix = full_text[prefix_start:si]
        matches = list(_SERIAL_NO_JSON_RE.finditer(prefix))
        if not matches:
            continue
        try:
            serial = int(matches[-1].group(1))
        except (ValueError, IndexError):
            continue
        idxs = getattr(sup, "grounding_chunk_indices", None)
        for row in urls_for_chunk_indices(idxs):
            out.setdefault(serial, []).append(row)

    for serial in list(out.keys()):
        out[serial] = _dedupe_web_sources(out[serial])
    return out


def merge_answer_sources_with_grounding_metadata(
    answered: list[Any],
    response: types.GenerateContentResponse,
    *,
    enabled: bool,
) -> list[Any]:
    """Prefer Google Search grounding chunk URLs over unconstrained model citations.

    When enabled and grounding chunks exist: keep only model URLs that appear in those
    chunks, prepend URLs mapped via ``grounding_supports`` → ``serial_no`` heuristics,
    and fall back to the global chunk list for factual rows so citations stay real."""
    if not enabled:
        return answered

    chunk_sources = extract_grounding_web_sources_from_chunks(response)
    if not chunk_sources:
        return answered

    allow = {normalize_source_url_for_match(s["url"]) for s in chunk_sources}
    by_serial = grounding_sources_by_serial_no(response)

    merged: list[Any] = []
    for aq in answered:
        serial_raw = getattr(aq, "serial_no", None)
        answer_text = str(getattr(aq, "answer", "") or "").strip()
        sentinel = answer_text in ("", "Not found", "Not relevant")

        if sentinel:
            merged.append(replace(aq, sources=[]))
            continue

        sid: int | None
        try:
            sid = int(serial_raw) if serial_raw is not None else None
        except (TypeError, ValueError):
            sid = None

        hinted = _dedupe_web_sources(list(by_serial.get(sid, [])) if sid is not None else [])

        raw_sources = getattr(aq, "sources", None) or []
        model_kept: list[dict[str, str]] = []
        if isinstance(raw_sources, list):
            for src in raw_sources:
                if not isinstance(src, dict):
                    continue
                u = str(src.get("url") or "").strip()
                if not u:
                    continue
                if normalize_source_url_for_match(u) not in allow:
                    continue
                title = str(src.get("title") or "").strip() or u
                model_kept.append({"title": title, "url": u})

        combined = _dedupe_web_sources([*hinted, *model_kept])
        if not combined:
            combined = _dedupe_web_sources(chunk_sources[:_GROUNDING_FALLBACK_CHUNK_CAP])

        merged.append(replace(aq, sources=combined))

    return merged


def summarise_response_for_logs(response: types.GenerateContentResponse) -> str:
    candidates = response.candidates or []
    if not candidates:
        return "<no candidates>"
    cand = candidates[0]
    fr = getattr(cand, "finish_reason", None)
    gm = getattr(cand, "grounding_metadata", None)
    n_queries = 0
    if gm is not None:
        q = getattr(gm, "web_search_queries", None)
        if isinstance(q, list):
            n_queries = len(q)
    parts = cand.content.parts if cand.content else None
    n_parts = len(parts or [])
    return f"finish={fr},parts={n_parts},web_queries={n_queries}"
