"""Cleanup-phase regression tests (pre-Phase 11).

Two narrow bugfixes:
  Bug 1 — admin/passport/grant_badge must actually grant (no-op regression).
  Bug 2 — lobbies/create must respect channel exclusivity (10c gap).

Reuses the live preview backend + Mongo, in the same style as
test_phase10c.py.
"""
from __future__ import annotations
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")
MONGO = MongoClient(MONGO_URL)
DB = MONGO[DB_NAME]


# ─── Helpers ────────────────────────────────────────────────────────────
def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, f"login {email} failed: {r.text[:200]}"
    me = s.get(f"{API}/auth/me", timeout=10).json()
    s._user_id = me["user_id"]
    s._email = email
    return s


def _reset_to_l1_no_premium(user_id: str):
    DB.user_badges.delete_many({"user_id": user_id})
    DB.user_ambassador_state.update_one(
        {"user_id": user_id},
        {"$set": {"level": 1, "points": 0, "badge_count": 0}},
        upsert=True)
    DB.user_ambassador_unlocks.delete_many({"user_id": user_id})
    DB.users.update_one({"user_id": user_id},
                          {"$set": {"is_premium": False}})


def _set_premium(user_id: str, value: bool):
    DB.users.update_one({"user_id": user_id},
                          {"$set": {"is_premium": value}})


def _set_ambassador_level(user_id: str, level: int):
    DB.user_ambassador_state.update_one(
        {"user_id": user_id},
        {"$set": {"level": level,
                    "points": {1: 0, 2: 100, 3: 500, 4: 2000, 5: 10000}[level]}},
        upsert=True)


def _close_active_lobby(user_id: str):
    DB.lobbies.update_many(
        {"host_user_id": user_id, "status": "live"},
        {"$set": {"status": "closed",
                    "closed_at": datetime.now(timezone.utc)}})


# ─── Fixtures ───────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def user_session():
    s = _login("test@bigfm.dubai", "TestUser123!")
    _reset_to_l1_no_premium(s._user_id)
    yield s


@pytest.fixture(scope="module")
def premium_session():
    s = _login("premium@bigfm.dubai", "PremiumTest123!")
    _set_premium(s._user_id, True)
    yield s


# ════════════════════════════════════════════════════════════════════════
# § Bug 1 — admin/passport/grant_badge
# ════════════════════════════════════════════════════════════════════════
def test_grant_badge_writes_row(admin_session, user_session):
    uid = user_session._user_id
    _reset_to_l1_no_premium(uid)
    DB.badge_admin_audit.delete_many({"target_user_id": uid,
                                                  "badge_id": "first_1000_hours"})
    r = admin_session.post(
        f"{API}/admin/passport/grant_badge",
        json={"user_id": uid, "badge_id": "first_1000_hours",
                "reason": "cleanup_phase_test"},
        timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["awarded"] is True
    # Row physically present in user_badges
    row = DB.user_badges.find_one({"user_id": uid,
                                              "badge_id": "first_1000_hours"})
    assert row is not None
    assert row.get("source") == "admin_grant"
    # Audit row written with reason
    audit = DB.badge_admin_audit.find_one({"target_user_id": uid,
                                                      "badge_id": "first_1000_hours",
                                                      "action": "grant"})
    assert audit is not None
    assert audit.get("reason") == "cleanup_phase_test"
    assert audit.get("actor_user_id") == admin_session._user_id


def test_grant_badge_idempotent(admin_session, user_session):
    uid = user_session._user_id
    # ensure already granted
    admin_session.post(
        f"{API}/admin/passport/grant_badge",
        json={"user_id": uid, "badge_id": "first_1000_hours"},
        timeout=15)
    before = DB.user_badges.count_documents(
        {"user_id": uid, "badge_id": "first_1000_hours"})
    r = admin_session.post(
        f"{API}/admin/passport/grant_badge",
        json={"user_id": uid, "badge_id": "first_1000_hours"},
        timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["awarded"] is False
    assert body["already_owned"] is True
    after = DB.user_badges.count_documents(
        {"user_id": uid, "badge_id": "first_1000_hours"})
    assert after == before, f"duplicate row created: before={before} after={after}"


def test_grant_badge_triggers_side_effects(admin_session, user_session):
    """Granting `first_1000_hours` (500 pts) on an L1 user must trigger
    the ambassador-score recompute and bump them to L3 (Insider)."""
    uid = user_session._user_id
    _reset_to_l1_no_premium(uid)
    # Pre-state
    pre = DB.user_ambassador_state.find_one({"user_id": uid}) or {}
    assert int(pre.get("points") or 0) == 0
    assert int(pre.get("level") or 1) == 1
    # Grant
    r = admin_session.post(
        f"{API}/admin/passport/grant_badge",
        json={"user_id": uid, "badge_id": "first_1000_hours"},
        timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    # Response carries the new state + delta (Phase 10c.1)
    assert body["state"]["level"] == 3
    assert body["state"]["points"] == 500
    assert body["delta"]["level_changed_from"] == 1
    assert body["delta"]["level_changed_to"] == 3
    # Mongo confirms persistence (recompute_ambassador wrote the state)
    post = DB.user_ambassador_state.find_one({"user_id": uid}) or {}
    assert int(post.get("points") or 0) == 500
    assert int(post.get("level") or 1) == 3
    assert int(post.get("badge_count") or 0) >= 1


def test_grant_badge_non_admin_403(user_session):
    r = user_session.post(
        f"{API}/admin/passport/grant_badge",
        json={"user_id": user_session._user_id,
                "badge_id": "first_1000_hours"},
        timeout=10)
    assert r.status_code in (401, 403), (r.status_code, r.text[:200])


def test_grant_badge_invalid_badge_id_404(admin_session, user_session):
    r = admin_session.post(
        f"{API}/admin/passport/grant_badge",
        json={"user_id": user_session._user_id,
                "badge_id": "this_badge_does_not_exist_xyz"},
        timeout=10)
    assert r.status_code == 404, r.text


# ════════════════════════════════════════════════════════════════════════
# § Bug 2 — lobbies/create must respect channel exclusivity
# ════════════════════════════════════════════════════════════════════════
def _channel_with_tier(tier: str) -> str:
    """Find a seeded channel with `exclusivity_tier=tier`.  Falls back to
    flipping `vip_lounge`/`bollywood_mehfil` if none exists."""
    for ch in DB.channels.find({"exclusivity_tier": tier, "active": True}):
        return ch["_id"]
    return None


def test_lobby_create_blocked_for_free_on_premium_channel(
        user_session, admin_session):
    """Free L1 user trying to create a lobby on a `premium` tier channel
    must get 403 with the gating payload."""
    uid = user_session._user_id
    _reset_to_l1_no_premium(uid)
    _close_active_lobby(uid)
    slug = _channel_with_tier("premium")
    # Fallback — flip premium_mehfil to ensure the tier exists
    if not slug:
        admin_session.post(
            f"{API}/admin/channels/premium_mehfil/exclusivity",
            json={"exclusivity_tier": "premium"}, timeout=10)
        slug = "premium_mehfil"
    r = user_session.post(
        f"{API}/lobbies/create",
        json={"name": "Test Premium Lobby",
                "channel_slug": slug,
                "city": "dubai"},
        timeout=10)
    assert r.status_code == 403, r.text
    detail = r.json().get("detail") or {}
    assert detail.get("code") == "premium_required", detail
    assert detail.get("upgrade_path") == "premium"
    assert detail.get("cta"), detail
    assert detail.get("message")


def test_lobby_create_allowed_for_premium(premium_session, admin_session):
    """Premium user can create on a premium channel → 200 ok with lobby_id."""
    uid = premium_session._user_id
    _close_active_lobby(uid)
    slug = _channel_with_tier("premium") or "premium_mehfil"
    r = premium_session.post(
        f"{API}/lobbies/create",
        json={"name": f"Premium Lobby {uuid.uuid4().hex[:6]}",
                "channel_slug": slug,
                "city": "dubai"},
        timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["channel_slug"] == slug
    assert body["host_user_id"] == uid
    _close_active_lobby(uid)


def test_lobby_create_allowed_for_ambassador_l3_on_l3_channel(
        admin_session, user_session):
    """Promote test user to L3, create lobby on vip_lounge (ambassador_l3)."""
    uid = user_session._user_id
    _reset_to_l1_no_premium(uid)
    _set_ambassador_level(uid, 3)
    _close_active_lobby(uid)
    # Ensure vip_lounge is at canonical ambassador_l3 tier
    admin_session.post(
        f"{API}/admin/channels/vip_lounge/exclusivity",
        json={"exclusivity_tier": "ambassador_l3",
                "gating_message": "Reach Insider (L3) to unlock the VIP Lounge."},
        timeout=10)
    r = user_session.post(
        f"{API}/lobbies/create",
        json={"name": f"L3 Lobby {uuid.uuid4().hex[:6]}",
                "channel_slug": "vip_lounge",
                "city": "dubai"},
        timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["channel_slug"] == "vip_lounge"
    assert body["host_user_id"] == uid
    _close_active_lobby(uid)


def test_lobby_create_blocked_for_l1_on_l3_channel(user_session,
                                                                        admin_session):
    """Bare L1 user must be blocked from hosting an L3 channel lobby."""
    uid = user_session._user_id
    _reset_to_l1_no_premium(uid)
    _close_active_lobby(uid)
    admin_session.post(
        f"{API}/admin/channels/vip_lounge/exclusivity",
        json={"exclusivity_tier": "ambassador_l3"}, timeout=10)
    r = user_session.post(
        f"{API}/lobbies/create",
        json={"name": "L1 sneaks in", "channel_slug": "vip_lounge",
                "city": "dubai"},
        timeout=10)
    assert r.status_code == 403, r.text
    detail = r.json().get("detail") or {}
    assert detail.get("code") == "ambassador_level_required"
    assert detail.get("required_tier") == "ambassador_l3"


def test_lobby_create_allowed_with_explicit_unlock(admin_session, user_session):
    """A user with an explicit `exclusive_channel` unlock for vip_lounge
    can host a lobby on it without being L3."""
    uid = user_session._user_id
    _reset_to_l1_no_premium(uid)
    _close_active_lobby(uid)
    # Grant the unlock via the admin endpoint shipped in 10c.1
    r0 = admin_session.post(
        f"{API}/admin/passport/grant_unlock",
        json={"user_id": uid, "unlock_id": "vip_lounge"}, timeout=10)
    assert r0.status_code == 200, r0.text
    r = user_session.post(
        f"{API}/lobbies/create",
        json={"name": f"Unlock Lobby {uuid.uuid4().hex[:6]}",
                "channel_slug": "vip_lounge", "city": "dubai"},
        timeout=10)
    assert r.status_code == 200, r.text
    _close_active_lobby(uid)
    # Revoke for hygiene
    admin_session.post(f"{API}/admin/passport/revoke_unlock",
                            json={"user_id": uid, "unlock_id": "vip_lounge"},
                            timeout=10)


def test_lobby_create_on_free_channel_unaffected(user_session):
    """Cleanup gate must not regress free channels."""
    uid = user_session._user_id
    _reset_to_l1_no_premium(uid)
    _close_active_lobby(uid)
    r = user_session.post(
        f"{API}/lobbies/create",
        json={"name": f"Free Lobby {uuid.uuid4().hex[:6]}",
                "channel_slug": "bollywood_mehfil",
                "city": "dubai"},
        timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["channel_slug"] == "bollywood_mehfil"
    _close_active_lobby(uid)


# ════════════════════════════════════════════════════════════════════════
# § Hygiene — OpenAPI still resolves
# ════════════════════════════════════════════════════════════════════════
def test_openapi_json_still_resolves():
    r = requests.get(f"{API}/openapi.json", timeout=10)
    assert r.status_code == 200, r.text[:200]
    spec = r.json()
    paths = spec.get("paths") or {}
    # Endpoints touched by this cleanup phase
    for p in ("/api/admin/passport/grant_badge",
                "/api/lobbies/create"):
        assert p in paths, f"openapi.json missing {p}"
