"""Phase 23 Session 4.5 — flip is_advertiser=true on test@bigfm.dubai
so the wizard's e2e tester can reach /advertiser/games/new.

Idempotent — running twice is a no-op (the $set is the same shape).
"""
from __future__ import annotations
import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient


async def grant(email: str = "test@bigfm.dubai") -> bool:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
              os.environ["DB_NAME"]]
    r = await db.users.update_one(
        {"email": email.lower()},
        {"$set": {"is_advertiser": True}})
    print(f"granted is_advertiser=True on {email}: matched={r.matched_count} "
                f"modified={r.modified_count}")
    return r.matched_count > 0


if __name__ == "__main__":
    asyncio.run(grant())
