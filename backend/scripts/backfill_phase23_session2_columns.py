"""Phase 23 Session 2 — backfill creator_type + JSON column defaults.

Walks every game_campaigns row that's missing `creator_type` and sets it
based on the inference rule from the audit doc:
  - is_platform_funded=True  → admin
  - advertiser_id set        → advertiser
  - otherwise                → business

Also ensures the 3 new JSON columns default to `{}` (sparse — only writes
where the field is missing).  Idempotent.

Run manually:
    python /app/backend/scripts/backfill_phase23_session2_columns.py
"""
from __future__ import annotations

import asyncio
import os
import sys


async def backfill(db) -> dict:
    summary = {"creator_type_inferred_admin": 0,
                  "creator_type_inferred_advertiser": 0,
                  "creator_type_inferred_business": 0,
                  "placement_rules_defaulted": 0,
                  "eligibility_rules_defaulted": 0,
                  "win_rules_defaulted": 0}

    r = await db.game_campaigns.update_many(
        {"creator_type": {"$exists": False}, "is_platform_funded": True},
        {"$set": {"creator_type": "admin"}})
    summary["creator_type_inferred_admin"] = r.modified_count

    r = await db.game_campaigns.update_many(
        {"creator_type": {"$exists": False},
          "advertiser_id": {"$nin": [None, ""]}},
        {"$set": {"creator_type": "advertiser"}})
    summary["creator_type_inferred_advertiser"] = r.modified_count

    r = await db.game_campaigns.update_many(
        {"creator_type": {"$exists": False}},
        {"$set": {"creator_type": "business"}})
    summary["creator_type_inferred_business"] = r.modified_count

    r = await db.game_campaigns.update_many(
        {"placement_rules_json": {"$exists": False}},
        {"$set": {"placement_rules_json": {}}})
    summary["placement_rules_defaulted"] = r.modified_count

    r = await db.game_campaigns.update_many(
        {"eligibility_rules_json": {"$exists": False}},
        {"$set": {"eligibility_rules_json": {}}})
    summary["eligibility_rules_defaulted"] = r.modified_count

    r = await db.game_campaigns.update_many(
        {"win_rules_json": {"$exists": False}},
        {"$set": {"win_rules_json": {}}})
    summary["win_rules_defaulted"] = r.modified_count

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
    print(await backfill(db))


if __name__ == "__main__":
    asyncio.run(_main())
