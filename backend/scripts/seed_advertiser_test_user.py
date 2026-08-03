"""Phase 42-E1.3 — Advertiser test fixture.

Seeds `advertest@bigfm.dubai` / `AdvTest123!` (role=advertiser) and an
associated `advertisers` row.  Idempotent — re-running just re-asserts
the password hash + role.

Usage:
    python3 backend/scripts/seed_advertiser_test_user.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

EMAIL = "advertest@bigfm.dubai"
PASSWORD = "AdvTest123!"
USER_ID_PREFIX = "user_adv"
ADV_NAME = "AdvTest QA Org"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    pw_hash = bcrypt.hashpw(
        PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    now = _now()

    existing = await db.users.find_one({"email": EMAIL})
    if existing:
        uid = existing["user_id"]
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {
                "password_hash": pw_hash,
                "role":              "advertiser",
                "updated_at":  now,
            }},
        )
    else:
        uid = f"{USER_ID_PREFIX}_{uuid.uuid4().hex[:14]}"
        await db.users.insert_one({
            "_id": uid,
            "user_id": uid,
            "email": EMAIL,
            "password_hash": pw_hash,
            "name": "Advertest QA",
            "auth_provider": "email",
            "role": "advertiser",
            "onboarding_complete": True,
            "home_city": "Dubai",
            "country": "AE",
            "preferred_market": "dubai",
            "bigcoin_balance": 0,
            "bigcoin_lifetime_earned": 0,
            "is_premium": True,            # premium so they don't see ads in own preview
            "subscription_status": "premium",
            "date_of_birth": "1990-01-01",
            "created_at": now,
            "updated_at": now,
        })

    # Advertisers row (org).  Use the user_id field to link.
    existing_adv = await db.advertisers.find_one({"user_id": uid})
    if existing_adv:
        adv_id = str(existing_adv.get("_id"))
    else:
        adv_id = uuid.uuid4().hex[:24]
        await db.advertisers.insert_one({
            "_id": adv_id,
            "user_id": uid,
            "name": ADV_NAME,
            "contact_email": EMAIL,
            "created_at": now,
            "updated_at": now,
        })

    print(f"user_id={uid}")
    print(f"advertiser_id={adv_id}")
    print(f"email={EMAIL}")
    print("status=ok")
    client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
