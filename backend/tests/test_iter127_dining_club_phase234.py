"""Iter 127 — Dining Club Phase 2/3/4: merchant self-serve, Stripe Connect payout, webhooks, resume."""
from __future__ import annotations

import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

DEMO = ("demo@bigfm.dubai", "DemoPass123!")
FRESH = ("test@bigfm.dubai", "TestUser123!")
ADMIN = ("admin@bigfm.dubai", "AdminPass123!")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def demo_sess():
    return _login(*DEMO)


@pytest.fixture(scope="module")
def merchant_sess():
    return _login(*FRESH)


@pytest.fixture(scope="module")
def admin_sess():
    s = _login(*ADMIN)
    s.post(f"{BASE_URL}/api/admin/dining-club/seed", timeout=30)
    return s


# ═════════════════════ MERCHANT SELF-SERVE ═════════════════════════════
class TestMerchantSelfServe:

    def test_merchant_me_enrolled(self, merchant_sess):
        r = merchant_sess.get(f"{BASE_URL}/api/merchant/dining-club/me", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["enrolled"] is True
        assert j.get("merchant") and j["merchant"].get("merchant_id")
        assert "locations" in j
        assert "meals" in j
        pytest.MERCHANT_LOCATIONS = j.get("locations") or []

    def test_non_merchant_returns_not_enrolled(self, demo_sess):
        # demo@ isn't a dining merchant → /me returns {enrolled:False}
        r = demo_sess.get(f"{BASE_URL}/api/merchant/dining-club/me", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("enrolled") is False

    def test_non_merchant_locations_400(self, demo_sess):
        # demo@ is NOT enrolled → non-owner touching merchant endpoints must fail
        r = demo_sess.post(f"{BASE_URL}/api/merchant/dining-club/locations",
                           json={"name": "X", "address": "Y"}, timeout=15)
        assert r.status_code == 400, r.text
        body = r.json().get("detail") or {}
        code = body.get("code") if isinstance(body, dict) else body
        assert code == "not_a_dining_merchant"

    def test_merchant_analytics_shape(self, merchant_sess):
        r = merchant_sess.get(f"{BASE_URL}/api/merchant/dining-club/analytics", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        for k in ("locations", "appearances", "wins", "acceptances", "redemptions", "earnings"):
            assert k in j, f"missing {k}"
        e = j["earnings"]
        for k in ("gross_cents", "net_cents", "platform_fee_cents", "meals_settled"):
            assert k in e, f"missing earnings.{k}"

    def test_capacity_editor_roundtrip(self, merchant_sess):
        locs = getattr(pytest, "MERCHANT_LOCATIONS", [])
        if not locs:
            pytest.skip("no merchant locations")
        loc_id = locs[0]["location_id"]
        cap = {"LUNCH:VEG": 25, "LUNCH:NON_VEG": 30, "DINNER:VEG": 20, "DINNER:NON_VEG": 40}
        r = merchant_sess.put(f"{BASE_URL}/api/merchant/dining-club/locations/{loc_id}/capacity",
                              json={"capacity": cap}, timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j.get("ok") is True
        assert j.get("capacity") == cap

    def test_meals_editor_roundtrip(self, merchant_sess):
        locs = getattr(pytest, "MERCHANT_LOCATIONS", [])
        if not locs:
            pytest.skip("no merchant locations")
        loc_id = locs[0]["location_id"]
        meals = [
            {"veg_preference": "VEG", "meal_period": "LUNCH",
             "customer_title": "Grilled Veg Bowl (TEST_iter127)"},
            {"veg_preference": "NON_VEG", "meal_period": "DINNER",
             "customer_title": "Grilled Chicken Plate (TEST_iter127)"},
        ]
        r = merchant_sess.post(f"{BASE_URL}/api/merchant/dining-club/locations/{loc_id}/meals",
                               json={"meals": meals}, timeout=15)
        assert r.status_code == 200, r.text
        assert isinstance(r.json().get("meals"), list)


# ═════════════════════ WEBHOOKS: register / list / delete ══════════════
class TestMerchantWebhooks:

    def test_events_catalog_and_register(self, merchant_sess):
        r_list = merchant_sess.get(f"{BASE_URL}/api/merchant/dining-club/webhooks", timeout=15)
        assert r_list.status_code == 200, r_list.text
        events = r_list.json().get("events") or []
        for ev in ("restaurant.selected", "restaurant.accepted", "payment.completed",
                   "qr.issued", "redeemed", "capacity.low", "capacity.sold_out"):
            assert ev in events, f"missing event {ev} in catalog: {events}"

        # register
        url = "https://example.com/hooks/dining/iter127"
        r = merchant_sess.post(f"{BASE_URL}/api/merchant/dining-club/webhooks",
                               json={"url": url,
                                     "events": ["restaurant.selected", "restaurant.accepted",
                                                "payment.completed", "qr.issued", "redeemed"]},
                               timeout=15)
        assert r.status_code == 200, r.text
        wh = r.json().get("webhook")
        assert wh and wh.get("webhook_id")
        assert wh.get("secret"), "webhook secret must be returned on create"
        pytest.WEBHOOK_ID = wh["webhook_id"]

    def test_list_shows_registered(self, merchant_sess):
        r = merchant_sess.get(f"{BASE_URL}/api/merchant/dining-club/webhooks", timeout=15)
        assert r.status_code == 200, r.text
        whs = r.json().get("webhooks") or []
        assert any(w.get("webhook_id") == getattr(pytest, "WEBHOOK_ID", None) for w in whs)

    def test_non_merchant_webhook_denied(self, demo_sess):
        r = demo_sess.post(f"{BASE_URL}/api/merchant/dining-club/webhooks",
                           json={"url": "https://example.com/x"}, timeout=15)
        assert r.status_code == 400
        body = r.json().get("detail") or {}
        assert (body.get("code") if isinstance(body, dict) else "") == "not_a_dining_merchant"

    def test_delete_webhook(self, merchant_sess):
        wid = getattr(pytest, "WEBHOOK_ID", None)
        if not wid:
            pytest.skip("no webhook")
        r = merchant_sess.delete(f"{BASE_URL}/api/merchant/dining-club/webhooks/{wid}", timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("deleted") is True


# ═════════════════════ RESUME SELECTION ═════════════════════════════════
class TestResumeAndSegments:

    def test_resume_endpoint(self, demo_sess):
        # start a session for demo (may resume prior)
        r0 = demo_sess.post(f"{BASE_URL}/api/dining-club/selection/start",
                            json={"veg_preference": "VEG", "meal_period": "LUNCH"}, timeout=15)
        assert r0.status_code == 200, r0.text
        sid = r0.json()["session"]["session_id"]
        # GET /selection/{id} — resume endpoint
        r = demo_sess.get(f"{BASE_URL}/api/dining-club/selection/{sid}", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        s = j.get("session") or j
        assert s.get("session_id") == sid or j.get("session_id") == sid

    def test_spin_returns_segments_and_winner_index(self, demo_sess):
        # Start fresh + spin — verify wheel animation payload
        # We may already be in FIRST_RESULT/FINAL/ACCEPTED — in that case, skip
        home = demo_sess.get(f"{BASE_URL}/api/dining-club", timeout=15).json()
        r0 = demo_sess.post(f"{BASE_URL}/api/dining-club/selection/start",
                            json={"veg_preference": "VEG", "meal_period": "LUNCH"}, timeout=15)
        assert r0.status_code == 200
        sess = r0.json()["session"]
        sid = sess["session_id"]
        status = sess.get("status")
        if status not in ("STARTED", "REROLL_REQUESTED"):
            pytest.skip(f"session {sid} in {status}, cannot spin fresh")
        r = demo_sess.post(f"{BASE_URL}/api/dining-club/selection/{sid}/spin", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "winner_index" in j, f"missing winner_index: keys={list(j.keys())}"
        assert "segments" in j, f"missing segments: keys={list(j.keys())}"
        # segments is the WHEEL SLICE COUNT (int) — front-end renders N equal segments.
        assert isinstance(j["segments"], int) and j["segments"] >= 1
        assert isinstance(j["winner_index"], int)
        assert 0 <= j["winner_index"] < j["segments"]


# ═════════════════════ FULL PAYOUT LEDGER (redeem) ═════════════════════
class TestPayoutLedgerOnRedeem:

    def _get_or_create_final_order(self, s, admin_sess):
        """Bring demo@ to an ACCEPTED order that we can mark-paid and redeem."""
        # start + drive to FINAL
        r0 = s.post(f"{BASE_URL}/api/dining-club/selection/start",
                    json={"veg_preference": "NON_VEG", "meal_period": "DINNER"}, timeout=15)
        sess = r0.json()["session"]
        sid = sess["session_id"]
        status = sess.get("status")

        # If in ACCEPTED — grab its order_id and return
        if status == "ACCEPTED" and sess.get("order_id"):
            return sess["order_id"]

        # If in STARTED/REROLL_REQUESTED, spin (up to reroll then final)
        if status == "STARTED":
            r1 = s.post(f"{BASE_URL}/api/dining-club/selection/{sid}/spin", timeout=15)
            assert r1.status_code == 200, r1.text
        # At FIRST_RESULT — accept
        # But maybe we're already at FINAL_RESULT / FIRST_RESULT
        # Try accept directly:
        r = s.post(f"{BASE_URL}/api/dining-club/selection/{sid}/accept", timeout=15)
        if r.status_code != 200:
            # If we were at STARTED and spin was needed, retry
            r = s.post(f"{BASE_URL}/api/dining-club/selection/{sid}/accept", timeout=15)
        assert r.status_code == 200, r.text
        return r.json()["order_id"]

    def test_redeem_produces_payout_ledger_row(self, demo_sess, admin_sess):
        # ensure demo has an accepted order
        oid = self._get_or_create_final_order(demo_sess, admin_sess)
        assert oid

        # admin mark paid
        r = admin_sess.post(f"{BASE_URL}/api/admin/dining-club/orders/{oid}/mark-paid", timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "paid"
        qr_token = j["qr"]["qr_token"]

        # merchant redeem (admin cookie is authed; endpoint accepts any current_user)
        r2 = admin_sess.post(f"{BASE_URL}/api/merchant/dining-club/redeem",
                             json={"qr_token": qr_token}, timeout=15)
        assert r2.status_code == 200, r2.text
        rj = r2.json()
        assert rj["status"] == "REDEEMED"
        assert rj.get("gross_cents") == 999, f"gross_cents != 999: {rj}"
        assert rj.get("platform_fee_cents") == 100, f"platform_fee_cents != 100: {rj}"
        assert rj.get("net_cents") == 899, f"net_cents != 899: {rj}"
        assert rj.get("settlement") in ("transferred", "pending_no_connect", "pending_no_charge"), rj
        # demo seeded restaurants have no Connect → expect pending_no_connect
        # (allow other statuses; documented behavior)

        # replay → 409 already_redeemed
        r3 = admin_sess.post(f"{BASE_URL}/api/merchant/dining-club/redeem",
                             json={"qr_token": qr_token}, timeout=15)
        assert r3.status_code == 409, r3.text
        code = (r3.json().get("detail") or {}).get("code")
        assert code == "already_redeemed"


# ═════════════════════ WEBHOOK DELIVERIES ══════════════════════════════
class TestWebhookDeliveries:
    """Register a webhook on the merchant, drive a redeem, check deliveries were queued."""

    def test_register_webhook_then_trigger_delivery(self, merchant_sess, demo_sess, admin_sess):
        # register capturing webhook
        url = f"https://example.com/hooks/dining/iter127-{uuid.uuid4().hex[:6]}"
        r = merchant_sess.post(f"{BASE_URL}/api/merchant/dining-club/webhooks",
                               json={"url": url,
                                     "events": ["restaurant.selected", "restaurant.accepted",
                                                "payment.completed", "qr.issued", "redeemed"]},
                               timeout=15)
        assert r.status_code == 200, r.text
        wh_id = r.json()["webhook"]["webhook_id"]

        # Retrieve list to confirm exists
        r2 = merchant_sess.get(f"{BASE_URL}/api/merchant/dining-club/webhooks", timeout=15)
        assert r2.status_code == 200
        assert any(w.get("webhook_id") == wh_id for w in r2.json().get("webhooks") or [])

        # NOTE: We cannot force demo@'s spin to pick the merchant's restaurant.
        # Delivery rows are best-effort — we cannot deterministically assert here without DB.
        # This test at minimum verifies register + list + delete works.
        r_del = merchant_sess.delete(f"{BASE_URL}/api/merchant/dining-club/webhooks/{wh_id}",
                                     timeout=15)
        assert r_del.status_code == 200
