"""Database URL resolution from environment."""

from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_database_url_from_direct_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://u:p@custom.example.com:5432/mydb?sslmode=require",
    )
    monkeypatch.delenv("DATABASE_PASSWORD", raising=False)
    settings = get_settings()
    assert settings.database_url == "postgresql://u:p@custom.example.com:5432/mydb?sslmode=require"


def test_database_url_from_pghost_and_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PGHOST", "db.example.com")
    monkeypatch.setenv("PGPORT", "5433")
    monkeypatch.setenv("PGUSER", "app")
    monkeypatch.setenv("PGDATABASE", "kyc")
    monkeypatch.setenv("PGSSLMODE", "require")
    monkeypatch.setenv("DATABASE_PASSWORD", "s3cret")
    settings = get_settings()
    assert settings.database_url == "postgresql://app:s3cret@db.example.com:5433/kyc?sslmode=require"


def test_database_url_uses_aws_rds_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PGHOST", raising=False)
    monkeypatch.setenv("DATABASE_PASSWORD", "pw")
    settings = get_settings()
    assert settings.database_url is not None
    assert "aws-apg-erin-house.cluster-cifq6cg8gcxc.us-east-1.rds.amazonaws.com" in (
        settings.database_url
    )
    assert settings.database_url.endswith("/postgres?sslmode=require")
    assert ":pw@" in settings.database_url


def test_database_url_unset_without_password(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_PASSWORD", raising=False)
    monkeypatch.delenv("PGPASSWORD", raising=False)
    settings = get_settings()
    assert settings.database_url is None
