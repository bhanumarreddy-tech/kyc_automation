"""Runtime configuration: secrets from environment, tuning from module constants."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import quote_plus

from dotenv import load_dotenv

load_dotenv(override=True)


# ---------------------------------------------------------------------------
# Non-secret tuning (change here; not via environment)
# ---------------------------------------------------------------------------

# Answer phase: JSON schema + Google Search (prefer Gemini 3.x class models).
GEMINI_MODEL_ANSWER = "gemini-3-flash-preview"

# Validation / validation-sources phase (e.g. Gemini 2.5 Pro).
# GEMINI_MODEL_VALIDATION = "gemini-2.5-pro"
GEMINI_MODEL_VALIDATION = "gemini-3-flash-preview"
LOG_LEVEL = "INFO"

CORS_ALLOWED_ORIGINS: tuple[str, ...] = (
    "http://localhost:8080",
    "http://localhost:5173",
    "http://127.0.0.1:8080",
    "http://127.0.0.1:5173",
    "https://kycautomation.bhanu-marreddy.workers.dev",
)

# Pipeline concurrency (respect API quota in production).
ANSWER_CONCURRENCY = 8
ANSWER_INTER_CALL_DELAY_SECONDS = 0.0
VALIDATION_CONCURRENCY = 2

# When True, send raw PDF/image bytes to validation calls; else extracted text only.
VALIDATION_ATTACH_DOCUMENTS = False

# ~75% of typical Gemini file limits (50 MiB PDF, 7 MiB text-style, 1000 pages,
# 3000 files) plus ~75% text budgets vs prior app defaults.
VALIDATION_MAX_PDF_BYTES = 39_321_600  # 0.75 × 50 MiB
VALIDATION_MAX_IMAGE_BYTES = 5_505_024  # 0.75 × 7 MiB
VALIDATION_MAX_TOTAL_TEXT_CHARS = 225_000
VALIDATION_MAX_TEXT_PREVIEW_CHARS = 37_500
VALIDATION_MAX_NATIVE_PARTS_PER_REQUEST = 2250  # 0.75 × 3000 files/prompt
VALIDATION_MAX_PAGES_PER_PDF_SLICE = 750  # 0.75 × 1000 pages
VALIDATION_TEXT_CHUNK_CHARS = 36_000

VALIDATION_USE_CHUNK_RETRIEVAL = False
VALIDATION_RETRIEVAL_CHUNK_TARGET_CHARS = 2250
VALIDATION_RETRIEVAL_TOP_CHUNKS = 36
VALIDATION_RETRIEVAL_RECALL_CHUNKS = 72

ENABLE_PROMPT_CACHING = True

GEMINI_OVERLOAD_EXTRA_ATTEMPTS = 3
GEMINI_OVERLOAD_BASE_DELAY_SECONDS = 10.0

# User-supplied reference URLs (fetched server-side for validation only).
REFERENCE_URL_MAX_PER_REQUEST = 20
REFERENCE_URL_MAX_RESPONSE_BYTES = 5_242_880  # 5 MiB per URL
REFERENCE_URL_FETCH_TIMEOUT_SECONDS = 30.0
REFERENCE_URL_MAX_REDIRECTS = 5
REFERENCE_URL_MAX_TEXT_CHARS = 120_000  # per URL after extraction/truncation


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


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    gemini_validation_model: str
    database_url: str | None = None
    log_level: str = "INFO"
    cors_origins: list[str] = field(default_factory=list)
    answer_concurrency: int = 1
    answer_inter_call_delay_seconds: float = 0.0
    validation_concurrency: int = 2
    validation_attach_documents: bool = False
    validation_max_pdf_bytes: int = VALIDATION_MAX_PDF_BYTES
    validation_max_image_bytes: int = VALIDATION_MAX_IMAGE_BYTES
    validation_max_total_text_chars: int = VALIDATION_MAX_TOTAL_TEXT_CHARS
    validation_max_text_preview_chars: int = VALIDATION_MAX_TEXT_PREVIEW_CHARS
    validation_max_native_parts_per_request: int = VALIDATION_MAX_NATIVE_PARTS_PER_REQUEST
    validation_max_pages_per_pdf_slice: int = VALIDATION_MAX_PAGES_PER_PDF_SLICE
    validation_text_chunk_chars: int = VALIDATION_TEXT_CHUNK_CHARS
    validation_use_chunk_retrieval: bool = VALIDATION_USE_CHUNK_RETRIEVAL
    validation_retrieval_chunk_target_chars: int = VALIDATION_RETRIEVAL_CHUNK_TARGET_CHARS
    validation_retrieval_top_chunks: int = VALIDATION_RETRIEVAL_TOP_CHUNKS
    validation_retrieval_recall_chunks: int = VALIDATION_RETRIEVAL_RECALL_CHUNKS
    enable_prompt_caching: bool = ENABLE_PROMPT_CACHING
    overload_extra_attempts: int = GEMINI_OVERLOAD_EXTRA_ATTEMPTS
    overload_base_delay_seconds: float = GEMINI_OVERLOAD_BASE_DELAY_SECONDS
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    reference_url_max_per_request: int = REFERENCE_URL_MAX_PER_REQUEST
    reference_url_max_response_bytes: int = REFERENCE_URL_MAX_RESPONSE_BYTES
    reference_url_fetch_timeout_seconds: float = REFERENCE_URL_FETCH_TIMEOUT_SECONDS
    reference_url_max_redirects: int = REFERENCE_URL_MAX_REDIRECTS
    reference_url_max_text_chars: int = REFERENCE_URL_MAX_TEXT_CHARS

    def s3_ready(self) -> bool:
        return bool(
            self.s3_endpoint_url
            and self.s3_bucket
            and self.s3_access_key_id
            and self.s3_secret_access_key
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    api_key = (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("GOOGLE_API_KEY", "").strip()
    )
    database_url = _resolve_database_url()

    s3_endpoint = os.environ.get("S3_ENDPOINT_URL", "").strip() or None
    s3_region_raw = os.environ.get("S3_REGION", "").strip().lower()
    s3_region = (
        os.environ.get("S3_REGION", "").strip()
        if s3_region_raw and s3_region_raw != "auto"
        else "us-east-1"
    )
    s3_bucket = os.environ.get("S3_BUCKET", "").strip() or None
    s3_access = os.environ.get("S3_ACCESS_KEY_ID", "").strip() or None
    s3_secret = os.environ.get("S3_SECRET_ACCESS_KEY", "").strip() or None

    return Settings(
        gemini_api_key=api_key,
        gemini_model=GEMINI_MODEL_ANSWER,
        gemini_validation_model=GEMINI_MODEL_VALIDATION,
        database_url=database_url,
        log_level=LOG_LEVEL,
        cors_origins=list(CORS_ALLOWED_ORIGINS),
        answer_concurrency=ANSWER_CONCURRENCY,
        answer_inter_call_delay_seconds=ANSWER_INTER_CALL_DELAY_SECONDS,
        validation_concurrency=VALIDATION_CONCURRENCY,
        validation_attach_documents=VALIDATION_ATTACH_DOCUMENTS,
        validation_max_pdf_bytes=VALIDATION_MAX_PDF_BYTES,
        validation_max_image_bytes=VALIDATION_MAX_IMAGE_BYTES,
        validation_max_total_text_chars=VALIDATION_MAX_TOTAL_TEXT_CHARS,
        validation_max_text_preview_chars=VALIDATION_MAX_TEXT_PREVIEW_CHARS,
        validation_max_native_parts_per_request=VALIDATION_MAX_NATIVE_PARTS_PER_REQUEST,
        validation_max_pages_per_pdf_slice=VALIDATION_MAX_PAGES_PER_PDF_SLICE,
        validation_text_chunk_chars=VALIDATION_TEXT_CHUNK_CHARS,
        validation_use_chunk_retrieval=VALIDATION_USE_CHUNK_RETRIEVAL,
        validation_retrieval_chunk_target_chars=VALIDATION_RETRIEVAL_CHUNK_TARGET_CHARS,
        validation_retrieval_top_chunks=VALIDATION_RETRIEVAL_TOP_CHUNKS,
        validation_retrieval_recall_chunks=VALIDATION_RETRIEVAL_RECALL_CHUNKS,
        enable_prompt_caching=ENABLE_PROMPT_CACHING,
        overload_extra_attempts=GEMINI_OVERLOAD_EXTRA_ATTEMPTS,
        overload_base_delay_seconds=GEMINI_OVERLOAD_BASE_DELAY_SECONDS,
        s3_endpoint_url=s3_endpoint,
        s3_region=s3_region if s3_region else "us-east-1",
        s3_bucket=s3_bucket,
        s3_access_key_id=s3_access,
        s3_secret_access_key=s3_secret,
        reference_url_max_per_request=REFERENCE_URL_MAX_PER_REQUEST,
        reference_url_max_response_bytes=REFERENCE_URL_MAX_RESPONSE_BYTES,
        reference_url_fetch_timeout_seconds=REFERENCE_URL_FETCH_TIMEOUT_SECONDS,
        reference_url_max_redirects=REFERENCE_URL_MAX_REDIRECTS,
        reference_url_max_text_chars=REFERENCE_URL_MAX_TEXT_CHARS,
    )
