"""Phase I — Business fixture seeder.

Creates a deterministic business storefront for QA:
* user        : test@bigfm.dubai (canonical owner)
* business_id : biz_qa_e3_karak (re-seeds idempotently)
* PIN          : 4242

Used by the testing agent's Phase I happy-path coverage.  The seed is
safe to re-run: it upserts on the business _id, restores defaults,
and re-attaches the `business` role to the user.
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

from datetime import datetime, timezone

import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient


BUSINESS_ID = "biz_qa_e3_karak"
OWNER_EMAIL = "test@bigfm.dubai"
TERMINAL_PIN = "4242"


def _hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode("utf-8"),
                                          bcrypt.gensalt(rounds=10)).decode("utf-8")


async def main() -> None:
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    owner = await db.users.find_one({"email": OWNER_EMAIL.lower()},
                                                                  {"user_id": 1})
    if not owner:
        print(f"[seed_business] owner user not found: {OWNER_EMAIL}")
        sys.exit(1)
    uid = owner["user_id"]
    now = datetime.now(timezone.utc)
    doc = {
        "_id":                          BUSINESS_ID,
        "owner_user_id":      uid,
        "name":                          "Karak Cafe (QA fixture)",
        "category":                  "cafe",
        "address":                  "Sheikh Zayed Rd, Dubai",
        "lat":                          25.20,
        "lng":                          55.27,
        "phone":                      "+971501234567",
        "website":                  "https://example.com/karak",
        "pos_terminal_pin_hash": _hash_pin(TERMINAL_PIN),
        "verified":                  True,
        "active":                      True,
        "redemption_count": 0,
        "created_at":              now,
        "updated_at":              now,
    }
    await db.businesses.update_one({"_id": BUSINESS_ID},
                                                                {"$set": doc}, upsert=True)
    # Attach the `business` role to the user (idempotent).
    await db.users.update_one(
        {"user_id": uid},
        {"$addToSet": {"roles": "business"},
          "$set": {"business_id": BUSINESS_ID, "is_business": True}})
    print(f"[seed_business] ok business_id={BUSINESS_ID} owner={uid} pin={TERMINAL_PIN}")


if __name__ == "__main__":
    asyncio.run(main())
