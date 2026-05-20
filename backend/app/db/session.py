"""Async SQLAlchemy engine and session factory (optional when DATABASE_URL is unset)."""

from __future__ import annotations

import ssl
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.db.models import Base

_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


def _asyncpg_safe_url(url: str) -> tuple[str, dict]:
    """asyncpg rejects ``sslmode`` as a keyword; strip it from the query string.

    When ``sslmode=require`` was present, enable TLS. Managed hosts (e.g. AWS RDS)
    may use intermediates that fail default verification from
    a Windows dev machine; use a permissive TLS context only in that ``require`` case.
    """

    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    connect_args: dict = {}
    keep: list[tuple[str, str]] = []
    want_permissive_tls = False
    for key, val in pairs:
        if key.lower() == "sslmode":
            mode = val.lower().strip()
            if mode == "require":
                want_permissive_tls = True
            elif mode in {"verify-ca", "verify-full"}:
                connect_args["ssl"] = ssl.create_default_context()
            continue
        keep.append((key, val))

    if want_permissive_tls:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ctx

    query = urlencode(keep)
    fixed = urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment)
    )
    return fixed, connect_args


def _async_database_url(url: str) -> str:
    """Use asyncpg driver for PostgreSQL URLs."""
    u = url.strip()
    if u.startswith("postgresql+asyncpg://"):
        return u
    if u.startswith("postgresql://"):
        return "postgresql+asyncpg://" + u.removeprefix("postgresql://")
    if u.startswith("postgres://"):
        return "postgresql+asyncpg://" + u.removeprefix("postgres://")
    return u


def db_session_maker() -> async_sessionmaker[AsyncSession] | None:
    """Returns the global async session factory, or ``None`` if the DB is disabled."""
    return _async_session_maker


async def _ensure_postgres_addon_columns(conn) -> None:
    """Add columns/tables introduced after first deploy (``create_all`` does not alter tables)."""

    if conn.engine.dialect.name != "postgresql":
        return

    # New JSONB column on existing table — without this, SELECTs from the ORM return 500 (undefined_column).
    await conn.execute(
        text(
            "ALTER TABLE kyc_submissions "
            "ADD COLUMN IF NOT EXISTS pipeline_intelligence JSONB"
        )
    )
    await conn.execute(
        text(
            "ALTER TABLE kyc_submission_metadata "
            "ADD COLUMN IF NOT EXISTS workflow_state JSONB NOT NULL DEFAULT '{}'::jsonb"
        )
    )
    await conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS kyc_intake_tokens (
                token VARCHAR(96) NOT NULL PRIMARY KEY,
                label VARCHAR(512) NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )


async def init_database() -> None:
    """Create engine, session factory, and tables when ``DATABASE_URL`` is set."""
    global _engine, _async_session_maker

    settings = get_settings()
    if not settings.database_url:
        return

    raw_url = _async_database_url(settings.database_url)
    async_url, connect_args = _asyncpg_safe_url(raw_url)
    _engine = create_async_engine(async_url, echo=False, connect_args=connect_args)
    _async_session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _ensure_postgres_addon_columns(conn)


async def dispose_database() -> None:
    """Dispose engine on shutdown."""
    global _engine, _async_session_maker

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _async_session_maker = None
