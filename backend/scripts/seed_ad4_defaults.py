"""Phase AD.4 — seed a default `coupon_save` commission rule + demo campaign."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("bigfm.ad4.seed")

RULE_ID = "cr_coupon_save_default"
DEFAULT_PLATFORM_PERCENT = 30.0  # merchant keeps 70%
TEST_ADVERTISER_ID = "advv2_9fac10b21f5595"
TEST_MERCHANT_ID = "biz_sc5_test_activated"
DEMO_CAMPAIGN_ID = "cc_ad4_demo_karak"


async def seed_ad4_commission_rule(db) -> dict:
    now = datetime.now(timezone.utc)
    r = await db.commission_rules.find_one_and_update(
        {"business_category": "*", "transaction_type": "coupon_save",
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
            "note":  "AD.4 default: 30% platform / 70% merchant on coupon-save.",
        }},
        upsert=True, return_document=True)
    return {"rule_id": (r or {}).get("rule_id"),
                  "commission_percent": (r or {}).get("commission_percent")}


async def seed_ad4_demo_campaign(db) -> dict:
    """Idempotent demo campaign attached to advv2_... sponsoring
    biz_sc5_test_activated (Acme Karak Co)."""
    now = datetime.now(timezone.utc)
    doc = {
        "_id":                                    DEMO_CAMPAIGN_ID,
        "campaign_id":                      DEMO_CAMPAIGN_ID,
        "advertiser_id":                    TEST_ADVERTISER_ID,
        "sponsoring_merchant_id":  TEST_MERCHANT_ID,
        "title":                                  "10 AED off · Karak Cafe",
        "description":                      "One free upgrade to premium Karak — this weekend only.",
        "terms":                                  "One per customer.  Valid in Dubai locations only.",
        "retail_value_cents":            1000,
        "value_currency":                  "AED",
        "cost_per_save_cents":          10,           # 10¢ per save
        "total_inventory":                8,
        "saves_count":                        0,
        "targeting":                          {"country_codes": ["AE", "US"],
                                                                        "category_tags": ["food", "coffee", "karak"]},
        "category_tags":                    ["food", "coffee"],
        "logo_url":                            None,
        "hero_image_url":                  None,
        "start_time":                        now - timedelta(minutes=5),
        "end_time":                            now + timedelta(days=30),
        "status":                                "live",
        "created_at":                        now,
        "updated_at":                        now,
        "submitted_at":                    now,
        "reviewed_at":                      now,
        "demo_fixture":                    True,
    }
    r = await db.coupon_campaigns.update_one(
        {"campaign_id": DEMO_CAMPAIGN_ID},
        {"$setOnInsert": doc}, upsert=True)
    return {"campaign_id": DEMO_CAMPAIGN_ID,
                  "created": bool(r.upserted_id)}


async def seed_all(db) -> dict:
    rule = await seed_ad4_commission_rule(db)
    camp = await seed_ad4_demo_campaign(db)
    logger.info("[ad4-seed] rule=%s campaign=%s", rule, camp)
    return {"rule": rule, "campaign": camp}


if __name__ == "__main__":
    import asyncio, os
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        print(await seed_all(db))
        client.close()
    asyncio.run(_run())
