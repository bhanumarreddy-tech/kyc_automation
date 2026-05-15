"""Ephemeral public-intake tokens (share ``/intake/{token}`` with a client)."""

from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException

from app.db.session import db_session_maker
from app.db.submissions import get_intake_token, mint_intake_token

router = APIRouter(prefix="/api", tags=["intake"])


@router.post("/intake/tokens")
async def create_intake_share_token(label: str = Form("")) -> dict[str, str]:
    maker = db_session_maker()
    if maker is None:
        raise HTTPException(
            status_code=503,
            detail="Database is not configured (needed to mint intake tokens)",
        )
    async with maker() as session:
        token = await mint_intake_token(session, label)
        await session.commit()
    return {"token": token, "intakePath": f"/intake/{token}"}


@router.get("/intake/tokens/{token}")
async def read_intake_share_token(token: str) -> dict[str, object]:
    maker = db_session_maker()
    if maker is None:
        return {"valid": False, "reason": "database_unavailable"}
    async with maker() as session:
        row = await get_intake_token(session, token)
    if row is None:
        return {"valid": False, "label": ""}
    return {"valid": True, "label": str(row.label or "")}
