"""FastAPI application entry point.

Run locally with::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.middleware.request_logging import RequestLoggingMiddleware
from app.routes import process as process_route

settings = get_settings()
_log_level = getattr(logging, settings.log_level, None)
logging.basicConfig(
    level=_log_level if isinstance(_log_level, int) else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)

app = FastAPI(
    title="KYC Automation Backend",
    description=(
        "FastAPI service that powers the Tiger Analytics KYC automation prototype. "
        "Accepts company documents and produces a fully populated KYC questionnaire "
        "by running per-section Gemini calls (one for answers with search grounding, "
        "one for document validation)."
    ),
    version="0.1.0",
)

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
    return {"status": "ok"}


app.include_router(process_route.router)
