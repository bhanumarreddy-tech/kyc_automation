"""Runtime configuration loaded from environment variables.."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv(override=True)

# Default model for answer + validation calls. Claude Opus 4.7 is the strongest
# general Claude API model paired with ``web_search_20260209`` (dynamic-filter
# web search). Override via ANTHROPIC_MODEL when needed.
DEFAULT_ANTHROPIC_MODEL = "claude-opus-4-7"

# Latest web-search server tool (`web_search_20260209`): uses code-assisted
# filtering so less raw HTML floods the context than ``web_search_20250305``.
# Fallback: set WEB_SEARCH_TOOL_TYPE=web_search_20250305 for older stacks.
DEFAULT_WEB_SEARCH_TOOL_TYPE = "web_search_20260209"


def _parse_origins(raw: str | None) -> list[str]:
    if not raw:
        return [
            "http://localhost:8080",
            "http://localhost:5173",
            "http://127.0.0.1:8080",
            "http://127.0.0.1:5173",
        ]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    anthropic_model: str
    max_file_mb: int
    max_web_searches: int
    web_search_tool_type: str
    web_search_direct_only: bool
    cors_origins: list[str] = field(default_factory=list)
    # NOTE: Web search consumes large input payloads (worst-case projection per
    # request scales with MAX_WEB_SEARCHES). Starter tiers need low max_uses
    # plus sequential answering (ANSWER_INTER_CALL_DELAY_SECONDS).
    answer_concurrency: int = 1
    answer_inter_call_delay_seconds: float = 0.0
    validation_concurrency: int = 2
    validation_attach_documents: bool = False
    enable_prompt_caching: bool = True
    max_retries: int = 5


def _parse_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _parse_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    model_raw = os.environ.get("ANTHROPIC_MODEL", "").strip()
    model = model_raw if model_raw else DEFAULT_ANTHROPIC_MODEL
    ws_tool_raw = os.environ.get("WEB_SEARCH_TOOL_TYPE", "").strip()
    web_search_tool_type = ws_tool_raw or DEFAULT_WEB_SEARCH_TOOL_TYPE
    return Settings(
        anthropic_api_key=api_key,
        anthropic_model=model,
        max_file_mb=_parse_int("MAX_FILE_MB", 20),
        # Typical default for Opus + web_search_20260209; lower to 1 for the
        # 30k input-tokens/min tier (see deployment notes in .env.example).
        max_web_searches=_parse_int("MAX_WEB_SEARCHES", 10),
        web_search_tool_type=web_search_tool_type,
        web_search_direct_only=_parse_bool("WEB_SEARCH_DIRECT_ONLY", False),
        cors_origins=_parse_origins(os.environ.get("CORS_ORIGINS")),
        answer_concurrency=_parse_int("ANSWER_CONCURRENCY", 1),
        answer_inter_call_delay_seconds=_parse_float(
            "ANSWER_INTER_CALL_DELAY_SECONDS", 0.0
        ),
        validation_concurrency=_parse_int("VALIDATION_CONCURRENCY", 2),
        validation_attach_documents=_parse_bool("VALIDATION_ATTACH_DOCUMENTS", False),
        enable_prompt_caching=_parse_bool("ENABLE_PROMPT_CACHING", True),
        max_retries=_parse_int("MAX_RETRIES", 5),
    )
