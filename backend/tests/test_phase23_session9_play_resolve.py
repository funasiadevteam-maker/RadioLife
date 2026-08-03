"""Phase 23 Session 9 — /api/play/resolve + /api/wallet/save + /api/wallet/items.

Tests the new server-resolved Play & Win surface that lives alongside
the legacy games_v2 routes.  Uses the same advertiser-fixture pattern
as Session 2 so it shares the seeded test user.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
import secrets
from datetime import datetime, timedelta, timezone


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
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[
        os.environ["DB_NAME"]]


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------
# Test fixture — a guaranteed-active campaign with a winnable prize.
# Probability_weight=100 + inventory=999 means the next play is always
# a win, which makes the wallet-save tests deterministic.
# ---------------------------------------------------------------------
async def _seed_winnable_campaign(db, advertiser_id: str = "adv_phase23_s9"
                                                              ) -> str:
    cid = f"cmp_p23s9_{uuid.uuid4().hex[:10]}"
    # Ensure advertiser exists (idempotent).
    await db.advertisers.update_one(
        {"_id": advertiser_id},
        {"$setOnInsert": {
            "_id": advertiser_id,
            "advertiser_id": advertiser_id,
            "user_id": "user_fixture_p23s9",
            "display_name": "P23S9 Test Co",
            "approval_status": "approved",
            "market": "dubai",
        }},
        upsert=True)
    await db.game_campaigns.insert_one({
        "_id": cid, "campaign_id": cid,
        "advertiser_id": advertiser_id,
        "template_id": "tpl_spin_wheel",
        "title": "P23S9 winnable",
        "sponsor_name": "P23S9",
        "status": "active",
        "open_to_all": True,
        "start_at": _now() - timedelta(days=1),
        "end_at": _now() + timedelta(days=7),
        "creator_type": "advertiser",
        "game_config_json": {},
        "brand_colors_json": {"primary": "#F72585"},
        "created_at": _now(),
    })
    await db.game_prizes.insert_one({
        "_id": f"prz_p23s9_{uuid.uuid4().hex[:8]}",
        "prize_id": f"prz_p23s9_{uuid.uuid4().hex[:8]}",
        "campaign_id": cid,
        "prize_type": "coupon",
        "title": "P23S9 Free Drink",
        "value_amount": 10, "value_currency": "AED",
        "probability_weight": 100,
        "inventory_remaining": 999,
        "inventory_total": 999,
        "max_per_user": 99,
        "redemption_method": "internal",
        "active": True,
    })
    return cid


async def _cleanup_campaign(db, cid: str) -> None:
    await db.game_campaigns.delete_one({"campaign_id": cid})
    await db.game_prizes.delete_many({"campaign_id": cid})
    await db.plays.delete_many({"gameId": cid})


async def _login_listener(ac):
    """Demo listener seeded by Phase 12c safety seed."""
    # Try the demo creds first; if missing, seed one.
    r = await ac.post("/api/auth/login",
        json={"email": "test@bigfm.dubai",
              "password": "TestUser123!"})
    if r.status_code != 200:
        # Fallback: create on the fly.
        from auth import hash_password
        db = _db()
        uid = f"user_{uuid.uuid4().hex[:14]}"
        await db.users.insert_one({
            "_id": uid, "user_id": uid,
            "email": "test@bigfm.dubai",
            "name": "P23S9 Listener",
            "password_hash": hash_password("TestUser123!"),
            "role": "listener", "is_premium": False,
            "billing_status": "active",
            "reward_multiplier": 1.0,
            "preference_vector": {"city": "Dubai"},
            "language": "en", "market": "dubai",
            "created_at": _now(),
        })
        r = await ac.post("/api/auth/login",
            json={"email": "test@bigfm.dubai",
                  "password": "TestUser123!"})
    assert r.status_code == 200, r.text
    j = r.json()
    return ({"Authorization": f"Bearer {j['session_token']}"},
              j["user_id"])


# =====================================================================
# /api/play/resolve
# =====================================================================
def test_play_resolve_happy_path():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        db = _db()
        cid = await _seed_winnable_campaign(db)
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            hdr, _uid = await _login_listener(ac)
            try:
                idem = secrets.token_hex(12)
                r = await ac.post("/api/play/resolve",
                                              json={"gameId": cid, "idempotencyKey": idem},
                                              headers=hdr)
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["playId"].startswith("ply_")
                assert body["won"] is True
                assert body["prizeTitle"] == "P23S9 Free Drink"
                assert body["coupon"]["code"].startswith("BIGFM-")
                # Persisted with the idempotencyKey.
                row = await db.plays.find_one({"_id": body["playId"]})
                assert row["idempotencyKey"] == idem
            finally:
                await _cleanup_campaign(db, cid)
    run(go())


def test_play_resolve_idempotent_replay():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        db = _db()
        cid = await _seed_winnable_campaign(db)
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            hdr, _ = await _login_listener(ac)
            try:
                idem = secrets.token_hex(12)
                r1 = await ac.post("/api/play/resolve",
                                              json={"gameId": cid, "idempotencyKey": idem},
                                              headers=hdr)
                r2 = await ac.post("/api/play/resolve",
                                              json={"gameId": cid, "idempotencyKey": idem},
                                              headers=hdr)
                assert r1.status_code == 200
                assert r2.status_code == 200
                # Same playId → no double-resolve, no inventory double-decrement.
                assert r1.json()["playId"] == r2.json()["playId"]
                count = await db.plays.count_documents(
                    {"idempotencyKey": idem})
                assert count == 1
            finally:
                await _cleanup_campaign(db, cid)
    run(go())


def test_play_resolve_auth_required():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            r = await ac.post("/api/play/resolve",
                                      json={"gameId": "anything",
                                              "idempotencyKey": secrets.token_hex(12)})
            assert r.status_code == 401, r.text
    run(go())


def test_play_resolve_unknown_game():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            hdr, _ = await _login_listener(ac)
            r = await ac.post("/api/play/resolve",
                                      json={"gameId": "cmp_does_not_exist_xyz",
                                              "idempotencyKey": secrets.token_hex(12)},
                                      headers=hdr)
            assert r.status_code == 404
    run(go())


# =====================================================================
# /api/wallet/save + /api/wallet/items
# =====================================================================
def test_wallet_save_happy_then_idempotent():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        db = _db()
        cid = await _seed_winnable_campaign(db)
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            hdr, uid = await _login_listener(ac)
            try:
                # Step 1: resolve a play (guaranteed win).
                idem_play = secrets.token_hex(12)
                rp = await ac.post("/api/play/resolve",
                                              json={"gameId": cid, "idempotencyKey": idem_play},
                                              headers=hdr)
                assert rp.status_code == 200 and rp.json()["won"]
                play_id = rp.json()["playId"]

                # Step 2: save to wallet.
                idem_save = secrets.token_hex(12)
                rs1 = await ac.post("/api/wallet/save",
                                            json={"playId": play_id,
                                                    "idempotencyKey": idem_save},
                                            headers=hdr)
                assert rs1.status_code == 200, rs1.text
                item1 = rs1.json()
                assert item1["walletItemId"]
                assert item1["prizeTitle"] == "P23S9 Free Drink"
                assert item1["code"].startswith("BIGFM-")

                # Step 3: save again — must return same walletItemId.
                rs2 = await ac.post("/api/wallet/save",
                                            json={"playId": play_id,
                                                    "idempotencyKey": idem_save},
                                            headers=hdr)
                assert rs2.status_code == 200
                assert rs2.json()["walletItemId"] == item1["walletItemId"]

                # Mongo: exactly one row.
                count = await db.wallet_items.count_documents(
                    {"playId": play_id, "listenerId": uid})
                assert count == 1

                # Step 4: GET /api/wallet/items should list it.
                rl = await ac.get("/api/wallet/items", headers=hdr)
                assert rl.status_code == 200
                ids = [it["walletItemId"] for it in rl.json()]
                assert item1["walletItemId"] in ids
            finally:
                await db.wallet_items.delete_many({"listenerId": uid,
                                                                "gameId": cid})
                await _cleanup_campaign(db, cid)
    run(go())


def test_wallet_save_unknown_play_404():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            hdr, _ = await _login_listener(ac)
            r = await ac.post("/api/wallet/save",
                                      json={"playId": "ply_does_not_exist",
                                              "idempotencyKey": secrets.token_hex(12)},
                                      headers=hdr)
            assert r.status_code == 404, r.text
    run(go())


def test_wallet_items_auth_required():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            r = await ac.get("/api/wallet/items")
            assert r.status_code == 401
    run(go())
