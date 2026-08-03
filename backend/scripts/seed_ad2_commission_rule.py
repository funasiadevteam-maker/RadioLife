"""Phase AD.2 — seed the sponsored-game commission rule.

Idempotent: creates OR updates the singleton fallback rule at
`{business_category=*, transaction_type=sponsored_game, market=None}`.

Default: 30% platform / 70% merchant.  Overridable via
`PATCH /api/admin/commission-rules/sponsored-game`.
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone

logger = logging.getLogger("bigfm.ad2.seed")

RULE_ID = "cr_sponsored_game_default"
DEFAULT_PLATFORM_PERCENT = 30.0  # merchant keeps 70%


async def seed_ad2_commission_rule(db) -> dict:
    now = datetime.now(timezone.utc)
    r = await db.commission_rules.find_one_and_update(
        {"business_category": "*", "transaction_type": "sponsored_game",
          "market": None},
        {"$setOnInsert": {
            "rule_id":                                          RULE_ID,
            "commission_percent":                    DEFAULT_PLATFORM_PERCENT,
            "fixed_fee_cents":                          0,
            "min_fee_cents":                              0,
            "max_fee_cents":                              None,
            "priority":                                        100,
            "active":                                          True,
            "effective_start":                        now,
            "effective_end":                              None,
            "stripe_fee_responsibility":      "platform",
            "created_at":                                  now,
            "updated_at":                                  now,
            "note":  "AD.2 default: 30% platform / 70% merchant on sponsored-game events.",
        }},
        upsert=True, return_document=True)
    logger.info("[ad2-seed] commission_rule=%s pct=%s",
                            (r or {}).get("rule_id"), (r or {}).get("commission_percent"))
    return {"rule_id": (r or {}).get("rule_id"),
                  "commission_percent": (r or {}).get("commission_percent")}


if __name__ == "__main__":
    import asyncio, os
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        res = await seed_ad2_commission_rule(db)
        print("[ad2-seed]", res)
        client.close()

    asyncio.run(_run())
