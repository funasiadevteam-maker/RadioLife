"""Phase 8c — Analytics + Leaderboard + Lead Forms + Webhooks + Compliance.

Covers:
  - Lead form CRUD; required_before_play gate; 24h dedupe; CSV
  - Webhook register; HMAC signature round-trip; test_ping live; retry backoff;
    max_retries_exceeded surfaces in admin queue
  - Leaderboard aggregation (plays / wins / saves / redemptions /
    completion_rate)
  - Compliance: submit_for_approval rejects with named missing fields;
    geo_not_eligible 451; age gating 403
  - Inventory reconcile: synthetic discrepancy detected; force_correct
    fixes + audit row
  - CSV exports: audit, analytics, leads
  - Smoke: 8a / 8b flows still green at the surface
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient


API = os.environ.get("PHASE7_API",
                       "https://mobile-games-v2.preview.emergentagent.com").rstrip("/") + "/api"
MONGO = os.environ.get("PHASE7_MONGO", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")


def _mongo():
    return AsyncIOMotorClient(MONGO)[DB_NAME]


def _run(coro):
    return asyncio.run(coro)


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.text}"
    s._user_id = r.json()["user_id"]
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def user_session():
    return _login("test@bigfm.dubai", "TestUser123!")


@pytest.fixture(scope="module")
def advertiser_session():
    return _login("advertiser@bigfm.dubai", "AdvertiserP8!23")


def _make_campaign(admin_session, template_id="tpl_scratch_card",
                       title="8c test campaign"):
    r = admin_session.post(f"{API}/games_v2/advertiser/campaigns",
                                  json={"template_id": template_id, "title": title,
                                          "open_to_all": True,
                                          "prizes": [{
                                              "prize_type": "bigcoin",
                                              "title": "5 BigCoin",
                                              "value_amount": 5,
                                              "probability_weight": 100,
                                              "inventory_total": 100,
                                              "redemption_method": "in_app_wallet",
                                          }],
                                          "compliance": {
                                              "terms_text": "Std terms",
                                              "odds_disclosure": "Odds vary",
                                              "no_purchase_necessary_text": "NPN",
                                          },
                                          "redemption_rules": {"expiration_days": 30}},
                                  timeout=15)
    assert r.status_code == 200, r.text
    cid = r.json()["campaign_id"]
    admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/submit_for_approval",
        timeout=15)
    admin_session.post(
        f"{API}/games_v2/admin/campaigns/{cid}/approve", timeout=15)
    return cid


# ════════════════════════════════════════════════════════════════════════
# § 1 — Lead capture forms
# ════════════════════════════════════════════════════════════════════════
def test_01_lead_form_crud(admin_session):
    cid = _make_campaign(admin_session, title="Lead Form CRUD")
    # Create
    payload = {
        "fields_json": [
            {"name": "email", "label": "Your email", "type": "email",
              "required": True},
            {"name": "phone", "label": "Mobile",     "type": "phone",
              "required": False},
            {"name": "city", "label": "City", "type": "select",
              "required": True, "options": ["Dubai", "Abu Dhabi", "Sharjah"]},
        ],
        "required_before_play": True,
        "consent_text": "We may email you with offers.",
        "consent_required": True,
        "submit_button_label": "Enter to win",
    }
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json=payload, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lead_form"]["form_id"]
    assert len(body["lead_form"]["fields_json"]) == 3
    # Get
    r = admin_session.get(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form", timeout=10)
    assert r.status_code == 200
    form = r.json()["lead_form"]
    assert form["required_before_play"] is True
    # Update (same endpoint, idempotent)
    payload["consent_text"] = "Updated consent"
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json=payload, timeout=10)
    assert r.status_code == 200
    assert r.json()["lead_form"]["consent_text"] == "Updated consent"
    # Delete
    r = admin_session.delete(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form", timeout=10)
    assert r.status_code == 200
    r = admin_session.get(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form", timeout=10)
    assert r.json()["lead_form"] is None


def test_02_lead_form_schema_rejects_bad_fields(admin_session):
    cid = _make_campaign(admin_session, title="Bad fields test")
    # No fields
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json={"fields_json": []}, timeout=10)
    assert r.status_code == 400
    assert "fields_required" in r.json()["detail"]
    # Invalid type
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json={"fields_json": [{"name": "x", "type": "bogus"}]}, timeout=10)
    assert r.status_code == 400
    # Select without options
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json={"fields_json": [{"name": "x", "type": "select", "required": True}]},
        timeout=10)
    assert r.status_code == 400


def test_03_lead_form_required_gate_blocks_start(admin_session, user_session):
    cid = _make_campaign(admin_session, title="Gate test campaign")
    admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json={"fields_json": [
            {"name": "email", "type": "email", "required": True}],
              "required_before_play": True,
              "consent_text": "Consent line",
              "consent_required": True},
        timeout=10)
    # Start without lead_id → 412
    r = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                 json={}, timeout=15)
    assert r.status_code == 412, f"got {r.status_code}: {r.text}"
    assert "lead_form_required" in r.json()["detail"]
    # Submit lead
    email = f"test+{uuid.uuid4().hex[:6]}@example.com"
    r = user_session.post(f"{API}/games_v2/campaigns/{cid}/submit_lead",
                                 json={"form_data": {"email": email},
                                         "consent_accepted": True}, timeout=10)
    assert r.status_code == 200, r.text
    lead_id = r.json()["lead_id"]
    # Now start should succeed (server finds the valid lead within 24h)
    r = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                 json={"lead_id": lead_id}, timeout=15)
    assert r.status_code == 200, r.text


def test_04_lead_24h_dedupe(admin_session, user_session):
    cid = _make_campaign(admin_session, title="Dedupe test")
    admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json={"fields_json": [{"name": "email", "type": "email", "required": True}],
              "required_before_play": True, "consent_required": False},
        timeout=10)
    email = f"dedup+{uuid.uuid4().hex[:6]}@example.com"
    r1 = user_session.post(f"{API}/games_v2/campaigns/{cid}/submit_lead",
                                  json={"form_data": {"email": email}},
                                  timeout=10).json()
    r2 = user_session.post(f"{API}/games_v2/campaigns/{cid}/submit_lead",
                                  json={"form_data": {"email": email}},
                                  timeout=10).json()
    assert r1["lead_id"] == r2["lead_id"]


def test_05_lead_validation_rejects_bad_email(admin_session, user_session):
    cid = _make_campaign(admin_session, title="Email validation")
    admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json={"fields_json": [{"name": "email", "type": "email", "required": True}],
              "consent_required": False},
        timeout=10)
    r = user_session.post(f"{API}/games_v2/campaigns/{cid}/submit_lead",
                                 json={"form_data": {"email": "not-an-email"}},
                                 timeout=10)
    assert r.status_code == 400
    assert "invalid_email" in r.json()["detail"]


def test_06_leads_list_and_csv(admin_session, user_session):
    cid = _make_campaign(admin_session, title="List + CSV")
    admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json={"fields_json": [
            {"name": "email", "type": "email", "required": True},
            {"name": "name", "type": "text", "required": False}],
              "required_before_play": False, "consent_required": False},
        timeout=10)
    user_session.post(f"{API}/games_v2/campaigns/{cid}/submit_lead",
                            json={"form_data": {"email": "a@x.com", "name": "A"}},
                            timeout=10)
    # List
    r = admin_session.get(
        f"{API}/games_v2/advertiser/campaigns/{cid}/leads", timeout=10)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(it["form_data"].get("email") == "a@x.com" for it in items)
    # CSV
    r = admin_session.get(
        f"{API}/games_v2/advertiser/campaigns/{cid}/leads.csv", timeout=10)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert any(row.get("email") == "a@x.com" for row in rows)
    assert "submission_id" in rows[0]


# ════════════════════════════════════════════════════════════════════════
# § 2 — Webhook delivery
# ════════════════════════════════════════════════════════════════════════
def test_10_webhook_register_and_list(advertiser_session):
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks",
        json={"url": "https://example.test/hook-list",
                "events_subscribed": ["lead_submitted", "game_completed"]},
        timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["raw_secret"].startswith("whk_")
    assert body["endpoint_id"].startswith("whep_")
    # List
    r = advertiser_session.get(f"{API}/games_v2/advertiser/webhooks", timeout=10)
    assert r.status_code == 200
    found = [e for e in r.json()["items"]
                if e["endpoint_id"] == body["endpoint_id"]]
    assert found
    # No raw_secret leaked
    for e in r.json()["items"]:
        assert "raw_secret" not in e
        assert "signing_secret_plain" not in e
        assert "signing_secret_hash" not in e


def test_11_webhook_register_validates_url(advertiser_session):
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks",
        json={"url": "ftp://bad.url", "events_subscribed": ["lead_submitted"]},
        timeout=10)
    assert r.status_code == 400
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks",
        json={"url": "https://x.test", "events_subscribed": ["totally_made_up"]},
        timeout=10)
    assert r.status_code == 400


def test_12_webhook_signature_round_trip():
    from services.games_v2_webhooks import sign_payload, verify_signature
    secret = "whk_test_secret_xyz"
    ts = 1700000000
    body = '{"hello":"world"}'
    sig = sign_payload(secret, ts, body)
    assert verify_signature(secret, ts, body, f"sha256={sig}")
    assert not verify_signature(secret, ts, body, "sha256=deadbeef")
    # Tampered body fails
    assert not verify_signature(secret, ts, '{"hello":"hacker"}',
                                          f"sha256={sig}")


def test_13_webhook_test_ping_delivers(advertiser_session):
    """test_ping fires a single attempt; we use a httpbin echo endpoint
    so we get a real 200 back."""
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks",
        json={"url": "https://httpbin.org/anything",
                "events_subscribed": ["test_ping"]},
        timeout=10).json()
    eid = r["endpoint_id"]
    secret = r["raw_secret"]
    # Fire test_ping
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks/{eid}/test", timeout=20)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["delivery_result"]["success"] is True
    assert out["delivery_result"]["status_code"] == 200
    # Inspect deliveries
    r = advertiser_session.get(
        f"{API}/games_v2/advertiser/webhooks/{eid}/deliveries", timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["status"] == "sent"
    assert items[0]["event_type"] == "test_ping"
    assert items[0]["last_response_code"] == 200


def test_14_webhook_failed_retries_with_backoff(advertiser_session):
    """We register a deliberately unreachable URL, fire a test_ping, and
    verify the row goes to status=failed with next_retry_at ~10s out."""
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks",
        json={"url": "https://0.0.0.0:1/never-listens",
                "events_subscribed": ["test_ping"]},
        timeout=10).json()
    eid = r["endpoint_id"]
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks/{eid}/test", timeout=15).json()
    wev = r["webhook_event_id"]
    # Fetch the row to check next_retry_at
    async def fetch():
        db = _mongo()
        return await db.game_webhook_events.find_one({"webhook_event_id": wev})
    ev = _run(fetch())
    assert ev["status"] == "failed"
    assert ev["attempts"] == 1
    delta = (ev["next_retry_at"] - ev["last_attempt_at"]).total_seconds()
    # First backoff = 10s ± wiggle
    assert 5 <= delta <= 15, f"expected ~10s backoff, got {delta}"


def test_15_webhook_max_retries_exceeded(advertiser_session):
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks",
        json={"url": "https://0.0.0.0:1/never-listens",
                "events_subscribed": ["test_ping"]},
        timeout=10).json()
    eid = r["endpoint_id"]
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks/{eid}/test", timeout=15).json()
    wev = r["webhook_event_id"]
    # Force 4 more failures via direct deliver_one calls (skip the
    # background scheduler)
    from services.games_v2_webhooks import deliver_one
    async def force_fail():
        db = _mongo()
        for _ in range(4):
            await db.game_webhook_events.update_one(
                {"webhook_event_id": wev}, {"$set": {"next_retry_at": _now_utc()}})
            await deliver_one(db, wev)
        return await db.game_webhook_events.find_one({"webhook_event_id": wev})
    ev = _run(force_fail())
    assert ev["status"] == "max_retries_exceeded", \
            f"status={ev['status']} attempts={ev['attempts']}"
    assert ev["attempts"] == 5
    # Surfaces in admin queue
    r = advertiser_session.get(
        f"{API}/games_v2/advertiser/webhooks/{eid}/deliveries", timeout=10)
    items = r.json()["items"]
    assert any(it["status"] == "max_retries_exceeded" for it in items)


def _now_utc():
    return datetime.now(timezone.utc)


def test_16_webhook_rotate_and_delete(advertiser_session):
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks",
        json={"url": "https://example.test/rotate",
                "events_subscribed": ["test_ping"]},
        timeout=10).json()
    eid = r["endpoint_id"]
    original_secret = r["raw_secret"]
    # Rotate
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks/{eid}/rotate_secret", timeout=10).json()
    assert r["raw_secret"] != original_secret
    assert r["raw_secret"].startswith("whk_")
    # Delete
    r = advertiser_session.delete(
        f"{API}/games_v2/advertiser/webhooks/{eid}", timeout=10)
    assert r.status_code == 200


# ════════════════════════════════════════════════════════════════════════
# § 4 — Leaderboard
# ════════════════════════════════════════════════════════════════════════
def test_30_leaderboard_admin_plays(admin_session, user_session):
    """Seed plays on a fresh campaign, then assert the advertiser
    leaderboard returns a non-empty ranked list including campaigns the
    admin's advertiser owns."""
    cid = _make_campaign(admin_session, title="Leaderboard test")
    # Play once
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                 json={}, timeout=15)
    assert s.status_code == 200, s.text
    sid = s.json()["session_id"]
    user_session.post(
        f"{API}/games_v2/sessions/{sid}/submit", json={}, timeout=15)
    r = admin_session.get(
        f"{API}/games_v2/advertiser/leaderboard",
        params={"metric": "plays", "window": "24h", "limit": 50}, timeout=10)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    # At least the leaderboard returns rows (could be top-50 of admin's
    # owned campaigns); confirm structure.
    assert items, "expected at least one campaign in 24h plays leaderboard"
    for it in items[:3]:
        for k in ("rank", "campaign_id", "title", "value"):
            assert k in it
        assert isinstance(it["value"], (int, float))


def test_31_leaderboard_invalid_metric(admin_session):
    r = admin_session.get(f"{API}/games_v2/admin/leaderboard",
                                 params={"metric": "bogus"}, timeout=10)
    assert r.status_code == 422
    assert "metric must be one of" in r.json()["detail"]


def test_32_leaderboard_completion_rate(admin_session):
    r = admin_session.get(
        f"{API}/games_v2/admin/leaderboard",
        params={"metric": "completion_rate", "window": "30d"}, timeout=10)
    assert r.status_code == 200
    for it in r.json()["items"]:
        assert 0.0 <= it["value"] <= 1.0


def test_33_leaderboard_advertiser_scope(advertiser_session):
    r = advertiser_session.get(f"{API}/games_v2/advertiser/leaderboard",
                                         params={"metric": "plays"}, timeout=10)
    assert r.status_code == 200


# ════════════════════════════════════════════════════════════════════════
# § 5 — Compliance hardening
# ════════════════════════════════════════════════════════════════════════
def test_40_compliance_blocks_missing_terms(admin_session):
    # Create a sweepstakes-prize campaign with empty compliance.
    # Single gift_card prize at weight 100 to satisfy spin_wheel weight=100 sum.
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns",
        json={"template_id": "tpl_scratch_card",
                "title": "Missing-compliance sweepstakes",
                "open_to_all": True,
                "prizes": [
                    {"prize_type": "gift_card", "title": "$10 gift card",
                      "value_amount": 10,
                      "probability_weight": 100,
                      "inventory_total": 20,
                      "redemption_method": "in_app_wallet"},
                ],
                "compliance": {},   # ← intentionally empty
                "redemption_rules": {"expiration_days": 30}},
        timeout=15).json()
    cid = r["campaign_id"]
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/submit_for_approval",
        timeout=10)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "compliance_missing" in detail
    # All three sweepstakes-relevant fields named
    assert "terms_text" in detail
    assert "odds_disclosure" in detail
    assert "no_purchase_necessary_text" in detail


def test_41_compliance_passes_with_all_fields(admin_session):
    cid = _make_campaign(admin_session, title="Clean compliance")
    # Already submitted+approved via helper; positive smoke via the
    # advertiser campaign-detail endpoint (admin owns adv_karak_cafe in
    # this test environment)
    r = admin_session.get(
        f"{API}/games_v2/advertiser/campaigns/{cid}", timeout=10)
    assert r.status_code == 200
    body = r.json()
    # The endpoint wraps in {"campaign": {...}}
    camp = body.get("campaign") or body
    assert camp.get("status") in ("active", "approved")


def test_42_geo_not_eligible(admin_session, user_session):
    cid = _make_campaign(admin_session, title="Geo test")
    # Patch the campaign's compliance to restrict to AQ only (Antarctica)
    async def restrict():
        db = _mongo()
        await db.game_compliance_settings.update_one(
            {"campaign_id": cid},
            {"$set": {"geo_restrictions_json": {"allowed_countries": ["AQ"]}}},
            upsert=True)
    _run(restrict())
    from services.games_v2_compliance import check_geo_eligibility
    # Direct unit assertion against a known-public IPv4
    with pytest.raises(ValueError, match="geo_not_eligible"):
        check_geo_eligibility(
            {"geo_restrictions_json": {"allowed_countries": ["AQ"]}},
            "8.8.8.8")   # Google DNS → US
    # And reachable via the listener start endpoint (route uses the
    # request client IP; in this test environment that's a private IP,
    # which our permissive fallback allows.  We still assert the unit
    # path works above.)


def test_43_age_gate_blocks_without_confirmation(admin_session):
    from services.games_v2_compliance import check_age_eligibility
    with pytest.raises(ValueError, match="age_not_confirmed"):
        check_age_eligibility({"age_restriction": "21"}, None, False)
    # Confirmed but under-age
    with pytest.raises(ValueError, match="age_below_minimum"):
        check_age_eligibility({"age_restriction": "21"}, 18, True)
    # Confirmed + adult passes
    check_age_eligibility({"age_restriction": "21"}, 30, True)


# ════════════════════════════════════════════════════════════════════════
# § 6 — Inventory ledger reconciliation
# ════════════════════════════════════════════════════════════════════════
def test_50_inventory_reconcile_clean(admin_session):
    cid = _make_campaign(admin_session, title="Clean inventory")
    r = admin_session.get(
        f"{API}/games_v2/admin/inventory_reconcile/{cid}", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["clean"] is True


def test_51_inventory_reconcile_detects_drift(admin_session):
    cid = _make_campaign(admin_session, title="Drift inventory")
    # Inject a synthetic discrepancy by directly mutating inventory_remaining
    async def break_it():
        db = _mongo()
        prizes = await db.game_prizes.find(
            {"campaign_id": cid}).to_list(10)
        for p in prizes:
            await db.game_prizes.update_one(
                {"prize_id": p["prize_id"]},
                {"$set": {"inventory_remaining": p["inventory_total"] - 50}})
    _run(break_it())
    r = admin_session.get(
        f"{API}/games_v2/admin/inventory_reconcile/{cid}", timeout=10)
    body = r.json()
    assert body["clean"] is False
    assert body["discrepancies"]


def test_52_inventory_force_correct(admin_session):
    cid = _make_campaign(admin_session, title="Force correct test")
    async def break_it():
        db = _mongo()
        p = await db.game_prizes.find_one({"campaign_id": cid})
        await db.game_prizes.update_one(
            {"prize_id": p["prize_id"]},
            {"$set": {"inventory_remaining": 1}})  # massively under-counted
        return p["prize_id"], p["inventory_total"]
    pid, total = _run(break_it())
    r = admin_session.post(
        f"{API}/games_v2/admin/inventory_reconcile/{cid}/force_correct",
        timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["corrected"] >= 1
    # Verify audit row written
    async def verify():
        db = _mongo()
        aud = await db.game_inventory_ledger.find_one(
            {"prize_id": pid, "action": "admin_correction"})
        prize = await db.game_prizes.find_one({"prize_id": pid})
        return aud, prize
    aud, prize = _run(verify())
    assert aud is not None
    assert aud["reason"] == "admin_correction"
    assert prize["inventory_remaining"] == total


def test_53_inventory_daily_scan(admin_session):
    # Break a campaign, run scan, verify alert
    cid = _make_campaign(admin_session, title="Daily scan target")
    async def break_it():
        db = _mongo()
        p = await db.game_prizes.find_one({"campaign_id": cid})
        await db.game_prizes.update_one(
            {"prize_id": p["prize_id"]},
            {"$set": {"inventory_remaining": p["inventory_total"] - 7}})
    _run(break_it())
    r = admin_session.post(
        f"{API}/games_v2/admin/inventory_reconcile/run_daily_scan",
        timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert body["alerts_generated"] >= 1
    # Alert visible
    r = admin_session.get(
        f"{API}/games_v2/admin/inventory_reconcile_alerts", timeout=10)
    items = r.json()["items"]
    assert any(it["campaign_id"] == cid for it in items)


# ════════════════════════════════════════════════════════════════════════
# § 7 — CSV exports
# ════════════════════════════════════════════════════════════════════════
def test_60_audit_csv_well_formed(admin_session):
    r = admin_session.get(
        f"{API}/games_v2/admin/redemption_audit_log.csv?limit=10",
        timeout=10)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    text = r.text
    reader = csv.DictReader(io.StringIO(text))
    assert reader.fieldnames is not None
    for col in ("audit_id", "ts", "outcome", "partner_token_id",
                  "campaign_id", "wallet_item_id", "qr_token_prefix"):
        assert col in reader.fieldnames, f"missing column: {col}"


def test_61_analytics_csv_well_formed(admin_session):
    cid = _make_campaign(admin_session, title="Analytics CSV")
    r = admin_session.get(
        f"{API}/games_v2/advertiser/campaigns/{cid}/analytics.csv",
        timeout=10)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    reader = csv.DictReader(io.StringIO(r.text))
    for col in ("event_id", "ts", "event_type", "campaign_id"):
        assert col in reader.fieldnames


# ════════════════════════════════════════════════════════════════════════
# § 8 — Smoke regressions
# ════════════════════════════════════════════════════════════════════════
def test_90_smoke_existing_play_and_win(user_session):
    r = user_session.get(f"{API}/games_v2/play_and_win", timeout=10)
    assert r.status_code == 200
    assert "unlocked_for_you" in r.json()


def test_91_smoke_openapi_lists_8c_routes():
    r = requests.get(f"{API}/openapi.json", timeout=10)
    paths = list(r.json()["paths"].keys())
    must = [
        "/api/games_v2/advertiser/campaigns/{campaign_id}/lead_form",
        "/api/games_v2/advertiser/campaigns/{campaign_id}/leads",
        "/api/games_v2/advertiser/campaigns/{campaign_id}/leads.csv",
        "/api/games_v2/campaigns/{campaign_id}/submit_lead",
        "/api/games_v2/advertiser/webhooks",
        "/api/games_v2/advertiser/webhooks/{endpoint_id}/test",
        "/api/games_v2/advertiser/leaderboard",
        "/api/games_v2/admin/leaderboard",
        "/api/games_v2/admin/inventory_reconcile/{campaign_id}",
        "/api/games_v2/admin/inventory_reconcile/{campaign_id}/force_correct",
        "/api/games_v2/admin/redemption_audit_log.csv",
        "/api/games_v2/advertiser/campaigns/{campaign_id}/analytics.csv",
        "/api/games_v2/admin/webhooks/run_delivery_sweep",
    ]
    missing = [m for m in must if m not in paths]
    assert not missing, f"missing 8c routes: {missing}"


# ════════════════════════════════════════════════════════════════════════
# § 9 — Phase 8c.1 — XFF geo, strict bodies, webhook sweep, leaderboard polish
# ════════════════════════════════════════════════════════════════════════
def test_100_client_ip_resolves_xff():
    """Unit: get_real_client_ip prefers left-most public IP from XFF."""
    from services.client_ip import get_real_client_ip

    def _mk(headers, host):
        class _C:
            pass
        c = _C()
        c.host = host

        class _R:
            pass
        r = _R()
        r.headers = headers
        r.client = c
        return r

    # XFF with public + private → returns public
    assert get_real_client_ip(
        _mk({"x-forwarded-for": "8.8.8.8, 10.0.0.1"}, "127.0.0.1")) == "8.8.8.8"
    # XFF with only private → falls through to direct
    assert get_real_client_ip(
        _mk({"x-forwarded-for": "10.0.0.1, 172.20.0.5"},
              "1.1.1.1")) == "1.1.1.1"
    # X-Real-IP fallback
    assert get_real_client_ip(
        _mk({"x-real-ip": "9.9.9.9"}, "10.0.0.1")) == "9.9.9.9"
    # Nothing forwarded → direct
    assert get_real_client_ip(_mk({}, "8.8.4.4")) == "8.8.4.4"


def test_101_geo_eligibility_matrix():
    """check_geo_eligibility 3-state matrix: public match / public mismatch /
    private degraded."""
    from services.games_v2_compliance import check_geo_eligibility
    comp = {"geo_restrictions_json": {"allowed_countries": ["US"]}}
    # 1) US public IP passes
    check_geo_eligibility(comp, "8.8.8.8")
    # 2) Non-US public IP raises geo_not_eligible
    with pytest.raises(ValueError, match="geo_not_eligible"):
        check_geo_eligibility(comp, "1.1.1.1")
    # 3) Private IP falls through with a WARN (no raise)
    check_geo_eligibility(comp, "10.0.0.1")


def test_102_geo_gate_via_xff(admin_session, user_session):
    """Integration: hit /start with X-Forwarded-For for a US-only campaign.
    1.1.1.1 (Cloudflare AU/global) → 451; 8.8.8.8 (Google US) → 200."""
    cid = _make_campaign(admin_session, title="US-only geo test")
    # Restrict to US
    async def restrict():
        db = _mongo()
        await db.game_compliance_settings.update_one(
            {"campaign_id": cid},
            {"$set": {"geo_restrictions_json": {"allowed_countries": ["US"]}}},
            upsert=True)
    _run(restrict())
    # AU (non-US) → 451
    r_au = user_session.post(
        f"{API}/games_v2/campaigns/{cid}/start", json={},
        headers={"X-Forwarded-For": "1.1.1.1"}, timeout=15)
    assert r_au.status_code == 451, f"AU got {r_au.status_code}: {r_au.text}"
    assert r_au.json()["detail"] == "geo_not_eligible"
    # US → 200
    r_us = user_session.post(
        f"{API}/games_v2/campaigns/{cid}/start", json={},
        headers={"X-Forwarded-For": "8.8.8.8"}, timeout=15)
    assert r_us.status_code == 200, f"US got {r_us.status_code}: {r_us.text}"


def test_110_lead_form_rejects_unknown_field(admin_session):
    cid = _make_campaign(admin_session, title="Strict body lead_form")
    # Unknown top-level field
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json={"fields_json": [
                {"name": "email", "type": "email", "required": True}],
                "what_is_this": "drop me"}, timeout=10)
    assert r.status_code == 400
    assert "unknown_fields" in r.json()["detail"]
    assert "what_is_this" in r.json()["detail"]


def test_111_lead_form_accepts_alias_fields(admin_session):
    cid = _make_campaign(admin_session, title="Alias-friendly lead_form")
    # `fields` should be auto-aliased to `fields_json`
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/lead_form",
        json={"fields": [
                {"name": "email", "type": "email", "required": True}]},
        timeout=10)
    assert r.status_code == 200, r.text
    form = r.json()["lead_form"]
    assert form["fields_json"][0]["name"] == "email"


def test_112_campaign_create_rejects_unknown_field(admin_session):
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns",
        json={"template_id": "tpl_scratch_card",
                "title": "Strict body test",
                "open_to_all": True,
                "prizes": [{"prize_type": "bigcoin", "title": "1 BC",
                              "value_amount": 1, "probability_weight": 100,
                              "inventory_total": 10,
                              "redemption_method": "in_app_wallet"}],
                "redemption_rules": {"expiration_days": 30},
                "compliance": {"terms_text": "Std", "odds_disclosure": "Odds",
                                  "no_purchase_necessary_text": "NPN"},
                "garbage_field": "drop me",
                "another_one":   42}, timeout=15)
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "unknown_fields" in detail
    assert "garbage_field" in detail
    assert "another_one" in detail


def test_113_campaign_create_lifts_compliance_aliases(admin_session):
    """Top-level `terms_text` etc. should be lifted into `compliance` block."""
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns",
        json={"template_id": "tpl_scratch_card",
                "title": "Alias-lifted compliance",
                "open_to_all": True,
                "prizes": [{"prize_type": "bigcoin", "title": "1 BC",
                              "value_amount": 1, "probability_weight": 100,
                              "inventory_total": 10,
                              "redemption_method": "in_app_wallet"}],
                "redemption_rules": {"expiration_days": 30},
                # ← top-level aliases (should be lifted server-side):
                "terms_text": "Top-level terms",
                "odds_disclosure": "Top-level odds",
                "no_purchase_necessary_text": "Top-level NPN"},
        timeout=15)
    assert r.status_code == 200, r.text
    cid = r.json()["campaign_id"]
    # submit_for_approval should pass since compliance was lifted
    r = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/submit_for_approval",
        timeout=15)
    assert r.status_code == 200, r.text


def test_120_webhook_sweep_with_as_of(advertiser_session, admin_session):
    """Register an unreachable endpoint, fire test_ping (one attempt
    already failed), then admin sweeps with as_of in the far future to
    fast-forward through all 5 retries → max_retries_exceeded.

    We isolate to JUST this test's event by patching `next_retry_at` to
    the far future *only* on this row, and then call deliver_one
    repeatedly via the sweep.  Avoids the sweep iterating over hundreds
    of prior unrelated failing events left behind by other tests."""
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks",
        json={"url": "https://0.0.0.0:1/never-listens",
                "events_subscribed": ["test_ping"]}, timeout=10).json()
    eid = r["endpoint_id"]
    fired = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks/{eid}/test", timeout=15).json()
    wev = fired["webhook_event_id"]
    # Mark all OTHER pending failed events as 'sent' so the sweep is fast.
    async def isolate():
        db = _mongo()
        await db.game_webhook_events.update_many(
            {"webhook_event_id": {"$ne": wev}, "status": "failed"},
            {"$set": {"status": "max_retries_exceeded",
                       "next_retry_at": None}})
    _run(isolate())
    far_future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    for _ in range(6):     # safety upper bound
        r = admin_session.post(
            f"{API}/games_v2/admin/webhooks/run_delivery_sweep",
            json={"as_of": far_future}, timeout=60)
        assert r.status_code == 200, r.text
        async def fetch():
            db = _mongo()
            return await db.game_webhook_events.find_one({"webhook_event_id": wev})
        ev = _run(fetch())
        if ev["status"] == "max_retries_exceeded":
            break
    assert ev["status"] == "max_retries_exceeded", \
            f"status={ev['status']} attempts={ev['attempts']}"
    assert ev["attempts"] == 5


def test_121_webhook_sweep_admin_only():
    r = requests.post(f"{API}/games_v2/admin/webhooks/run_delivery_sweep",
                            json={}, timeout=10)
    assert r.status_code in (401, 403)


def test_130_leaderboard_full_counter_set(admin_session, user_session):
    cid = _make_campaign(admin_session, title="Counter-set leaderboard test")
    # Drive a play
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                 json={}, timeout=15).json()
    user_session.post(
        f"{API}/games_v2/sessions/{s['session_id']}/submit",
        json={}, timeout=15)
    # Fetch the leaderboard and verify EVERY row carries the full counter set
    r = admin_session.get(
        f"{API}/games_v2/admin/leaderboard?metric=plays&window=24h&limit=10",
        timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "expected leaderboard rows"
    for it in items:
        for k in ("rank", "campaign_id", "title", "sponsor_name",
                    "metric", "window", "value", "plays", "wins", "saves",
                    "redemptions", "completion_rate", "brand_color"):
            assert k in it, f"missing field '{k}' in leaderboard row: {it}"
        # No nulls in counters
        for ck in ("plays", "wins", "saves", "redemptions"):
            assert isinstance(it[ck], int), f"{ck} is {type(it[ck])}"
        assert isinstance(it["completion_rate"], (int, float))
