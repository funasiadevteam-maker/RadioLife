"""Phase 42-D follow-up — Free-tier fixture user.

Seeds `freetest@bigfm.dubai` / `FreeTest123!` — a pristine free-tier
listener used by e1_tester to verify the *trial-eligible* branch of
`POST /api/billing/start_premium_trial` (state="started") AND the
free-tier pre-roll fire path on imported stations.

Idempotent: re-running re-asserts the free flags + password hash AND
WIPES any accumulated trial / premium / favorite state so the fixture
always lands back at the "never used a trial, no premium" baseline.

Test cases covered:
    - POST /api/billing/start_premium_trial → state="started"
    - GET  /api/billing/trial_status → is_premium_or_trial=false
    - GET  /api/users/me/ad-settings → is_premium=false, ad_free_enabled=false
    - Imported-station tap triggers the Phase 42-B2 pre-roll overlay.

Usage:
    python3 backend/scripts/seed_free_test_user.py
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

EMAIL = "freetest@bigfm.dubai"
PASSWORD = "FreeTest123!"
USER_ID_PREFIX = "user_free"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


# Canonical FREE flags — every premium/trial flag is explicitly $unset
# so the user is in the "never trialed, no premium" baseline state.
# `services.premium_gate.is_premium_or_trial` returns False for this row.
FREE_FLAGS_SET = {
    "is_premium": False,
    "subscription_status": "free",
    "tier": "free",
    "ad_settings": {
        "ad_free_enabled": False,
        "updated_at": _now(),
    },
}
FREE_FLAGS_UNSET = {
    "subscription": "",
    "premium_until": "",
    "trial_started_at": "",
    "trial_ends_at": "",
    "trial_used": "",
}


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    existing = await db.users.find_one({"email": EMAIL})
    pw_hash = bcrypt.hashpw(
        PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    now = _now()

    if existing:
        uid = existing["user_id"]
        # Wipe favorites + pre-roll impressions + any voucher redemptions
        # tied to this user so the next test runs against a clean slate.
        fav_deleted = await db.user_favorite_stations.delete_many({"user_id": uid})
        imp_deleted = await db.live_radio_ad_impressions.delete_many({"user_id": uid})
        vr_deleted = await db.voucher_redemptions.delete_many({"user_id": uid})
        sg_deleted = await db.subscription_grants.delete_many({"user_id": uid})

        await db.users.update_one(
            {"user_id": uid},
            {
                "$set": {
                    "password_hash": pw_hash,
                    **FREE_FLAGS_SET,
                    "updated_at": now,
                },
                "$unset": FREE_FLAGS_UNSET,
            },
        )
        print(f"user_id={uid}")
        print(f"email={EMAIL}")
        print(f"favorites_cleared={fav_deleted.deleted_count}")
        print(f"impressions_cleared={imp_deleted.deleted_count}")
        print(f"voucher_redemptions_cleared={vr_deleted.deleted_count}")
        print(f"grants_cleared={sg_deleted.deleted_count}")
        print("status=reset_to_free")
        client.close()
        return

    user_id = _new_id(USER_ID_PREFIX)
    await db.users.insert_one({
        "_id": user_id,
        "user_id": user_id,
        "email": EMAIL,
        "password_hash": pw_hash,
        "name": "Free Test (42-D fixture)",
        "picture": None,
        "auth_provider": "email",
        "role": "user",
        "onboarding_complete": True,
        "home_city": "Dubai",
        "country": "AE",
        "preferred_market": "dubai",
        "preference_vector": {
            "languages": ["english"],
            "genres": ["pop"],
            "eras": ["2020s"],
            "moods": ["energetic"],
            "activities": [],
        },
        "bigcoin_balance": 0,
        "bigcoin_lifetime_earned": 0,
        "date_of_birth": "1990-01-01",
        "created_at": now,
        "updated_at": now,
        **FREE_FLAGS_SET,
    })
    print(f"user_id={user_id}")
    print(f"email={EMAIL}")
    print("status=created")
    client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
