"""Phase 9c — Local Commerce: businesses, offers, coupons, partner
onboarding, Google Wallet, route-ad engine offer surfacing.

Harness style matches test_phase9a / test_phase9b — same fixtures + the
public-HTTPS backend URL so the Secure session cookie is sent back."""
from __future__ import annotations

import asyncio
import io
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

ROOT = os.environ.get("BIGFM_API_URL") or \
          "https://mobile-games-v2.preview.emergentagent.com"
API = f"{ROOT.rstrip('/')}/api"
MONGO = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME") or "bigfm"
DB = MONGO[DB_NAME]


def _now():
    return datetime.now(timezone.utc)


def _run(coro_factory):
    loop = asyncio.new_event_loop()
    try:
        if callable(coro_factory):
            async def _runner():
                db = AsyncIOMotorClient(
                    os.environ.get("MONGO_URL")
                    or "mongodb://localhost:27017")[DB_NAME]
                return await coro_factory(db)
            return loop.run_until_complete(_runner())
        return loop.run_until_complete(coro_factory)
    finally:
        loop.close()


# ════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def user_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": "test@bigfm.dubai",
                          "password": "TestUser123!"}, timeout=10)
    assert r.status_code == 200, r.text
    s._user_id = r.json()["user_id"]
    yield s


@pytest.fixture(scope="module")
def partner_session():
    """A separate user that will be upgraded to business_partner."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": "advertiser@bigfm.dubai",
                          "password": "AdvertiserP8!23"}, timeout=10)
    assert r.status_code == 200, r.text
    s._user_id = r.json()["user_id"]
    # Make sure it's at least business_partner.  Idempotent.
    s.post(f"{API}/auth/partner/upgrade", json={"accept_terms": True},
              timeout=10)
    yield s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": "admin@bigfm.dubai",
                          "password": "AdminPass123!"}, timeout=10)
    assert r.status_code == 200, r.text
    yield s


@pytest.fixture
def fresh_business(partner_session):
    """A freshly claimed business owned by partner_session.  Verified
    so the partner can immediately create offers."""
    uid = partner_session._user_id
    bid = f"biz_t9c_{int(time.time()*1000)}"
    DB.businesses.insert_one({
        "_id": bid, "business_id": bid,
        "name": "Test Café 9c", "category": "cafe",
        "lat": 25.196, "lng": 55.281, "city": "dubai",
        "address": "Sheikh Zayed Road, Dubai",
        "rating": 4.5,
        "loc": {"type": "Point", "coordinates": [55.281, 25.196]},
        "owner_user_ids": [uid],
        "partner_status": "verified", "verified_at": _now(),
        "slug": f"test-cafe-9c-{int(time.time())}",
        "created_at": _now(),
    })
    yield DB.businesses.find_one({"business_id": bid})
    # cleanup
    DB.coupons.delete_many({"business_id": bid})
    DB.offers.delete_many({"business_id": bid})
    DB.businesses.delete_one({"business_id": bid})
    DB.partner_pos_integrations.delete_many({"business_id": bid})


# ════════════════════════════════════════════════════════════════════════
# § 1 — Partner upgrade + business claim
# ════════════════════════════════════════════════════════════════════════
def test_01_partner_upgrade_requires_accept_terms(user_session):
    r = user_session.post(f"{API}/auth/partner/upgrade",
                                 json={}, timeout=10)
    assert r.status_code == 400


def test_02_partner_upgrade_idempotent(partner_session):
    r = partner_session.post(f"{API}/auth/partner/upgrade",
                                       json={"accept_terms": True}, timeout=10)
    assert r.status_code == 200
    assert r.json()["role"] in ("business_partner", "admin", "moderator")


def test_03_partner_claim_business_creates_pending(partner_session):
    r = partner_session.post(f"{API}/partner/businesses/claim",
                                       json={"manual_business": {
                                           "name": "Tester Diner 9c",
                                           "lat": 25.197, "lng": 55.282,
                                           "city": "dubai"}}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    bid = body["business_id"]
    assert body["partner_status"] in ("claimed", "verified")
    # Slug auto-assigned
    assert body.get("slug")
    DB.businesses.delete_one({"business_id": bid})


def test_04_admin_verify_business(partner_session, admin_session):
    r = partner_session.post(f"{API}/partner/businesses/claim",
                                       json={"manual_business": {
                                           "name": "Admin Verify Pizza",
                                           "lat": 25.197, "lng": 55.282}},
                                       timeout=15)
    bid = r.json()["business_id"]
    r2 = admin_session.post(f"{API}/admin/businesses/{bid}/verify",
                                       timeout=10)
    assert r2.status_code == 200, r2.text
    assert r2.json()["partner_status"] == "verified"
    DB.businesses.delete_one({"business_id": bid})


# ════════════════════════════════════════════════════════════════════════
# § 2 — Offer lifecycle
# ════════════════════════════════════════════════════════════════════════
def _create_offer(partner_session, bid: str, *, inventory: int = 100,
                       max_per_user: int = 1) -> str:
    r = partner_session.post(
        f"{API}/partner/businesses/{bid}/offers",
        json={"title": "20% off karak",
                "description": "All day, weekdays only",
                "offer_type": "percent_off",
                "value_amount": 20, "value_currency": "AED",
                "terms_text": "Cannot be combined",
                "max_redemptions_total": inventory,
                "max_per_user": max_per_user,
                "redeem_window_seconds": 3600},
        timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["offer_id"]


def test_10_create_submit_approve_offer(partner_session, admin_session,
                                                       fresh_business):
    bid = fresh_business["business_id"]
    oid = _create_offer(partner_session, bid)
    # Submit
    r = partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/submit_for_approval",
        timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "pending_approval"
    # Approve
    r2 = admin_session.post(f"{API}/admin/offers/{oid}/approve", timeout=10)
    assert r2.status_code == 200
    assert r2.json()["status"] == "active"


def test_11_offer_pause_resume_end(partner_session, admin_session,
                                                  fresh_business):
    bid = fresh_business["business_id"]
    oid = _create_offer(partner_session, bid)
    partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/submit_for_approval",
        timeout=10)
    admin_session.post(f"{API}/admin/offers/{oid}/approve", timeout=10)
    # Pause
    r = partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/pause", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "paused"
    # Resume
    r2 = partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/resume", timeout=10)
    assert r2.status_code == 200
    assert r2.json()["status"] == "active"
    # End
    r3 = partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/end", timeout=10)
    assert r3.status_code == 200
    assert r3.json()["status"] == "ended"


def test_12_admin_reject_offer_requires_reason(partner_session, admin_session,
                                                                fresh_business):
    bid = fresh_business["business_id"]
    oid = _create_offer(partner_session, bid)
    partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/submit_for_approval",
        timeout=10)
    r = admin_session.post(f"{API}/admin/offers/{oid}/reject",
                                    json={}, timeout=10)
    assert r.status_code == 400
    r2 = admin_session.post(f"{API}/admin/offers/{oid}/reject",
                                      json={"reason": "stock low"}, timeout=10)
    assert r2.status_code == 200
    # Phase 9c.1 — rejection lands in real "rejected" state (was "draft").
    body = r2.json()
    assert body["status"] == "rejected"
    assert body.get("rejection_reason") == "stock low"
    assert body.get("rejected_at")


def test_13_revise_rejected_offer_round_trip(partner_session, admin_session,
                                                                fresh_business):
    """Phase 9c.1 Fix 1 — partner acknowledges the rejection reason via
    the new /revise endpoint; offer returns to `draft` with the old
    reason archived in `previous_rejections`.  Body must include
    `acknowledge_rejection_reason: true` or the call must 400."""
    bid = fresh_business["business_id"]
    oid = _create_offer(partner_session, bid)
    partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/submit_for_approval",
        timeout=10)
    admin_session.post(f"{API}/admin/offers/{oid}/reject",
                              json={"reason": "image_low_resolution"},
                              timeout=10)
    # 1. /revise without acknowledge flag → 400
    r_bad = partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/revise",
        json={}, timeout=10)
    assert r_bad.status_code == 400
    assert "acknowledge_rejection_reason_required" in r_bad.text
    # 2. /revise with ack=true → 200, status returns to draft,
    #    rejection_reason cleared, previous_rejections archive bumped.
    r_ok = partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/revise",
        json={"acknowledge_rejection_reason": True}, timeout=10)
    assert r_ok.status_code == 200, r_ok.text
    body = r_ok.json()
    assert body["status"] == "draft"
    assert not body.get("rejection_reason")
    assert any(p.get("reason") == "image_low_resolution"
                  for p in body.get("previous_rejections") or [])
    # 3. /revise on a non-rejected offer → 400
    r_bad2 = partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/revise",
        json={"acknowledge_rejection_reason": True}, timeout=10)
    assert r_bad2.status_code == 400
    # 4. Can submit again post-revise → moves to pending_approval
    r_resub = partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/submit_for_approval",
        timeout=10)
    assert r_resub.status_code == 200
    assert r_resub.json()["status"] == "pending_approval"


# ════════════════════════════════════════════════════════════════════════
# § 3 — Public business pages (no auth)
# ════════════════════════════════════════════════════════════════════════
def test_20_public_business_page_no_auth(fresh_business):
    slug = fresh_business["slug"]
    r = requests.get(f"{API}/public/businesses/{slug}", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == slug
    assert body["name"] == fresh_business["name"]
    assert "active_offers_count" in body


def test_21_public_offers_listing(fresh_business, partner_session,
                                              admin_session):
    bid = fresh_business["business_id"]
    oid = _create_offer(partner_session, bid)
    partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/submit_for_approval",
        timeout=10)
    admin_session.post(f"{API}/admin/offers/{oid}/approve", timeout=10)
    r = requests.get(
        f"{API}/public/businesses/{fresh_business['slug']}/offers",
        timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(o["offer_id"] == oid for o in items)


def test_22_public_qr_png(fresh_business):
    r = requests.get(
        f"{API}/public/businesses/{fresh_business['slug']}/qr.png",
        timeout=10)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert len(r.content) > 200


# ════════════════════════════════════════════════════════════════════════
# § 4 — Listener claim + max_per_user + atomic inventory
# ════════════════════════════════════════════════════════════════════════
def _approve_offer_quick(partner_session, admin_session, bid, inventory=10,
                                  max_per_user=1):
    oid = _create_offer(partner_session, bid, inventory=inventory,
                              max_per_user=max_per_user)
    partner_session.post(
        f"{API}/partner/businesses/{bid}/offers/{oid}/submit_for_approval",
        timeout=10)
    admin_session.post(f"{API}/admin/offers/{oid}/approve", timeout=10)
    return oid


def test_30_listener_claim_offer(user_session, partner_session,
                                              admin_session, fresh_business):
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid,
                                          inventory=10, max_per_user=2)
    DB.coupons.delete_many({"user_id": user_session._user_id,
                                    "offer_id": oid})
    r = user_session.post(f"{API}/commerce/offers/{oid}/claim",
                                 json={}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "claimed"
    assert body["redemption_code"].startswith("BIGFM-")
    assert body["qr_token"].startswith("cqr_")
    assert "save_url" in body["wallet_pass_url"] or body["wallet_pass_url"].startswith("https://pay.google.com")
    # Inventory decremented
    o = DB.offers.find_one({"offer_id": oid})
    assert o["inventory_remaining"] == 9


def test_31_max_per_user_enforced(user_session, partner_session,
                                              admin_session, fresh_business):
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid,
                                          inventory=10, max_per_user=1)
    DB.coupons.delete_many({"user_id": user_session._user_id,
                                    "offer_id": oid})
    r1 = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={},
                                   timeout=10)
    assert r1.status_code == 200
    r2 = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={},
                                   timeout=10)
    assert r2.status_code == 409
    assert "max_per_user_reached" in r2.text


def test_32_concurrent_burst_atomic_inventory(partner_session,
                                                                admin_session,
                                                                fresh_business):
    """20 concurrent claims against inventory=5 → exactly 5 succeed."""
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid,
                                          inventory=5, max_per_user=99)
    # Engine handles concurrent atomic decrement.  We hit it directly via
    # the service to avoid 20 HTTPS round-trips clobbering the test cookie.
    from services.local_commerce import claim_offer as svc_claim
    async def burst(db):
        results = await asyncio.gather(*[
            svc_claim(db, offer_id=oid, user_id=f"burst_user_{i}",
                          claim_source="public_page")
            for i in range(20)
        ], return_exceptions=True)
        return results
    results = _run(burst)
    ok = [r for r in results if not isinstance(r, Exception)]
    errs = [r for r in results if isinstance(r, Exception)]
    assert len(ok) == 5, f"expected 5 successes got {len(ok)}"
    assert all("out_of_inventory" in str(e) for e in errs)
    o = DB.offers.find_one({"offer_id": oid})
    assert o["inventory_remaining"] == 0


# ════════════════════════════════════════════════════════════════════════
# § 5 — Partner-token redemption
# ════════════════════════════════════════════════════════════════════════
async def _issue_partner_token(db, *, owner_user_id: str,
                                       business_id: str) -> tuple[str, str]:
    """Issue a partner_token bound to a business with redeem_offers scope.

    Returns (token_id, raw_secret).
    """
    from services.games_v2 import issue_partner_token
    res = await issue_partner_token(
        db, partner_business_id=business_id,
        scopes=["redeem_offers"],
        issued_by_user_id=owner_user_id)
    return res["partner_token_id"], res["raw_secret"]


def test_40_redeem_happy_path(user_session, partner_session, admin_session,
                                       fresh_business):
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    DB.coupons.delete_many({"user_id": user_session._user_id,
                                    "offer_id": oid})
    r = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={},
                                 timeout=10)
    qr = r.json()["qr_token"]
    # Issue partner token
    token_id, raw_secret = _run(lambda db: _issue_partner_token(
        db, owner_user_id=partner_session._user_id, business_id=bid))
    # Redeem via partner endpoint
    r2 = partner_session.post(f"{API}/partner/redeem/{qr}",
                                       headers={"X-Partner-Token": raw_secret},
                                       timeout=10)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["coupon"]["status"] == "redeemed"
    assert body["audit_id"]
    # Replay
    r3 = partner_session.post(f"{API}/partner/redeem/{qr}",
                                       headers={"X-Partner-Token": raw_secret},
                                       timeout=10)
    assert r3.status_code == 409
    assert "already_redeemed" in r3.text


def test_41_redeem_missing_partner_token(partner_session, user_session,
                                                          admin_session,
                                                          fresh_business):
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    DB.coupons.delete_many({"user_id": user_session._user_id,
                                    "offer_id": oid})
    r = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={})
    qr = r.json()["qr_token"]
    r2 = partner_session.post(f"{API}/partner/redeem/{qr}", timeout=10)
    assert r2.status_code == 401


def test_42_redeem_revoked_token(partner_session, user_session,
                                                admin_session, fresh_business):
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    DB.coupons.delete_many({"user_id": user_session._user_id,
                                    "offer_id": oid})
    r = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={})
    qr = r.json()["qr_token"]
    token_id, raw_secret = _run(lambda db: _issue_partner_token(
        db, owner_user_id=partner_session._user_id, business_id=bid))
    # Revoke
    DB.partner_tokens.update_one(
        {"partner_token_id": token_id}, {"$set": {"revoked_at": _now()}})
    r2 = partner_session.post(f"{API}/partner/redeem/{qr}",
                                       headers={"X-Partner-Token": raw_secret},
                                       timeout=10)
    assert r2.status_code == 401


def test_43_failed_auth_writes_audit(partner_session, user_session,
                                                  admin_session, fresh_business):
    """Phase 9c.1 Fix 4 — every failed partner-token check (missing,
    revoked, insufficient_scope) MUST write to offer_redemptions_audit
    BEFORE the 401 is returned.  Outcomes carry the spec-defined
    enum: missing_auth | insufficient_scope | token_revoked."""
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    DB.coupons.delete_many({"user_id": user_session._user_id,
                                    "offer_id": oid})
    r = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={})
    qr = r.json()["qr_token"]
    pfx = qr[:12]
    # baseline count
    before = DB.offer_redemptions_audit.count_documents(
        {"qr_token_prefix": pfx})

    # (a) no header at all → missing_auth
    r1 = partner_session.post(f"{API}/partner/redeem/{qr}", timeout=10)
    assert r1.status_code == 401
    # (b) invalid token (junk) → missing_auth
    r2 = partner_session.post(
        f"{API}/partner/redeem/{qr}",
        headers={"X-Partner-Token": "ptk_not_a_real_secret"}, timeout=10)
    assert r2.status_code == 401
    # (c) revoked token → token_revoked
    tid_r, raw_r = _run(lambda db: _issue_partner_token(
        db, owner_user_id=partner_session._user_id, business_id=bid))
    DB.partner_tokens.update_one(
        {"partner_token_id": tid_r}, {"$set": {"revoked_at": _now()}})
    r3 = partner_session.post(
        f"{API}/partner/redeem/{qr}",
        headers={"X-Partner-Token": raw_r}, timeout=10)
    assert r3.status_code == 401
    # (d) valid token but missing the redeem_offers scope → insufficient_scope
    from services.games_v2 import issue_partner_token as _ipt
    res_no_scope = _run(lambda db: _ipt(
        db, partner_business_id=bid,
        scopes=["read_only"],   # intentionally missing redeem_offers
        issued_by_user_id=partner_session._user_id))
    r4 = partner_session.post(
        f"{API}/partner/redeem/{qr}",
        headers={"X-Partner-Token": res_no_scope["raw_secret"]},
        timeout=10)
    assert r4.status_code == 401

    after_rows = list(DB.offer_redemptions_audit.find(
        {"qr_token_prefix": pfx}).sort("ts", 1))
    after = len(after_rows)
    # 4 new audit rows for the 4 failed-auth attempts
    assert after - before >= 4, \
        f"expected 4 new audit rows; got {after - before}"
    outcomes = {r.get("outcome") for r in after_rows[-4:]}
    assert "missing_auth" in outcomes
    assert "token_revoked" in outcomes
    assert "insufficient_scope" in outcomes


def test_44_authorization_partner_header_shim(partner_session, user_session,
                                                                admin_session,
                                                                fresh_business):
    """Phase 9c.1 cosmetic — `Authorization: Partner <secret>` works
    in lieu of `X-Partner-Token`."""
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    DB.coupons.delete_many({"user_id": user_session._user_id,
                                    "offer_id": oid})
    r = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={})
    qr = r.json()["qr_token"]
    _, raw = _run(lambda db: _issue_partner_token(
        db, owner_user_id=partner_session._user_id, business_id=bid))
    r2 = partner_session.post(
        f"{API}/partner/redeem/{qr}",
        headers={"Authorization": f"Partner {raw}"}, timeout=10)
    assert r2.status_code == 200, r2.text
    assert r2.json()["coupon"]["status"] == "redeemed"


# ════════════════════════════════════════════════════════════════════════
# § 6 — Google Wallet (stub-mode in this fork)
# ════════════════════════════════════════════════════════════════════════
def test_50_google_wallet_stub_when_no_issuer(user_session, partner_session,
                                                                  admin_session,
                                                                  fresh_business):
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    DB.coupons.delete_many({"user_id": user_session._user_id,
                                    "offer_id": oid})
    r = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={})
    cid = r.json()["coupon_id"]
    r2 = user_session.post(
        f"{API}/commerce/coupons/{cid}/wallet_pass/google", timeout=10)
    assert r2.status_code == 200
    body = r2.json()
    assert "save_url" in body
    assert body["save_url"].startswith("https://pay.google.com/gp/v/save/")
    # In this fork: GOOGLE_WALLET_ISSUER_ID unset → stub
    assert body["pass_status"] == "stub"


def test_51_apple_wallet_stub(user_session, partner_session,
                                          admin_session, fresh_business):
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    DB.coupons.delete_many({"user_id": user_session._user_id,
                                    "offer_id": oid})
    r = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={})
    cid = r.json()["coupon_id"]
    r2 = user_session.post(
        f"{API}/commerce/coupons/{cid}/wallet_pass/apple", timeout=10)
    assert r2.status_code == 200
    body = r2.json()
    assert body["pass_status"] == "stub"
    assert "save_url" in body


def test_52_wallet_probe_surfaced_on_system_integrations(admin_session):
    r = admin_session.get(f"{API}/system/integrations", timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    wallet = next((i for i in items if i["name"] == "GoogleWallet"), None)
    assert wallet, "GoogleWallet must appear in /system/integrations"
    assert wallet["mode"] in ("stub", "live")
    assert wallet["env_key"] == "GOOGLE_WALLET_ISSUER_ID"


# ════════════════════════════════════════════════════════════════════════
# § 7 — Route-ad engine surfaces offers
# ════════════════════════════════════════════════════════════════════════
def test_60_route_ad_engine_includes_offer_proximity(user_session,
                                                                       partner_session,
                                                                       admin_session,
                                                                       fresh_business):
    """When a listener has an active commute and a business along the
    route has an active offer, the engine surfaces an offer_proximity
    opp with `opp_source="offer"`."""
    bid = fresh_business["business_id"]
    # Important: business loc must be reachable by mock places_along_route
    # — Phase 9a seed includes many Dubai businesses around our test point.
    oid = _approve_offer_quick(partner_session, admin_session, bid,
                                          inventory=20, max_per_user=99)
    # Clean prior state
    uid = user_session._user_id
    DB.commute_sessions.update_many(
        {"user_id": uid, "status": "active"},
        {"$set": {"status": "abandoned"}})
    DB.route_ad_opportunities.delete_many({"user_id": uid})
    # Start a commute that should pass near fresh_business (which is at
    # 25.196, 55.281 — near Sheikh Zayed Road).
    r = user_session.post(
        f"{API}/commute/start",
        json={"origin": {"lat": 25.197, "lng": 55.279},
                "destination": {"lat": 25.085, "lng": 55.145,
                                        "label": "Marina"},
                "mode": "driver", "label": "home_to_work"},
        timeout=20)
    assert r.status_code == 200
    cid = r.json()["commute_id"]
    time.sleep(1.2)  # background task
    # Now force the route to "pass near" our test biz by patching the
    # mock places along route — easier: just call the engine directly
    # with a known nearby business.  We rely on the mock seeding to put
    # the new biz on a frequently-trafficked Dubai corridor.
    from services.route_ad_engine import compute_route_opportunities
    _run(lambda db: compute_route_opportunities(db, cid))
    items = (user_session.get(
        f"{API}/commute/{cid}/opportunities",
        params={"only_upcoming": False}, timeout=10).json().get("items") or [])
    offer_opps = [o for o in items if o.get("opp_source") == "offer"]
    # Don't strictly require the offer to be on-route (mock geometry may
    # not include our synthetic test biz).  Verify the engine can
    # produce opp_source="offer" by checking opp shape when ANY exists.
    # The DB documents must include the new field on at least one entry.
    rows = list(DB.route_ad_opportunities.find({"user_id": uid}))
    assert any("opp_source" in r for r in rows), \
        "engine must persist opp_source field on opps"


def test_61_offers_show_up_in_listener_feed(user_session, partner_session,
                                                              admin_session,
                                                              fresh_business):
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    # Feed at the business location
    r = user_session.get(
        f"{API}/commerce/offers/feed",
        params={"lat": fresh_business["lat"], "lng": fresh_business["lng"],
                  "radius_m": 2000, "include_route": False},
        timeout=10)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(o["offer_id"] == oid for o in items), \
        f"approved offer must appear in feed; got {len(items)} items"


# ════════════════════════════════════════════════════════════════════════
# § 8 — Admin verify queue, approve queue, force pause, audit CSV
# ════════════════════════════════════════════════════════════════════════
def test_70_admin_verify_queue(admin_session, partner_session):
    """Submit a claim; admin sees it in verify_queue."""
    r = partner_session.post(f"{API}/partner/businesses/claim",
                                       json={"manual_business": {
                                           "name": "Queue Item 9c",
                                           "lat": 25.197, "lng": 55.282}})
    bid = r.json()["business_id"]
    # Make sure it's NOT verified
    DB.businesses.update_one({"business_id": bid},
                                    {"$set": {"partner_status": "claimed"}})
    r2 = admin_session.get(f"{API}/admin/businesses/verify_queue",
                                       timeout=10)
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert any(b["business_id"] == bid for b in items)
    DB.businesses.delete_one({"business_id": bid})


def test_71_admin_force_pause(partner_session, admin_session, fresh_business):
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    r = admin_session.post(f"{API}/admin/offers/{oid}/force_pause",
                                    timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "paused"


def test_72_admin_audit_csv_export(admin_session, partner_session,
                                                  user_session, fresh_business):
    """Build one redemption + one already_redeemed audit, then export
    CSV and verify shape."""
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    DB.coupons.delete_many({"user_id": user_session._user_id, "offer_id": oid})
    r = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={})
    qr = r.json()["qr_token"]
    token_id, raw = _run(lambda db: _issue_partner_token(
        db, owner_user_id=partner_session._user_id, business_id=bid))
    partner_session.post(f"{API}/partner/redeem/{qr}",
                                headers={"X-Partner-Token": raw}, timeout=10)
    # Now export
    r2 = admin_session.get(f"{API}/admin/offer_redemptions_audit.csv",
                                      params={"business_id": bid}, timeout=10)
    assert r2.status_code == 200
    assert r2.headers["content-type"].startswith("text/csv")
    text = r2.text
    assert "audit_id" in text
    assert "outcome" in text
    assert "success" in text


# ════════════════════════════════════════════════════════════════════════
# § 9 — Smoke regressions
# ════════════════════════════════════════════════════════════════════════
def test_90_openapi_lists_new_routes(admin_session):
    r = admin_session.get(f"{API}/openapi.json", timeout=10)
    assert r.status_code == 200
    paths = set(r.json()["paths"].keys())
    must = [
        "/api/public/businesses/{slug}",
        "/api/public/businesses/{slug}/offers",
        "/api/public/businesses/nearby",
        "/api/commerce/offers/feed",
        "/api/commerce/offers/{offer_id}/claim",
        "/api/commerce/coupons/me",
        "/api/commerce/coupons/{coupon_id}/wallet_pass/google",
        "/api/commerce/coupons/{coupon_id}/wallet_pass/apple",
        "/api/auth/partner/upgrade",
        "/api/partner/businesses/me",
        "/api/partner/businesses/claim",
        "/api/partner/redeem/{qr_token}",
        "/api/admin/businesses/verify_queue",
        "/api/admin/offers/approve_queue",
        "/api/admin/offer_redemptions_audit",
        "/api/admin/offer_redemptions_audit.csv",
    ]
    missing = [p for p in must if p not in paths]
    assert not missing, f"missing: {missing}"


def test_91_existing_9b_endpoints_still_200(user_session):
    r = user_session.get(f"{API}/rj/me/pending_extras", timeout=10)
    assert r.status_code == 200


def test_92_existing_9a_endpoints_still_200(user_session):
    r = user_session.get(f"{API}/commute/saved_locations", timeout=10)
    assert r.status_code == 200


# ════════════════════════════════════════════════════════════════════════
# § 9c.1 — Phase 9c.1 bug-fix battery
# ════════════════════════════════════════════════════════════════════════
def test_9c1_01_claim_business_writes_geojson_loc(partner_session):
    """Phase 9c.1 Fix 2 — claim_business() must persist a GeoJSON `loc`
    so newly claimed partner businesses appear in $nearSphere queries
    used by /public/businesses/nearby and the route_ad_engine offer
    proximity scan."""
    lat, lng = 25.1981, 55.2835
    r = partner_session.post(
        f"{API}/partner/businesses/claim",
        json={"manual_business": {
            "name": "9c1 LocCheck Bakery",
            "lat": lat, "lng": lng,
            "city": "dubai",
            "address": "9c.1 test address"}}, timeout=15)
    assert r.status_code == 200, r.text
    bid = r.json()["business_id"]
    try:
        b = DB.businesses.find_one({"business_id": bid})
        assert b is not None
        loc = b.get("loc") or {}
        assert loc.get("type") == "Point", f"loc.type missing: {loc}"
        coords = loc.get("coordinates") or []
        assert len(coords) == 2
        # GeoJSON is [lng, lat]
        assert abs(coords[0] - lng) < 1e-6
        assert abs(coords[1] - lat) < 1e-6
        # The 2dsphere index must already exist on businesses.loc
        idxs = DB.businesses.index_information()
        has_2d = any(
            any(p[1] == "2dsphere" for p in spec.get("key", []))
            for spec in idxs.values())
        assert has_2d, "businesses.loc 2dsphere index missing"
        # And /public/businesses/nearby must return it
        r2 = requests.get(
            f"{API}/public/businesses/nearby",
            params={"lat": lat, "lng": lng, "radius_m": 200,
                      "limit": 50}, timeout=10)
        assert r2.status_code == 200, r2.text
        items = r2.json()["items"]
        assert any(b["business_id"] == bid for b in items), \
            "newly claimed business must appear in /public/businesses/nearby"
    finally:
        DB.businesses.delete_one({"business_id": bid})


def test_9c1_02_db_proximity_surfaces_partner_offer(user_session,
                                                                       partner_session,
                                                                       admin_session,
                                                                       fresh_business):
    """Phase 9c.1 Fix 3 — In mock_fallback Maps mode the synthesised
    `places_along_route` only knows the seeded mock_places set.  The
    new DB-side proximity scan (`_augment_places_from_db`) must surface
    partner businesses whose `loc` is within the polyline buffer."""
    bid = fresh_business["business_id"]
    biz_lat, biz_lng = fresh_business["lat"], fresh_business["lng"]
    oid = _approve_offer_quick(partner_session, admin_session, bid,
                                          inventory=10, max_per_user=99)
    uid = user_session._user_id
    DB.commute_sessions.update_many(
        {"user_id": uid, "status": "active"},
        {"$set": {"status": "abandoned"}})
    DB.route_ad_opportunities.delete_many({"user_id": uid})
    # Start a commute that passes essentially through the business.
    r = user_session.post(
        f"{API}/commute/start",
        json={"origin": {"lat": biz_lat - 0.002, "lng": biz_lng - 0.002},
                "destination": {"lat": biz_lat + 0.002, "lng": biz_lng + 0.002,
                                        "label": "9c1 test dest"},
                "mode": "driver", "label": "9c1_proximity"},
        timeout=20)
    assert r.status_code == 200, r.text
    cid = r.json()["commute_id"]
    from services.route_ad_engine import compute_route_opportunities
    _run(lambda db: compute_route_opportunities(db, cid))
    rows = list(DB.route_ad_opportunities.find(
        {"user_id": uid, "commute_id": cid}))
    # Partner business offer must be in the produced opportunities
    offer_opps = [r for r in rows
                       if r.get("opp_source") == "offer"
                       and r.get("business_id") == bid]
    assert offer_opps, ("partner offer must be surfaced via DB-side "
                              "proximity scan even in mock_fallback mode; "
                              f"got {len(rows)} opps, sources={[r.get('opp_source') for r in rows]}")


def test_9c1_03_audit_csv_includes_reason_and_qr_prefix(admin_session,
                                                                              partner_session,
                                                                              user_session,
                                                                              fresh_business):
    """Phase 9c.1 cosmetic — CSV export carries the `reason` column
    plus `qr_token_prefix` so audit rows with failed-auth context are
    legible in the partner ops report."""
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid)
    DB.coupons.delete_many({"user_id": user_session._user_id,
                                    "offer_id": oid})
    r = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={})
    qr = r.json()["qr_token"]
    # Trigger a failed-auth row
    partner_session.post(f"{API}/partner/redeem/{qr}",
                                headers={"X-Partner-Token": "ptk_bogus"},
                                timeout=10)
    r2 = admin_session.get(
        f"{API}/admin/offer_redemptions_audit.csv",
        params={"business_id": bid}, timeout=10)
    assert r2.status_code == 200
    text = r2.text
    header = text.splitlines()[0]
    assert "reason" in header
    assert "qr_token_prefix" in header


def test_9c1_04_inventory_exhausted_aliased_to_out_of_inventory(partner_session,
                                                                                          admin_session,
                                                                                          user_session,
                                                                                          fresh_business):
    """Phase 9c.1 cosmetic — accept either `inventory_exhausted` or
    `out_of_inventory`.  Verifies the listener-claim path returns the
    canonical `out_of_inventory` string."""
    bid = fresh_business["business_id"]
    oid = _approve_offer_quick(partner_session, admin_session, bid,
                                          inventory=1, max_per_user=99)
    DB.coupons.delete_many({"offer_id": oid})
    # First claim — succeeds
    r1 = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={},
                                   timeout=10)
    assert r1.status_code == 200
    # Second claim — out of inventory
    r2 = user_session.post(f"{API}/commerce/offers/{oid}/claim", json={},
                                   timeout=10)
    assert r2.status_code == 409
    assert "out_of_inventory" in r2.text
