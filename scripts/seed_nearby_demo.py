"""Idempotent DEMO seed so the Home 'Near you now' row is visible in preview:
- demo@bigfm.dubai follows the demo Karak merchant(s)
- two already-accepted friends have a recent check-in / pay there
Real collections (`user_business_relations`, `scan_earn_events`) — the same
signals the /api/social/friends-nearby endpoint reads.
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

DEMO_EMAIL = "demo@bigfm.dubai"
FRIEND_EMAILS = ["freeuser@bigfm.dubai", "test@bigfm.dubai"]
MERCHANT = "biz_demo_karak"


def _now():
    return datetime.now(timezone.utc)


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "app")]
    demo = await db.users.find_one({"email": DEMO_EMAIL})
    uid = demo["user_id"]

    # 1) demo follows the Karak demo merchant (idempotent).
    existing = await db.user_business_relations.find_one(
        {"user_id": uid, "merchant_id": MERCHANT, "kind": "follow"})
    if not existing:
        rid = f"ubr_{uuid.uuid4().hex[:16]}"
        await db.user_business_relations.insert_one({
            "_id": rid, "relation_id": rid, "user_id": uid,
            "merchant_id": MERCHANT, "kind": "follow", "active": True,
            "created_at": _now(),
        })
        print(f"follow created: {uid} -> {MERCHANT}")
    else:
        await db.user_business_relations.update_one(
            {"_id": existing["_id"]}, {"$set": {"active": True}})
        print(f"follow already present: {uid} -> {MERCHANT}")

    # 2) friends check in recently (idempotent-ish: skip if a recent one exists).
    acts = [("checked in", 18.0, 20), ("paid", 24.5, 55)]  # (label, usd, minutes-ago)
    for i, fe in enumerate(FRIEND_EMAILS):
        fu = await db.users.find_one({"email": fe})
        if not fu:
            continue
        fid = fu["user_id"]
        recent = await db.scan_earn_events.find_one(
            {"user_id": fid, "merchant_id": MERCHANT,
             "at": {"$gte": _now() - timedelta(hours=1)}})
        if recent:
            print(f"recent check-in already present: {fe}")
            continue
        _, usd, mins = acts[i % len(acts)]
        await db.scan_earn_events.insert_one({
            "event_id": f"se_{uuid.uuid4().hex[:14]}",
            "user_id": fid, "merchant_id": MERCHANT, "amount_usd": usd,
            "at": _now() - timedelta(minutes=mins),
        })
        print(f"check-in seeded: {fe} @ {MERCHANT} ({mins}m ago)")

    # 3) Ensure the merchant's active offer has a short discount_label so the
    #    'Near you now' deal hook reads cleanly (e.g. "50% off"), and a near
    #    expiry so the deal countdown is visible in the demo.
    res = await db.offers.update_many(
        {"business_id": MERCHANT, "status": "active",
          "$or": [{"discount_label": None}, {"discount_label": {"$exists": False}}]},
        {"$set": {"discount_label": "50% off Karak"}})
    print(f"offer label set on {res.modified_count} active offer(s)")
    exp = datetime.now(timezone.utc) + timedelta(hours=6)
    res2 = await db.offers.update_many(
        {"business_id": MERCHANT, "status": "active"},
        {"$set": {"expires_at": exp}})
    print(f"offer expiry refreshed (+6h) on {res2.modified_count} active offer(s)")


if __name__ == "__main__":
    asyncio.run(main())
