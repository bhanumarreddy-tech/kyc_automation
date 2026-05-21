"""FastAPI application entry point.

Run locally with::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import text

from app.config import get_settings
from app.services.mlflow_tracing import configure as configure_mlflow_tracing
from app.db.session import db_session_maker, dispose_database, init_database
from app.middleware.request_logging import RequestLoggingMiddleware
from app.routes import history as history_route
from app.routes import intake as intake_route
from app.routes import narrative as narrative_route
from app.routes import process as process_route

settings = get_settings()
_log_level = getattr(logging, settings.log_level, None)
logging.basicConfig(
    level=_log_level if isinstance(_log_level, int) else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)

_http_logger = logging.getLogger("app.http")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_mlflow_tracing()
    await init_database()
    yield
    await dispose_database()


app = FastAPI(
    title="KYC Automation Backend",
    description=(
        "FastAPI service that powers the Tiger Analytics KYC automation prototype. "
        "Accepts company documents and produces a fully populated KYC questionnaire "
        "by running per-section Gemini calls (one for answers with search grounding, "
        "one for document validation)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(HTTPException)
async def _log_http_exception(request: Request, exc: HTTPException):
    if exc.status_code >= 400:
        _http_logger.warning(
            "%s %s -> HTTP %s detail=%r",
            request.method,
            request.url.path,
            exc.status_code,
            exc.detail,
        )
    return await http_exception_handler(request, exc)


@app.exception_handler(RequestValidationError)
async def _log_request_validation(request: Request, exc: RequestValidationError):
    _http_logger.warning(
        "%s %s -> validation failed: %s",
        request.method,
        request.url.path,
        exc.errors(),
    )
    return await request_validation_exception_handler(request, exc)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Last added runs first: log full request duration including CORS for every call.
app.add_middleware(RequestLoggingMiddleware)


@app.get("/api/health")
async def healthcheck() -> dict[str, str]:
    """Liveness plus whether submission History can persist (Postgres)."""
    out: dict[str, str] = {"status": "ok"}
    settings = get_settings()
    if not settings.database_url:
        out["database"] = "disabled"
        return out

    maker = db_session_maker()
    if maker is None:
        out["database"] = "disabled"
        return out

    try:
        async with maker() as session:
            await session.execute(text("SELECT 1"))
        out["database"] = "connected"
    except Exception:
        _http_logger.exception("health database probe failed")
        out["database"] = "error"
    return out


app.include_router(process_route.router)
app.include_router(history_route.router)
app.include_router(intake_route.router)
app.include_router(narrative_route.router)
