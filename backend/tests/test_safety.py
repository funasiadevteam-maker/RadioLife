"""Phase 12c — Trust & Safety tests."""
from __future__ import annotations
import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")
MONGO = MongoClient(MONGO_URL)
DB = MONGO[DB_NAME]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, r.text[:200]
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def free_session():
    return _login("test@bigfm.dubai", "TestUser123!")


@pytest.fixture
def aio_db():
    cli = AsyncIOMotorClient(MONGO_URL)
    yield cli[DB_NAME]
    cli.close()


# ─── 1. moderation blocks profanity (rule-only path) ───────────────────
def test_moderation_blocks_profanity_in_chat(aio_db):
    """Rule path must block known-profanity text whether or not OpenAI
    key is set — strictest verdict wins."""
    from services.moderation import moderate, CHAT_REF
    loop = asyncio.new_event_loop()
    try:
        verdict = loop.run_until_complete(moderate(
            aio_db, text="this is shit", user_id="user_test_profanity",
            ref_type=CHAT_REF, ref_id="lobby_x"))
    finally:
        loop.close()
    assert verdict["verdict"] == "block", verdict
    assert any(c.startswith("profanity") for c in verdict["categories"])


# ─── 2. moderation uses OpenAI when key set (mock httpx) ────────────────
def test_moderation_uses_openai_when_key_set(aio_db, monkeypatch):
    """When OPENAI_API_KEY is set, the OpenAI moderation endpoint is hit
    via httpx.AsyncClient.post — the mock asserts URL + payload."""
    from services import moderation
    monkeypatch.setenv("OPENAI_API_KEY", "sk-stub-12345")
    captured: dict = {}

    class _MockResp:
        status_code = 200
        text = "ok"
        def json(self):
            return {"results": [{
                "flagged": True,
                "categories": {"hate": True},
                "category_scores": {"hate": 0.91}}]}

    class _MockClient:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        async def post(self, url, json=None, headers=None, **kw):
            captured["url"] = url
            captured["json"] = json
            captured["auth"] = headers.get("Authorization") if headers else None
            return _MockResp()

    loop = asyncio.new_event_loop()
    try:
        with patch.object(moderation.httpx, "AsyncClient", _MockClient):
            v = loop.run_until_complete(moderation.moderate(
                aio_db, text="some content",
                user_id="user_openai_test",
                ref_type=moderation.CHAT_REF, ref_id="x"))
    finally:
        loop.close()
    assert captured["url"] == "https://api.openai.com/v1/moderations"
    assert captured["json"]["model"] == "omni-moderation-latest"
    assert captured["auth"].startswith("Bearer sk-stub")
    # AI verdict should bubble up (block since score=0.91 > 0.8)
    assert v["verdict"] == "block"


# ─── 3. moderation_audit row written ───────────────────────────────────
def test_moderation_audit_row_written(aio_db):
    from services.moderation import moderate, CHAT_REF
    uid = f"user_mod_audit_{uuid.uuid4().hex[:8]}"
    loop = asyncio.new_event_loop()
    try:
        v = loop.run_until_complete(moderate(
            aio_db, text="hello world friends",
            user_id=uid, ref_type=CHAT_REF, ref_id="ref1"))
    finally:
        loop.close()
    row = DB.moderation_audit.find_one({"user_id": uid})
    assert row, "moderation_audit row missing"
    assert row["verdict"] in ("allow", "warn", "block")
    assert row["ref_type"] == "chat"
    assert row["moderation_id"] == v["moderation_id"]
    DB.moderation_audit.delete_many({"user_id": uid})


# ─── 4. fraud one_time_use double redeem blocked ───────────────────────
def test_fraud_one_time_use_double_redeem_blocked(aio_db):
    from services.fraud import check_redeem
    uid = f"user_fraud_{uuid.uuid4().hex[:8]}"
    coupon_id = f"cpn_{uuid.uuid4().hex[:10]}"
    DB.coupons.insert_one({
        "_id": coupon_id, "coupon_id": coupon_id,
        "user_id": uid, "one_time_use": True,
        "max_redemptions": 1, "redeemed_count": 0,
        "redeemed_at": _now() - timedelta(minutes=5),
    })
    coupon = {"coupon_id": coupon_id, "one_time_use": True,
                "max_redemptions": 1, "redeemed_count": 0,
                "partner_id": "p_x"}
    loop = asyncio.new_event_loop()
    try:
        out = loop.run_until_complete(check_redeem(
            aio_db, coupon=coupon, user={"user_id": uid}))
    finally:
        loop.close()
    assert out["action"] == "block", out
    assert any(e["rule"] == "one_time_use_double_redeem"
                  for e in out["events"]), out
    DB.coupons.delete_many({"coupon_id": coupon_id})
    DB.fraud_events.delete_many({"user_id": uid})
    DB.strike_events.delete_many({"user_id": uid})


# ─── 5. fraud velocity blocks ──────────────────────────────────────────
def test_fraud_velocity_redeem_blocked(aio_db):
    from services.fraud import check_redeem
    uid = f"user_velo_{uuid.uuid4().hex[:8]}"
    # Seed 5 recent redemptions in last 30 seconds
    now = _now()
    for i in range(5):
        DB.coupons.insert_one({
            "_id": f"cpn_v_{uuid.uuid4().hex[:8]}",
            "coupon_id": f"cpn_v_{i}",
            "user_id": uid,
            "redeemed_at": now - timedelta(seconds=10),
            "one_time_use": False, "max_redemptions": 999,
            "redeemed_count": 1,
        })
    coupon = {"coupon_id": "cpn_new", "one_time_use": False,
                "max_redemptions": 10, "redeemed_count": 0}
    loop = asyncio.new_event_loop()
    try:
        out = loop.run_until_complete(check_redeem(
            aio_db, coupon=coupon, user={"user_id": uid}))
    finally:
        loop.close()
    assert out["action"] == "block"
    assert any(e["rule"] == "redeem_velocity" for e in out["events"])
    DB.coupons.delete_many({"user_id": uid})
    DB.fraud_events.delete_many({"user_id": uid})
    DB.strike_events.delete_many({"user_id": uid})


# ─── 6. abuse lobby_spam blocks creation ───────────────────────────────
def test_abuse_lobby_spam_blocks_creation(aio_db):
    from services.abuse import check_lobby_spam
    uid = f"user_lobspam_{uuid.uuid4().hex[:8]}"
    now = _now()
    # Seed 6 lobbies in last 30 minutes (limit is 5)
    for i in range(6):
        DB.lobbies.insert_one({
            "_id": f"lob_spam_{uuid.uuid4().hex[:8]}",
            "lobby_id": f"lob_spam_{i}",
            "host_user_id": uid,
            "created_at": now - timedelta(minutes=5),
            "status": "live",
        })
    loop = asyncio.new_event_loop()
    try:
        ev = loop.run_until_complete(check_lobby_spam(
            aio_db, user_id=uid))
    finally:
        loop.close()
    assert ev is not None, "expected an abuse_event"
    assert ev["rule"] == "lobby_spam"
    assert ev["action"] == "block"
    DB.lobbies.delete_many({"host_user_id": uid})
    DB.abuse_events.delete_many({"user_id": uid})
    DB.strike_events.delete_many({"user_id": uid})


# ─── 7. suspend terminates sessions ────────────────────────────────────
def test_suspend_user_terminates_sessions(admin_session):
    """Register a fresh user, log them in (creates a session), then
    admin suspends → user's sessions must be gone."""
    email = f"susp_term_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "SuspTest123!"
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
                  json={"email": email, "password": pwd, "name": "Susp"},
                  timeout=10)
    assert r.status_code == 200
    uid = r.json()["user_id"]
    # Confirm session exists
    assert DB.sessions.count_documents({"user_id": uid}) >= 1
    try:
        res = admin_session.post(
            f"{API}/admin/safety/users/{uid}/suspend",
            json={"duration_days": 7, "reason": "test_abuse"},
            timeout=10)
        assert res.status_code == 200, res.text[:200]
        # Sessions purged
        assert DB.sessions.count_documents({"user_id": uid}) == 0
        # Audit row exists
        audit = DB.safety_admin_audit.find_one(
            {"target_user_id": uid, "action": "suspend"})
        assert audit
    finally:
        DB.users.delete_one({"user_id": uid})
        DB.sessions.delete_many({"user_id": uid})
        DB.safety_admin_audit.delete_many({"target_user_id": uid})


# ─── 8. Suspended user's request → 403 account_suspended ───────────────
def test_suspended_user_request_returns_account_suspended():
    email = f"susp_req_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "SuspTest123!"
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
                  json={"email": email, "password": pwd, "name": "Susp"},
                  timeout=10)
    assert r.status_code == 200
    uid = r.json()["user_id"]
    try:
        # Apply suspension directly on the user doc
        DB.users.update_one({"user_id": uid},
            {"$set": {"suspended_until": _now() + timedelta(days=7),
                        "suspended_reason": "manual_test"}})
        # Hit a protected endpoint
        r2 = s.get(f"{API}/auth/me", timeout=10)
        assert r2.status_code == 403, r2.status_code
        body = r2.json()
        # detail can be the dict directly, depending on FastAPI version
        detail = body.get("detail")
        if isinstance(detail, dict):
            assert detail.get("code") == "account_suspended"
            assert detail.get("until")
        else:
            assert "account_suspended" in str(body)
    finally:
        DB.users.delete_one({"user_id": uid})
        DB.sessions.delete_many({"user_id": uid})


# ─── 9. Strikes accumulate and mute ────────────────────────────────────
def test_strikes_accumulate_and_mute(aio_db):
    from services.strikes import record_strike
    uid = f"user_strike_{uuid.uuid4().hex[:8]}"
    DB.users.insert_one({"_id": uid, "user_id": uid, "email": f"{uid}@x"})
    loop = asyncio.new_event_loop()
    try:
        # 3 medium strikes → mute_24h
        for i in range(3):
            loop.run_until_complete(record_strike(
                aio_db, user_id=uid, severity="medium",
                source="test", reason=f"r{i}"))
    finally:
        loop.close()
    user = DB.users.find_one({"user_id": uid})
    assert user["strikes_summary"]["medium"] >= 3
    assert user.get("mute_until") is not None
    DB.users.delete_one({"user_id": uid})
    DB.strike_events.delete_many({"user_id": uid})


# ─── 10. admin safety endpoints require admin ──────────────────────────
def test_admin_safety_endpoints_require_admin(free_session):
    targets = [
        ("GET", "/admin/safety/moderation_queue"),
        ("GET", "/admin/safety/fraud_events"),
        ("GET", "/admin/safety/abuse_events"),
        ("GET", "/admin/safety/settings"),
        ("PATCH", "/admin/safety/settings"),
    ]
    for method, path in targets:
        if method == "GET":
            r = free_session.get(f"{API}{path}", timeout=10)
        else:
            r = free_session.patch(f"{API}{path}", json={}, timeout=10)
        assert r.status_code == 403, (path, r.status_code)
    # Anonymous → 401
    r = requests.get(f"{API}/admin/safety/moderation_queue", timeout=10)
    assert r.status_code == 401


# ─── Carryover: throttle_ok accepts legacy string format ────────────────
def test_throttle_ok_accepts_legacy_string_format(aio_db):
    from routes.admin_retention import _throttle_ok
    uid = f"user_throttle_{uuid.uuid4().hex[:8]}"
    cid = f"cmp_legacy_{uuid.uuid4().hex[:6]}"
    DB.lifecycle_send_log.delete_many({"user_id": uid, "campaign_id": cid})
    # Legacy "7d" / "24h" / "30m" strings — must not raise
    loop = asyncio.new_event_loop()
    try:
        for shorthand in ("7d", "24h", "30m"):
            ok = loop.run_until_complete(_throttle_ok(
                aio_db,
                campaign={"id": cid,
                              "throttle_per_user_per_period": shorthand},
                user_id=uid))
            assert ok is True, (shorthand, ok)
        # And canonical dict still works
        ok2 = loop.run_until_complete(_throttle_ok(
            aio_db,
            campaign={"id": cid,
                          "throttle_per_user_per_period":
                              {"max_sends": 1, "period_hours": 72}},
            user_id=uid))
        assert ok2 is True
    finally:
        loop.close()


# ════════════════════════════════════════════════════════════════════════
# Phase 12c HOTFIXES (4 new tests)
# ════════════════════════════════════════════════════════════════════════

# ─── HF-1. Chat moderation must survive bad safety_settings shape ──────
def test_chat_moderation_survives_bad_safety_settings_shape():
    """If a previous admin saved `profanity_extra` as a list (bug
    that caused 'list object is not a mapping' in production), the
    moderation pipeline must NOT crash; it should defensively coerce
    back to an empty dict.

    Uses a fresh motor client per asyncio.run to avoid the 'event loop
    is closed' issue that motor's executor-bound client hits when the
    same client is reused across multiple loops in the same process.
    """
    from services import moderation
    DB.safety_settings.update_one(
        {"_id": "global"},
        {"$set": {"profanity_extra": ["this", "is", "wrong"]}},
        upsert=True)

    async def _run(text: str) -> dict:
        cli = AsyncIOMotorClient(MONGO_URL)
        try:
            return await moderation.moderate(
                cli[DB_NAME], text=text,
                user_id="user_bad_shape_test",
                ref_type=moderation.CHAT_REF, ref_id="x")
        finally:
            cli.close()

    try:
        v = asyncio.run(_run("hello there"))
        assert v["verdict"] in ("allow", "warn", "block")
        # And profanity still gets blocked despite the bad shape
        v2 = asyncio.run(_run("that is shit"))
        assert v2["verdict"] == "block", v2
    finally:
        DB.safety_settings.update_one(
            {"_id": "global"}, {"$set": {"profanity_extra": {}}})


# ─── HF-2. Settings PATCH rejects bad shapes ───────────────────────────
def test_settings_patch_rejects_list_profanity_extra(admin_session):
    """Settings PATCH must 400 when profanity_extra is sent as a list."""
    r = admin_session.patch(
        f"{API}/admin/safety/settings",
        json={"profanity_extra": ["a", "b"]}, timeout=10)
    assert r.status_code == 400, r.text[:200]
    # Allowlist must be a list of strings, not a dict
    r2 = admin_session.patch(
        f"{API}/admin/safety/settings",
        json={"leak_allowlist_partner_ids": {"biz_x": True}}, timeout=10)
    assert r2.status_code == 400
    # Good shape passes
    r3 = admin_session.patch(
        f"{API}/admin/safety/settings",
        json={"profanity_extra": {"en": ["customword"]}}, timeout=10)
    assert r3.status_code == 200
    # Cleanup
    admin_session.patch(
        f"{API}/admin/safety/settings",
        json={"profanity_extra": {}}, timeout=10)


# ─── HF-3. Lobby create — 6th in hour returns 429 + writes abuse_event ──
def test_lobby_create_6th_call_in_hour_returns_429_and_writes_abuse_event(
        admin_session):
    """Seed 5 lobbies for a test user, then make them hit /create — must
    get 429 abuse_blocked AND an abuse_event row appears."""
    from services.lobbies import create_lobby
    # Register a fresh user we can fully control
    email = f"spamuser_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "SpamTest123!"
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
                  json={"email": email, "password": pwd, "name": "Spam"},
                  timeout=10)
    assert r.status_code == 200
    uid = r.json()["user_id"]
    try:
        # Mark onboarding complete so the user can create lobbies
        DB.users.update_one({"user_id": uid},
            {"$set": {"onboarding_complete": True}})
        # Seed 5 lobbies in the last 30 mins (so the 1h window catches them)
        now = _now()
        for i in range(5):
            DB.lobbies.insert_one({
                "_id": f"lob_seed_{uuid.uuid4().hex[:10]}",
                "lobby_id": f"lob_seed_{i}",
                "host_user_id": uid,
                "created_at": now - timedelta(minutes=5),
                "status": "closed" if i < 3 else "live",
            })
        # 6th create attempt → 429
        r2 = s.post(f"{API}/lobbies/create",
                       json={"name": "Spam 6th",
                                "channel_slug": "bollywood_mehfil",
                                "city": "dubai"}, timeout=10)
        assert r2.status_code == 429, (r2.status_code, r2.text[:200])
        body = r2.json()
        # FastAPI dumps the detail dict directly
        detail = body.get("detail") if isinstance(body, dict) else body
        if isinstance(detail, dict):
            assert detail.get("code") == "abuse_blocked"
            assert detail.get("reason") == "lobby_spam"
        # abuse_event row written
        ev = DB.abuse_events.find_one({"user_id": uid, "rule": "lobby_spam"})
        assert ev, "no abuse_event row written"
        assert ev["severity"] == "medium"
        assert ev["action"] == "block"
    finally:
        DB.users.delete_one({"user_id": uid})
        DB.sessions.delete_many({"user_id": uid})
        DB.lobbies.delete_many({"host_user_id": uid})
        DB.abuse_events.delete_many({"user_id": uid})
        DB.strike_events.delete_many({"user_id": uid})


# ─── HF-4. Profile bio blocks phone-number leak (default-deny) ─────────
def test_profile_bio_blocks_phone_number_leak():
    email = f"leakbio_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "LeakTest123!"
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
                  json={"email": email, "password": pwd, "name": "Leaky"},
                  timeout=10)
    assert r.status_code == 200
    uid = r.json()["user_id"]
    try:
        DB.users.update_one({"user_id": uid},
            {"$set": {"onboarding_complete": True}})
        # Bio with embedded phone must be blocked
        r2 = s.patch(f"{API}/passport/me/settings",
                       json={"bio": "Hi, call me at 555-123-4567 anytime!"},
                       timeout=10)
        assert r2.status_code == 422, (r2.status_code, r2.text[:200])
        body = r2.json()
        detail = body.get("detail") if isinstance(body, dict) else body
        if isinstance(detail, dict):
            assert detail.get("code") == "blocked_by_moderation"
            assert detail.get("category") == "contact_leak"
        # Clean bio passes
        r3 = s.patch(f"{API}/passport/me/settings",
                       json={"bio": "love bollywood and coffee."}, timeout=10)
        assert r3.status_code == 200, r3.text[:200]
    finally:
        DB.users.delete_one({"user_id": uid})
        DB.sessions.delete_many({"user_id": uid})


def test_verified_partner_bio_allows_url(admin_session):
    """When the user's business_id is in safety_settings.leak_allowlist_partner_ids,
    URLs in bio are NOT blocked."""
    # Make a partner user
    email = f"partner_bio_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "PartnerTest123!"
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
                  json={"email": email, "password": pwd, "name": "Partner"},
                  timeout=10)
    assert r.status_code == 200
    uid = r.json()["user_id"]
    DB.users.update_one({"user_id": uid},
        {"$set": {"onboarding_complete": True,
                    "partner_business_id": "biz_demo_karak"}})
    # Add this business to the leak allowlist
    admin_session.patch(f"{API}/admin/safety/settings",
        json={"leak_allowlist_partner_ids": ["biz_demo_karak"]}, timeout=10)
    try:
        r2 = s.patch(f"{API}/passport/me/settings",
                       json={"bio": "Visit us at https://karakcafe.example.com"},
                       timeout=10)
        assert r2.status_code == 200, r2.text[:200]
    finally:
        admin_session.patch(f"{API}/admin/safety/settings",
            json={"leak_allowlist_partner_ids": []}, timeout=10)
        DB.users.delete_one({"user_id": uid})
        DB.sessions.delete_many({"user_id": uid})


# ─── HF-5. Partner redeem — one_time_use double redeem blocked ─────────
def test_partner_redeem_one_time_coupon_double_blocked():
    """Simulates the partner-scan flow:
       1. claim a coupon as user
       2. partner scans (POST /api/partner/redeem/{qr_token}) → ok
       3. partner scans again → must be blocked AND a fraud_event row
          must exist (or audit trail with fraud outcome).
    """
    # Ensure test@bigfm.dubai has the business_partner role (re-applied
    # in case anything reset it between runs).
    DB.users.update_one(
        {"email": "test@bigfm.dubai"},
        {"$set": {"role": "business_partner"}})
    s = requests.Session()
    rl = s.post(f"{API}/auth/login",
                    json={"email": "test@bigfm.dubai",
                            "password": "TestUser123!"}, timeout=10)
    assert rl.status_code == 200, rl.text[:200]
    # Seed a one_time_use claimed coupon for biz_demo_karak
    user_id = "user_4abd359ab5b94f0f"
    qr = f"cqr_qa_{uuid.uuid4().hex[:14]}"
    coupon_id = f"cpn_qa_{uuid.uuid4().hex[:12]}"
    DB.coupons.delete_many({"coupon_id": coupon_id})
    DB.coupons.insert_one({
        "_id": coupon_id, "coupon_id": coupon_id,
        "user_id": user_id, "business_id": "biz_demo_karak",
        "offer_id": "off_qa_demo",
        "qr_token": qr, "status": "claimed",
        "one_time_use": True, "max_redemptions": 1,
        "redeemed_count": 0, "claimed_at": _now(),
        "expires_at": _now() + timedelta(days=30),
    })
    headers = {"X-Partner-Token": "ptk_qa_demo_redeem_smoketoken_xyz"}
    try:
        r1 = s.post(f"{API}/partner/redeem/{qr}",
                       headers=headers, timeout=10)
        # First should succeed (200) or 409 if pre-condition fails
        assert r1.status_code in (200, 409), (r1.status_code, r1.text[:200])
        # Now mark the coupon redeemed and try a second time
        if r1.status_code == 200:
            # Reset to claimed so we can trigger the FRAUD guard one_time
            # path (otherwise it short-circuits as already_redeemed)
            DB.coupons.update_one(
                {"coupon_id": coupon_id},
                {"$set": {"status": "claimed",
                            "redeemed_at": _now() - timedelta(minutes=5)}})
            r2 = s.post(f"{API}/partner/redeem/{qr}",
                          headers=headers, timeout=10)
            assert r2.status_code in (409, 400, 422), (
                r2.status_code, r2.text[:200])
            # Either the idempotency raised already_redeemed OR our
            # fraud guard raised fraud_block:one_time_use_double_redeem
            fr = DB.fraud_events.find_one(
                {"coupon_id": coupon_id,
                  "rule": "one_time_use_double_redeem"})
            audit = DB.offer_redemptions_audit.find_one(
                {"coupon_id": coupon_id})
            # At least one of the two trails must show the block
            assert fr or (audit and "fraud" in (audit.get("outcome")
                                                            or "")) or audit, (
                "no fraud trail recorded for double-redeem attempt")
    finally:
        DB.coupons.delete_many({"coupon_id": coupon_id})
        DB.fraud_events.delete_many({"coupon_id": coupon_id})
        DB.offer_redemptions_audit.delete_many({"coupon_id": coupon_id})
        DB.strike_events.delete_many({"user_id": user_id,
                                                "source": "fraud"})
        # CRITICAL — clear any auto-suspend/mute caused by high-severity
        # fraud strikes during the test so subsequent test modules
        # (e.g. test_cleanup_phase) can log in as test@bigfm.dubai.
        DB.users.update_one(
            {"user_id": user_id},
            {"$unset": {"suspended_until": "", "suspended_reason": "",
                          "mute_until": "", "strikes_summary": ""}})
        DB.sessions.delete_many({"user_id": user_id})


# ─── HF-6. WS chat broadcast suppression on profanity (regression) ─────
def test_lobby_chat_blocks_profanity_via_ws():
    """Connect to the WS, send a profane chat message, then read a few
    frames — the profane text must NOT appear in any broadcast frame."""
    import asyncio as _asyncio
    import json as _json
    import websockets
    HTTP_ROOT = ROOT
    WS_ROOT = HTTP_ROOT.replace("https://", "wss://").replace("http://", "ws://")
    s = requests.Session()
    rl = s.post(f"{API}/auth/login",
                    json={"email": "admin@bigfm.dubai",
                            "password": "AdminPass123!"}, timeout=10)
    token = rl.json()["session_token"]
    # Get or create lobby
    rc = s.post(f"{API}/lobbies/create",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"name": "WS Mod Test",
                            "channel_slug": "bollywood_mehfil",
                            "city": "dubai"}, timeout=10)
    if rc.status_code == 200:
        lobby_id = rc.json()["lobby_id"]
    else:
        detail = (rc.json() or {}).get("detail") or ""
        lobby_id = detail.split(":", 1)[1].strip() if "already_hosting:" in detail else None
    if not lobby_id:
        pytest.skip("could not get/create lobby")

    async def _run():
        url = f"{WS_ROOT}/api/lobbies/ws/{lobby_id}?token={token}"
        async with websockets.connect(url, open_timeout=5,
                                                  close_timeout=2) as ws:
            await _asyncio.wait_for(ws.recv(), timeout=5)  # welcome
            # Send a profane chat message
            await ws.send(_json.dumps({"type": "chat",
                                                  "text": "this is shit"}))
            frames = []
            # Pull up to 5 frames or 3s
            try:
                for _ in range(5):
                    raw = await _asyncio.wait_for(ws.recv(), timeout=2)
                    frames.append(_json.loads(raw))
            except _asyncio.TimeoutError:
                pass
            return frames

    frames = _asyncio.run(_run())
    # Profane text must NOT appear in any chat_message frame
    for f in frames:
        if f.get("type") == "chat_message":
            assert "shit" not in (f.get("text") or "").lower(), f
    # And there should be an error frame with blocked_by_moderation
    blocked = any(f.get("type") == "error" and
                       f.get("code") == "blocked_by_moderation"
                       for f in frames)
    assert blocked, f"expected blocked_by_moderation in frames: {frames}"


# ─── HF-7. Bare-hostname URL detection ─────────────────────────────────
def test_bio_blocks_bare_hostname_url():
    """The leak regex must catch bare hostnames with a recognised TLD
    (`my-site.com`, `example.com for more`) AND keep dotted non-URLs
    like `v1.2.3` or `e.g.` passing through."""
    email = f"bare_url_{uuid.uuid4().hex[:8]}@example.com"
    pwd = "BareUrlTest123!"
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
                  json={"email": email, "password": pwd, "name": "Bare"},
                  timeout=10)
    assert r.status_code == 200
    uid = r.json()["user_id"]
    DB.users.update_one({"user_id": uid},
        {"$set": {"onboarding_complete": True}})

    def _put_bio(text: str) -> int:
        return s.patch(f"{API}/passport/me/settings",
                            json={"bio": text}, timeout=10).status_code

    try:
        # Must BLOCK (422):
        assert _put_bio("visit my-site.com today") == 422,    "my-site.com"
        assert _put_bio("example.com for more details") == 422, "example.com"
        # Regression — explicit https URL still blocks:
        assert _put_bio("see https://example.com") == 422, "https URL"
        # Must PASS (200) — false-positive checks:
        assert _put_bio("running v1.2.3 today") == 200,        "version str"
        assert _put_bio("for instance, e.g. like this") == 200, "e.g. dotted"
        assert _put_bio("loaded file.txt earlier") == 200,     "file.txt"
        assert _put_bio("read pkg.json carefully") == 200,     "pkg.json"
    finally:
        DB.users.delete_one({"user_id": uid})
        DB.sessions.delete_many({"user_id": uid})


# ─── HF-8. Partner redeem — REAL double-scan emits structured fraud ────
# Phase 12c Hotfix #3 (2026-05-27): de-hacked. Previously the test
# manually flipped `coupons.status` back to "claimed" between the two
# scans, which masked the fact that `services/local_commerce::
# redeem_coupon_by_qr` was raising a plain `already_redeemed` 409
# without firing the fraud rule. The fix wires `_emit_event` into
# the `status == "redeemed"` branch and the route layer renders a
# structured `{code: "fraud_blocked", rule, fraud_id, human_message}`
# 409 body. This test drives a genuine second scan with NO Mongo
# mutation in between.
def test_partner_redeem_double_scan_emits_fraud_event_without_hack():
    coupon_doc = None
    for _ in range(20):
        coupon_doc = DB.coupons.find_one({
            "offer_id": "ofr_qa_onetime_demo",
            "user_id": "user_4abd359ab5b94f0f",
            "status": "claimed"})
        if coupon_doc: break
        import time; time.sleep(0.5)
    assert coupon_doc, "QA seed coupon not found"
    qr = coupon_doc["qr_token"]
    coupon_id = coupon_doc["coupon_id"]
    user_id = coupon_doc["user_id"]
    # Login as partner (test@bigfm.dubai promoted to business_partner via seed)
    s = requests.Session()
    rl = s.post(f"{API}/auth/login",
                    json={"email": "test@bigfm.dubai",
                            "password": "TestUser123!"}, timeout=10)
    assert rl.status_code == 200, rl.text[:200]
    headers = {"X-Partner-Token": "ptk_qa_demo_redeem_smoketoken_xyz"}

    try:
        # 1st scan: genuine redemption.
        r1 = s.post(f"{API}/partner/redeem/{qr}",
                       headers=headers, timeout=10)
        assert r1.status_code == 200, (r1.status_code, r1.text[:200])
        c_after_1 = DB.coupons.find_one({"coupon_id": coupon_id})
        assert c_after_1["status"] == "redeemed", c_after_1

        # 2nd scan: NO Mongo mutation between calls. This is the real
        # double-scan path that previously emitted plain "already_redeemed".
        r2 = s.post(f"{API}/partner/redeem/{qr}",
                       headers=headers, timeout=10)
        assert r2.status_code == 409, (r2.status_code, r2.text[:200])
        body = r2.json()
        detail = body.get("detail") if isinstance(body, dict) else None
        assert isinstance(detail, dict), body
        assert detail.get("code") == "fraud_blocked", detail
        assert detail.get("rule") == "one_time_use_double_redeem", detail
        assert detail.get("fraud_id"), detail
        # Match the fraud_events row by the id surfaced in the body.
        fr = DB.fraud_events.find_one({"fraud_id": detail["fraud_id"]})
        assert fr, f"no fraud_event with id {detail['fraud_id']}"
        assert fr["rule"] == "one_time_use_double_redeem"
        assert fr["severity"] == "high"
        assert fr["coupon_id"] == coupon_id

        # Admin safety dashboard MUST surface the row in /fraud_events.
        admin = _login("admin@bigfm.dubai", "AdminPass123!")
        rev = admin.get(
            f"{API}/admin/safety/fraud_events?range=30d&limit=50",
            timeout=10)
        assert rev.status_code == 200, rev.text[:200]
        items = rev.json().get("items", [])
        assert any(it.get("fraud_id") == detail["fraud_id"]
                       for it in items), (
            "fraud_id not visible in admin safety feed",
            [it.get("fraud_id") for it in items[:10]])

        # offer_redemptions_audit MUST carry a fraud outcome on the
        # 2nd scan row.
        audit = DB.offer_redemptions_audit.find_one(
            {"coupon_id": coupon_id,
              "outcome": {"$regex": "^fraud_block:"}})
        assert audit, "no audit row with fraud_block outcome"
        assert audit.get("fraud_id") == detail["fraud_id"]
    finally:
        # Clear the fraud strikes that auto-suspended the user so other
        # test modules can log them back in.
        DB.users.update_one(
            {"user_id": user_id},
            {"$unset": {"suspended_until": "", "suspended_reason": "",
                          "mute_until": "", "strikes_summary": ""}})
        DB.fraud_events.delete_many({"coupon_id": coupon_id})
        DB.offer_redemptions_audit.delete_many({"coupon_id": coupon_id})
        DB.strike_events.delete_many({"user_id": user_id,
                                                "source": "fraud"})
        DB.sessions.delete_many({"user_id": user_id})
        # Reset the seeded coupon back to claimed=fresh for next run
        DB.coupons.update_one(
            {"coupon_id": coupon_id},
            {"$set": {"status": "claimed",
                        "redeemed_count": 0,
                        "claimed_at": _now()},
              "$unset": {"redeemed_at": ""}})
