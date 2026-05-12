"""Gemini (Google AI) async client helpers used by answer and validation."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import re
from functools import lru_cache
from typing import Any

from google import genai
from google.genai import errors, types

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


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
