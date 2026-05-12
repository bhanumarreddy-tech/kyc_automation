"""Thin wrapper around the Anthropic async SDK.

We use a single shared :class:`anthropic.AsyncAnthropic` client and expose
small helpers for the things this codebase actually needs:

* Extracting plain text from a Claude response.
* Parsing a Claude response as strict JSON, allowing for a response prefill
  (e.g. ``"{"``) and a few common formatting quirks.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from anthropic import AsyncAnthropic

from app.config import get_settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_client() -> AsyncAnthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        max_retries=settings.max_retries,
    )


def extract_text(message: Any) -> str:
    """Concatenate the text content blocks from an Anthropic message response."""
    chunks: list[str] = []
    for block in getattr(message, "content", []) or []:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            text = getattr(block, "text", "") or ""
            if text:
                chunks.append(text)
    return "".join(chunks)


_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


def _strip_code_fences(text: str) -> str:
    return _JSON_FENCE_RE.sub("", text).strip()


def parse_json_response(message: Any, prefill: str = "") -> Any:
    """Parse a Claude response body as JSON.

    ``prefill`` is the assistant prefix we asked the model to continue from
    (e.g. ``"{"``); it is prepended to the returned text before parsing.
    Robust to common formatting issues (markdown fences, trailing commentary,
    stray prose adjacent to the object).
    """

    def _try_parse_segment(segment: str) -> Any | None:
        stripped = segment.strip()
        cleaned = _strip_code_fences(stripped)
        if not cleaned.strip():
            return None
        body = cleaned.strip()
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            # Scan each `{` — raw_decode parses exactly one JSON value and skips
            # trailing whitespace. Prefer this over slicing first `{` … last `}`
            # which breaks when strings contain `}` or extra text is concatenated.
            for idx in range(len(body)):
                if body[idx] != "{":
                    continue
                try:
                    obj, _end = decoder.raw_decode(body, idx)
                    return obj
                except json.JSONDecodeError:
                    continue
            return None

    raw_concat = extract_text(message)
    combined = (prefill + raw_concat) if prefill else raw_concat

    parsed = _try_parse_segment(combined)
    if parsed is not None:
        return parsed

    # Collect non-empty strips (same ORDER as concatenation in extract_text).
    stripped_segments = [t.strip() for t in _assistant_text_segments(message) if t.strip()]

    # Newest-first: JSON often lands in a middle block while later blocks hold
    # stray explanations or truncation fragments.
    for seg in reversed(stripped_segments):
        candidate = (prefill + seg) if prefill else seg
        if candidate.strip() == combined.strip():
            continue
        parsed_seg = _try_parse_segment(candidate)
        if parsed_seg is not None:
            return parsed_seg

    logger.warning("Claude response did not contain parsable JSON")
    logger.debug("Combined text (prefix 4000 chars): %s", combined[:4000])
    raise json.JSONDecodeError("no JSON object decoded", combined, 0)


def _assistant_text_segments(message: Any) -> list[str]:
    """Raw ``text`` block bodies in assistant message order (non-empty strings)."""
    out: list[str] = []
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = getattr(block, "text", "") or ""
            if text:
                out.append(text)
    return out
