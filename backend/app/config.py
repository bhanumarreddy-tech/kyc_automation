"""Runtime configuration loaded from environment variables.."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv(override=True)

# Default Gemini model when GEMINI_MODEL is unset (Gemini 3.1 Flash — preview ID).
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-preview"

# Railway Postgres — non-secret connection defaults (match Railway Postgres plugin outputs).
# Password comes only from env (DATABASE_PASSWORD / POSTGRES_PASSWORD / PGPASSWORD).
RAILWAY_PG_USER = "postgres"
RAILWAY_PG_DATABASE = "railway"
RAILWAY_PG_PUBLIC_HOST = "yamabiko.proxy.rlwy.net"
RAILWAY_PG_PUBLIC_PORT = 47180
RAILWAY_PG_INTERNAL_HOST = "postgres.railway.internal"
RAILWAY_PG_INTERNAL_PORT = 5432


def _running_on_railway() -> bool:
    """Prefer internal TCP when the API itself is deployed on Railway."""
    return bool(
        os.environ.get("RAILWAY_ENVIRONMENT", "").strip()
        or os.environ.get("RAILWAY_PROJECT_ID", "").strip()
        or os.environ.get("RAILWAY_SERVICE_ID", "").strip()
    )


def _postgres_password() -> str:
    return (
        os.environ.get("DATABASE_PASSWORD", "").strip()
        or os.environ.get("POSTGRES_PASSWORD", "").strip()
        or os.environ.get("PGPASSWORD", "").strip()
    )


def _resolve_database_url() -> str | None:
    """Build async Postgres URL from password env vars + hardcoded Railway endpoints."""
    password = _postgres_password()
    if not password:
        return None

    user_q = quote_plus(RAILWAY_PG_USER)
    pwd_q = quote_plus(password)

    if _running_on_railway():
        host = RAILWAY_PG_INTERNAL_HOST
        port = RAILWAY_PG_INTERNAL_PORT
        suffix = ""
    else:
        host = RAILWAY_PG_PUBLIC_HOST
        port = RAILWAY_PG_PUBLIC_PORT
        suffix = "?sslmode=require"

    return (
        f"postgresql://{user_q}:{pwd_q}@{host}:{port}/{RAILWAY_PG_DATABASE}{suffix}"
    )


def _parse_origins(raw: str | None) -> list[str]:
    if not raw:
        return [
            "http://localhost:8080",
            "http://localhost:5173",
            "http://127.0.0.1:8080",
            "http://127.0.0.1:5173",
        ]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]

# Normalize the log level
def _normalize_log_level(raw: str | None, default: str = "INFO") -> str:
    if not raw or not raw.strip():
        return default
    return raw.strip().upper()


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    database_url: str | None = None
    log_level: str = "INFO"
    cors_origins: list[str] = field(default_factory=list)
    answer_concurrency: int = 1
    answer_inter_call_delay_seconds: float = 0.0
    validation_concurrency: int = 2
    validation_attach_documents: bool = False
    enable_prompt_caching: bool = True
    # After SDK retries, quota/overload can still surface; extra backoff rounds.
    overload_extra_attempts: int = 3
    overload_base_delay_seconds: float = 10.0


def _parse_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(minimum, value)


def _parse_int_min0(name: str, default: int) -> int:
    """Like ``_parse_int`` but allows zero (e.g. disable optional retries)."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(0, value)


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
    api_key = (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )
    model_raw = os.environ.get("GEMINI_MODEL", "").strip()
    model = model_raw if model_raw else DEFAULT_GEMINI_MODEL
    database_url = _resolve_database_url()
    return Settings(
        gemini_api_key=api_key,
        gemini_model=model,
        database_url=database_url,
        log_level=_normalize_log_level(os.environ.get("LOG_LEVEL")),
        cors_origins=_parse_origins(os.environ.get("CORS_ORIGINS")),
        answer_concurrency=_parse_int("ANSWER_CONCURRENCY", 1),
        answer_inter_call_delay_seconds=_parse_float(
            "ANSWER_INTER_CALL_DELAY_SECONDS", 0.0
        ),
        validation_concurrency=_parse_int("VALIDATION_CONCURRENCY", 2),
        validation_attach_documents=_parse_bool("VALIDATION_ATTACH_DOCUMENTS", False),
        enable_prompt_caching=_parse_bool("ENABLE_PROMPT_CACHING", True),
        overload_extra_attempts=_parse_int_min0("GEMINI_OVERLOAD_EXTRA_ATTEMPTS", 3),
        overload_base_delay_seconds=_parse_float(
            "GEMINI_OVERLOAD_BASE_DELAY_SECONDS", 10.0, minimum=1.0
        ),
    )
