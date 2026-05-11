"""Runtime configuration loaded from environment variables.."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv(override=True)


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
    cors_origins: list[str] = field(default_factory=list)
    answer_concurrency: int = 4
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


def _parse_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5").strip() or "claude-sonnet-4-5"
    return Settings(
        anthropic_api_key=api_key,
        anthropic_model=model,
        max_file_mb=_parse_int("MAX_FILE_MB", 20),
        max_web_searches=_parse_int("MAX_WEB_SEARCHES", 10),
        cors_origins=_parse_origins(os.environ.get("CORS_ORIGINS")),
        answer_concurrency=_parse_int("ANSWER_CONCURRENCY", 4),
        validation_concurrency=_parse_int("VALIDATION_CONCURRENCY", 2),
        validation_attach_documents=_parse_bool("VALIDATION_ATTACH_DOCUMENTS", False),
        enable_prompt_caching=_parse_bool("ENABLE_PROMPT_CACHING", True),
        max_retries=_parse_int("MAX_RETRIES", 5),
    )
