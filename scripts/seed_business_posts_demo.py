"""Seed demo business social posts + a boosted (sponsored) post so the wall can
show organic BUSINESS_POST cards (to a follower) and a labelled SPONSORED_POST
card (to non-Premium users). Idempotent."""
import os
import asyncio
from datetime import datetime, timezone, timedelta

import motor.motor_asyncio as motor
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")


async def main():
    c = motor.AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = c[os.environ["DB_NAME"]]
    now = datetime.now(timezone.utc)
    nowiso = now.isoformat()

    demo = await db.users.find_one({"email": "demo@bigfm.dubai"})
    uid = demo["user_id"]

    # A business the demo user follows (from M2). Fall back to any business.
    rel = await db.user_business_relations.find_one(
        {"user_id": uid, "kind": "follow"})
    bizid = rel.get("merchant_id") if rel else None
    biz = await db.businesses.find_one({"business_id": bizid}) if bizid else None
    if not biz:
        biz = await db.businesses.find_one({"name": {"$regex": "Karak", "$options": "i"}}) \
            or await db.businesses.find_one({})
        bizid = biz["business_id"]
        # ensure the demo user follows it so the organic post shows under Following
        await db.user_business_relations.update_one(
            {"user_id": uid, "merchant_id": bizid, "kind": "follow"},
            {"$set": {"user_id": uid, "merchant_id": bizid, "kind": "follow",
                      "active": True, "created_at": nowiso}}, upsert=True)
    print("demo follows business:", bizid, biz.get("name"))

    # Organic business post (approved so followers see it immediately).
    organic_id = f"post_demo_biz_{bizid}"[:40]
    await db.social_posts.update_one(
        {"_id": organic_id},
        {"$set": {"_id": organic_id, "post_id": organic_id, "page_id": bizid,
                  "author_user_id": biz.get("owner_user_id"), "business_id": bizid,
                  "post_type": "offer", "text": "Fresh karak + saffron pista on us this week — show this post for a free upgrade! ☕",
                  "media_urls": [], "visibility": "public", "approval_status": "approved",
                  "status": "approved", "cta_label": "View Offer", "reaction_counts": {},
                  "comment_count": 0, "share_count": 0, "created_at": now}}, upsert=True)

    # A second post to BOOST (sponsored). Owned by the same business.
    boost_src = f"post_demo_boost_{bizid}"[:40]
    await db.social_posts.update_one(
        {"_id": boost_src},
        {"$set": {"_id": boost_src, "post_id": boost_src, "page_id": bizid,
                  "author_user_id": biz.get("owner_user_id"), "business_id": bizid,
                  "post_type": "offer", "text": "20% off every dinner platter tonight — tap to grab the deal before 10pm!",
                  "media_urls": [], "visibility": "public", "approval_status": "approved",
                  "status": "approved", "cta_label": "View Offer", "reaction_counts": {},
                  "comment_count": 0, "share_count": 0, "created_at": now}}, upsert=True)
    await db.boosted_posts.update_one(
        {"_id": f"boost_{boost_src}"},
        {"$set": {"_id": f"boost_{boost_src}", "post_id": boost_src, "business_id": bizid,
                  "goal": "coupon_claims", "budget_cents": 5000, "cta_label": "View Offer",
                  "destination": biz.get("slug") or bizid,
                  "start_at": nowiso, "end_at": (now + timedelta(days=7)).isoformat(),
                  "status": "active", "created_by": biz.get("owner_user_id"),
                  "created_at": now}}, upsert=True)

    print("seeded organic + boosted (sponsored) business posts")
    c.close()


if __name__ == "__main__":
    asyncio.run(main())
