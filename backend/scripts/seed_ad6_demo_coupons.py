"""Phase AD.6 — Seed a test advertiser-scope coupon for E2E demos.

Idempotent — safe to run at boot.  Creates:
    - A `saved` coupon owned by `advv2_9fac10b21f5595` (Acme Karak Co)
        with code `ADV-DEMO-VALID` — used to demo the happy-path scan.
    - An `expired` coupon `ADV-DEMO-EXPIRED` — used to demo the 410.
    - A `redeemed` coupon `ADV-DEMO-REDEEMED` — used to demo the 409.

These rows are marked `demo_fixture=True` so a future cleanup sweep can
purge them safely.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("bigfm.ad6.seed")

TEST_ADVERTISER_ID = "advv2_9fac10b21f5595"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def seed_ad6_demo_coupons(db) -> dict:
    now = _now()
    made = []
    for spec in [
        {"code": "ADV-DEMO-VALID",        "status": "saved",
          "expires_at": now + timedelta(days=30)},
        {"code": "ADV-DEMO-EXPIRED",    "status": "saved",
          "expires_at": now - timedelta(days=1)},
        {"code": "ADV-DEMO-REDEEMED", "status": "redeemed",
          "expires_at": now + timedelta(days=30),
          "redeemed_at": now - timedelta(hours=2)},
    ]:
        doc = {
            "_id":                              f"cpn_ad6_{spec['code'].lower().replace('-', '_')}",
            "coupon_id":                    f"cpn_ad6_{spec['code'].lower().replace('-', '_')}",
            "code":                            spec["code"],
            "short_code":                spec["code"],
            "advertiser_id":            TEST_ADVERTISER_ID,
            "ad_campaign_id":          "adcv2_1cf5ba69c4d1ed",  # existing AD.1 fixture
            "coupon_type":                "coupon",
            "status":                          spec["status"],
            "user_id":                        "user_demo_8b88c27e0f",
            "discount_value":          10.0,
            "value_currency":          "AED",
            "issued_at":                  now - timedelta(days=1),
            "expires_at":                spec["expires_at"],
            "source_type":                "advertiser_demo",
            "demo_fixture":              True,
        }
        if "redeemed_at" in spec:
            doc["redeemed_at"] = spec["redeemed_at"]
        r = await db.coupons.update_one(
            {"coupon_id": doc["coupon_id"]},
            {"$setOnInsert": doc}, upsert=True)
        if r.upserted_id or r.matched_count == 0:
            made.append(doc["code"])
    logger.info("[ad6-seed] demo coupons seeded/exists (created now: %s)", made)
    return {"created": made,
                  "test_advertiser_id": TEST_ADVERTISER_ID}


if __name__ == "__main__":
    import asyncio, os
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        print(await seed_ad6_demo_coupons(db))
        client.close()

    asyncio.run(_run())
