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
    Robust to common formatting issues (markdown fences, trailing commentary).
    """
    raw = extract_text(message)
    combined = (prefill + raw) if prefill else raw
    cleaned = _strip_code_fences(combined)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to pick out the first JSON object in the string.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except json.JSONDecodeError as exc:
                logger.warning("Failed to parse Claude response as JSON: %s", exc)
                logger.debug("Raw text was: %s", cleaned)
                raise
        logger.warning("Claude response did not contain a JSON object")
        logger.debug("Raw text was: %s", cleaned)
        raise
