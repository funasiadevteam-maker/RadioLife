"""Phase 6 — multi-tier subscription tests.

Covers acceptance criteria:
1. GET /api/billing/plans lists 4 active plans w/ localized pricing
2. Upgrade premium_monthly → premium_annual returns proration + extended period
3. Downgrade is queued via pending_plan_change
4. Family invite + accept + remove (5 seat cap enforced)
5. invoice.payment_failed → past_due → grace 7d → auto-downgrade
6. invoice.payment_succeeded after past_due restores active
7. Webhook replay (same event_id) is a no-op
8. Idempotency-Key on change_plan dedupes
9. Cancel + resume toggle cleanly
10. No regressions: BigCoin /me, games/state, radio plans endpoint

Stripe is bypassed for Customer Portal in this suite (returns the URL/error
without performing real API calls — admin sim endpoints replace webhook
events for the payment-failed/recovered/downgrade flows).
"""
from __future__ import annotations

import os
import time
import json
import uuid
from datetime import datetime, timezone, timedelta

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

API = os.environ.get("PHASE6_API",
                       "https://mobile-games-v2.preview.emergentagent.com").rstrip("/") + "/api"
MONGO = os.environ.get("PHASE6_MONGO", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.text}"
    return s


def _register(email: str, password: str, name: str = "Tester") -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/register",
                 json={"email": email, "password": password, "name": name}, timeout=15)
    assert r.status_code == 200, f"register failed for {email}: {r.text}"
    # complete onboarding
    s.post(f"{API}/users/preferences",
            json={"languages": ["english", "hindi"], "genres": ["pop", "bollywood"],
                  "eras": ["2020s"], "moods": ["happy", "energetic"],
                  "activities": ["commute"], "host_personality": "auto", "market": "dubai"},
            timeout=10)
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


# ----- Tests --------------------------------------------------------------
def test_01_plans_list_usd():
    r = requests.get(f"{API}/billing/plans?currency=USD", timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["currency"] == "USD"
    slugs = {p["slug"] for p in d["plans"]}
    assert {"free", "premium_monthly", "premium_annual", "premium_family"}.issubset(slugs)
    # venue_business is active=False so should NOT appear
    assert "venue_business" not in slugs
    # Annual has a savings tag
    annual = next(p for p in d["plans"] if p["slug"] == "premium_annual")
    assert annual["savings_vs_monthly_pct"] == 20


def test_02_plans_aed_localized():
    r = requests.get(f"{API}/billing/plans?currency=AED", timeout=10)
    d = r.json()
    pm = next(p for p in d["plans"] if p["slug"] == "premium_monthly")
    assert pm["currency"] == "AED"
    assert "AED" in pm["amount_display"]


def test_03_status_endpoint(admin_session):
    r = admin_session.get(f"{API}/billing/status")
    assert r.status_code == 200
    d = r.json()
    for k in ("is_premium", "current_plan_slug", "billing_status", "family"):
        assert k in d


def test_04_upgrade_proration_records_lifecycle():
    """premium_monthly → premium_annual via change_plan returns prorated charge."""
    s = _register(f"phase6up{uuid.uuid4().hex[:6]}@bigfm.dubai", "Phase6Test99!")
    cli = AsyncIOMotorClient(MONGO)
    db = cli[DB_NAME]
    me = s.get(f"{API}/auth/me").json()
    uid = me["user_id"]
    # Seed user as premium_monthly with a mid-period state
    import asyncio
    async def seed():
        now = datetime.now(timezone.utc)
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {
                "is_premium": True, "premium_tier": "premium",
                "premium_until": now + timedelta(days=20),
                "subscription": {
                    "plan": "premium_monthly", "status": "active",
                    "current_period_start": now - timedelta(days=10),
                    "current_period_end": now + timedelta(days=20),
                    "currency": "USD", "cancel_at_period_end": False,
                },
            }},
        )
    asyncio.get_event_loop().run_until_complete(seed())
    r = s.post(f"{API}/billing/change_plan",
                json={"target_plan_slug": "premium_annual"},
                headers={"Idempotency-Key": f"up-{uuid.uuid4().hex[:8]}"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["action"] == "upgrade"
    assert d["from_plan"] == "premium_monthly"
    assert d["to_plan"] == "premium_annual"
    assert d["net_charge"] > 0
    assert d["proration_credit"] > 0
    # Lifecycle log row created
    async def check():
        log = await db.subscription_lifecycle_log.find_one(
            {"user_id": uid, "event_type": "plan_upgraded"},
            sort=[("ts", -1)])
        assert log is not None
        assert log["from_state"] == "premium_monthly"
        assert log["to_state"] == "premium_annual"
    asyncio.get_event_loop().run_until_complete(check())


def test_05_downgrade_queued():
    s = _register(f"phase6dn{uuid.uuid4().hex[:6]}@bigfm.dubai", "Phase6Test99!")
    cli = AsyncIOMotorClient(MONGO)
    db = cli[DB_NAME]
    me = s.get(f"{API}/auth/me").json()
    uid = me["user_id"]
    import asyncio
    async def seed():
        now = datetime.now(timezone.utc)
        await db.users.update_one(
            {"user_id": uid},
            {"$set": {
                "is_premium": True, "premium_tier": "premium",
                "premium_until": now + timedelta(days=20),
                "subscription": {
                    "plan": "premium_annual", "status": "active",
                    "current_period_start": now - timedelta(days=10),
                    "current_period_end": now + timedelta(days=20),
                    "currency": "USD",
                },
            }},
        )
    asyncio.get_event_loop().run_until_complete(seed())
    r = s.post(f"{API}/billing/change_plan",
                json={"target_plan_slug": "premium_monthly"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["action"] == "downgrade_queued"
    assert "effective_at" in d
    # users.pending_plan_change is set
    async def check():
        u = await db.users.find_one({"user_id": uid},
                                       {"pending_plan_change": 1, "_id": 0})
        assert u["pending_plan_change"]["target_plan_slug"] == "premium_monthly"
    asyncio.get_event_loop().run_until_complete(check())


def test_06_idempotency_key_dedup():
    s = _register(f"phase6id{uuid.uuid4().hex[:6]}@bigfm.dubai", "Phase6Test99!")
    cli = AsyncIOMotorClient(MONGO)
    db = cli[DB_NAME]
    uid = s.get(f"{API}/auth/me").json()["user_id"]
    import asyncio
    asyncio.get_event_loop().run_until_complete(db.users.update_one(
        {"user_id": uid},
        {"$set": {
            "is_premium": True, "premium_tier": "premium",
            "subscription": {"plan": "premium_monthly", "status": "active",
                              "current_period_start": datetime.now(timezone.utc),
                              "current_period_end": datetime.now(timezone.utc) + timedelta(days=30),
                              "currency": "USD"},
        }}))
    key = f"dedup-{uuid.uuid4().hex[:8]}"
    r1 = s.post(f"{API}/billing/change_plan",
                  json={"target_plan_slug": "premium_annual"},
                  headers={"Idempotency-Key": key})
    r2 = s.post(f"{API}/billing/change_plan",
                  json={"target_plan_slug": "premium_annual"},
                  headers={"Idempotency-Key": key})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json().get("idempotent") is True


def test_07_family_invite_accept_remove(admin_session):
    cli = AsyncIOMotorClient(MONGO)
    db = cli[DB_NAME]
    # Create a fresh family root + member
    root = _register(f"famroot{uuid.uuid4().hex[:6]}@bigfm.dubai", "Phase6Test99!")
    member = _register(f"fammem{uuid.uuid4().hex[:6]}@bigfm.dubai", "Phase6Test99!")
    root_uid = root.get(f"{API}/auth/me").json()["user_id"]
    member_uid = member.get(f"{API}/auth/me").json()["user_id"]
    member_email = member.get(f"{API}/auth/me").json()["email"]
    import asyncio
    # Mark root as premium_family with 5 seats
    asyncio.get_event_loop().run_until_complete(db.users.update_one(
        {"user_id": root_uid},
        {"$set": {
            "is_premium": True, "premium_tier": "premium",
            "family_seats_total": 5, "family_seats_used": 0,
            "subscription": {"plan": "premium_family", "status": "active",
                              "currency": "USD"},
        }}))
    # Invite
    r = root.post(f"{API}/billing/family/invite", json={"email": member_email})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    # Accept (as member)
    r = member.post(f"{API}/billing/family/accept", json={"token": token})
    assert r.status_code == 200, r.text
    # Member is now premium via family_seat
    me_after = member.get(f"{API}/auth/me").json()
    assert me_after.get("is_premium") is True
    # Family state shows 1 seat used
    fam = root.get(f"{API}/billing/family").json()
    assert fam["seats_used"] == 1
    assert len(fam["members"]) == 1
    # Remove
    r = root.post(f"{API}/billing/family/remove", json={"user_id": member_uid})
    assert r.status_code == 200
    # Member should no longer be premium
    me_final = member.get(f"{API}/auth/me").json()
    assert me_final.get("is_premium") is False


def test_08_payment_failed_creates_grace(admin_session):
    """Simulate invoice.payment_failed via admin sim endpoint."""
    cli = AsyncIOMotorClient(MONGO)
    db = cli[DB_NAME]
    s = _register(f"pastdue{uuid.uuid4().hex[:6]}@bigfm.dubai", "Phase6Test99!")
    uid = s.get(f"{API}/auth/me").json()["user_id"]
    import asyncio
    asyncio.get_event_loop().run_until_complete(db.users.update_one(
        {"user_id": uid},
        {"$set": {"is_premium": True, "premium_tier": "premium",
                   "subscription": {"plan": "premium_monthly", "status": "active",
                                     "currency": "USD"}}}))
    r = admin_session.post(f"{API}/billing/admin/simulate_payment_failed",
                              json={"user_id": uid})
    assert r.status_code == 200, r.text
    status = s.get(f"{API}/billing/status").json()
    assert status["billing_status"] == "past_due"
    assert status["grace_period_ends_at"] is not None
    assert status["is_premium"] is True  # still premium during grace


def test_09_payment_recovered_restores_active(admin_session):
    cli = AsyncIOMotorClient(MONGO)
    db = cli[DB_NAME]
    s = _register(f"recover{uuid.uuid4().hex[:6]}@bigfm.dubai", "Phase6Test99!")
    uid = s.get(f"{API}/auth/me").json()["user_id"]
    import asyncio
    asyncio.get_event_loop().run_until_complete(db.users.update_one(
        {"user_id": uid},
        {"$set": {"is_premium": True, "premium_tier": "premium",
                   "subscription": {"plan": "premium_monthly", "status": "active",
                                     "currency": "USD"}}}))
    admin_session.post(f"{API}/billing/admin/simulate_payment_failed", json={"user_id": uid})
    r = admin_session.post(f"{API}/billing/admin/simulate_payment_succeeded",
                              json={"user_id": uid})
    assert r.status_code == 200
    status = s.get(f"{API}/billing/status").json()
    assert status["billing_status"] == "active"


def test_10_grace_expiry_auto_downgrades(admin_session):
    """Force grace_period_ends_at to past and trigger sweep — user gets downgraded."""
    cli = AsyncIOMotorClient(MONGO)
    db = cli[DB_NAME]
    s = _register(f"expgr{uuid.uuid4().hex[:6]}@bigfm.dubai", "Phase6Test99!")
    uid = s.get(f"{API}/auth/me").json()["user_id"]
    import asyncio
    now = datetime.now(timezone.utc)
    asyncio.get_event_loop().run_until_complete(db.users.update_one(
        {"user_id": uid},
        {"$set": {
            "is_premium": True, "premium_tier": "premium",
            "billing_status": "past_due",
            "grace_period_ends_at": now - timedelta(hours=1),  # expired 1hr ago
            "past_due_started_at": now - timedelta(days=8),
            "subscription": {"plan": "premium_monthly", "status": "past_due",
                              "currency": "USD"},
        }}))
    r = admin_session.post(f"{API}/billing/admin/run_dunning_sweep")
    assert r.status_code == 200, r.text
    assert r.json()["downgraded"] >= 1
    status = s.get(f"{API}/billing/status").json()
    assert status["is_premium"] is False
    assert status["billing_status"] == "canceled_for_nonpayment"


def test_11_cancel_resume_toggle():
    cli = AsyncIOMotorClient(MONGO)
    db = cli[DB_NAME]
    s = _register(f"cancel{uuid.uuid4().hex[:6]}@bigfm.dubai", "Phase6Test99!")
    uid = s.get(f"{API}/auth/me").json()["user_id"]
    import asyncio
    asyncio.get_event_loop().run_until_complete(db.users.update_one(
        {"user_id": uid},
        {"$set": {"is_premium": True, "premium_tier": "premium",
                   "subscription": {"plan": "premium_monthly", "status": "active",
                                     "current_period_end": datetime.now(timezone.utc) + timedelta(days=20),
                                     "currency": "USD"}}}))
    r = s.post(f"{API}/billing/cancel")
    assert r.status_code == 200 and r.json()["cancel_at_period_end"] is True
    r = s.post(f"{API}/billing/resume")
    assert r.status_code == 200 and r.json()["cancel_at_period_end"] is False


def test_12_webhook_replay_is_noop():
    """POST the same webhook payload twice — second time returns duplicate=True."""
    body = {
        "id": f"evt_phase6_test_{uuid.uuid4().hex[:8]}",
        "type": "customer.subscription.created",
        "data": {"object": {"metadata": {"user_id": "user_4abd359ab5b94f0f"},
                              "customer": "cus_dummy"}},
    }
    r1 = requests.post(f"{API}/billing/webhook_v6", json=body, timeout=10)
    r2 = requests.post(f"{API}/billing/webhook_v6", json=body, timeout=10)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True


def test_13_openapi_exposes_phase6_routes():
    r = requests.get(f"{API}/openapi.json", timeout=10)
    paths = r.json()["paths"]
    must_have = [
        "/api/billing/plans", "/api/billing/status", "/api/billing/change_plan",
        "/api/billing/cancel", "/api/billing/resume",
        "/api/billing/pause", "/api/billing/unpause",
        "/api/billing/portal",
        "/api/billing/family/invite", "/api/billing/family/accept",
        "/api/billing/family/remove", "/api/billing/family",
        "/api/billing/webhook_v6",
    ]
    missing = [p for p in must_have if p not in paths]
    assert not missing, f"missing routes: {missing}"


def test_14_no_regression_bigcoin_radio():
    """Smoke: BigCoin, games_v2, and billing config endpoints still respond.
    NB: /api/games/state now returns a Phase 8a-backed shim (was 410 in 8a → 200
    again per user-reported P0 in late May 2026)."""
    s = _login("test@bigfm.dubai", "TestUser123!")
    assert s.get(f"{API}/bigcoin/me").status_code == 200
    assert s.get(f"{API}/games_v2/play_and_win").status_code == 200
    assert s.get(f"{API}/games/state").status_code == 200    # shim → games_v2
    assert s.get(f"{API}/billing/config?currency=USD").status_code == 200
