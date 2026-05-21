"""Tests for Postgres URL resolution in app.config."""

from __future__ import annotations

import pytest

from app.config import _resolve_database_url, get_settings


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch):
    for name in (
        "RAILWAY_ENVIRONMENT",
        "RAILWAY_PROJECT_ID",
        "RAILWAY_SERVICE_ID",
        "DATABASE_URL",
        "DATABASE_PUBLIC_URL",
        "POSTGRES_URL",
        "PGHOST",
        "PGPORT",
        "PGUSER",
        "PGPASSWORD",
        "POSTGRES_PASSWORD",
        "PGDATABASE",
        "POSTGRES_DB",
    ):
        monkeypatch.delenv(name, raising=False)
    _clear_settings_cache()
    yield
    _clear_settings_cache()


def test_railway_prefers_database_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@postgres.railway.internal:5432/railway")
    monkeypatch.setenv(
        "DATABASE_PUBLIC_URL",
        "postgresql://u:p@proxy.rlwy.net:41305/railway",
    )
    assert _resolve_database_url() == "postgresql://u:p@postgres.railway.internal:5432/railway"


def test_railway_falls_back_to_database_public_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "staging")
    monkeypatch.setenv(
        "DATABASE_PUBLIC_URL",
        "postgresql://u:p@kodama.proxy.rlwy.net:41305/railway",
    )
    url = _resolve_database_url()
    assert url is not None
    assert "kodama.proxy.rlwy.net:41305" in url
    assert "sslmode=require" in url


def test_local_uses_database_public_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(
        "DATABASE_PUBLIC_URL",
        "postgresql://u:p@kodama.proxy.rlwy.net:41305/railway",
    )
    url = _resolve_database_url()
    assert url is not None
    assert "sslmode=require" in url


def test_railway_builds_from_pg_parts_when_no_url(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.setenv("PGHOST", "postgres.railway.internal")
    monkeypatch.setenv("PGPORT", "5432")
    monkeypatch.setenv("PGUSER", "postgres")
    monkeypatch.setenv("PGPASSWORD", "secret")
    monkeypatch.setenv("PGDATABASE", "railway")
    url = _resolve_database_url()
    assert url == "postgresql://postgres:secret@postgres.railway.internal:5432/railway"


def test_returns_none_when_incomplete(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("PGPASSWORD", "only-password")
    assert _resolve_database_url() is None
