"""Phase AUTH.1 — Seed the permanent playbook test user + session.

Idempotent.  Safe to re-run.  Adds `playbook.test@bigfm.dubai` + a
never-expiring session so tester Playwright scripts can inject the
cookie without a first curl.

Boot-invoked from `server.py` after Phase CLAIM.1 init.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

log = logging.getLogger("bigfm.auth1.seed")

PLAYBOOK_USER_ID       = "user_pw_test_playbook_a"
PLAYBOOK_EMAIL             = "playbook.test@bigfm.dubai"
PLAYBOOK_SESSION_TOKEN = "bsess_playbook_permanent_do_not_delete"


async def seed_playbook_user(db) -> dict:
    now = datetime.now(timezone.utc)
    forever = datetime(2099, 12, 31, tzinfo=timezone.utc)

    await db.users.update_one(
        {"user_id": PLAYBOOK_USER_ID},
        {"$setOnInsert": {
            "user_id":                          PLAYBOOK_USER_ID,
            "email":                              PLAYBOOK_EMAIL,
            "name":                                "Playbook Test User",
            "picture":                          None,
            "auth_provider":            "google",
            "auth_providers":          ["google"],
            "google_email":                PLAYBOOK_EMAIL,
            "google_name":                "Playbook Test User",
            "google_picture":            None,
            "google_linked_at":        now,
            "role":                                "user",
            "onboarding_complete":  True,
            "preference_vector":      {},
            "created_at":                    now,
            "last_login_at":              now,
        }},
        upsert=True)

    # sessions (historical hot path)
    await db.sessions.update_one(
        {"token": PLAYBOOK_SESSION_TOKEN},
        {"$setOnInsert": {
            "user_id":            PLAYBOOK_USER_ID,
            "token":                  PLAYBOOK_SESSION_TOKEN,
            "created_at":      now,
            "expires_at":      forever,
            "ip":                        "127.0.0.1",
            "user_agent":      "playbook-permanent",
        }},
        upsert=True)

    # user_sessions (playbook-canonical)
    await db.user_sessions.update_one(
        {"session_token": PLAYBOOK_SESSION_TOKEN},
        {"$setOnInsert": {
            "user_id":                PLAYBOOK_USER_ID,
            "session_token":  PLAYBOOK_SESSION_TOKEN,
            "provider":              "google",
            "created_at":          now,
            "last_used_at":      now,
            "expires_at":          forever,
            "ip":                            "127.0.0.1",
            "user_agent":          "playbook-permanent",
        }},
        upsert=True)

    return {"user_id": PLAYBOOK_USER_ID,
                        "session_token": PLAYBOOK_SESSION_TOKEN,
                        "email": PLAYBOOK_EMAIL}


async def _cli():
    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient
    load_dotenv("/app/backend/.env")
    logging.basicConfig(level=logging.INFO)
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    r = await seed_playbook_user(db)
    print(r)


if __name__ == "__main__":
    asyncio.run(_cli())
