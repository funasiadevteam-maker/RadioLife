"""Phase 12b — Retention engine tests.

Hits the live backend like test_phase10c / test_admin_analytics.  Heavy
use of direct Mongo writes to seed scenarios (playback_logs recency,
subscription state, push tokens) so the tests don't depend on a clean
sequence of real user actions.
"""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

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


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, r.text[:200]
    me = s.get(f"{API}/auth/me", timeout=10).json()
    s._user_id = me["user_id"]
    return s


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    return _login("test@bigfm.dubai", "TestUser123!")


@pytest.fixture
def dormant_user_id():
    """Seed a synthetic dormant user: created 60d ago, no plays."""
    uid = f"user_dormant_{uuid.uuid4().hex[:12]}"
    DB.users.insert_one({
        "user_id": uid,
        "email": f"{uid}@test.bigfm.dubai",
        "name": "Dormant Tester",
        "auth_provider": "test",
        "role": "user",
        "onboarding_complete": True,
        "is_premium": False,
        "created_at": _now() - timedelta(days=60),
        "preference_vector": {},
    })
    yield uid
    DB.users.delete_one({"user_id": uid})
    DB.churn_scores.delete_many({"user_id": uid})
    DB.playback_logs.delete_many({"user_id": uid})


# ─── 1. Churn computation correctness ──────────────────────────────────
def test_churn_score_computes_band_correctly(dormant_user_id):
    """A 60-day-old user with zero plays must land in dormant band."""
    from services.churn_score import compute_score, band_for_score
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    loop = asyncio.new_event_loop()
    try:
        payload = loop.run_until_complete(compute_score(db, dormant_user_id))
    finally:
        loop.close()
        cli.close()
    assert payload["band"] in ("at_risk", "dormant"), payload
    assert payload["score"] >= 51
    # Sanity: band_for_score consistent
    assert band_for_score(payload["score"]) == payload["band"]


# ─── 2. Admin gate ──────────────────────────────────────────────────────
def test_admin_retention_endpoints_require_admin(free_session):
    for ep in ("triggers", "churn_distribution", "campaigns",
                  "send_log"):
        r = free_session.get(f"{API}/admin/retention/{ep}", timeout=10)
        assert r.status_code == 403, (ep, r.status_code, r.text[:200])
    # Anon
    r = requests.get(f"{API}/admin/retention/triggers", timeout=10)
    assert r.status_code == 401


# ─── 3. Create + toggle ─────────────────────────────────────────────────
def test_create_and_toggle_campaign(admin_session):
    payload = {
        "name": "Test inactive-7d", "trigger": "inactive_7d",
        "channels": ["email"],
        "template": {"email_subject": "Hey {name}",
                          "email_body": "<p>Come back, {name}!</p>"},
        "active": False,
    }
    r = admin_session.post(f"{API}/admin/retention/campaigns",
                                    json=payload, timeout=10)
    assert r.status_code == 200, r.text[:200]
    cid = r.json()["id"]
    # Toggle active
    r2 = admin_session.patch(f"{API}/admin/retention/campaigns/{cid}",
                                      json={"active": True}, timeout=10)
    assert r2.status_code == 200
    assert r2.json()["active"] is True
    # Cleanup
    DB.lifecycle_campaigns.delete_one({"id": cid})


# ─── 4. Dry-run audience count ──────────────────────────────────────────
def test_campaign_dry_run_counts_audience(admin_session, dormant_user_id):
    # Force the dormant user into the dormant band via direct write
    DB.churn_scores.update_one(
        {"user_id": dormant_user_id},
        {"$set": {"user_id": dormant_user_id, "score": 92,
                    "band": "dormant",
                    "computed_at": _now(),
                    "expires_at": _now() + timedelta(hours=24),
                    "signals": {}}}, upsert=True)
    # Create campaign targeting dormant band
    r = admin_session.post(f"{API}/admin/retention/campaigns",
        json={"name": "Dry-run scope", "trigger": "inactive_7d",
                "channels": ["email"],
                "template": {"email_subject": "x", "email_body": "y"},
                "active": False}, timeout=10)
    cid = r.json()["id"]
    try:
        dr = admin_session.post(
            f"{API}/admin/retention/campaigns/{cid}/dry_run", timeout=15)
        assert dr.status_code == 200
        body = dr.json()
        assert "audience_size" in body
        assert body["audience_size"] >= 1, body
        assert dormant_user_id in body["sample_user_ids"]
    finally:
        DB.lifecycle_campaigns.delete_one({"id": cid})


# ─── 5. run_now writes send_log ─────────────────────────────────────────
def test_campaign_run_now_writes_send_log(admin_session, dormant_user_id):
    DB.churn_scores.update_one(
        {"user_id": dormant_user_id},
        {"$set": {"user_id": dormant_user_id, "score": 92,
                    "band": "dormant", "computed_at": _now(),
                    "expires_at": _now() + timedelta(hours=24),
                    "signals": {}}}, upsert=True)
    r = admin_session.post(f"{API}/admin/retention/campaigns",
        json={"name": "Run-now scope", "trigger": "inactive_7d",
                "channels": ["email"],
                "template": {"email_subject": "subj",
                                "email_body": "body"},
                "active": True}, timeout=10)
    cid = r.json()["id"]
    try:
        rn = admin_session.post(
            f"{API}/admin/retention/campaigns/{cid}/run_now",
            timeout=20)
        assert rn.status_code == 200, rn.text[:200]
        assert rn.json()["sent_email"] >= 1
        # send_log must have a row for this user+campaign
        row = DB.lifecycle_send_log.find_one(
            {"user_id": dormant_user_id, "campaign_id": cid})
        assert row, "no send_log row written"
        assert row["channel"] == "email"
    finally:
        DB.lifecycle_send_log.delete_many({"campaign_id": cid})
        DB.delivery_queue.delete_many({"campaign_id": cid})
        DB.lifecycle_campaigns.delete_one({"id": cid})


# ─── 6. Email stub when SENDGRID absent ─────────────────────────────────
def test_delivery_email_stub_when_sendgrid_absent(caplog):
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from services.delivery import send_email
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    loop = asyncio.new_event_loop()
    user = {"user_id": f"user_stubtest_{uuid.uuid4().hex[:8]}",
              "email": "stub@example.com", "name": "Stub"}
    # Ensure no SENDGRID_API_KEY in env
    if os.environ.get("SENDGRID_API_KEY"):
        pytest.skip("SENDGRID_API_KEY is set; stub path inapplicable")
    try:
        with caplog.at_level("WARNING", logger="bigfm.delivery"):
            log = loop.run_until_complete(send_email(
                db, user=user, campaign_id="cmp_test",
                subject="Hi", body_template="<p>Hi</p>"))
    finally:
        loop.close()
        cli.close()
    assert log["status"] == "stubbed"
    # HIGHLIGHTED MOCK warning emitted
    assert any("HIGHLIGHTED MOCK" in r.getMessage() for r in caplog.records)
    # Queue row written
    dq = DB.delivery_queue.find_one({"user_id": user["user_id"]})
    assert dq, "delivery_queue stub row missing"
    # cleanup
    DB.lifecycle_send_log.delete_many({"user_id": user["user_id"]})
    DB.delivery_queue.delete_many({"user_id": user["user_id"]})


# ─── 7. Push uses Expo endpoint ─────────────────────────────────────────
def test_delivery_push_uses_expo_endpoint():
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import delivery
    cli = AsyncIOMotorClient(MONGO_URL)
    db = cli[DB_NAME]
    loop = asyncio.new_event_loop()
    uid = f"user_push_{uuid.uuid4().hex[:8]}"
    # Seed a fake push token
    DB.user_push_tokens.insert_one({
        "_id": f"pt_{uuid.uuid4().hex[:10]}",
        "user_id": uid,
        "expo_push_token": "ExponentPushToken[xxxxxxxxx]",
        "platform": "ios", "active": True,
        "created_at": _now(), "updated_at": _now(),
    })
    user = {"user_id": uid, "email": "x@y.z", "name": "Pusher"}
    captured: dict = {}
    async def fake_expo(messages, client=None):
        captured["messages"] = messages
        return [{"status": "ok", "id": "exp_receipt_1"}]
    try:
        with patch.object(delivery, "_expo_send", new=fake_expo):
            log = loop.run_until_complete(delivery.send_push(
                db, user=user, campaign_id="cmp_push",
                title="Hello {name}!",
                body_template="Come back {name}",
                vars={"name": "Buddy"},
                deep_link="/?utm=push"))
    finally:
        loop.close()
        cli.close()
        DB.user_push_tokens.delete_many({"user_id": uid})
        DB.lifecycle_send_log.delete_many({"user_id": uid})
        DB.push_deliveries.delete_many({"user_id": uid})
    assert log["status"] == "sent", log
    assert captured["messages"]
    msg = captured["messages"][0]
    assert msg["to"].startswith("ExponentPushToken[")
    assert msg["title"] == "Hello Buddy!"
    assert msg["body"] == "Come back Buddy"
    assert msg["data"]["deep_link"] == "/?utm=push"


# ─── 8 + 9. /api/me/reactivation_prompt behaviour ───────────────────────
def test_reactivation_prompt_for_dormant_user_returns_payload():
    """Login as a fresh test user, force their churn band to dormant,
    then assert /api/me/reactivation_prompt returns a body."""
    # Create + login a brand-new user via the API
    email = f"react_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "ReactTest123!"
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
                  json={"email": email, "password": password,
                          "name": "React Tester"}, timeout=10)
    assert r.status_code == 200, r.text[:200]
    uid = r.json()["user_id"]
    try:
        # Force dormant band
        DB.churn_scores.update_one(
            {"user_id": uid},
            {"$set": {"user_id": uid, "score": 90, "band": "dormant",
                        "computed_at": _now(),
                        "expires_at": _now() + timedelta(hours=24),
                        "signals": {}}}, upsert=True)
        # Clear any dismissal
        DB.reactivation_dismiss.delete_many({"user_id": uid})
        rp = s.get(f"{API}/api/" if False else
                       f"{API}/me/reactivation_prompt", timeout=10)
        assert rp.status_code == 200, rp.text[:200]
        body = rp.json()
        for k in ("prompt_type", "headline", "body", "cta_label",
                    "cta_href", "dismissable_until"):
            assert k in body, body
        assert body["prompt_type"] == "dormant"
    finally:
        DB.users.delete_one({"user_id": uid})
        DB.churn_scores.delete_many({"user_id": uid})
        DB.reactivation_dismiss.delete_many({"user_id": uid})
        DB.sessions.delete_many({"user_id": uid})


def test_reactivation_prompt_for_healthy_user_returns_204():
    """Login as healthy user (admin has a fresh session) → 204."""
    email = f"healthy_{uuid.uuid4().hex[:8]}@example.com"
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
                  json={"email": email, "password": "HealthyTest123!",
                          "name": "Healthy"}, timeout=10)
    assert r.status_code == 200
    uid = r.json()["user_id"]
    try:
        # Force healthy band so we don't depend on real signal calc
        DB.churn_scores.update_one(
            {"user_id": uid},
            {"$set": {"user_id": uid, "score": 10, "band": "healthy",
                        "computed_at": _now(),
                        "expires_at": _now() + timedelta(hours=24),
                        "signals": {}}}, upsert=True)
        rp = s.get(f"{API}/me/reactivation_prompt", timeout=10)
        assert rp.status_code == 204, rp.status_code
    finally:
        DB.users.delete_one({"user_id": uid})
        DB.churn_scores.delete_many({"user_id": uid})
        DB.sessions.delete_many({"user_id": uid})


# ─── 10. force_band QA override ─────────────────────────────────────────
def test_recompute_user_force_band_overrides_signals(
        admin_session, dormant_user_id):
    """`?force_band=...` MUST upsert a churn_scores row with that exact
    band, midpoint score, signals.forced=True, and the admin's user_id.
    Existing (no-param) behaviour stays untouched."""
    # 1. Force healthy on a user we know is *naturally* dormant
    r = admin_session.post(
        f"{API}/admin/retention/recompute_user/{dormant_user_id}"
        f"?force_band=healthy", timeout=10)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["band"] == "healthy"
    assert body["score"] == 12  # band midpoint
    assert body["signals"]["forced"] is True
    assert body["signals"]["forced_by"]  # admin user_id stamped
    # Mongo row matches
    row = DB.churn_scores.find_one({"user_id": dormant_user_id})
    assert row["band"] == "healthy"
    assert row["signals"]["forced"] is True

    # 2. Force at_risk
    r2 = admin_session.post(
        f"{API}/admin/retention/recompute_user/{dormant_user_id}"
        f"?force_band=at_risk", timeout=10)
    assert r2.status_code == 200
    assert r2.json()["band"] == "at_risk"
    assert r2.json()["score"] == 63

    # 3. Invalid band → 400
    rbad = admin_session.post(
        f"{API}/admin/retention/recompute_user/{dormant_user_id}"
        f"?force_band=elite", timeout=10)
    assert rbad.status_code == 400, rbad.text

    # 4. No force_band → falls through to natural compute (should
    # land on at_risk or dormant for this fixture).
    r4 = admin_session.post(
        f"{API}/admin/retention/recompute_user/{dormant_user_id}",
        timeout=10)
    assert r4.status_code == 200
    assert r4.json()["band"] in ("at_risk", "dormant")
    # And signals should NOT carry forced=True any more
    assert r4.json()["signals"].get("forced") is not True

    # 5. Unknown user → 404
    runknown = admin_session.post(
        f"{API}/admin/retention/recompute_user/user_does_not_exist"
        f"?force_band=dormant", timeout=10)
    assert runknown.status_code == 404

    # 6. force_band=dormant must also stamp synthetic playback_logs so
    # that an `inactive_7d` campaign's dry_run picks up the forced user.
    r6 = admin_session.post(
        f"{API}/admin/retention/recompute_user/{dormant_user_id}"
        f"?force_band=dormant", timeout=10)
    assert r6.status_code == 200
    sig = r6.json()["signals"]
    assert sig["forced"] is True
    assert "forced_last_played_at" in sig, sig
    # Synthetic playback log row exists
    pl = DB.playback_logs.find_one(
        {"user_id": dormant_user_id, "qa_forced": True})
    assert pl, "synthetic playback_logs row not written"
    # Now an inactive_7d campaign must include this user in its audience
    c = admin_session.post(f"{API}/admin/retention/campaigns",
        json={"name": "Force-band audience check",
                "trigger": "inactive_7d",
                "channels": ["email"],
                "template": {"email_subject": "x", "email_body": "y"},
                "active": False}, timeout=10)
    cid = c.json()["id"]
    try:
        dr = admin_session.post(
            f"{API}/admin/retention/campaigns/{cid}/dry_run", timeout=15)
        assert dr.status_code == 200
        body = dr.json()
        assert body["audience_size"] >= 1, body
        assert dormant_user_id in body["sample_user_ids"], body
    finally:
        DB.lifecycle_campaigns.delete_one({"id": cid})
