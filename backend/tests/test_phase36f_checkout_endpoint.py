"""Phase 36f — Creator SaaS tier checkout endpoint tests.

Endpoint: `POST /api/podcasts/creators/{cid}/subscription/checkout`.
Mobile + web parity. Stripe stays in `mock` mode for these tests so the
checkout session URL is synthesized locally (`/mock/stripe/checkout?...`).
"""
from __future__ import annotations
import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app/backend")
os.environ["STRIPE_MODE"] = "mock"   # Force-mock the Stripe path.
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def _register(ac, prefix="creator"):
    suf = uuid.uuid4().hex[:8]
    r = await ac.post("/api/auth/register",
        json={"email": f"{prefix}_36f_{suf}@bigfm.dubai",
                  "password": "Pwd1234!", "name": "P36f"})
    assert r.status_code == 200, r.text
    j = r.json()
    return j["session_token"], j["user_id"]


async def _login_admin(ac):
    r = await ac.post("/api/auth/login",
        json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


async def _hdr(tok):  return {"Authorization": f"Bearer {tok}"}


async def _make_approved_creator(db, user_id: str) -> dict:
    cid = f"crt_{uuid.uuid4().hex[:10]}"
    row = {"id": cid, "user_id": user_id,
              "display_name": "P36f Creator",
              "application_status": "approved",
              "approval_status": "approved",
              "is_approved": True}
    await db.podcast_creators.insert_one(row)
    return row


async def _clean(db, creator_id: str):
    await db.creator_saas_subscriptions.delete_many({"creator_id": creator_id})


_BODY = {"plan_id": "creator_pro",
                "success_url": "https://bigfm.dubai/sub/ok",
                "cancel_url":   "https://bigfm.dubai/sub/cancel"}


# ─── 1. Happy path ────────────────────────────────────────────────

def test_creator_can_create_checkout_session_returns_2xx_with_url():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=20) as ac:
            tok, uid = await _register(ac)
            cr = await _make_approved_creator(db, uid)
            r = await ac.post(
                f"/api/podcasts/creators/{cr['id']}/subscription/checkout",
                json=_BODY, headers=await _hdr(tok))
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["checkout_url"]
            assert body["session_id"].startswith("cs_")
            assert body["plan_id"] == "creator_pro"
            assert body["subscription_id"].startswith("csub_")
            assert body["expires_at"]
            await _clean(db, cr["id"])
    run(go())


# ─── 2. Cross-creator → 403 ───────────────────────────────────────

def test_non_owner_creator_403_on_someone_elses_checkout():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=20) as ac:
            tokA, uA = await _register(ac, "owner")
            tokB, uB = await _register(ac, "attacker")
            crA = await _make_approved_creator(db, uA)
            await _make_approved_creator(db, uB)   # attacker is also a creator
            r = await ac.post(
                f"/api/podcasts/creators/{crA['id']}/subscription/checkout",
                json=_BODY, headers=await _hdr(tokB))
            assert r.status_code == 403, r.text
    run(go())


# ─── 3. Admin bypass ──────────────────────────────────────────────

def test_admin_can_create_checkout_on_behalf_of_creator():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=20) as ac:
            _, uA = await _register(ac, "owner_admin_bypass")
            cr = await _make_approved_creator(db, uA)
            hdr = await _login_admin(ac)
            r = await ac.post(
                f"/api/podcasts/creators/{cr['id']}/subscription/checkout",
                json=_BODY, headers=hdr)
            assert r.status_code == 200, r.text
            assert r.json()["checkout_url"]
            await _clean(db, cr["id"])
    run(go())


# ─── 4. Idempotency / already-subscribed ──────────────────────────

def test_already_subscribed_creator_gets_409_not_duplicate_session():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=20) as ac:
            tok, uid = await _register(ac, "dup")
            cr = await _make_approved_creator(db, uid)
            # Seed an ACTIVE sub directly so the next checkout call must 409.
            from datetime import datetime, timezone
            await db.creator_saas_subscriptions.insert_one({
                "id":                            "csub_seeded_for_test",
                "creator_id":            cr["id"],
                "owner_user_id":  uid,
                "plan_id":                  "creator_lite",
                "stripe_subscription_id": "sub_seeded",
                "status":                    "active",
                "created_at":            datetime.now(timezone.utc),
            })
            r = await ac.post(
                f"/api/podcasts/creators/{cr['id']}/subscription/checkout",
                json=_BODY, headers=await _hdr(tok))
            assert r.status_code == 409, r.text
            detail = r.json().get("detail") or {}
            assert detail.get("code") == "already_subscribed"
            assert detail.get("subscription_id") == "csub_seeded_for_test"
            # And no duplicate session row got inserted.
            n = await db.creator_saas_subscriptions.count_documents(
                {"creator_id": cr["id"]})
            assert n == 1, "duplicate checkout row created"
            await _clean(db, cr["id"])
    run(go())


# ─── 5. Invalid plan_id ────────────────────────────────────────────

def test_invalid_plan_id_returns_400():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=20) as ac:
            tok, uid = await _register(ac, "invalid_plan")
            cr = await _make_approved_creator(db, uid)
            bad = {**_BODY, "plan_id": "creator_galactic"}
            r = await ac.post(
                f"/api/podcasts/creators/{cr['id']}/subscription/checkout",
                json=bad, headers=await _hdr(tok))
            assert r.status_code == 400, r.text
            detail = r.json().get("detail") or {}
            assert detail.get("code") == "invalid_plan_id"
            assert "creator_pro" in detail.get("allowed", [])
    run(go())


# ─── 6. Stripe mode (mock) ─────────────────────────────────────────

def test_checkout_uses_current_stripe_mode_test_env():
    """In mock mode the SDK is NOT called, the synthesized URL fingerprint
    is `/mock/stripe/checkout?...`. Asserts no real `sk_live_*` call leaked
    through the wrapper."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        from services import stripe_client
        server = importlib.import_module("server")
        db = _db()
        # Defensive: ensure environment is mock for this test.
        prev_mode = os.environ.get("STRIPE_MODE")
        os.environ["STRIPE_MODE"] = "mock"
        try:
            assert stripe_client.stripe_mode() == "mock"
            async with AsyncClient(transport=ASGITransport(app=server.app),
                                                      base_url="http://test", timeout=20) as ac:
                tok, uid = await _register(ac, "mode_check")
                cr = await _make_approved_creator(db, uid)
                r = await ac.post(
                    f"/api/podcasts/creators/{cr['id']}/subscription/checkout",
                    json=_BODY, headers=await _hdr(tok))
                assert r.status_code == 200, r.text
                url = r.json()["checkout_url"]
                assert "/mock/stripe/checkout" in url, \
                    f"expected mock URL fingerprint, got {url}"
                # And the persisted row holds the mock price + session id.
                row = await db.creator_saas_subscriptions.find_one(
                    {"creator_id": cr["id"]})
                assert row["stripe_price_id"].startswith("price_mock_")
                assert row["stripe_checkout_session_id"].startswith("cs_")
                await _clean(db, cr["id"])
        finally:
            if prev_mode is not None:
                os.environ["STRIPE_MODE"] = prev_mode
            else:
                os.environ.pop("STRIPE_MODE", None)
    run(go())
