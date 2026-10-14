"""Idempotent BigCoin top-up so demo flows (100% points scan-to-pay) always
work in preview.  Tops a user UP TO TARGET by inserting a single ledger
credit for the shortfall; a no-op once at/above target.
"""
import os
import uuid
import asyncio
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

TARGETS = {"demo@bigfm.dubai": 10000, "freeuser@bigfm.dubai": 5000}


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "app")]
    for email, target in TARGETS.items():
        u = await db.users.find_one({"email": email})
        if not u:
            print(f"skip (no user): {email}")
            continue
        uid = u["user_id"]
        pipe = [{"$match": {"user_id": uid}},
                {"$group": {"_id": None, "total": {"$sum": "$delta"}}}]
        bal = 0
        async for d in db.points_ledger.aggregate(pipe):
            bal = int(d.get("total") or 0)
        if bal >= target:
            print(f"{email}: balance {bal} >= {target}, no top-up")
            continue
        delta = target - bal
        await db.points_ledger.insert_one({
            "entry_id": f"ple_{uuid.uuid4().hex[:14]}",
            "user_id": uid,
            "delta": delta,
            "source": "demo_topup",
            "metadata": {"reason": "preview_demo_sustain"},
            "created_at": datetime.now(timezone.utc),
        })
        print(f"{email}: +{delta} → {target}")


if __name__ == "__main__":
    asyncio.run(main())
