"""Iteration 116 — Skip policy correctness tests.

Validates:
- compliance.get_skip_policy / set_skip_policy (Free=1, Premium=6, 3600s, no unlimited)
- compliance.skip_state normalized shape + rolling-window math
- GET /api/radio/skip_state (cookie auth)
- POST /api/radio/skip enforcement (429 with retry_after + upgrade_cta for free only)
- Admin GET/PUT /api/admin/radio/skip-rules
- GET /api/billing/plans max_skips_per_hour=1 (free) and =6 (premium*), never -1/Unlimited
"""
import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
import requests

def _resolve_base_url():
    u = os.environ.get("REACT_APP_BACKEND_URL")
    if u:
        return u.rstrip("/")
    # read from /app/frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    except Exception:
        pass
    return ""

BASE_URL = _resolve_base_url()
assert BASE_URL, "REACT_APP_BACKEND_URL is required"

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
TEST_EMAIL = "test@bigfm.dubai"
TEST_PASS = "TestUser123!"

sys.path.insert(0, "/app/backend")


# ────────── cookie-auth clients ──────────
def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def test_user():
    return _login(TEST_EMAIL, TEST_PASS)


@pytest.fixture(scope="module")
def me_test(test_user):
    r = test_user.get(f"{BASE_URL}/api/auth/me", timeout=10)
    assert r.status_code == 200
    return r.json()


# ────────── 1. compliance.get_skip_policy / set_skip_policy ──────────
def test_get_skip_policy_free_and_premium():
    from compliance import get_skip_policy, set_skip_policy
    # reset defaults
    set_skip_policy(free=1, premium=6, window_sec=3600)
    p_free = get_skip_policy(False)
    p_prem = get_skip_policy(True)
    assert p_free == {"tier": "free", "limit": 1, "window_sec": 3600}
    assert p_prem == {"tier": "premium", "limit": 6, "window_sec": 3600}


def test_set_skip_policy_clamps_negative_to_zero():
    from compliance import get_skip_policy, set_skip_policy
    set_skip_policy(free=-5, premium=-5, window_sec=30)  # window <60 clamps to 60
    assert get_skip_policy(False)["limit"] == 0
    assert get_skip_policy(True)["limit"] == 0
    assert get_skip_policy(False)["window_sec"] == 60
    # restore
    set_skip_policy(free=1, premium=6, window_sec=3600)


# ────────── 2. compliance.skip_state — normalized shape + rolling window ──────────
@pytest.mark.asyncio
async def test_skip_state_shape_and_rolling_window():
    from motor.motor_asyncio import AsyncIOMotorClient
    from compliance import skip_state, set_skip_policy
    set_skip_policy(free=1, premium=6, window_sec=3600)
    client = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "bigfm")]
    uid = "TEST_skip_user_iter116"
    # clean
    await db.playback_logs.delete_many({"user_id": uid})
    now = datetime.now(timezone.utc)

    # empty
    ss = await skip_state(db, uid, is_premium=False)
    assert set(ss.keys()) == {"tier", "used", "limit", "remaining",
                                "window_sec", "reset_in_sec", "exhausted", "unlimited"}
    assert ss["unlimited"] is False
    assert ss["tier"] == "free"
    assert ss["limit"] == 1
    assert ss["used"] == 0
    assert ss["remaining"] == 1
    assert ss["exhausted"] is False
    assert ss["reset_in_sec"] == 0

    # Insert 1 recent + 1 old (outside window)
    await db.playback_logs.insert_many([
        {"user_id": uid, "event": "skip", "timestamp": now - timedelta(seconds=10)},
        {"user_id": uid, "event": "skip", "timestamp": now - timedelta(seconds=7200)},  # 2h old
    ])
    ss = await skip_state(db, uid, is_premium=False)
    assert ss["used"] == 1   # old one must NOT count
    assert ss["remaining"] == 0
    assert ss["exhausted"] is True
    assert ss["reset_in_sec"] > 0 and ss["reset_in_sec"] <= 3600

    # Premium tier gets 6-limit, same events → used=1, remaining=5, not exhausted
    ss_p = await skip_state(db, uid, is_premium=True)
    assert ss_p["tier"] == "premium"
    assert ss_p["limit"] == 6
    assert ss_p["used"] == 1
    assert ss_p["remaining"] == 5
    assert ss_p["exhausted"] is False
    assert ss_p["reset_in_sec"] == 0
    assert ss_p["unlimited"] is False

    # Fill premium to exactly 6 in window → exhausted, reset_in_sec>0
    await db.playback_logs.delete_many({"user_id": uid})
    times = [now - timedelta(seconds=s) for s in [100, 200, 300, 400, 500, 600]]
    await db.playback_logs.insert_many([
        {"user_id": uid, "event": "skip", "timestamp": t} for t in times
    ])
    ss_p = await skip_state(db, uid, is_premium=True)
    assert ss_p["used"] == 6
    assert ss_p["remaining"] == 0
    assert ss_p["exhausted"] is True
    # oldest = 600s ago, so reset ~3000s away
    assert 2900 < ss_p["reset_in_sec"] <= 3000

    # cleanup
    await db.playback_logs.delete_many({"user_id": uid})
    client.close()


# ────────── 3. GET /api/radio/skip_state ──────────
def test_get_radio_skip_state_endpoint(test_user):
    r = test_user.get(f"{BASE_URL}/api/radio/skip_state", timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("tier", "used", "limit", "remaining", "window_sec",
                "reset_in_sec", "exhausted", "unlimited"):
        assert k in d, f"missing {k}"
    assert d["unlimited"] is False
    assert d["window_sec"] == 3600
    assert d["tier"] in ("free", "premium")
    assert d["limit"] in (1, 6)


def test_get_radio_skip_state_unauth():
    r = requests.get(f"{BASE_URL}/api/radio/skip_state", timeout=10)
    assert r.status_code in (401, 403)


# ────────── 4. Admin GET/PUT /api/admin/radio/skip-rules ──────────
def test_admin_skip_rules_get(admin):
    r = admin.get(f"{BASE_URL}/api/admin/radio/skip-rules", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["free"] == 1
    assert d["premium"] == 6
    assert d["window_sec"] == 3600


def test_admin_skip_rules_put_and_restore(admin):
    # override
    r = admin.put(f"{BASE_URL}/api/admin/radio/skip-rules",
                    json={"free": 2, "premium": 8, "window_sec": 1800}, timeout=10)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["free"] == 2 and d["premium"] == 8 and d["window_sec"] == 1800
    # verify persisted
    r2 = admin.get(f"{BASE_URL}/api/admin/radio/skip-rules", timeout=10)
    d2 = r2.json()
    assert d2["free"] == 2 and d2["premium"] == 8 and d2["window_sec"] == 1800
    # RESTORE
    r3 = admin.put(f"{BASE_URL}/api/admin/radio/skip-rules",
                     json={"free": 1, "premium": 6, "window_sec": 3600}, timeout=10)
    assert r3.status_code == 200
    assert r3.json()["free"] == 1 and r3.json()["premium"] == 6


def test_admin_skip_rules_requires_admin(test_user):
    r = test_user.get(f"{BASE_URL}/api/admin/radio/skip-rules", timeout=10)
    assert r.status_code in (401, 403)
    r = test_user.put(f"{BASE_URL}/api/admin/radio/skip-rules", json={"free": 5}, timeout=10)
    assert r.status_code in (401, 403)


# ────────── 5. GET /api/billing/plans ──────────
def test_billing_plans_no_unlimited():
    r = requests.get(f"{BASE_URL}/api/billing/plans", timeout=15)
    assert r.status_code == 200
    plans = r.json()
    # normalize
    items = plans if isinstance(plans, list) else plans.get("plans", [])
    assert items, "no plans returned"
    for p in items:
        feats = p.get("features") or {}
        m = feats.get("max_skips_per_hour")
        assert m != -1, f"plan {p.get('id')} still has max_skips_per_hour=-1"
        # Check no 'unlimited' copy anywhere in plan description/features text
        blob = str(p).lower()
        assert "unlimited skip" not in blob, f"'unlimited skip' found in plan {p.get('id')}"
        assert "∞" not in str(p), f"'∞' found in plan {p.get('id')}"
    # Confirm free=1 and premium tiers=6
    by_id = {p.get("id") or p.get("plan_id") or p.get("slug"): p for p in items}
    # find free plan
    free = next((p for p in items if (p.get("id") or "").lower() in ("free", "plan_free")
                    or (p.get("tier") or "").lower() == "free"), None)
    if free:
        assert free.get("features", {}).get("max_skips_per_hour") == 1
    prem_plans = [p for p in items if (p.get("features") or {}).get("ad_free") is True]
    for p in prem_plans:
        assert p["features"].get("max_skips_per_hour") == 6, \
            f"premium-ish plan {p.get('id')} skips={p['features'].get('max_skips_per_hour')}"


# ────────── 6. POST /api/radio/skip — enforcement ──────────
def _create_session(session):
    """Try to start a radio session; skip test if backend does not have music seeded."""
    r = session.post(f"{BASE_URL}/api/radio/start", json={"channel": "hinglish"}, timeout=60)
    if r.status_code != 200:
        r = session.post(f"{BASE_URL}/api/radio/start", json={}, timeout=60)
    if r.status_code != 200:
        pytest.skip(f"radio/start unavailable: {r.status_code} {r.text[:200]}")
    return r.json().get("session_id")


def test_free_user_skip_enforcement(test_user, me_test):
    """Free user allowed exactly 1 skip; 2nd → 429."""
    uid = me_test.get("user_id") or me_test.get("id")
    # ensure is_premium=False + clear old skips via direct Mongo
    from pymongo import MongoClient
    mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    dbn = os.environ.get("DB_NAME", "bigfm")
    mc[dbn].users.update_one({"user_id": uid}, {"$set": {"is_premium": False}})
    mc[dbn].playback_logs.delete_many({"user_id": uid, "event": {"$in": ["skip", "skip_limit_reached"]}})

    # skip_state should be fresh
    ss0 = test_user.get(f"{BASE_URL}/api/radio/skip_state").json()
    assert ss0["tier"] == "free" and ss0["used"] == 0 and ss0["limit"] == 1

    sid = _create_session(test_user)
    # First skip → 200
    r1 = test_user.post(f"{BASE_URL}/api/radio/skip?session_id={sid}", timeout=30)
    # Some deployments return 200 with skip_state.exhausted:true
    assert r1.status_code == 200, f"first skip failed: {r1.status_code} {r1.text[:300]}"
    d1 = r1.json()
    assert d1.get("skip_state", {}).get("used") == 1
    assert d1.get("skip_state", {}).get("exhausted") is True

    # Second skip → 429 with proper body
    r2 = test_user.post(f"{BASE_URL}/api/radio/skip?session_id={sid}", timeout=30)
    assert r2.status_code == 429, f"expected 429, got {r2.status_code}: {r2.text[:300]}"
    d2 = r2.json()
    for k in ("detail", "tier", "limit", "used", "remaining", "reset_in_sec", "window_sec", "skip_state"):
        assert k in d2, f"missing {k} in 429 body"
    assert d2["tier"] == "free"
    assert d2["limit"] == 1
    assert d2["remaining"] == 0
    assert d2["reset_in_sec"] > 0
    assert "6 skips every hour" in d2.get("upgrade_cta", ""), "free tier upgrade_cta missing/wrong"
    assert r2.headers.get("Retry-After") is not None
    # skip_limit_reached must be logged
    n = mc[dbn].playback_logs.count_documents({"user_id": uid, "event": "skip_limit_reached"})
    assert n >= 1
    # Skip count is exactly 1 (blocked did NOT count)
    n_skips = mc[dbn].playback_logs.count_documents({"user_id": uid, "event": "skip"})
    assert n_skips == 1, f"expected 1 completed skip, got {n_skips}"

    # cleanup
    mc[dbn].playback_logs.delete_many({"user_id": uid, "event": {"$in": ["skip", "skip_limit_reached"]}})
    mc.close()


def test_premium_user_skip_enforcement(test_user, me_test):
    """Flip test user to premium, expect exactly 6 skips then 429 with NO upgrade_cta."""
    uid = me_test.get("user_id") or me_test.get("id")
    from pymongo import MongoClient
    mc = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    dbn = os.environ.get("DB_NAME", "bigfm")
    orig = mc[dbn].users.find_one({"user_id": uid}, {"is_premium": 1}) or {}
    orig_prem = bool(orig.get("is_premium", False))
    mc[dbn].users.update_one({"user_id": uid}, {"$set": {"is_premium": True}})
    mc[dbn].playback_logs.delete_many({"user_id": uid, "event": {"$in": ["skip", "skip_limit_reached"]}})
    try:
        ss0 = test_user.get(f"{BASE_URL}/api/radio/skip_state").json()
        assert ss0["tier"] == "premium" and ss0["limit"] == 6, f"tier not premium: {ss0}"

        sid = _create_session(test_user)
        ok_count = 0
        for i in range(6):
            r = test_user.post(f"{BASE_URL}/api/radio/skip?session_id={sid}", timeout=30)
            if r.status_code == 200:
                ok_count += 1
            else:
                pytest.fail(f"skip #{i+1} unexpectedly returned {r.status_code}: {r.text[:200]}")
        assert ok_count == 6

        # 7th → 429, no upgrade_cta
        r7 = test_user.post(f"{BASE_URL}/api/radio/skip?session_id={sid}", timeout=30)
        assert r7.status_code == 429, f"7th expected 429 got {r7.status_code}: {r7.text[:200]}"
        d = r7.json()
        assert d["tier"] == "premium"
        assert d["limit"] == 6
        assert d["remaining"] == 0
        assert d["reset_in_sec"] > 0
        assert "upgrade_cta" not in d, f"premium 429 must NOT have upgrade_cta, got: {d.get('upgrade_cta')}"
        assert d.get("skip_state", {}).get("unlimited") is False
    finally:
        mc[dbn].users.update_one({"user_id": uid}, {"$set": {"is_premium": orig_prem}})
        mc[dbn].playback_logs.delete_many({"user_id": uid, "event": {"$in": ["skip", "skip_limit_reached"]}})
        mc.close()
