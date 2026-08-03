"""Phase 18c — Pacing health demo seed.

Idempotently upserts two fixture campaigns used by the admin pacing-health
panel + test report screenshots:

  - cmp_test_ahead_001  "BBQ Pit Mega Push"   (ahead:  spend 90% / time 50%)
  - cmp_test_behind_001 "Karak Slow Burn"     (behind: spend  5% / time 50%)

Both target `__nonexistent_chan__` so they never show up in the live ad-pick
auction.  Status `active`, approved.  Safe to re-run.

Used by:
  - server.py lifespan bootstrap (auto runs every boot)
  - `python -m scripts.seed_pacing_demo` (manual one-shot CLI)
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient


_FIXTURES = [
    {
        "id":                                    "cmp_test_ahead_001",
        "name":                                "BBQ Pit Mega Push",
        "_spend_pct_of_budget":  0.90,   # → ahead vs 50% time progress
    },
    {
        "id":                                    "cmp_test_behind_001",
        "name":                                "Karak Slow Burn",
        "_spend_pct_of_budget":  0.05,   # → behind vs 50% time progress
    },
    {
        "id":                                    "cmp_test_onpace_001",
        "name":                                "Steady Eddie",
        "_spend_pct_of_budget":  0.50,   # → on_pace (50% spend vs 50% time)
    },
]


async def seed_pacing_demo(db) -> dict:
    """Upsert the two pacing demo campaigns. Returns a counts dict."""
    now           = datetime.now(timezone.utc)
    start_date  = (now - timedelta(days=5)).isoformat()
    end_date    = (now + timedelta(days=5)).isoformat()
    budget       = 1000.0
    created = 0
    updated = 0
    for f in _FIXTURES:
        spend = round(budget * f["_spend_pct_of_budget"], 2)
        doc = {
            "id":                            f["id"],
            "advertiser_id":              "adv_demo_karak",
            "name":                         f["name"],
            "status":                       "active",
            "approval_status":         "approved",
            "start_date":                  start_date,
            "end_date":                    end_date,
            "budget_total_usd":     budget,
            "spend_usd":                  spend,
            # Park targeting on a slug no real listener uses so the auction
            # never picks these fixtures.  Pacing-health panel reads the
            # campaign doc directly, so panel still renders.
            "targeting":                  {"channels": ["__nonexistent_chan__"]},
            "frequency_caps":         {},
            "takeover_config":         {"enabled": False},
            "created_at":                 now,
            "updated_at":                 now,
            "_is_pacing_fixture":  True,
        }
        res = await db.ad_campaigns.update_one(
            {"id": f["id"]},
            {"$set": doc,
              "$setOnInsert": {"first_seeded_at": now}},
            upsert=True)
        if res.upserted_id is not None:
            created += 1
        elif res.modified_count:
            updated += 1
    return {"created": created, "updated": updated,
              "total_fixtures": len(_FIXTURES)}


async def _cli():
    mongo_url = os.environ["MONGO_URL"]
    db_name    = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    try:
        r = await seed_pacing_demo(client[db_name])
        print(f"[seed_pacing_demo] {r}")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(_cli())
