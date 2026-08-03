"""Phase ADMOD.1 — Backward-compat migration.

For every existing `pending_admin` / `pending_approval` row in
`coupon_campaigns` / `ad_campaigns_v2` / `merchant_predict_win_campaigns`,
ensure there's a corresponding `ad_creative_reviews` row so the unified
queue picks them up.

Idempotent — safe to re-run at every boot.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from services import ad_creative_review_service as _svc

logger = logging.getLogger("bigfm.admod1.migrate")


async def _mig_one(db, *, ad_type: str, target_id: str,
                                        advertiser_id: str, submitted_by: str) -> str:
    existing = await db.ad_creative_reviews.find_one(
        {"ad_type": ad_type, "target_id": target_id})
    if existing:
        return "skipped"
    await _svc.create_review(
        db, ad_type=ad_type, target_id=target_id,
        advertiser_id=advertiser_id, submitted_by=submitted_by,
        run_moderation=False)   # skip moderation on backfill
    return "created"


async def migrate_all(db) -> Dict[str, Any]:
    stats: Dict[str, int] = {"advertiser_campaign": 0,
                                                    "coupon_campaign": 0,
                                                    "sponsored_predict_win": 0}
    # Coupon campaigns awaiting admin
    async for r in db.coupon_campaigns.find(
            {"status": {"$in": ["pending_admin"]}},
            {"campaign_id": 1, "advertiser_id": 1, "submitted_by": 1,
              "_id": 0}):
        action = await _mig_one(
            db, ad_type="coupon_campaign",
            target_id=r.get("campaign_id"),
            advertiser_id=r.get("advertiser_id") or "",
            submitted_by=r.get("submitted_by") or "system_migrate")
        if action == "created":
            stats["coupon_campaign"] += 1
    # AD.1 advertiser campaigns awaiting approval
    async for r in db.ad_campaigns_v2.find(
            {"status": {"$in": ["pending_approval", "pending_admin"]}},
            {"campaign_id": 1, "advertiser_id": 1, "_id": 0}):
        action = await _mig_one(
            db, ad_type="advertiser_campaign",
            target_id=r.get("campaign_id"),
            advertiser_id=r.get("advertiser_id") or "",
            submitted_by="system_migrate")
        if action == "created":
            stats["advertiser_campaign"] += 1
    # Predict-win merchant campaigns
    async for r in db.merchant_predict_win_campaigns.find(
            {"approval_status": {"$in": ["pending_admin", "pending_approval"]}},
            {"campaign_id": 1, "advertiser_id": 1, "_id": 0}):
        action = await _mig_one(
            db, ad_type="sponsored_predict_win",
            target_id=r.get("campaign_id"),
            advertiser_id=r.get("advertiser_id") or "",
            submitted_by="system_migrate")
        if action == "created":
            stats["sponsored_predict_win"] += 1
    logger.info("[admod1] backfill: %s", stats)
    return stats


if __name__ == "__main__":
    import asyncio, os
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _run():
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        print(await migrate_all(db))
    asyncio.run(_run())
