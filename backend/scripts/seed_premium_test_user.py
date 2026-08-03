"""Phase 42-B-redux — Premium-tier fixture user.

Seeds `premiumtest@bigfm.dubai` / `PremiumTest123!` — a Premium subscriber
account used to verify the pre-roll premium short-circuit AND the
Ad Preferences toggle UI in the premium state.

Idempotent: re-running re-asserts the premium flags + password hash; safe
to run repeatedly.

Test cases covered:
    - POST /api/live-radio/preroll/request → `{has_preroll: false, reason: "premium"}`
    - GET  /api/users/me/ad-settings → `{is_premium: true, ad_free_enabled: true}`
    - PATCH /api/users/me/ad-settings (premium can flip the toggle)

Usage:
    python3 backend/scripts/seed_premium_test_user.py
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

EMAIL = "premiumtest@bigfm.dubai"
PASSWORD = "PremiumTest123!"
USER_ID_PREFIX = "user_prem"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


# Canonical premium flags — matched against
# `services.premium_gate.is_premium_or_trial` which honors any of these:
#   • user.is_premium=True
#   • user.subscription.status in {"active","trialing"}
#   • user.subscription_status in {"premium","trial"}
PREMIUM_FLAGS = {
    "is_premium": True,
    "subscription_status": "premium",
    "tier": "premium",
    "subscription": {
        "status": "active",
        "plan": "premium_yearly",
        "current_period_end": (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        ),
    },
    # Per 42-B brief: premium users default to ad-free=true.
    "ad_settings": {
        "ad_free_enabled": True,
        "updated_at": _now(),
    },
}


async def main() -> None:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]

    existing = await db.users.find_one({"email": EMAIL})
    pw_hash = bcrypt.hashpw(
        PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    now = _now()

    if existing:
        # Idempotent — wipe any pre-roll impressions accumulated since
        # previous run so the premium-skip check always lands in the
        # `reason: "premium"` branch (not `frequency_cap` from a prior
        # impersonated-free run).
        deleted = await db.live_radio_ad_impressions.delete_many(
            {"user_id": existing["user_id"]})
        await db.users.update_one(
            {"user_id": existing["user_id"]},
            {"$set": {
                "password_hash": pw_hash,
                **PREMIUM_FLAGS,
                "updated_at": now,
            }},
        )
        print(f"user_id={existing['user_id']}")
        print(f"email={EMAIL}")
        print(f"impressions_cleared={deleted.deleted_count}")
        print("status=refreshed")
        client.close()
        return

    user_id = _new_id(USER_ID_PREFIX)
    await db.users.insert_one({
        "_id": user_id,
        "user_id": user_id,
        "email": EMAIL,
        "password_hash": pw_hash,
        "name": "Premium Test (42-B fixture)",
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
        **PREMIUM_FLAGS,
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
