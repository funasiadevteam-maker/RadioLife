"""Sub-Phase E2 — modal-verification fixture user.

Seeds `predictest@bigfm.dubai` / `PredictTest123!` — a plain listener
account reserved for E2 Enter-modal smoke checks.  Idempotent: re-run is
safe (drops the existing user's `predict_win_entries` rows so the modal
remains reachable).

Usage:
    python3 backend/scripts/seed_e2_modal_user.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import bcrypt
from motor.motor_asyncio import AsyncIOMotorClient

EMAIL = "predictest@bigfm.dubai"
PASSWORD = "PredictTest123!"
USER_ID_PREFIX = "user_pwm"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


async def main() -> None:
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "bigfm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    existing = await db.users.find_one({"email": EMAIL})
    if existing:
        # Idempotent — wipe any picks accumulated since previous run so
        # the Enter modal is always reachable for this fixture.
        deleted = await db.predict_win_entries.delete_many(
            {"user_id": existing["user_id"]})
        # Ensure the password still matches in case a prior run changed it.
        pw_hash = bcrypt.hashpw(
            PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        await db.users.update_one(
            {"user_id": existing["user_id"]},
            {"$set": {
                "password_hash": pw_hash,
                "updated_at": _now(),
            }},
        )
        print(f"user_id={existing['user_id']}")
        print(f"email={EMAIL}")
        print(f"entries_cleared={deleted.deleted_count}")
        print("status=refreshed")
        client.close()
        return

    user_id = _new_id(USER_ID_PREFIX)
    now = _now()
    pw_hash = bcrypt.hashpw(
        PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    await db.users.insert_one({
        "_id": user_id,
        "user_id": user_id,
        "email": EMAIL,
        "password_hash": pw_hash,
        "name": "Predict Test (E2 modal)",
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
        "date_of_birth": "1995-01-01",
        "created_at": now,
        "updated_at": now,
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
