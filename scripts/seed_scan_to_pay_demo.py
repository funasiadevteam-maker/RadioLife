"""Idempotent seed: make the demo Karak merchant(s) fully demoable for
scan-to-pay in PREVIEW *without* Stripe Connect.

The Stripe key in this env is a restricted LIVE key without
`connected_account_write`, so we cannot create a test Connect account and we
must not run real card charges. Instead we enable scan-to-pay with 100% BigPoints
redemption, so a user with enough points can pay the FULL bill with points
(card_cents == 0 → Stripe branch skipped) and still get a real captured receipt
end-to-end. Safe, no money moves.
"""
import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

TARGET_PATTERNS = ["karak"]          # name regex (case-insensitive)
TARGET_IDS = ["m_karak", "biz_demo_karak", "biz_karak_cafe_karama"]


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "app")]
    q = {"$or": [
        {"business_id": {"$in": TARGET_IDS}},
        *[{"name": {"$regex": p, "$options": "i"}} for p in TARGET_PATTERNS],
    ]}
    updated = []
    async for b in db.businesses.find(q):
        bid = b.get("business_id")
        if not bid:
            continue
        r = await db.businesses.update_one(
            {"business_id": bid},
            {"$set": {
                "scan_to_pay_enabled": True,
                "points_per_dollar": int(b.get("points_per_dollar") or 10),
                "max_points_redemption_pct": 100,   # allow a full points-only receipt
                "min_scan_to_pay_amount_cents": int(b.get("min_scan_to_pay_amount_cents") or 0),
            }})
        updated.append((bid, b.get("name"), r.modified_count))
    print(f"Matched/updated {len(updated)} merchant(s):")
    for bid, name, mod in updated:
        print(f"  - {bid} | {name} | modified={mod}")
    if not updated:
        print("  (no matching merchants found)")


if __name__ == "__main__":
    asyncio.run(main())
