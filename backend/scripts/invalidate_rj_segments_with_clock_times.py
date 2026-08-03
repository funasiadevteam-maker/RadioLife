"""Invalidate cached RJ segments that contain clock-time hallucinations
('7 AM', '8 PM', '5 AM', '10 PM', etc.) baked in from the old prompt.
After this runs, the next listener radio request will regenerate fresh
segments with the new HINGLISH_SYSTEM_PROMPT (which forbids clock times)
and the new market-aware _ctx_for_now() (correct timezone).

Idempotent.  Also nukes warm_start_segments since those cache cold-start
audio under the same old prompt — only 2 rows, low blast radius.
"""
import asyncio
import os
import re
import sys

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

CLOCK_RGX = re.compile(
    r"\b\d{1,2}\s*(AM|PM|am|pm|a\.m\.|p\.m\.|:00|o[' ]?clock)\b")


async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

    # 1. segments — keep rows clean, delete rows with clock strings
    to_delete: list = []
    async for s in db.segments.find({}, {"_id": 1, "rj_script": 1}):
        txt = s.get("rj_script") or ""
        if CLOCK_RGX.search(txt):
            to_delete.append(s["_id"])
    print(f"segments to invalidate (had clock-time): {len(to_delete)}")
    if to_delete:
        r = await db.segments.delete_many({"_id": {"$in": to_delete}})
        print(f"  deleted_segments={r.deleted_count}")

    # 2. warm_start_segments — wipe (only 2 rows; will regenerate on next
    # cold-start under the new prompt + the new market-aware ctx).
    ws_count = await db.warm_start_segments.count_documents({})
    print(f"warm_start_segments to wipe: {ws_count}")
    if ws_count:
        r = await db.warm_start_segments.delete_many({})
        print(f"  deleted_warm_start={r.deleted_count}")

    # 3. rj_audios — also delete any with clock strings (defensive).
    rj_to_delete: list = []
    async for s in db.rj_audios.find({}, {"_id": 1, "script": 1}):
        txt = s.get("script") or ""
        if CLOCK_RGX.search(txt):
            rj_to_delete.append(s["_id"])
    print(f"rj_audios to invalidate: {len(rj_to_delete)}")
    if rj_to_delete:
        r = await db.rj_audios.delete_many({"_id": {"$in": rj_to_delete}})
        print(f"  deleted_rj_audios={r.deleted_count}")

    # 4. Final hygiene counts.
    s_after = await db.segments.count_documents({})
    ws_after = await db.warm_start_segments.count_documents({})
    print(f"FINAL: segments={s_after}  warm_start_segments={ws_after}")


if __name__ == "__main__":
    asyncio.run(main())
