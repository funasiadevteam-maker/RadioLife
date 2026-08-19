"""Iteration 96 — Partner API v1: LIVE Stripe hosted Checkout for
Sponsorships (trivia + rj_read) and Marketplace Promotions
(Promoted-rail + Category Spotlight).

Backend-only: verifies the LIVE path returns a real checkout.stripe.com
URL + session_id, the object flips to pending_payment, ownership is
scoped, submit-guard is enforced for trivia, and the SANDBOX path
activates instantly with no Stripe. The full PAID->ACTIVE round-trip
(which requires opening the Stripe hosted page) is covered by the
Playwright script under /app/backend/tests (separate from pytest)."""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/") + "/api/v1"

LIVE_KEY = "rlk_live_RI7fonLpLAzW.pL6e_b7Ok-f5FsNmSkyxwtLeWYWStHTCZsP0Kmqf6SM"
SANDBOX_KEY = "rlk_test_m55nJ-GmIviJ.0cKrGo5T3AKq_FLmZcqPvePDkLzhMdGIlQIB8T5an2Q"


def _h(k):
    return {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def live_advertiser():
    """Create (or fetch cached) an advertiser under the LIVE key."""
    r = requests.post(f"{BASE_URL}/advertisers", headers=_h(LIVE_KEY), json={
        "name": f"TEST_iter96_live_{uuid.uuid4().hex[:6]}",
        "contact_email": "test+iter96@example.com",
    })
    assert r.status_code == 201, r.text
    adv = r.json()["advertiser"]
    return adv["advertiser_id"]


@pytest.fixture(scope="module")
def sandbox_advertiser():
    r = requests.post(f"{BASE_URL}/advertisers", headers=_h(SANDBOX_KEY), json={
        "name": f"TEST_iter96_sbx_{uuid.uuid4().hex[:6]}",
        "contact_email": "test+iter96sbx@example.com",
    })
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["environment"].lower() == "sandbox"
    assert d["advertiser"]["status"] == "active"
    return d["advertiser"]["advertiser_id"]


# ── AUTH / SCOPE ────────────────────────────────────────────────────
class TestAuth:
    def test_no_bearer_returns_401(self):
        r = requests.get(f"{BASE_URL}/me")
        assert r.status_code == 401

    def test_bad_key_returns_401(self):
        r = requests.get(f"{BASE_URL}/me", headers=_h("rlk_test_bogus.bogus"))
        assert r.status_code == 401

    def test_live_key_has_all_scopes(self):
        r = requests.get(f"{BASE_URL}/me", headers=_h(LIVE_KEY))
        assert r.status_code == 200
        d = r.json()
        assert d["environment"].lower() == "live"
        assert "campaigns:write" in d["scopes"]
        assert "campaigns:read" in d["scopes"]
        assert "catalog:read" in d["scopes"]


# ── P0 TRIVIA (LIVE) ────────────────────────────────────────────────
class TestTriviaLive:
    def test_create_trivia_draft_and_checkout(self, live_advertiser):
        from datetime import datetime, timedelta, timezone
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=14)
        # Draft
        body = {
            "type": "trivia", "advertiser_id": live_advertiser,
            "sponsor_target_type": "any",
            "prize_pool": [{"rank": 1, "points_reward": 500, "currency": "usd"},
                           {"rank": 2, "points_reward": 125, "currency": "usd"}],
            "winner_selection": "top_n",
            "display_name": "TEST Trivia iter96", "tagline": "Play & win",
            "logo_url": "https://placehold.co/128",
            "start_at": start.isoformat(), "end_at": end.isoformat(),
        }
        r = requests.post(f"{BASE_URL}/sponsorships", headers=_h(LIVE_KEY), json=body)
        assert r.status_code == 201, r.text
        d = r.json()
        sp = d["sponsorship"]
        sid = sp.get("id") or sp.get("sponsorship_id")
        assert sid
        assert sp.get("status") in ("draft", "pending_payment"), sp
        pytest.trivia_sid = sid
        pytest.trivia_adv = live_advertiser

    def test_trivia_submit_returns_use_checkout(self):
        sid = pytest.trivia_sid
        adv = pytest.trivia_adv
        r = requests.post(
            f"{BASE_URL}/sponsorships/{sid}/submit",
            headers=_h(LIVE_KEY),
            params={"type": "trivia", "advertiser_id": adv})
        assert r.status_code == 409, r.text
        code = (r.json().get("detail") or {}).get("code")
        assert code == "use_checkout_endpoint"

    def test_trivia_checkout_returns_stripe_url(self):
        sid = pytest.trivia_sid
        adv = pytest.trivia_adv
        r = requests.post(
            f"{BASE_URL}/sponsorships/{sid}/checkout",
            headers=_h(LIVE_KEY),
            params={"type": "trivia", "advertiser_id": adv},
            json={})
        assert r.status_code == 200, r.text
        d = r.json()
        url = d.get("checkout_url")
        sess = d.get("session_id")
        assert url and "checkout.stripe.com" in url, d
        assert sess and sess.startswith("cs_test_"), d
        pytest.trivia_checkout_url = url
        pytest.trivia_session = sess
        # Sponsorship should now be pending_payment
        rr = requests.get(f"{BASE_URL}/sponsorships/{sid}",
                          headers=_h(LIVE_KEY),
                          params={"type": "trivia", "advertiser_id": adv})
        assert rr.status_code == 200
        assert rr.json()["sponsorship"].get("status") == "pending_payment"

    def test_trivia_checkout_status_pre_payment_not_paid(self):
        sid = pytest.trivia_sid
        adv = pytest.trivia_adv
        r = requests.get(
            f"{BASE_URL}/sponsorships/{sid}/checkout/status",
            headers=_h(LIVE_KEY),
            params={"type": "trivia", "advertiser_id": adv})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("paid") is not True


# ── P0 RJ READ (LIVE) ───────────────────────────────────────────────
class TestRjReadLive:
    def test_create_rj_draft(self, live_advertiser):
        from datetime import datetime, timedelta, timezone
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=14)
        body = {
            "type": "rj_read", "advertiser_id": live_advertiser,
            "persona_id": "persona_demo_rj_ava",
            "any_station": True,
            "disclosure_prefix": "Sponsored by",
            "plays_target": 10,
            "cost_per_play_cents": 5,
            "script_body": "auto",
            "product_name": "Acme Cola",
            "start_at": start.isoformat(), "end_at": end.isoformat(),
        }
        r = requests.post(f"{BASE_URL}/sponsorships", headers=_h(LIVE_KEY), json=body)
        assert r.status_code == 201, r.text
        sp = r.json()["sponsorship"]
        sid = sp.get("id") or sp.get("sponsored_read_id")
        assert sid, sp
        pytest.rj_sid = sid
        pytest.rj_adv = live_advertiser

    def test_rj_submit_moves_to_pending_moderation(self):
        sid = pytest.rj_sid
        adv = pytest.rj_adv
        script = ("Sponsored by Acme Cola. Crisp, refreshing — grab an "
                  "ice-cold Acme Cola today, only on RadioLife.")
        r = requests.post(
            f"{BASE_URL}/sponsorships/{sid}/submit",
            headers=_h(LIVE_KEY),
            params={"type": "rj_read", "advertiser_id": adv},
            json={"final_script": script})
        assert r.status_code == 200, r.text
        # Poll the state
        rr = requests.get(f"{BASE_URL}/sponsorships/{sid}",
                          headers=_h(LIVE_KEY),
                          params={"type": "rj_read", "advertiser_id": adv})
        assert rr.status_code == 200
        st = rr.json()["sponsorship"].get("status")
        assert st in ("pending_moderation", "approved", "ready"), st

    def test_rj_checkout_returns_stripe_url(self):
        sid = pytest.rj_sid
        adv = pytest.rj_adv
        r = requests.post(
            f"{BASE_URL}/sponsorships/{sid}/checkout",
            headers=_h(LIVE_KEY),
            params={"type": "rj_read", "advertiser_id": adv},
            json={})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("checkout_url", "").startswith("https://checkout.stripe.com"), d
        assert d.get("session_id", "").startswith("cs_test_"), d


# ── P1 MARKETPLACE CATALOG ───────────────────────────────────────────
class TestMarketplaceCatalog:
    def test_tiers(self):
        r = requests.get(f"{BASE_URL}/marketplace/promotion/tiers", headers=_h(LIVE_KEY))
        assert r.status_code == 200
        tiers = r.json().get("tiers") or []
        assert len(tiers) == 3, tiers

    def test_categories(self):
        r = requests.get(f"{BASE_URL}/marketplace/categories", headers=_h(LIVE_KEY))
        assert r.status_code == 200
        items = r.json().get("items") or []
        assert len(items) > 0
        assert any(c.get("key") == "restaurant" for c in items)

    def test_businesses(self):
        r = requests.get(f"{BASE_URL}/marketplace/businesses",
                         headers=_h(LIVE_KEY), params={"q": ""})
        assert r.status_code == 200
        items = r.json().get("items") or []
        assert len(items) > 0
        assert all("business_id" in b for b in items)


# ── P1 PROMOTED-RAIL (LIVE) ─────────────────────────────────────────
class TestPromotedRailLive:
    def test_promotion_checkout_returns_stripe_url(self):
        r = requests.post(f"{BASE_URL}/marketplace/promotion/checkout",
                          headers=_h(LIVE_KEY),
                          json={"business_id": "biz_demo_grill", "tier": "spotlight_7"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("checkout_url", "").startswith("https://checkout.stripe.com"), d
        assert d.get("session_id", "").startswith("cs_test_"), d
        assert d.get("promotion_id", "").startswith("promo_"), d
        pytest.promo_id = d["promotion_id"]
        # status should be pending_payment via status endpoint
        rr = requests.get(f"{BASE_URL}/marketplace/promotion/{d['promotion_id']}/status",
                          headers=_h(LIVE_KEY))
        assert rr.status_code == 200
        assert rr.json().get("status") == "pending_payment"

    def test_promotion_bad_tier(self):
        r = requests.post(f"{BASE_URL}/marketplace/promotion/checkout",
                          headers=_h(LIVE_KEY),
                          json={"business_id": "biz_demo_grill", "tier": "nope"})
        assert r.status_code == 400
        assert (r.json().get("detail") or {}).get("code") == "bad_tier"

    def test_promotion_unknown_business(self):
        r = requests.post(f"{BASE_URL}/marketplace/promotion/checkout",
                          headers=_h(LIVE_KEY),
                          json={"business_id": "biz_does_not_exist", "tier": "spotlight_7"})
        assert r.status_code == 404
        assert (r.json().get("detail") or {}).get("code") == "business_not_found"

    def test_promotion_unknown_id_404(self):
        # Ownership scoping: an unknown/foreign promotion_id must 404 for the caller.
        # NOTE: LIVE + SANDBOX keys share partner_id (same partner, two envs);
        # a truly-different partner would also 404 on the same code path.
        r = requests.get(f"{BASE_URL}/marketplace/promotion/promo_deadbeefxx/status",
                         headers=_h(LIVE_KEY))
        assert r.status_code == 404, r.text
        assert (r.json().get("detail") or {}).get("code") == "promotion_not_found"


# ── P1 CATEGORY SPOTLIGHT (LIVE) ────────────────────────────────────
class TestSpotlightLive:
    def test_spotlight_checkout_returns_stripe_url(self):
        r = requests.post(f"{BASE_URL}/marketplace/spotlight/checkout",
                          headers=_h(LIVE_KEY),
                          json={"business_id": "biz_demo_grill",
                                "category": "restaurant",
                                "bid_cents": 25, "amount_cents": 2000})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("checkout_url", "").startswith("https://checkout.stripe.com"), d
        assert d.get("session_id", "").startswith("cs_test_"), d
        assert d.get("bid_id", "").startswith("cbid_"), d
        pytest.spot_session = d["session_id"]
        pytest.spot_bid = d["bid_id"]

    def test_spotlight_status_pending(self):
        r = requests.get(
            f"{BASE_URL}/marketplace/spotlight/{pytest.spot_session}/status",
            headers=_h(LIVE_KEY))
        assert r.status_code == 200
        d = r.json()
        assert d.get("status") in ("pending", "credited")  # unpaid so still pending
        # Idempotent poll — no state change
        r2 = requests.get(
            f"{BASE_URL}/marketplace/spotlight/{pytest.spot_session}/status",
            headers=_h(LIVE_KEY))
        assert r2.status_code == 200
        assert r2.json().get("status") == d.get("status")

    def test_spotlight_get_by_business(self):
        r = requests.get(f"{BASE_URL}/marketplace/spotlight",
                         headers=_h(LIVE_KEY),
                         params={"business_id": "biz_demo_grill"})
        assert r.status_code == 200
        assert "bid" in r.json()

    def test_spotlight_bad_category(self):
        r = requests.post(f"{BASE_URL}/marketplace/spotlight/checkout",
                          headers=_h(LIVE_KEY),
                          json={"business_id": "biz_demo_grill",
                                "category": "nonsense",
                                "bid_cents": 25, "amount_cents": 2000})
        assert r.status_code == 400
        assert (r.json().get("detail") or {}).get("code") == "bad_category"

    def test_spotlight_unknown_business(self):
        r = requests.post(f"{BASE_URL}/marketplace/spotlight/checkout",
                          headers=_h(LIVE_KEY),
                          json={"business_id": "biz_nope",
                                "category": "restaurant",
                                "bid_cents": 25, "amount_cents": 2000})
        assert r.status_code == 404
        assert (r.json().get("detail") or {}).get("code") == "business_not_found"

    def test_spotlight_bid_out_of_range(self):
        # Pydantic gate 1..1000 -> 422 (validation)
        r = requests.post(f"{BASE_URL}/marketplace/spotlight/checkout",
                          headers=_h(LIVE_KEY),
                          json={"business_id": "biz_demo_grill",
                                "category": "restaurant",
                                "bid_cents": 9999, "amount_cents": 2000})
        assert r.status_code in (400, 422)

    def test_spotlight_amount_too_small(self):
        r = requests.post(f"{BASE_URL}/marketplace/spotlight/checkout",
                          headers=_h(LIVE_KEY),
                          json={"business_id": "biz_demo_grill",
                                "category": "restaurant",
                                "bid_cents": 25, "amount_cents": 100})
        assert r.status_code in (400, 422)


# ── SANDBOX INSTANT PATH ────────────────────────────────────────────
class TestSandboxInstant:
    def test_sandbox_advertiser_is_active(self, sandbox_advertiser):
        assert sandbox_advertiser

    def test_sandbox_trivia_is_active(self, sandbox_advertiser):
        from datetime import datetime, timedelta, timezone
        start = datetime.now(timezone.utc)
        end = start + timedelta(days=14)
        body = {"type": "trivia", "advertiser_id": sandbox_advertiser,
                "sponsor_target_type": "any",
                "prize_pool": [{"rank": 1, "points_reward": 100, "currency": "bc"}],
                "winner_selection": "top_n",
                "display_name": "TEST sbx trivia",
                "start_at": start.isoformat(), "end_at": end.isoformat()}
        r = requests.post(f"{BASE_URL}/sponsorships",
                          headers=_h(SANDBOX_KEY), json=body)
        assert r.status_code == 201, r.text
        sp = r.json()["sponsorship"]
        assert sp.get("status") == "active", sp
        sid = sp.get("id") or sp.get("sponsorship_id")
        # /checkout should be a no-op for sandbox
        rr = requests.post(
            f"{BASE_URL}/sponsorships/{sid}/checkout",
            headers=_h(SANDBOX_KEY),
            params={"type": "trivia", "advertiser_id": sandbox_advertiser})
        assert rr.status_code == 200
        d = rr.json()
        assert d.get("sandbox") is True and d.get("checkout_required") is False

    def test_sandbox_promotion_instant_active(self):
        r = requests.post(f"{BASE_URL}/marketplace/promotion/checkout",
                          headers=_h(SANDBOX_KEY),
                          json={"business_id": "biz_demo_grill", "tier": "spotlight_7"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("sandbox") is True
        assert d.get("status") == "active"
        assert d.get("checkout_required") is False

    def test_sandbox_spotlight_instant_funded(self):
        r = requests.post(f"{BASE_URL}/marketplace/spotlight/checkout",
                          headers=_h(SANDBOX_KEY),
                          json={"business_id": "biz_demo_grill",
                                "category": "restaurant",
                                "bid_cents": 25, "amount_cents": 2000})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("sandbox") is True
        assert d.get("status") == "active"
        assert d.get("budget_cents", 0) >= 2000
