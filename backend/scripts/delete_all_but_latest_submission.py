"""One-off: delete all rows in kyc_submissions except the one with newest created_at.

Usage (from backend directory)::

    python scripts/delete_all_but_latest_submission.py

Requires DATABASE_PASSWORD (or POSTGRES_PASSWORD / PGPASSWORD) in .env — same as the API.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
load_dotenv(_BACKEND / ".env", override=True)


DELETE_SQL = """
DELETE FROM kyc_submissions
WHERE id <> (
  SELECT id
  FROM kyc_submissions
  ORDER BY created_at DESC NULLS LAST, id DESC
  LIMIT 1
);
"""


async def main() -> int:
    from app.config import get_settings
    from app.db.session import _async_database_url

    settings = get_settings()
    db_url = settings.database_url
    if not db_url:
        print("No database URL resolved. Set DATABASE_PASSWORD (or Postgres password) in .env.")
        return 1

    # Asyncpg does not accept sslmode=? in the URL; use connect_args ssl instead when required.
    base_url = db_url.split("?", 1)[0].strip()
    connect_args = {}
    if "?sslmode=require" in db_url or "&sslmode=require" in db_url:
        connect_args["ssl"] = "require"

    engine = create_async_engine(
        _async_database_url(base_url),
        echo=False,
        connect_args=connect_args if connect_args else {},
    )
    try:
        async with engine.begin() as conn:
            before = (
                await conn.execute(text("SELECT COUNT(*) FROM kyc_submissions"))
            ).scalar_one()
            latest = (
                await conn.execute(
                    text(
                        """SELECT id, created_at::text FROM kyc_submissions
                        ORDER BY created_at DESC NULLS LAST, id DESC LIMIT 1"""
                    )
                )
            ).fetchone()
            print(f"kyc_submissions row count before: {before}")
            if latest:
                print(f"Keeping newest row id={latest[0]} created_at={latest[1]}")
            else:
                print("Table empty; nothing to delete.")
                return 0

            result = await conn.execute(text(DELETE_SQL))
            deleted = result.rowcount
            after = (
                await conn.execute(text("SELECT COUNT(*) FROM kyc_submissions"))
            ).scalar_one()
            print(f"Deleted rows (driver rowcount): {deleted}")
            print(f"kyc_submissions row count after: {after}")
    finally:
        await engine.dispose()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
