"""Phase 7 — Social Lobbies pytest suite.

Drives the live FastAPI server through `requests` so motor / asyncio share the
server's event loop. Mirrors the Phase 6 test layout. WebSocket protocol is
exercised via `websockets` directly in test_24_ws_chat_broadcast.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone

import pytest
import requests
import websockets
from motor.motor_asyncio import AsyncIOMotorClient

API = os.environ.get("PHASE7_API",
                       "https://mobile-games-v2.preview.emergentagent.com").rstrip("/") + "/api"
WS_BASE = API.replace("https://", "wss://").replace("http://", "ws://")
MONGO = os.environ.get("PHASE7_MONGO", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")

FREE_CAP = 50
PREMIUM_CAP = 200
DAILY_JOIN_CAP = 3


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.text}"
    s._user_id = r.json()["user_id"]
    return s


@pytest.fixture(scope="module")
def free_session():
    # Ensure test@bigfm.dubai is in a clean free-tier state before the suite.
    async def reset():
        db = _mongo()
        await db.users.update_one(
            {"email": "test@bigfm.dubai"},
            {"$set": {"is_premium": False, "premium_tier": None,
                       "premium_source": None, "billing_status": "active",
                       "reward_multiplier": 1.0,
                       "current_plan_slug": "free",
                       "subscription.plan": "free",
                       "subscription.status": "free"},
             "$unset": {"family_root_user_id": "", "premium_until": "",
                         "grace_period_ends_at": "", "past_due_started_at": ""}},
        )
    asyncio.run(reset())
    return _login("test@bigfm.dubai", "TestUser123!")


@pytest.fixture(scope="module")
def premium_session():
    return _login("premium@bigfm.dubai", "PremiumTest123!")


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


def _mongo():
    cli = AsyncIOMotorClient(MONGO)
    return cli[DB_NAME]


async def _clean_lobbies(user_id: str):
    db = _mongo()
    await db.lobbies.delete_many({"host_user_id": user_id})
    await db.lobby_members.delete_many({"user_id": user_id})
    await db.lobby_joins_daily.delete_many({"user_id": user_id})


def _run(coro):
    asyncio.run(coro)


def _wipe_host(user_id: str):
    _run(_clean_lobbies(user_id))


# ----------------------------------------------------------------------
def test_01_list_lobbies_public_works():
    r = requests.get(f"{API}/lobbies/list", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body


def test_02_host_caps_free(free_session):
    r = free_session.get(f"{API}/lobbies/host_caps", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["free_host_max_listeners"] == FREE_CAP
    assert body["premium_host_max_listeners"] == PREMIUM_CAP
    assert body["max_listeners"] == FREE_CAP
    assert body["is_premium"] is False
    assert body["free_join_daily_cap"] == DAILY_JOIN_CAP


def test_03_host_caps_premium(premium_session):
    r = premium_session.get(f"{API}/lobbies/host_caps", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["is_premium"] is True
    assert body["max_listeners"] == PREMIUM_CAP


def test_04_create_lobby_and_listed(free_session):
    _wipe_host(free_session._user_id)
    name = f"Test Lobby {uuid.uuid4().hex[:6]}"
    r = free_session.post(f"{API}/lobbies/create",
                              json={"name": name,
                                    "channel_slug": "bollywood_mehfil",
                                    "mood": "chill"}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["host_user_id"] == free_session._user_id
    assert body["max_listeners"] == FREE_CAP
    lobby_id = body["lobby_id"]
    # Listed publicly
    r2 = requests.get(f"{API}/lobbies/list", timeout=10).json()
    assert any(it["lobby_id"] == lobby_id for it in r2["items"])
    # Detail
    r3 = free_session.get(f"{API}/lobbies/{lobby_id}", timeout=10).json()
    assert r3["i_am_host"] is True
    free_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


def test_05_cannot_double_host(free_session):
    _wipe_host(free_session._user_id)
    r = free_session.post(f"{API}/lobbies/create",
                              json={"name": "First",
                                    "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    r2 = free_session.post(f"{API}/lobbies/create",
                                json={"name": "Second",
                                      "channel_slug": "bollywood_mehfil"}, timeout=10)
    assert r2.status_code == 400
    assert "already_hosting" in r2.json()["detail"]
    free_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


def test_06_premium_only_channel_blocks_free(free_session):
    _wipe_host(free_session._user_id)
    r = free_session.post(f"{API}/lobbies/create",
                              json={"name": "Premium attempt",
                                    "channel_slug": "premium_mehfil"}, timeout=10)
    assert r.status_code == 400
    assert "premium" in r.json()["detail"].lower()


def test_07_unknown_channel_blocked(free_session):
    _wipe_host(free_session._user_id)
    r = free_session.post(f"{API}/lobbies/create",
                              json={"name": "Bad",
                                    "channel_slug": "nope_does_not_exist"}, timeout=10)
    assert r.status_code == 400


def test_08_join_leave_flow(premium_session, free_session):
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Join-flow",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    # Clear free user's quota + membership
    _run(_clean_lobbies(free_session._user_id))
    rj = free_session.post(f"{API}/lobbies/{lobby_id}/join", timeout=10)
    assert rj.status_code == 200, rj.text
    assert rj.json()["role"] == "listener"
    assert rj.json()["current_listener_count"] >= 2
    # Leave
    rl = free_session.post(f"{API}/lobbies/{lobby_id}/leave", timeout=10)
    assert rl.status_code == 200
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


async def _make_synth_lobbies(n: int) -> list:
    """Insert N synthetic lobby docs directly into Mongo so tests can hammer
    the join quota without spinning up N real hosts."""
    db = _mongo()
    ids = []
    for i in range(n):
        lid = f"lob_synth_{uuid.uuid4().hex[:10]}"
        await db.lobbies.insert_one({
            "_id": lid, "lobby_id": lid, "name": f"Synth {i}",
            "host_user_id": f"user_synth_{i}",
            "host_display_name": "synth", "host_avatar_color": "#888",
            "channel_slug": "bollywood_mehfil",
            "channel_name": "Bollywood Mehfil",
            "is_public": True, "max_listeners": 50,
            "current_listener_count": 1, "status": "live",
            "created_at": datetime.now(timezone.utc),
            "closed_at": None, "skips_used_window": [],
            "current_segment_id": None,
        })
        ids.append(lid)
    return ids


async def _clean_synth_lobbies(ids: list):
    db = _mongo()
    await db.lobbies.delete_many({"_id": {"$in": ids}})
    await db.lobby_members.delete_many({"lobby_id": {"$in": ids}})


def test_09_free_user_daily_join_cap(free_session):
    """Free listener can join up to DAILY_JOIN_CAP lobbies / UTC day; cap+1 fails."""
    synth_ids = _run_returning(_make_synth_lobbies(DAILY_JOIN_CAP + 1))
    try:
        _run(_clean_joins(free_session._user_id, synth_ids))
        for i in range(DAILY_JOIN_CAP):
            rj = free_session.post(f"{API}/lobbies/{synth_ids[i]}/join", timeout=10)
            assert rj.status_code == 200, f"join {i} failed: {rj.text}"
        # Cap+1 — must fail
        rj_over = free_session.post(f"{API}/lobbies/{synth_ids[-1]}/join", timeout=10)
        assert rj_over.status_code == 400
        assert rj_over.json()["detail"] == "free_daily_join_cap_reached"
    finally:
        _run(_clean_synth_lobbies(synth_ids))
        _run(_clean_joins(free_session._user_id, synth_ids))


async def _clean_joins(user_id: str, lobby_ids: list):
    db = _mongo()
    await db.lobby_joins_daily.delete_many({"user_id": user_id})
    await db.lobby_members.delete_many({"user_id": user_id,
                                              "lobby_id": {"$in": lobby_ids}})


def _run_returning(coro):
    """Run a coroutine and return its result via a synchronous wrapper."""
    return asyncio.run(coro)


def test_10_premium_user_unlimited_joins(premium_session):
    """Premium users bypass the daily join cap."""
    synth_ids = _run_returning(_make_synth_lobbies(DAILY_JOIN_CAP + 2))
    try:
        _run(_clean_joins(premium_session._user_id, synth_ids))
        for i in range(DAILY_JOIN_CAP + 2):
            rj = premium_session.post(f"{API}/lobbies/{synth_ids[i]}/join", timeout=10)
            assert rj.status_code == 200, f"premium join {i} failed: {rj.text}"
    finally:
        _run(_clean_synth_lobbies(synth_ids))
        _run(_clean_joins(premium_session._user_id, synth_ids))


# ----------------------------------------------------------------------
async def _force_segment(lobby_id: str, seg_id: str):
    db = _mongo()
    await db.lobbies.update_one(
        {"lobby_id": lobby_id},
        {"$set": {"current_segment_id": seg_id}},
    )


def test_11_skip_vote_solo_majority(premium_session):
    """Single user in a lobby is automatically majority (1/1, threshold=1)."""
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Skip test",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    _run(_force_segment(lobby_id, f"seg_fake_{uuid.uuid4().hex[:8]}"))
    rv = premium_session.post(f"{API}/lobbies/{lobby_id}/skip_vote", timeout=10)
    assert rv.status_code == 200
    body = rv.json()
    assert body["votes"] == 1
    assert body["threshold"] == 1
    assert body["triggered"] is True
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


def test_12_skip_vote_requires_segment(premium_session):
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Skip test 2",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    rv = premium_session.post(f"{API}/lobbies/{lobby_id}/skip_vote", timeout=10)
    assert rv.status_code == 400
    assert rv.json()["detail"] == "no_current_segment"
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


async def _count_skip_votes(lobby_id: str) -> int:
    return await _mongo().lobby_skip_votes.count_documents({"lobby_id": lobby_id})


def test_13_announce_segment_clears_stale_votes(premium_session):
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Announce test",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    seg1 = f"seg_{uuid.uuid4().hex[:8]}"
    ann = premium_session.post(f"{API}/lobbies/{lobby_id}/announce_segment",
                                     json={"segment_id": seg1,
                                           "segment_url": f"/api/radio/segment/{seg1}",
                                           "duration_sec": 60.0,
                                           "track_title": "Test Song",
                                           "track_artist": "Test Artist"}, timeout=10)
    assert ann.status_code == 200
    rv = premium_session.post(f"{API}/lobbies/{lobby_id}/skip_vote", timeout=10)
    assert rv.json()["triggered"]
    seg2 = f"seg_{uuid.uuid4().hex[:8]}"
    ann2 = premium_session.post(f"{API}/lobbies/{lobby_id}/announce_segment",
                                      json={"segment_id": seg2,
                                            "segment_url": f"/api/radio/segment/{seg2}",
                                            "duration_sec": 70.0,
                                            "track_title": "Next"}, timeout=10)
    assert ann2.status_code == 200
    assert _run_returning(_count_skip_votes(lobby_id)) == 0
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


def test_14_announce_segment_requires_host(premium_session, free_session):
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Host-only",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    _run(_clean_joins(free_session._user_id, [lobby_id]))
    free_session.post(f"{API}/lobbies/{lobby_id}/join", timeout=10)
    bad = free_session.post(f"{API}/lobbies/{lobby_id}/announce_segment",
                                  json={"segment_id": "seg_x"}, timeout=10)
    assert bad.status_code == 403
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


def test_15_kick_authorization(premium_session, free_session):
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Kick test",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    _run(_clean_joins(free_session._user_id, [lobby_id]))
    free_session.post(f"{API}/lobbies/{lobby_id}/join", timeout=10)
    # Free user can't kick the host
    bad = free_session.post(f"{API}/lobbies/{lobby_id}/kick",
                                  json={"user_id": premium_session._user_id}, timeout=10)
    assert bad.status_code == 403
    # Host kicks listener — OK
    good = premium_session.post(f"{API}/lobbies/{lobby_id}/kick",
                                       json={"user_id": free_session._user_id,
                                             "reason": "test"}, timeout=10)
    assert good.status_code == 200
    # Host can't kick self
    self_kick = premium_session.post(f"{API}/lobbies/{lobby_id}/kick",
                                            json={"user_id": premium_session._user_id},
                                            timeout=10)
    assert self_kick.status_code == 400
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


def test_16_close_authorization(premium_session, free_session):
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Close test",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    bad = free_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)
    assert bad.status_code == 403
    good = premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)
    assert good.status_code == 200
    again = premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)
    assert again.json().get("already_closed") is True


def test_17_invite_token_flow(premium_session, free_session):
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Invite test",
                                        "channel_slug": "bollywood_mehfil",
                                        "is_public": False}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    inv = premium_session.post(f"{API}/lobbies/{lobby_id}/invite", timeout=10)
    assert inv.status_code == 200
    token = inv.json()["token"]
    assert token.startswith("li_")
    _run(_clean_joins(free_session._user_id, [lobby_id]))
    bad = free_session.post(f"{API}/lobbies/{lobby_id}/join", timeout=10)
    assert bad.status_code == 400
    assert bad.json()["detail"] == "invite_required"
    good = free_session.post(f"{API}/lobbies/{lobby_id}/join",
                                   json={"invite_token": token}, timeout=10)
    assert good.status_code == 200
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


def test_18_transfer_host(premium_session, free_session):
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Transfer test",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    _run(_clean_joins(free_session._user_id, [lobby_id]))
    free_session.post(f"{API}/lobbies/{lobby_id}/join", timeout=10)
    tr = premium_session.post(f"{API}/lobbies/{lobby_id}/transfer_host",
                                     json={"user_id": free_session._user_id}, timeout=10)
    assert tr.status_code == 200, tr.text
    # Old host can't close any more
    bad = premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)
    assert bad.status_code == 403
    good = free_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)
    assert good.status_code == 200


def test_19_change_channel_host_only(premium_session, free_session):
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Channel test",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    good = premium_session.post(f"{API}/lobbies/{lobby_id}/change_channel",
                                       json={"channel_slug": "party_dubai"}, timeout=10)
    assert good.status_code == 200
    assert good.json()["channel_slug"] == "party_dubai"
    _run(_clean_joins(free_session._user_id, [lobby_id]))
    free_session.post(f"{API}/lobbies/{lobby_id}/join", timeout=10)
    bad = free_session.post(f"{API}/lobbies/{lobby_id}/change_channel",
                                  json={"channel_slug": "bollywood_mehfil"}, timeout=10)
    assert bad.status_code == 403
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


def test_20_capacity_enforced(premium_session):
    """max_listeners cap is honored on /join."""
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Capacity test",
                                        "channel_slug": "bollywood_mehfil",
                                        "max_listeners": 2}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    # Force current_listener_count to the cap
    async def bump():
        await _mongo().lobbies.update_one(
            {"lobby_id": lobby_id},
            {"$set": {"current_listener_count": 2}})
    _run(bump())
    s = _login("test@bigfm.dubai", "TestUser123!")
    _run(_clean_joins(s._user_id, [lobby_id]))
    rj = s.post(f"{API}/lobbies/{lobby_id}/join", timeout=10)
    assert rj.status_code == 400
    assert rj.json()["detail"] == "lobby_full"
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


# ----------------------------------------------------------------------
# WebSocket smoke — chat broadcast end-to-end
def test_21_ws_chat_and_reaction_broadcast(premium_session, free_session):
    """Two sockets in one lobby: host sends chat, listener receives it.
    Listener sends emoji reaction, host receives it."""
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "WS test",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    _run(_clean_joins(free_session._user_id, [lobby_id]))
    free_session.post(f"{API}/lobbies/{lobby_id}/join", timeout=10)

    host_cookie = premium_session.cookies.get("bigfm_session")
    listener_cookie = free_session.cookies.get("bigfm_session")
    ws_url = f"{WS_BASE}/lobbies/ws/{lobby_id}"

    async def run():
        async with websockets.connect(
                ws_url, additional_headers=[("Cookie", f"bigfm_session={host_cookie}")]) as host_ws, \
                websockets.connect(
                ws_url, additional_headers=[("Cookie", f"bigfm_session={listener_cookie}")]) as lst_ws:
            # Consume hello on each
            await host_ws.recv()
            await lst_ws.recv()
            # Drain any presence_update (listener WS connect triggers nothing
            # extra since join was already broadcast via REST).
            # Host sends chat
            await host_ws.send(json.dumps({"type": "chat", "text": "Hello dil se!"}))
            # Both sockets should receive a chat_message
            got_host = json.loads(await asyncio.wait_for(host_ws.recv(), timeout=5))
            got_lst = json.loads(await asyncio.wait_for(lst_ws.recv(), timeout=5))
            assert got_host["type"] == "chat_message"
            assert got_host["text"] == "Hello dil se!"
            assert got_lst["type"] == "chat_message"
            assert got_lst["text"] == "Hello dil se!"
            # Listener sends reaction
            await lst_ws.send(json.dumps({"type": "reaction", "emoji": "🔥"}))
            # Listener also receives their own reaction (no exclude_sender).
            # Drain BOTH receivers so we land on a clean slate.
            got_h2 = json.loads(await asyncio.wait_for(host_ws.recv(), timeout=5))
            got_lst2 = json.loads(await asyncio.wait_for(lst_ws.recv(), timeout=5))
            assert got_h2["type"] == "reaction"
            assert got_h2["emoji"] == "🔥"
            assert got_h2["user_id"] == free_session._user_id
            assert got_lst2["type"] == "reaction"
            # Bad emoji rejected
            await lst_ws.send(json.dumps({"type": "reaction", "emoji": "💀"}))
            err = json.loads(await asyncio.wait_for(lst_ws.recv(), timeout=5))
            assert err["type"] == "error"
            assert err["code"] == "emoji_not_allowed"
    asyncio.run(run())
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


def test_22_ws_unauthorized_no_cookie():
    """WS without auth cookie gets closed with 4401."""
    # Build any lobby URL — handler closes BEFORE checking lobby anyway.
    ws_url = f"{WS_BASE}/lobbies/ws/lob_nonexistent"

    async def run():
        async with websockets.connect(ws_url) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            assert json.loads(msg)["code"] == "unauthorized"
            # Server closes after error message
            with pytest.raises(websockets.exceptions.ConnectionClosed):
                await asyncio.wait_for(ws.recv(), timeout=5)
    asyncio.run(run())


def test_23_ws_not_a_member_blocked(premium_session, free_session):
    """A logged-in user who never joined the lobby cannot open the WS."""
    _wipe_host(premium_session._user_id)
    r = premium_session.post(f"{API}/lobbies/create",
                                  json={"name": "Not-member test",
                                        "channel_slug": "bollywood_mehfil"}, timeout=10)
    lobby_id = r.json()["lobby_id"]
    # Free user did NOT join
    _run(_clean_joins(free_session._user_id, [lobby_id]))
    listener_cookie = free_session.cookies.get("bigfm_session")
    ws_url = f"{WS_BASE}/lobbies/ws/{lobby_id}"

    async def run():
        async with websockets.connect(
                ws_url, additional_headers=[("Cookie", f"bigfm_session={listener_cookie}")]) as ws:
            msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            assert msg["type"] == "error"
            assert msg["code"] == "not_a_member"
    asyncio.run(run())
    premium_session.post(f"{API}/lobbies/{lobby_id}/close", timeout=10)


def test_24_dunning_resets_subscription_plan_to_free():
    """Phase 6.1 cleanup one-liner: when dunning sweep auto-downgrades a
    past_due user, the user's `subscription.plan` mirror is reset to "free".
    Tests reuse the admin sim endpoints + as_of dunning hook (Phase 6.1)."""
    admin = _login("admin@bigfm.dubai", "AdminPass123!")
    premium = _login("premium@bigfm.dubai", "PremiumTest123!")
    target_uid = premium._user_id
    # Restore premium first (in case a prior test left them downgraded)
    async def restore():
        db = _mongo()
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        end = now + timedelta(days=365)
        await db.users.update_one(
            {"user_id": target_uid},
            {"$set": {
                "is_premium": True, "premium_tier": "premium",
                "premium_source": "paid", "premium_until": end,
                "billing_status": "active",
                "current_plan_slug": "premium_annual",
                "subscription.plan": "premium_annual",
                "subscription.status": "active",
                "subscription.current_period_start": now,
                "subscription.current_period_end": end,
                "subscription.cancel_at_period_end": False,
                "subscription.paused": False,
            },
             "$unset": {"grace_period_ends_at": "", "past_due_started_at": "",
                          "downgraded_at": "", "pending_plan_change": ""}}
        )
    _run(restore())
    sim = admin.post(f"{API}/billing/admin/simulate_payment_failed",
                       json={"user_id": target_uid}, timeout=10)
    assert sim.status_code == 200
    # Run sweep with as_of +8 days
    from datetime import timedelta
    as_of = (datetime.now(timezone.utc) + timedelta(days=8)).isoformat().replace("+00:00", "Z")
    sweep = admin.post(f"{API}/billing/admin/run_dunning_sweep",
                          json={"as_of": as_of}, timeout=10)
    assert sweep.status_code == 200
    body = sweep.json()
    assert body["downgraded"] >= 1
    # Verify user.subscription.plan was reset to "free"
    async def fetch_user():
        return await _mongo().users.find_one({"user_id": target_uid},
                                                  {"subscription.plan": 1,
                                                   "billing_status": 1,
                                                   "current_plan_slug": 1, "_id": 0})
    u = _run_returning(fetch_user())
    assert u["subscription"]["plan"] == "free"
    assert u["billing_status"] == "canceled_for_nonpayment"
    assert u["current_plan_slug"] == "free"
    # Restore for downstream test runs
    _run(restore())
