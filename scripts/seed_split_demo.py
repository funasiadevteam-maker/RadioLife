"""Idempotent demo: an ACTIVE bill-split (one share paid, one pending) so the
Wallet → My Splits 'Who's paid' tracker shows real progress in preview.
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

MERCHANT = "biz_demo_karak"
SPLIT_ID = "bsplit_demo_whospaid"


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "app")]
    demo = await db.users.find_one({"email": "demo@bigfm.dubai"})
    if not demo:
        print("no demo user"); return
    uid = demo["user_id"]
    now = datetime.now(timezone.utc)
    biz = await db.businesses.find_one({"business_id": MERCHANT}, {"name": 1})
    desc = f"Split at {biz.get('name') if biz else 'Karak Cafe'}"

    await db.bill_splits.update_one(
        {"id": SPLIT_ID},
        {"$set": {
            "id": SPLIT_ID,
            "initiator_user_id": uid,
            "merchant_id": MERCHANT,
            "location_id": None,
            "total_amount_cents": 2000,
            "currency": "aed",
            "description": desc,
            "status": "partial",               # one paid, one still pending
            "qr_token": None,
            "created_at": now,
            "expires_at": now + timedelta(days=7),
            "completed_at": None,
        }},
        upsert=True)

    shares = [
        {"id": "bsshr_demo_you", "share_amount_cents": 1000, "status": "paid",
         "display_name": "You", "user_id": uid, "paid_at": now, "claimed_at": now},
        {"id": "bsshr_demo_friend", "share_amount_cents": 1000, "status": "pending",
         "display_name": "Alex", "user_id": None, "paid_at": None, "claimed_at": None},
    ]
    for sh in shares:
        await db.bill_split_shares.update_one(
            {"id": sh["id"]},
            {"$set": {**sh, "split_id": SPLIT_ID, "currency": "aed",
                      "invite_token": sh.get("invite_token") or uuid.uuid4().hex,
                      "created_at": now}},
            upsert=True)
    print(f"seeded split {SPLIT_ID}: You=paid, Alex=pending (1/2 paid)")


if __name__ == "__main__":
    asyncio.run(main())
