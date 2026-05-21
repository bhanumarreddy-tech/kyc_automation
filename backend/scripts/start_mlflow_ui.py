#!/usr/bin/env python3
"""Start MLflow UI with Postgres tracking on Railway or file storage locally."""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import quote_plus


def _env_first(*names: str) -> str:
    for name in names:
        val = os.environ.get(name, "").strip()
        if val:
            return val
    return ""


def _running_on_railway() -> bool:
    return bool(
        os.environ.get("RAILWAY_ENVIRONMENT", "").strip()
        or os.environ.get("RAILWAY_PROJECT_ID", "").strip()
        or os.environ.get("RAILWAY_SERVICE_ID", "").strip()
    )


def _postgres_password() -> str:
    return _env_first("POSTGRES_PASSWORD", "PGPASSWORD", "DATABASE_PASSWORD")


def _postgres_db_name() -> str:
    return _env_first("PGDATABASE", "POSTGRES_DB")


def _build_database_url(
    *,
    host: str,
    port: str,
    user: str,
    password: str,
    database: str,
    sslmode: str | None = None,
) -> str | None:
    if not all([host, port, user, password, database]):
        return None
    try:
        port_int = int(port)
    except ValueError:
        return None
    user_q = quote_plus(user)
    pwd_q = quote_plus(password)
    suffix = f"?sslmode={sslmode}" if sslmode else ""
    return f"postgresql://{user_q}:{pwd_q}@{host}:{port_int}/{database}{suffix}"


def _ensure_public_ssl(url: str) -> str:
    if "sslmode=" in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}sslmode=require"


def resolve_database_url() -> str | None:
    """Resolve Postgres URL from Railway-style env vars."""
    for name in ("DATABASE_URL", "POSTGRES_URL", "DATABASE_PUBLIC_URL"):
        url = os.environ.get(name, "").strip()
        if not url:
            continue
        if name == "DATABASE_PUBLIC_URL":
            return _ensure_public_ssl(url)
        return url
    sslmode = "require" if not _running_on_railway() else None
    return _build_database_url(
        host=_env_first("PGHOST"),
        port=_env_first("PGPORT"),
        user=_env_first("PGUSER"),
        password=_postgres_password(),
        database=_postgres_db_name(),
        sslmode=sslmode,
    )


def _is_file_tracking_uri(uri: str) -> bool:
    u = uri.strip().lower()
    return u.startswith("file:") or u in {"./mlruns", "mlruns"}


def resolve_tracking_uri() -> str:
    """Prefer Postgres over inherited ``file:./mlruns`` from shared Railway env."""
    db_url = resolve_database_url()
    if db_url:
        return db_url

    explicit = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
    if explicit and not _is_file_tracking_uri(explicit):
        return explicit
    if explicit:
        return explicit

    raise SystemExit(
        "error: no MLflow tracking store configured. "
        "Link Postgres to this Railway service (DATABASE_URL) or set "
        "MLFLOW_TRACKING_URI to a postgresql:// URL."
    )


def _redact_url(url: str) -> str:
    return re.sub(r"(://[^:/@]+:)[^@]+(@)", r"\1***\2", url, count=1)


def _workers() -> str:
    return os.environ.get("MLFLOW_UI_WORKERS", "1").strip() or "1"


def _serve_artifacts() -> bool:
    raw = os.environ.get("MLFLOW_SERVE_ARTIFACTS", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return False


def _artifact_root() -> str:
    return os.environ.get("MLFLOW_DEFAULT_ARTIFACT_ROOT", "file:///tmp/mlartifacts").strip()


def _allowed_hosts() -> str | None:
    explicit = os.environ.get("MLFLOW_ALLOWED_HOSTS", "").strip()
    if explicit:
        return explicit
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if domain:
        return f"localhost,127.0.0.1,{domain}"
    if _running_on_railway():
        return "*"
    return None


def _cors_allowed_origins() -> str | None:
    explicit = os.environ.get("MLFLOW_CORS_ALLOWED_ORIGINS", "").strip()
    if explicit:
        return explicit
    domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if domain:
        return f"https://{domain}"
    if _running_on_railway():
        return "*"
    return None


def main() -> None:
    uri = resolve_tracking_uri()
    port = os.environ.get("PORT", "5000").strip() or "5000"
    workers = _workers()
    serve_artifacts = _serve_artifacts()
    artifact_root = _artifact_root()

    print(
        f"Starting MLflow UI on 0.0.0.0:{port} "
        f"backend={_redact_url(uri)} "
        f"workers={workers} "
        f"serve_artifacts={serve_artifacts} "
        f"artifact_root={artifact_root}"
    )
    if _running_on_railway():
        print(
            "Railway: ensure Networking → Target port matches $PORT "
            f"(currently {port}). Health check path: /health",
            file=sys.stderr,
        )
        print(
            "Railway: allocate at least 1 GB RAM for this service. "
            "Exit code -9 (SIGKILL) on 512 MB usually means OOM.",
            file=sys.stderr,
        )
    if _is_file_tracking_uri(uri):
        print(
            "warning: using file-based MLflow store; link Postgres on Railway for shared traces",
            file=sys.stderr,
        )

    # Build the mlflow ui command.  --gunicorn-opts was removed in MLflow 3.x,
    # so only include it when running on a 2.x release.
    import importlib.metadata

    try:
        _mlflow_version = tuple(
            int(x) for x in importlib.metadata.version("mlflow").split(".")[:2]
        )
    except Exception:
        _mlflow_version = (2, 0)

    cmd = [
        "mlflow",
        "ui",
        "--host",
        "0.0.0.0",
        "--port",
        port,
        "--workers",
        workers,
        "--backend-store-uri",
        uri,
        "--registry-store-uri",
        uri,
        "--default-artifact-root",
        artifact_root,
    ]
    if _mlflow_version < (3, 0):
        cmd += [
            "--gunicorn-opts",
            "--timeout 120 --graceful-timeout 30 --log-level info",
        ]
    else:
        allowed_hosts = _allowed_hosts()
        if allowed_hosts:
            cmd += ["--allowed-hosts", allowed_hosts]
        cors_origins = _cors_allowed_origins()
        if cors_origins:
            cmd += ["--cors-allowed-origins", cors_origins]
    if not serve_artifacts:
        cmd.append("--no-serve-artifacts")

    # Replace this wrapper process so we do not keep two Python runtimes in memory.
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
