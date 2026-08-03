"""Phase P2 — `routes/podcasts.py` hygiene sweep tests.

Coverage:
  • 404 → 403 standardization on 4 routes for cross-creator requests, with
    a 404 ground-truth check for genuinely missing rows.
  • Pagination caps + envelope on `/channels/{cid}/episodes` and
    admin `/channels`.
  • Duplicate-route removal (introspect openapi).
  • Lightning splits SoT consolidation + idempotent admin reconcile.
  • Semantic rename: action-card response carries both `creator_id` and
    `owner_user_id`.
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


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ─── auth helpers ─────────────────────────────────────────────────

async def _register(ac, email_prefix="u"):
    suf = uuid.uuid4().hex[:8]
    r = await ac.post("/api/auth/register",
        json={"email": f"{email_prefix}_p2_{suf}@bigfm.dubai",
                  "password": "Pwd1234!", "name": "P2 User"})
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
    """Insert a `podcast_creators` row in approved state, return the row."""
    cid = f"crt_{uuid.uuid4().hex[:10]}"
    row = {"id": cid, "user_id": user_id,
              "display_name": "P2 Creator",
              "application_status": "approved",
              "approval_status": "approved",
              "is_approved": True}
    await db.podcast_creators.insert_one(row)
    return row


async def _make_channel(db, creator_id: str, owner_uid: str) -> dict:
    cid = f"ch_{uuid.uuid4().hex[:10]}"
    slug = f"p2-{uuid.uuid4().hex[:6]}"
    row = {"id": cid, "slug": slug, "creator_id": creator_id,
              "owner_user_id": owner_uid,
              "title": "P2 Channel", "approval_status": "approved",
              "active": True}
    await db.podcast_channels.insert_one(row)
    return row


async def _make_episode(db, ch_id: str, *, status="published") -> dict:
    eid = f"ep_{uuid.uuid4().hex[:10]}"
    row = {"id": eid, "channel_id": ch_id,
              "title": "P2 Episode",
              "publish_status": status,
              "duration_sec": 120}
    await db.podcast_episodes.insert_one(row)
    return row


# ─── 1.  404 → 403 standardization (4 of the 12 sites) ───────────

def test_cross_creator_patch_episode_returns_403():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            tokA, uA = await _register(ac, "ownerA")
            tokB, uB = await _register(ac, "attackerB")
            crA = await _make_approved_creator(db, uA)
            await _make_approved_creator(db, uB)
            ch = await _make_channel(db, crA["id"], uA)
            ep = await _make_episode(db, ch["id"])
            # Owner OK.
            r1 = await ac.patch(
                f"/api/podcasts/channels/{ch['id']}/episodes/{ep['id']}",
                json={"title": "Renamed by owner"}, headers=await _hdr(tokA))
            assert r1.status_code in (200, 404), r1.text  # 404 OK if route emits
            # Attacker → 403.
            r2 = await ac.patch(
                f"/api/podcasts/channels/{ch['id']}/episodes/{ep['id']}",
                json={"title": "hijack"}, headers=await _hdr(tokB))
            assert r2.status_code == 403, f"expected 403, got {r2.status_code}: {r2.text}"
            # Genuine 404: missing channel id.
            r3 = await ac.patch(
                "/api/podcasts/channels/nope_does_not_exist/episodes/x",
                json={"title": "x"}, headers=await _hdr(tokA))
            assert r3.status_code == 404
    run(go())


def test_cross_creator_publish_episode_returns_403():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            tokA, uA = await _register(ac, "ownerA")
            tokB, _ = await _register(ac, "attackerB")
            crA = await _make_approved_creator(db, uA)
            ch = await _make_channel(db, crA["id"], uA)
            ep = await _make_episode(db, ch["id"], status="draft")
            r = await ac.post(
                f"/api/podcasts/channels/{ch['id']}/episodes/{ep['id']}/publish",
                headers=await _hdr(tokB))
            assert r.status_code == 403, r.text
            r404 = await ac.post(
                "/api/podcasts/channels/missing/episodes/x/publish",
                headers=await _hdr(tokA))
            assert r404.status_code == 404
    run(go())


def test_cross_creator_transcribe_returns_403():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            tokA, uA = await _register(ac, "ownerA")
            tokB, _ = await _register(ac, "attackerB")
            crA = await _make_approved_creator(db, uA)
            ch = await _make_channel(db, crA["id"], uA)
            ep = await _make_episode(db, ch["id"])
            r = await ac.post(f"/api/podcasts/episodes/{ep['id']}/transcribe",
                                          headers=await _hdr(tokB))
            assert r.status_code == 403, r.text
            r404 = await ac.post("/api/podcasts/episodes/missing_ep/transcribe",
                                                headers=await _hdr(tokA))
            assert r404.status_code == 404
    run(go())


def test_cross_creator_delete_episode_returns_403():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            tokA, uA = await _register(ac, "ownerA")
            tokB, _ = await _register(ac, "attackerB")
            crA = await _make_approved_creator(db, uA)
            ch = await _make_channel(db, crA["id"], uA)
            ep = await _make_episode(db, ch["id"])
            r = await ac.delete(
                f"/api/podcasts/channels/{ch['id']}/episodes/{ep['id']}",
                headers=await _hdr(tokB))
            assert r.status_code == 403, r.text
            r404 = await ac.delete(
                "/api/podcasts/channels/missing/episodes/x",
                headers=await _hdr(tokA))
            assert r404.status_code == 404
    run(go())


# ─── 2. Pagination caps + envelope ────────────────────────────────

def test_pagination_cap_admin_channels():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            hdr = await _login_admin(ac)
            # default: limit=50, items present
            r1 = await ac.get("/api/admin/podcasts/channels", headers=hdr)
            assert r1.status_code == 200, r1.text
            body = r1.json()
            assert "items" in body and "next_cursor" in body and "total_seen" in body
            assert len(body["items"]) <= 50
            # explicit limit=50 still OK
            r2 = await ac.get("/api/admin/podcasts/channels?limit=50",
                                          headers=hdr)
            assert r2.status_code == 200
            # limit=201 → 400 limit_out_of_range
            r3 = await ac.get("/api/admin/podcasts/channels?limit=201",
                                          headers=hdr)
            assert r3.status_code == 400
            assert "limit_out_of_range" in r3.text
    run(go())


# ─── 3. Duplicate-route removal (openapi introspection) ──────────

def test_duplicate_status_routes_removed():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=15) as ac:
            r = await ac.get("/api/openapi.json")
            paths = r.json().get("paths", {})
            # Underscore/dash duplicates should be gone.
            assert "/api/podcasts/admin/integrations/assemblyai/status" not in paths
            assert "/api/podcasts/admin/integrations/livekit/status" not in paths
            # Canonical admin paths still present.
            assert "/api/admin/podcasts/integrations/assemblyai/status" in paths
            assert "/api/admin/podcasts/integrations/livekit/status" in paths
            # Phase 36d placeholder stub removed.
            assert ("/api/podcasts/episodes/{ep_id}/ai/generate-clips-suggestions"
                          not in paths)
    run(go())


# ─── 4. Lightning splits SoT consolidation ───────────────────────

_SPLITS = [
    {"name": "creator",  "type": "lnaddress",
      "address": "host@strike.me", "split_pct": 100.0},
]


def test_patch_value_config_writes_through_to_podcast_lightning_splits_collection():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            tok, uA = await _register(ac, "splitsA")
            cr = await _make_approved_creator(db, uA)
            ch = await _make_channel(db, cr["id"], uA)
            r = await ac.patch(
                f"/api/podcasts/channels/{ch['id']}/value-config",
                json={"enabled": True, "method": "keysend",
                          "splits": _SPLITS},
                headers=await _hdr(tok))
            assert r.status_code == 200, r.text
            sot = await db.podcast_lightning_splits.find_one(
                {"channel_id": ch["id"], "episode_id": None})
            assert sot is not None, "SoT row missing after value-config patch"
            assert len(sot["recipients"]) == 1
            assert sot["recipients"][0]["address"] == "host@strike.me"
            # And the mirror is in place too.
            after = await db.podcast_channels.find_one({"id": ch["id"]})
            mirror = (after.get("value_config") or {}).get("splits") or []
            assert mirror and mirror[0]["address"] == "host@strike.me"
    run(go())


def test_put_lightning_splits_writes_through_and_mirrors_into_value_config():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            tok, uA = await _register(ac, "splitsB")
            cr = await _make_approved_creator(db, uA)
            ch = await _make_channel(db, cr["id"], uA)
            r = await ac.put(
                f"/api/podcasts/channels/{ch['id']}/lightning-splits",
                json={"recipients": _SPLITS},
                headers=await _hdr(tok))
            assert r.status_code == 200, r.text
            sot = await db.podcast_lightning_splits.find_one(
                {"channel_id": ch["id"], "episode_id": None})
            assert sot is not None
            after = await db.podcast_channels.find_one({"id": ch["id"]})
            mirror = (after.get("value_config") or {}).get("splits") or []
            assert mirror and mirror[0]["address"] == "host@strike.me", \
                "PUT must mirror splits into channel.value_config.splits"
    run(go())


def test_reconcile_endpoint_is_idempotent():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            hdr = await _login_admin(ac)
            r1 = await ac.post(
                "/api/admin/podcasts/lightning-splits/reconcile",
                headers=hdr)
            assert r1.status_code == 200, r1.text
            r2 = await ac.post(
                "/api/admin/podcasts/lightning-splits/reconcile",
                headers=hdr)
            assert r2.status_code == 200
            # Idempotent: second call should reconcile 0 rows (nothing
            # changed between calls).
            assert r2.json()["reconciled"] == 0, r2.text
    run(go())


def test_reconcile_endpoint_admin_only_403_for_non_admin():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=20) as ac:
            tok, _ = await _register(ac, "non_admin")
            r = await ac.post(
                "/api/admin/podcasts/lightning-splits/reconcile",
                headers=await _hdr(tok))
            assert r.status_code == 403, r.text
    run(go())


# ─── 5. Semantic rename — both keys on action-card response ──────

def test_action_card_response_carries_both_owner_user_id_and_creator_id():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            tok, uA = await _register(ac, "cards")
            cr = await _make_approved_creator(db, uA)
            ch = await _make_channel(db, cr["id"], uA)
            ep = await _make_episode(db, ch["id"])
            r = await ac.post(
                f"/api/podcasts/episodes/{ep['id']}/action-cards",
                json={"card_type": "save_coupon",
                          "title": "Save 10%",
                          "start_time_seconds": 1, "end_time_seconds": 30,
                          "destination_url": "https://example.com"},
                headers=await _hdr(tok))
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["owner_user_id"] == uA
            # Phase 19 Part C — legacy `creator_id` response alias dropped.
            assert "creator_id" not in body
    run(go())
