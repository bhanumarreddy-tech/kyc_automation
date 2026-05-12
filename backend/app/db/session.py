"""Async SQLAlchemy engine and session factory (optional when DATABASE_URL is unset)."""

from __future__ import annotations

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


async def init_database() -> None:
    """Create engine, session factory, and tables when ``DATABASE_URL`` is set."""
    global _engine, _async_session_maker

    settings = get_settings()
    if not settings.database_url:
        return

    async_url = _async_database_url(settings.database_url)
    _engine = create_async_engine(async_url, echo=False)
    _async_session_maker = async_sessionmaker(
        _engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def dispose_database() -> None:
    """Dispose engine on shutdown."""
    global _engine, _async_session_maker

    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _async_session_maker = None
