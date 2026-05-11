"""FastAPI application entry point.

Run locally with::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes import process as process_route

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
)

settings = get_settings()

app = FastAPI(
    title="KYC Automation Backend",
    description=(
        "FastAPI service that powers the Tiger Analytics KYC automation prototype. "
        "Accepts company documents and produces a fully populated KYC questionnaire "
        "by running per-section Claude calls (one for answers, one for document validation)."
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


@app.get("/api/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(process_route.router)
