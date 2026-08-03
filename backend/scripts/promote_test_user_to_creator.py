"""Idempotent one-shot: promote `test@bigfm.dubai` to creator role + approved.

Run:
    python /app/backend/scripts/promote_test_user_to_creator.py

Second run reports all counts as 0.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone


TARGET_EMAIL = "test@bigfm.dubai"


async def promote(db) -> dict:
    summary = {"role_changed": 0,
                  "creator_status_set": 0,
                  "creator_id_set": 0,
                  "creator_row_created": 0,
                  "creator_row_updated_to_approved": 0,
                  "demo_channel_seeded": 0}

    user = await db.users.find_one({"email": TARGET_EMAIL})
    if not user:
        print(f"!! user {TARGET_EMAIL} not found — aborting")
        return {**summary, "error": "user_not_found"}

    uid = user["user_id"]
    now = datetime.now(timezone.utc)

    # ── creator row ────────────────────────────────────────────────────
    creator = await db.podcast_creators.find_one({"user_id": uid})
    if not creator:
        cid = "crt_" + uuid.uuid4().hex[:14]
        await db.podcast_creators.insert_one({
            "_id": cid, "id": cid, "user_id": uid,
            "display_name": user.get("name") or "Test Listener Creator",
            "contact_email": TARGET_EMAIL,
            "bio": "Demo creator seeded for end-to-end testing.",
            "market": user.get("market") or "dubai",
            "application_status": "approved",
            "approved_at": now,
            "applied_at": now,
            "created_at": now,
        })
        summary["creator_row_created"] = 1
        creator_id = cid
    else:
        creator_id = creator.get("id") or creator.get("_id")
        if creator.get("application_status") != "approved":
            await db.podcast_creators.update_one(
                {"user_id": uid},
                {"$set": {"application_status": "approved",
                              "approved_at": now}})
            summary["creator_row_updated_to_approved"] = 1

    # ── user row ───────────────────────────────────────────────────────
    user_set = {}
    if user.get("role") != "creator":
        user_set["role"] = "creator"
        summary["role_changed"] = 1
    if user.get("creator_status") != "approved":
        user_set["creator_status"] = "approved"
        summary["creator_status_set"] = 1
    if user.get("creator_id") != creator_id:
        user_set["creator_id"] = creator_id
        summary["creator_id_set"] = 1
    if user_set:
        await db.users.update_one({"user_id": uid}, {"$set": user_set})

    # ── optional demo channel ────────────────────────────────────────
    existing_channel = await db.podcast_channels.find_one(
        {"creator_id": creator_id})
    if not existing_channel:
        ch_id = "pch_" + uuid.uuid4().hex[:14]
        await db.podcast_channels.insert_one({
            "_id": ch_id, "id": ch_id, "creator_id": creator_id,
            "title": "Test Listener’s Demo Show",
            "description": "Auto-seeded demo channel for end-to-end testing.",
            "category": "lifestyle",
            "language": "en", "market": user.get("market") or "dubai",
            "approval_status": "approved",
            "approved_at": now, "created_at": now,
            "episode_count": 0,
        })
        summary["demo_channel_seeded"] = 1

    return summary


async def _main():
    sys.path.insert(0, "/app/backend")
    try:
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
    except Exception:
        pass
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    print(await promote(db))


if __name__ == "__main__":
    asyncio.run(_main())
