"""Phase 10c — Exclusive Channel Gating tests.

Direct synthetic seeding via Mongo for ambassador state + unlocks, then
HTTP assertions against the live backend. Reuses the auth helpers from
test_phase10b (admin + user session). No mocking of the gate path —
exercises real `check_channel_access` through `/api/radio/start`,
`/api/radio/switch_channel`, `/api/channels`.
"""
from __future__ import annotations
import os, time, uuid
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
    assert r.status_code == 200, f"login failed: {r.text[:200]}"
    me = s.get(f"{API}/auth/me", timeout=10).json()
    s._user_id = me["user_id"]
    return s


def _set_ambassador_level(user_id: str, level: int, *, points: int = None):
    """Force the user's ambassador state to `level`. Used to simulate
    promotion without running the full earn pipeline."""
    level_names = {1: "Listener", 2: "Regular", 3: "Insider",
                       4: "Ambassador", 5: "Diamond Ambassador"}
    thresholds = {1: 0, 2: 100, 3: 500, 4: 2000, 5: 10000}
    pts = points if points is not None else thresholds[level]
    DB.user_ambassador_state.update_one(
        {"user_id": user_id},
        {"$set": {"user_id": user_id, "level": level,
                    "level_name": level_names[level],
                    "points": pts,
                    "next_level_name": level_names.get(level + 1, "max"),
                    "updated_at": datetime.now(timezone.utc)}},
        upsert=True)


def _wipe_unlocks(user_id: str):
    DB.user_ambassador_unlocks.delete_many({"user_id": user_id})


def _grant_channel_unlock(user_id: str, channel_slug: str, *,
                                expires_in_days: int = 30):
    DB.user_ambassador_unlocks.insert_one({
        "_id": uuid.uuid4().hex,
        "user_id": user_id,
        "unlock_kind": "exclusive_channel",
        "ref": channel_slug,
        "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=expires_in_days),
    })


def _set_channel_exclusivity(slug: str, *, tier: str,
                                       gating_message: str = None,
                                       unlock_required_id: str = None):
    patch = {"exclusivity_tier": tier,
              "exclusivity_tier_locked": True,
              "premium_only": (tier == "premium")}
    if gating_message is not None:
        patch["gating_message"] = gating_message
    if unlock_required_id is not None:
        patch["unlock_required_id"] = unlock_required_id
    DB.channels.update_one({"_id": slug}, {"$set": patch})


def _reset_test_user(user_id: str):
    """Drop user back to L1, no premium, no unlocks for a clean test."""
    _wipe_unlocks(user_id)
    _set_ambassador_level(user_id, 1, points=0)
    DB.users.update_one({"user_id": user_id},
                          {"$set": {"is_premium": False}})


# ─── Fixtures ───────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def user_session():
    s = _login("test@bigfm.dubai", "TestUser123!")
    _reset_test_user(s._user_id)
    yield s


# ─── Tests ──────────────────────────────────────────────────────────────
def test_10c_01_free_user_to_free_channel_200(user_session):
    _reset_test_user(user_session._user_id)
    DB.warm_start_segments.delete_many({"user_id": user_session._user_id})
    r = user_session.post(f"{API}/radio/start",
                                  json={"channel": "bollywood_mehfil"},
                                  timeout=20)
    assert r.status_code == 200, r.text


def test_10c_02_free_user_to_premium_channel_403(user_session):
    _reset_test_user(user_session._user_id)
    r = user_session.post(f"{API}/radio/start",
                                  json={"channel": "premium_mehfil"},
                                  timeout=20)
    assert r.status_code == 403, r.text
    detail = r.json().get("detail") or {}
    assert detail.get("code") == "premium_required"
    assert detail.get("upgrade_path") == "premium"
    cta = detail.get("cta") or {}
    assert cta.get("label"), detail
    assert cta.get("href"), detail


def test_10c_03_premium_user_to_premium_channel_200(user_session):
    _reset_test_user(user_session._user_id)
    DB.users.update_one({"user_id": user_session._user_id},
                          {"$set": {"is_premium": True}})
    DB.warm_start_segments.delete_many({"user_id": user_session._user_id})
    r = user_session.post(f"{API}/radio/start",
                                  json={"channel": "premium_mehfil"},
                                  timeout=20)
    assert r.status_code == 200, r.text


def test_10c_04_l1_user_to_ambassador_l3_channel_403(user_session):
    _reset_test_user(user_session._user_id)
    r = user_session.post(f"{API}/radio/start",
                                  json={"channel": "vip_lounge"}, timeout=20)
    assert r.status_code == 403, r.text
    detail = r.json().get("detail") or {}
    assert detail.get("code") == "ambassador_level_required"
    assert detail.get("upgrade_path") == "earn_badges"
    assert detail.get("required_tier") == "ambassador_l3"
    cta = detail.get("cta") or {}
    assert cta.get("required_level") == 3
    assert cta.get("points_needed", 0) > 0
    assert "Earn" in (cta.get("label") or "")


def test_10c_05_l3_user_to_ambassador_l3_channel_200(user_session):
    _reset_test_user(user_session._user_id)
    _set_ambassador_level(user_session._user_id, 3)
    DB.warm_start_segments.delete_many({"user_id": user_session._user_id})
    r = user_session.post(f"{API}/radio/start",
                                  json={"channel": "vip_lounge"}, timeout=20)
    assert r.status_code == 200, r.text


def test_10c_06_l3_user_to_ambassador_l5_channel_403(user_session):
    _reset_test_user(user_session._user_id)
    _set_ambassador_level(user_session._user_id, 3)
    r = user_session.post(f"{API}/radio/start",
                                  json={"channel": "diamond_room"},
                                  timeout=20)
    assert r.status_code == 403
    detail = r.json().get("detail") or {}
    assert detail.get("required_tier") == "ambassador_l5"
    assert (detail.get("cta") or {}).get("required_level") == 5


def test_10c_07_explicit_unlock_grants_then_expires(user_session):
    """Phase 10c — explicit `exclusive_channel` unlock lets a low-level
    user into a high-tier channel; an expired row revokes access."""
    _reset_test_user(user_session._user_id)
    # 1) Active unlock → 200
    _grant_channel_unlock(user_session._user_id, "vip_lounge",
                                  expires_in_days=30)
    DB.warm_start_segments.delete_many({"user_id": user_session._user_id})
    r = user_session.post(f"{API}/radio/start",
                                  json={"channel": "vip_lounge"}, timeout=20)
    assert r.status_code == 200, r.text
    # 2) Expire the unlock → 403
    _wipe_unlocks(user_session._user_id)
    DB.user_ambassador_unlocks.insert_one({
        "_id": uuid.uuid4().hex,
        "user_id": user_session._user_id,
        "unlock_kind": "exclusive_channel",
        "ref": "vip_lounge",
        "created_at": datetime.now(timezone.utc) - timedelta(days=60),
        "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
    })
    r2 = user_session.post(f"{API}/radio/start",
                                    json={"channel": "vip_lounge"},
                                    timeout=20)
    assert r2.status_code == 403, r2.text


def test_10c_08_channel_listing_has_access_field(user_session):
    _reset_test_user(user_session._user_id)
    r = user_session.get(f"{API}/channels", timeout=10)
    assert r.status_code == 200
    body = r.json()
    chans = {c["slug"]: c for c in body["channels"]}
    # vip_lounge should be locked for a fresh L1 user
    assert chans["vip_lounge"]["access"]["allowed"] is False
    assert chans["vip_lounge"]["exclusivity_tier"] == "ambassador_l3"
    # bollywood_mehfil should be open
    assert chans["bollywood_mehfil"]["access"]["allowed"] is True
    # default channel must be one the user can actually start
    default = body["default"]
    assert chans[default]["access"]["allowed"] is True


def test_10c_09_channel_listing_unlocks_after_promotion(user_session):
    _reset_test_user(user_session._user_id)
    _set_ambassador_level(user_session._user_id, 3)
    r = user_session.get(f"{API}/channels", timeout=10)
    chans = {c["slug"]: c for c in r.json()["channels"]}
    assert chans["vip_lounge"]["access"]["allowed"] is True
    assert chans["diamond_room"]["access"]["allowed"] is False


def test_10c_10_admin_can_flip_exclusivity(admin_session, user_session):
    """Admin flips `bollywood_mehfil` to ambassador_l5 → free L1 user
    is blocked immediately."""
    _reset_test_user(user_session._user_id)
    # snapshot original
    orig = DB.channels.find_one({"_id": "bollywood_mehfil"})
    orig_tier = orig.get("exclusivity_tier", "free")
    orig_gm = orig.get("gating_message")
    orig_locked = orig.get("exclusivity_tier_locked", False)
    try:
        r = admin_session.post(
            f"{API}/admin/channels/bollywood_mehfil/exclusivity",
            json={"exclusivity_tier": "ambassador_l5",
                    "gating_message": "Test flip — L5 only."},
            timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["channel"]["exclusivity_tier"] == "ambassador_l5"
        # User now blocked
        r2 = user_session.post(f"{API}/radio/start",
                                        json={"channel": "bollywood_mehfil"},
                                        timeout=20)
        assert r2.status_code == 403, r2.text
        assert (r2.json().get("detail") or {}).get("required_tier") \
                  == "ambassador_l5"
    finally:
        # restore
        DB.channels.update_one(
            {"_id": "bollywood_mehfil"},
            {"$set": {"exclusivity_tier": orig_tier,
                        "gating_message": orig_gm,
                        "exclusivity_tier_locked": orig_locked,
                        "premium_only": orig.get("premium_only", False)}})


def test_10c_11_admin_endpoint_requires_admin(user_session):
    r = user_session.post(
        f"{API}/admin/channels/bollywood_mehfil/exclusivity",
        json={"exclusivity_tier": "premium"}, timeout=10)
    assert r.status_code in (401, 403), (r.status_code, r.text[:200])


def test_10c_12_admin_endpoint_rejects_unknown_tier(admin_session):
    r = admin_session.post(
        f"{API}/admin/channels/vip_lounge/exclusivity",
        json={"exclusivity_tier": "garbage_tier"}, timeout=10)
    assert r.status_code == 400, r.text
    assert "Allowed" in (r.json().get("detail") or "")


def test_10c_13_admin_endpoint_404_on_unknown_channel(admin_session):
    r = admin_session.post(
        f"{API}/admin/channels/__nonexistent__/exclusivity",
        json={"exclusivity_tier": "premium"}, timeout=10)
    assert r.status_code == 404


def test_10c_14_switch_channel_respects_gate(user_session):
    """Start a free channel session, then try to switch to a locked one."""
    _reset_test_user(user_session._user_id)
    DB.warm_start_segments.delete_many({"user_id": user_session._user_id})
    r1 = user_session.post(f"{API}/radio/start",
                                    json={"channel": "bollywood_mehfil"},
                                    timeout=20)
    assert r1.status_code == 200, r1.text
    session_id = r1.json()["session_id"]
    r2 = user_session.post(f"{API}/radio/switch_channel",
                                    json={"session_id": session_id,
                                            "channel": "diamond_room"},
                                    timeout=15)
    assert r2.status_code == 403, r2.text
    detail = r2.json().get("detail") or {}
    assert detail.get("code") == "ambassador_level_required"


def test_10c_15_smoke_existing_endpoints_still_work(user_session):
    """Phase 10c must not regress prior endpoints."""
    paths = [
        ("GET", "/leaderboards/dubai?metric=listening_minutes_7d"),
        ("GET", "/passport/me"),
        ("GET", "/channels"),
    ]
    for method, p in paths:
        r = user_session.request(method, f"{API}{p}", timeout=10)
        assert r.status_code in (200, 304), \
            f"{method} {p} -> {r.status_code}: {r.text[:200]}"


def test_10c_16_no_unlocks_after_test_user_reset(user_session):
    """Hygiene — leave user_ambassador_unlocks empty for downstream tests."""
    _reset_test_user(user_session._user_id)
    rows = list(DB.user_ambassador_unlocks.find(
        {"user_id": user_session._user_id}))
    assert rows == []



# ════════════════════════════════════════════════════════════════════════
# § Phase 10c.1 — Three follow-up fixes
# ════════════════════════════════════════════════════════════════════════
def test_10c1_01_grant_badge_actually_grants_points_and_transitions_level(
        admin_session, user_session):
    """Fix 1 — admin grant of `first_1000_hours` (500 pts) on an L1 user
    must transition them to L3 (Insider).  Response carries `state` and
    `delta` so the caller can verify without a second roundtrip."""
    uid = user_session._user_id
    # Reset user to a clean L1 / 0 points / 0 badges baseline
    DB.user_badges.delete_many({"user_id": uid})
    DB.user_ambassador_state.update_one(
        {"user_id": uid},
        {"$set": {"level": 1, "points": 0, "badge_count": 0}},
        upsert=True)
    r = admin_session.post(
        f"{API}/admin/passport/grant_badge",
        json={"user_id": uid, "badge_id": "first_1000_hours"},
        timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["awarded"] is True
    assert body["already_owned"] is False
    assert body["badge"]["points"] == 500
    assert body["state"]["level"] == 3
    assert body["state"]["points"] == 500
    assert body["state"]["badge_count"] == 1
    assert body["delta"]["points_delta"] == 500
    assert body["delta"]["level_changed_from"] == 1
    assert body["delta"]["level_changed_to"] == 3


def test_10c1_02_grant_badge_idempotent_returns_already_owned(
        admin_session, user_session):
    """Granting the same badge twice must not double-count points."""
    uid = user_session._user_id
    # First grant (no-op if already owned from previous test)
    admin_session.post(
        f"{API}/admin/passport/grant_badge",
        json={"user_id": uid, "badge_id": "first_1000_hours"},
        timeout=15)
    pre = DB.user_ambassador_state.find_one({"user_id": uid}) or {}
    pre_pts = int(pre.get("points") or 0)
    pre_count = int(pre.get("badge_count") or 0)
    r = admin_session.post(
        f"{API}/admin/passport/grant_badge",
        json={"user_id": uid, "badge_id": "first_1000_hours"},
        timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["awarded"] is False
    assert body["already_owned"] is True
    post = DB.user_ambassador_state.find_one({"user_id": uid}) or {}
    assert int(post.get("points") or 0) == pre_pts
    assert int(post.get("badge_count") or 0) == pre_count


def test_10c1_03_grant_unlock_then_radio_start_200_then_revoke_403(
        admin_session, user_session):
    """Fix 2 — full grant_unlock → /start 200 → revoke_unlock → /start 403."""
    uid = user_session._user_id
    # Flip vip_lounge to exclusive_unlock w/ a fresh sponsor id
    sponsor_id = f"pepsi_test_{int(time.time())}"
    try:
        r0 = admin_session.post(
            f"{API}/admin/channels/vip_lounge/exclusivity",
            json={"exclusivity_tier": "exclusive_unlock",
                    "unlock_required_id": sponsor_id,
                    "gating_message": "Sponsor exclusive — test."},
            timeout=10)
        assert r0.status_code == 200, r0.text
        # Reset user, baseline 403
        _reset_test_user(uid)
        r1 = user_session.post(
            f"{API}/radio/start",
            json={"channel": "vip_lounge"}, timeout=20)
        assert r1.status_code == 403, r1.text
        # Grant
        r2 = admin_session.post(
            f"{API}/admin/passport/grant_unlock",
            json={"user_id": uid, "unlock_id": sponsor_id,
                    "source": "sponsor_test"},
            timeout=10)
        assert r2.status_code == 200, r2.text
        b = r2.json()
        assert b["ok"] is True and b["idempotent"] is False
        assert b["unlock_id"] == sponsor_id
        # /start 200
        DB.warm_start_segments.delete_many({"user_id": uid})
        r3 = user_session.post(
            f"{API}/radio/start",
            json={"channel": "vip_lounge"}, timeout=20)
        assert r3.status_code == 200, r3.text
        # Re-grant → idempotent:true
        r4 = admin_session.post(
            f"{API}/admin/passport/grant_unlock",
            json={"user_id": uid, "unlock_id": sponsor_id},
            timeout=10)
        assert r4.status_code == 200
        assert r4.json()["idempotent"] is True
        # Revoke
        r5 = admin_session.post(
            f"{API}/admin/passport/revoke_unlock",
            json={"user_id": uid, "unlock_id": sponsor_id},
            timeout=10)
        assert r5.status_code == 200
        assert r5.json()["modified"] >= 1
        # /start 403 again
        r6 = user_session.post(
            f"{API}/radio/start",
            json={"channel": "vip_lounge"}, timeout=20)
        assert r6.status_code == 403, r6.text
    finally:
        # Restore vip_lounge to canonical ambassador_l3
        admin_session.post(
            f"{API}/admin/channels/vip_lounge/exclusivity",
            json={"exclusivity_tier": "ambassador_l3",
                    "gating_message": ("Reach Insider (L3) to unlock the "
                                              "VIP Lounge — premium music for "
                                              "premium ears.")},
            timeout=10)


def test_10c1_04_grant_unlock_audit_row_written(admin_session, user_session):
    """Audit collection captures the action."""
    uid = user_session._user_id
    aid = f"audit_test_{int(time.time())}"
    DB.unlock_admin_audit.delete_many({"target_user_id": uid,
                                                  "unlock_id": aid})
    r = admin_session.post(
        f"{API}/admin/passport/grant_unlock",
        json={"user_id": uid, "unlock_id": aid}, timeout=10)
    assert r.status_code == 200
    rows = list(DB.unlock_admin_audit.find({"target_user_id": uid,
                                                          "unlock_id": aid}))
    assert any(r["action"] == "grant" for r in rows), rows
    admin_session.post(
        f"{API}/admin/passport/revoke_unlock",
        json={"user_id": uid, "unlock_id": aid}, timeout=10)
    rows2 = list(DB.unlock_admin_audit.find({"target_user_id": uid,
                                                          "unlock_id": aid}))
    assert any(r["action"] == "revoke" for r in rows2), rows2


def test_10c1_05_grant_unlock_requires_admin(user_session):
    r = user_session.post(
        f"{API}/admin/passport/grant_unlock",
        json={"user_id": user_session._user_id,
                "unlock_id": "hack_test"}, timeout=10)
    assert r.status_code in (401, 403), (r.status_code, r.text[:200])


def test_10c1_06_radio_start_missing_channel_returns_400(user_session):
    """Fix 3 — no `channel` and no `channel_slug` returns 400 channel_required."""
    r = user_session.post(f"{API}/radio/start", json={}, timeout=10)
    assert r.status_code == 400, r.text
    detail = r.json().get("detail") or {}
    assert detail.get("code") == "channel_required"
    assert "channel" in (detail.get("fields") or [])
    assert "channel_slug" in (detail.get("fields") or [])


def test_10c1_07_radio_start_accepts_channel_slug_alias(user_session):
    """Fix 3 — `channel_slug` works as an alias for `channel`."""
    _reset_test_user(user_session._user_id)
    DB.warm_start_segments.delete_many(
        {"user_id": user_session._user_id})
    r = user_session.post(
        f"{API}/radio/start",
        json={"channel_slug": "bollywood_mehfil"}, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["segment"]["channel_slug"] == "bollywood_mehfil"


def test_10c1_08_radio_start_canonical_channel_wins_over_slug(user_session):
    """When both fields are present, EITHER should be honored — Pydantic
    alias chooses one deterministically, the gate is still enforced."""
    _reset_test_user(user_session._user_id)
    DB.warm_start_segments.delete_many(
        {"user_id": user_session._user_id})
    r = user_session.post(
        f"{API}/radio/start",
        json={"channel": "bollywood_mehfil",
                "channel_slug": "bollywood_mehfil"}, timeout=20)
    assert r.status_code == 200, r.text
    seg = r.json()["segment"]
    assert seg["channel_slug"] == "bollywood_mehfil"


def test_10c1_09_flip_to_free_clears_gating_message(admin_session):
    """Cosmetic — flipping a gated channel back to `free` clears the
    stale `gating_message`."""
    # Seed gating_message via a gated flip first
    r1 = admin_session.post(
        f"{API}/admin/channels/bollywood_mehfil/exclusivity",
        json={"exclusivity_tier": "ambassador_l5",
                "gating_message": "Temporary gate for cosmetic test."},
        timeout=10)
    assert r1.status_code == 200, r1.text
    assert (r1.json()["channel"].get("gating_message")
                == "Temporary gate for cosmetic test.")
    # Flip back to free
    r2 = admin_session.post(
        f"{API}/admin/channels/bollywood_mehfil/exclusivity",
        json={"exclusivity_tier": "free"}, timeout=10)
    assert r2.status_code == 200, r2.text
    assert r2.json()["channel"].get("gating_message") is None
    # Restore canonical state
    DB.channels.update_one(
        {"_id": "bollywood_mehfil"},
        {"$set": {"exclusivity_tier_locked": False}})
