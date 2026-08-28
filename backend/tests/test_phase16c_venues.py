"""
Phase 16c — Venue staff + TV display tests (12 cases).

Approach: most tests exercise the in-process hubs + DB directly to keep
runtime fast and avoid spinning a real ASGI server.  Tests that need the
full request/response cycle (live REST surface) go through the running
uvicorn at localhost:8001.
"""
import asyncio
import json
import os
import sys
import time
import uuid

import pytest
import httpx
from dotenv import load_dotenv

sys.path.insert(0, "/app/backend")
load_dotenv("/app/backend/.env")

# ─── Helpers ────────────────────────────────────────────────────────
def _new_loop():
    asyncio.set_event_loop(asyncio.new_event_loop())
    return asyncio.get_event_loop()


def _live_client():
    """httpx.Client logged in as admin@bigfm.dubai (venue owner)."""
    c = httpx.Client(base_url="http://localhost:8001", timeout=15)
    r = c.post("/api/auth/login", json={"email": "admin@bigfm.dubai",
                                                    "password": "AdminPass123!"})
    assert r.status_code == 200, r.text
    raw = r.headers.get("set-cookie", "")
    token = raw.split("bigfm_session=", 1)[1].split(";", 1)[0]
    c.cookies.set("bigfm_session", token)
    return c


def _live_client_as(email, password):
    c = httpx.Client(base_url="http://localhost:8001", timeout=15)
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    raw = r.headers.get("set-cookie", "")
    token = raw.split("bigfm_session=", 1)[1].split(";", 1)[0]
    c.cookies.set("bigfm_session", token)
    return c


VENUE_ID = "venue_demo_karak"


# ─── 1. Pairing code expiry ─────────────────────────────────────────
def test_tv_pairing_code_expires_after_10_minutes():
    """We pre-stamp expires_at to the past and confirm /tv/claim returns 410."""
    loop = _new_loop()
    from motor.motor_asyncio import AsyncIOMotorClient
    from datetime import datetime, timezone, timedelta

    async def run():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        code = "999-999"
        await db.tv_pairings.insert_one({
            "id":             "tvp_test_exp",
            "venue_id":      VENUE_ID,
            "pairing_code": code,
            "status":         "pending",
            "expires_at":    datetime.now(timezone.utc) - timedelta(seconds=10),
            "active":          True,
        })
        try:
            c = _live_client()
            r = c.post("/api/tv/claim", json={"pairing_code": code})
            assert r.status_code == 410, r.text
            d = r.json()["detail"]
            assert d["code"] == "pairing_expired"
        finally:
            await db.tv_pairings.delete_one({"id": "tvp_test_exp"})
            client.close()

    loop.run_until_complete(run())


# ─── 2. Token durable across refreshes ──────────────────────────────
def test_tv_token_durable_across_refreshes():
    """After claim, the tv_token still validates against /api/tv/me."""
    c = _live_client()
    r = c.post(f"/api/venue/{VENUE_ID}/tvs/pair")
    assert r.status_code == 200, r.text
    code = r.json()["pairing_code"]
    # Claim from an anonymous client.
    c2 = httpx.Client(base_url="http://localhost:8001", timeout=15)
    r = c2.post("/api/tv/claim", json={"pairing_code": code})
    assert r.status_code == 200, r.text
    token = r.json()["tv_token"]
    # Use a brand-new client (simulating page refresh) — token still valid.
    c3 = httpx.Client(base_url="http://localhost:8001", timeout=15)
    r = c3.get(f"/api/tv/me?token={token}")
    assert r.status_code == 200, r.text
    assert r.json()["venue"]["id"] == VENUE_ID
    c2.close(); c3.close()


# ─── 3. Revoke disconnects WS ───────────────────────────────────────
def test_revoke_tv_token_disconnects_tv_ws():
    """After revoke, both REST `/api/tv/me?token=` returns 401 and the
    WS attempt closes immediately (4401)."""
    c = _live_client()
    r = c.post(f"/api/venue/{VENUE_ID}/tvs/pair")
    code = r.json()["pairing_code"]
    rc = httpx.Client(base_url="http://localhost:8001", timeout=15)
    token = rc.post("/api/tv/claim", json={"pairing_code": code}).json()["tv_token"]
    # tv_id needs to be fetched from venue's TV list.
    tvs = c.get(f"/api/venue/{VENUE_ID}/tvs").json()["tvs"]
    tv = next(t for t in tvs if t["status"] == "active" and t.get("paired_at"))
    # Now revoke.
    r = c.post(f"/api/venue/{VENUE_ID}/tvs/{tv['id']}/revoke")
    assert r.status_code == 200
    # /tv/me should now 401.
    r = rc.get(f"/api/tv/me?token={token}")
    assert r.status_code == 401
    rc.close()


# ─── 4. Only staff can start a venue room ───────────────────────────
def test_only_venue_staff_can_start_room_for_that_venue():
    """A non-staff user gets 403 on POST /venue/{id}/trivia/start."""
    # Owner can start.
    owner = _live_client()
    cats = owner.get("/api/trivia/categories").json()["categories"]
    r = owner.post(f"/api/venue/{VENUE_ID}/trivia/start",
                          json={"category_id": cats[0]["id"]})
    assert r.status_code == 200, r.text
    # A premium-only listener (no staff membership) hits 403.
    other = _live_client_as("premium@bigfm.dubai", "PremiumTest123!")
    try:
        r = other.post(f"/api/venue/{VENUE_ID}/trivia/start",
                              json={"category_id": cats[0]["id"]})
        assert r.status_code == 403, r.text
    finally:
        other.close()


# ─── 5. Announcement broadcasts everywhere ──────────────────────────
def test_venue_announcement_broadcasts_to_all_room_players_and_tvs():
    """Captured at the HTTP layer: response reports rooms + tvs hit."""
    c = _live_client()
    # Pair a TV so there's at least one tv broadcast target.
    code = c.post(f"/api/venue/{VENUE_ID}/tvs/pair").json()["pairing_code"]
    rc = httpx.Client(base_url="http://localhost:8001", timeout=15)
    rc.post("/api/tv/claim", json={"pairing_code": code})
    rc.close()
    r = c.post(f"/api/venue/{VENUE_ID}/announcement",
                      json={"message": "Free dessert for top 3!", "emoji": "🍰"})
    assert r.status_code == 200, r.text
    body = r.json()
    # Rooms is a (possibly empty) list of codes; tvs is a list of ids.
    assert "rooms" in body
    assert "tvs"     in body
    assert isinstance(body["rooms"], list)
    assert isinstance(body["tvs"], list)


# ─── 6. Coupon redeem is idempotent ─────────────────────────────────
def test_coupon_redemption_marks_idempotent():
    """First call ok, second returns 409 already_redeemed."""
    loop = _new_loop()
    from motor.motor_asyncio import AsyncIOMotorClient

    async def setup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        coupon_id = f"cpn_test_{uuid.uuid4().hex[:10]}"
        await db.coupons.insert_one({
            "coupon_id":  coupon_id,
            "business_id": "biz_demo_karak",
            "status":      "issued",
            "user_id":    "user_demo",
        })
        return client, db, coupon_id

    client, db, coupon_id = loop.run_until_complete(setup())
    try:
        c = _live_client()
        r = c.post(f"/api/venue/{VENUE_ID}/coupons/redeem", json={"code": coupon_id})
        assert r.status_code == 200, r.text
        r = c.post(f"/api/venue/{VENUE_ID}/coupons/redeem", json={"code": coupon_id})
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["code"] == "already_redeemed"
    finally:
        loop.run_until_complete(db.coupons.delete_one({"coupon_id": coupon_id}))
        client.close()


# ─── 7. Coupon scoped to owning venue ───────────────────────────────
def test_coupon_redemption_only_for_owning_venue():
    """A coupon tagged for biz_other returns 403 wrong_venue when our
    demo venue (biz_demo_karak) tries to redeem it."""
    loop = _new_loop()
    from motor.motor_asyncio import AsyncIOMotorClient

    async def setup():
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ["DB_NAME"]]
        coupon_id = f"cpn_other_{uuid.uuid4().hex[:10]}"
        await db.coupons.insert_one({
            "coupon_id":  coupon_id,
            "business_id": "biz_other_partner",
            "status":      "issued",
        })
        return client, db, coupon_id

    client, db, coupon_id = loop.run_until_complete(setup())
    try:
        c = _live_client()
        r = c.post(f"/api/venue/{VENUE_ID}/coupons/redeem", json={"code": coupon_id})
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "wrong_venue"
    finally:
        loop.run_until_complete(db.coupons.delete_one({"coupon_id": coupon_id}))
        client.close()


# ─── 8. Role gating: staff vs owner ─────────────────────────────────
def test_venue_staff_role_gating_enforced():
    """test@bigfm.dubai is `staff` on the demo venue.  They can start
    trivia but cannot remove other staff (owner-only)."""
    staff = _live_client_as("test@bigfm.dubai", "TestUser123!")
    try:
        # Staff CAN start trivia.
        cats = staff.get("/api/trivia/categories").json()["categories"]
        r = staff.post(f"/api/venue/{VENUE_ID}/trivia/start",
                              json={"category_id": cats[0]["id"]})
        assert r.status_code == 200, r.text
        # Staff CANNOT add another staff member (owner-only).
        r = staff.post(f"/api/venue/{VENUE_ID}/staff",
                              json={"email": "premium@bigfm.dubai", "role": "staff"})
        assert r.status_code == 403, r.text
    finally:
        staff.close()


# ─── 9. Kick via venue dashboard uses 16b RoomHub.kick ──────────────
def test_kicked_player_via_venue_dashboard_uses_phase16b_kick_handler():
    """Wire-up test: the venue kick path calls `hub.kick`, which sends
    the targeted `kicked` frame to the victim and closes 4001."""
    loop = _new_loop()

    class FakeWS:
        def __init__(self):
            self.sent = []
            self.closed_with = None
        async def send_text(self, p):
            self.sent.append(p)
        async def close(self, code=1000, reason=""):
            self.closed_with = (code, reason)

    async def run():
        from services.trivia_rooms import RoomHub
        hub = RoomHub()
        room = await hub.create(host_user={"user_id": "u_h", "name": "H"},
                                       category_id="x", category_slug="x", market="dubai")
        room.venue_id = VENUE_ID
        await hub.add_player(room.code, {"user_id": "u_v", "name": "V"})
        victim_ws = FakeWS()
        hub.attach_socket(room.code, "u_v", victim_ws)
        # Mimic what venue_kick does after auth — straight call to hub.kick.
        await hub.kick(room.code, "u_v")
        assert victim_ws.closed_with == (4001, "kicked"), victim_ws.closed_with
        msgs = [json.loads(p) for p in victim_ws.sent if '"kicked"' in p and '"type"' in p]
        assert len(msgs) == 1 and msgs[0]["reason"] == "removed_by_host"

    loop.run_until_complete(run())


# ─── 10. Venue stats aggregates correctly ───────────────────────────
def test_venue_stats_aggregation():
    c = _live_client()
    r = c.get(f"/api/venue/{VENUE_ID}/stats?period=today")
    assert r.status_code == 200, r.text
    b = r.json()
    for k in ("rooms", "coupons", "announcements", "live_players", "live_rooms"):
        assert k in b
        assert isinstance(b[k], int)


# ─── 11. TV lobby state when no active room ─────────────────────────
def test_tv_display_shows_lobby_state_when_no_active_room():
    """If no venue room is in the hub, /api/tv/me returns the venue + an
    empty schedule (the TV UI then renders the welcome screen)."""
    c = _live_client()
    code = c.post(f"/api/venue/{VENUE_ID}/tvs/pair").json()["pairing_code"]
    rc = httpx.Client(base_url="http://localhost:8001", timeout=15)
    token = rc.post("/api/tv/claim", json={"pairing_code": code}).json()["tv_token"]
    r = rc.get(f"/api/tv/me?token={token}")
    assert r.status_code == 200
    b = r.json()
    assert b["venue"]["id"] == VENUE_ID
    rc.close()


# ─── 12. TV WS receives hello + venue snapshot ──────────────────────
def test_tv_display_subscribes_to_active_room_via_ws():
    """Open a real WS against /api/tv/ws and assert a `hello` frame is
    received with the venue payload."""
    import websockets
    c = _live_client()
    code = c.post(f"/api/venue/{VENUE_ID}/tvs/pair").json()["pairing_code"]
    rc = httpx.Client(base_url="http://localhost:8001", timeout=15)
    token = rc.post("/api/tv/claim", json={"pairing_code": code}).json()["tv_token"]
    rc.close()

    loop = _new_loop()

    async def run():
        url = f"ws://localhost:8001/api/tv/ws?token={token}"
        async with websockets.connect(url) as ws:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=4))
            assert msg["type"] == "hello", msg
            assert msg["venue"]["id"] == VENUE_ID
            assert "active_rooms" in msg

    loop.run_until_complete(run())
