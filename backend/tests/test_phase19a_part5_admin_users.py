"""Phase 19a Part 5 regression suite — admin user management.

This file is being seeded preemptively with ONE regression test for the
role-reset-on-login bug surfaced during commit fad918b investigation.
The investigation concluded the bug WAS the safety_seed boot-time reset
(patched in commit fad918b); the login path itself does not reset role.
This test guards against any future regression.

The rest of Phase 19a Part 5 (list / role-change / activate / deactivate
endpoints + safety rails) will land in a follow-up dispatch and expand
this file.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid


sys.path.insert(0, "/app/backend")
os.environ["STRIPE_MODE"] = "mock"
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def test_promoted_creator_role_persists_across_login():
    """Regression for the safety_seed boot-time reset (commit fad918b).

    Asserts:
      1. Promote test@bigfm.dubai to role='creator' via direct DB write
      2. POST /api/auth/login returns role='creator' (not business_partner)
      3. DB row still has role='creator' after the login round-trip
    """
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient

        srv = importlib.import_module("server")
        db = _db()

        # Ensure the test user exists.  If not, skip — the seed step is
        # owned by services/safety_seed.py and not by this test.
        existing = await db.users.find_one({"email": "test@bigfm.dubai"})
        if not existing:
            print("SKIP: test@bigfm.dubai not seeded yet")
            return

        # Snapshot original role so we don't permanently change demo data
        # if this test runs out-of-order against the live DB.
        original_role = existing.get("role")
        original_creator_id = existing.get("creator_id")
        original_creator_status = existing.get("creator_status")

        try:
            # Force role=creator + ensure creator_id is linked (idempotent
            # — uses whatever podcast_creators row already exists)
            cr = await db.podcast_creators.find_one(
                {"user_id": existing["user_id"]})
            if not cr:
                cid = "crt_" + uuid.uuid4().hex[:14]
                from datetime import datetime, timezone
                await db.podcast_creators.insert_one({
                    "_id": cid, "id": cid,
                    "user_id": existing["user_id"],
                    "display_name": existing.get("name") or "Test",
                    "contact_email": "test@bigfm.dubai",
                    "application_status": "approved",
                    "approved_at": datetime.now(timezone.utc),
                    "applied_at": datetime.now(timezone.utc),
                    "created_at": datetime.now(timezone.utc),
                })
                creator_id = cid
            else:
                creator_id = cr.get("id") or cr.get("_id")

            await db.users.update_one(
                {"email": "test@bigfm.dubai"},
                {"$set": {"role": "creator",
                              "creator_status": "approved",
                              "creator_id": creator_id}})

            # Login round-trip via ASGI transport
            async with AsyncClient(transport=ASGITransport(app=srv.app),
                                              base_url="http://test",
                                              timeout=15) as ac:
                r = await ac.post("/api/auth/login",
                    json={"email": "test@bigfm.dubai",
                              "password": "TestUser123!"})
                assert r.status_code == 200, r.text
                body = r.json()
                assert body.get("role") == "creator", \
                    f"login response role should be 'creator', got {body.get('role')!r}"

            # DB row must still be creator after the login round-trip
            after = await db.users.find_one({"email": "test@bigfm.dubai"})
            assert after.get("role") == "creator", \
                f"DB role should still be 'creator' after login, got {after.get('role')!r}"
        finally:
            # Restore original state to avoid polluting demo seed
            restore = {}
            if original_role is not None:
                restore["role"] = original_role
            if original_creator_id is not None:
                restore["creator_id"] = original_creator_id
            else:
                # if it wasn't set before, unset it
                pass
            if original_creator_status is not None:
                restore["creator_status"] = original_creator_status
            if restore:
                await db.users.update_one(
                    {"email": "test@bigfm.dubai"}, {"$set": restore})
    run(go())
