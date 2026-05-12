"""Serve the FastAPI app with ``python -m app`` — honors ``PORT`` as an integer (no shell)."""

from __future__ import annotations

import os
import sys

import uvicorn


def _port(default: int = 8000) -> int:
    raw = os.environ.get("PORT", str(default)).strip()
    try:
        return int(raw)
    except ValueError:
        if raw != str(default):
            print(
                f"Invalid PORT={raw!r}; using default {default}. "
                "Set PORT to digits only (not shell syntax like '${PORT:-8000}').",
                file=sys.stderr,
            )
        return default


def main() -> None:
    reload = os.environ.get("UVICORN_RELOAD", "").lower() in {"1", "true", "yes"}
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=_port(),
        reload=reload,
    )


if __name__ == "__main__":
    main()
