"""Iteration 66 — RadioLife Super Marketplace: Membership Wallet + Ticket Scan.

Tests four backend features:
  • GET  /api/shop/memberships/mine (authed) → shape + seeded rows.
  • POST /api/shop/memberships/{id}/claim → decrements + limit_reached.
  • POST /api/merchant/marketplace/events/tickets/checkin → success / repeat / not_found.
Web uses test@bigfm.dubai (cookie), mobile uses demo@bigfm.dubai (bearer).
"""
from __future__ import annotations

import os
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    for path in ("/app/frontend/.env", "/app/mobile/.env"):
        try:
            with open(path) as f:
                for ln in f:
                    if ln.startswith("REACT_APP_BACKEND_URL=") or ln.startswith("EXPO_PUBLIC_BACKEND_URL="):
                        return ln.split("=", 1)[1].strip().rstrip("/")
        except FileNotFoundError:
            continue
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_backend_url()


# ─────────────────────── auth fixtures ───────────────────────
@pytest.fixture(scope="module")
def web_session():
    """Cookie session for test@bigfm.dubai (web login)."""
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "test@bigfm.dubai", "password": "TestUser123!"},
               timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def mobile_headers():
    """Bearer token via /api/auth/demo for demo@bigfm.dubai."""
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token") or r.json().get("access_token") or r.json().get("token")
    assert tok, f"no bearer token: {r.json()}"
    return {"Authorization": f"Bearer {tok}"}


# ─────────────────────── Membership Wallet ───────────────────────
class TestMembershipsMine:
    """GET /api/shop/memberships/mine — shape + seeded 2 rows for both accounts."""

    SEEDED_PLAN_IDS = {"mplan_sample_biz_sample_ambreens_glam",
                       "mplan_sample_biz_sample_funpizza_coffee"}

    def _assert_wallet_shape(self, items):
        assert isinstance(items, list) and len(items) >= 2, f"expected >=2 memberships, got {items}"
        seeded = [r for r in items if r.get("plan_id") in self.SEEDED_PLAN_IDS]
        assert len(seeded) == 2, f"expected both seeded memberships, got {[r.get('plan_id') for r in items]}"
        plan_names = {r["plan_name"] for r in seeded}
        assert "Unlimited Blowouts" in plan_names, plan_names
        assert "Coffee Club" in plan_names, plan_names
        for row in seeded:
            assert row.get("sponsor_name"), row
            assert isinstance(row.get("price_cents"), int), row
            assert row.get("interval") == "month", row
            assert row.get("current_period_end"), f"seeded row missing current_period_end: {row}"
            benefits = row.get("benefits")
            assert isinstance(benefits, list) and len(benefits) >= 1, row
            for b in benefits:
                assert "label" in b and "qty" in b and "remaining" in b and "period" in b, b

    def test_web_wallet(self, web_session):
        r = web_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        assert r.status_code == 200, r.text
        self._assert_wallet_shape(r.json()["items"])

    def test_mobile_wallet(self, mobile_headers):
        r = requests.get(f"{BASE_URL}/api/shop/memberships/mine",
                         headers=mobile_headers, timeout=15)
        assert r.status_code == 200, r.text
        self._assert_wallet_shape(r.json()["items"])


# ─────────────────────── Benefit Claim ───────────────────────
class TestClaim:
    """POST /api/shop/memberships/{id}/claim decrements remaining and hits limit_reached."""

    def test_web_claim_blowout_and_limit(self, web_session):
        r = web_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        assert r.status_code == 200
        blow = next(m for m in r.json()["items"] if m["plan_name"] == "Unlimited Blowouts")
        # Claim the "10% off colour" (qty=1/month) — after 1 claim, second must 400 limit_reached.
        mid = blow["membership_id"]
        # First find the colour benefit
        colour_bnf = next(b for b in blow["benefits"] if b["benefit_id"] == "bnf_colour_off")
        already_used = colour_bnf["qty"] - colour_bnf["remaining"]

        # If not already used, first claim should succeed
        if already_used == 0:
            c1 = web_session.post(f"{BASE_URL}/api/shop/memberships/{mid}/claim",
                                  json={"benefit_id": "bnf_colour_off"}, timeout=15)
            assert c1.status_code == 200, c1.text
            data = c1.json()
            assert data["ok"] is True
            assert data["remaining"] == 0

        # Now second attempt must hit limit_reached (400)
        c2 = web_session.post(f"{BASE_URL}/api/shop/memberships/{mid}/claim",
                              json={"benefit_id": "bnf_colour_off"}, timeout=15)
        assert c2.status_code == 400, c2.text
        body = c2.json()
        # FastAPI HTTPException detail wraps our code
        code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")
        assert code == "limit_reached", body

    def test_web_claim_pizza_option_required(self, web_session):
        """bnf_weekly_pizza has options=[…] — without option, expect option_required 400."""
        # Seed only guarantees Coffee Club + Blowouts memberships (not pizza). Look up plan
        # and confirm the pizza plan itself. If user doesn't hold pizza plan, skip.
        r = web_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        items = r.json()["items"]
        pizza = next((m for m in items if m["plan_name"] == "Weekly Pizza Club"), None)
        if not pizza:
            pytest.skip("Weekly Pizza Club not seeded for this account (spec says Coffee Club only).")
        mid = pizza["membership_id"]
        c = web_session.post(f"{BASE_URL}/api/shop/memberships/{mid}/claim",
                             json={"benefit_id": "bnf_weekly_pizza"}, timeout=15)
        assert c.status_code == 400
        body = c.json()
        code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")
        assert code == "option_required", body


# ─────────────────────── Ticket Check-in ───────────────────────
class TestTicketCheckin:
    """POST /api/merchant/marketplace/events/tickets/checkin — success/repeat/404."""

    URL = f"{BASE_URL}/api/merchant/marketplace/events/tickets/checkin"

    def test_web_checkin_flow(self, web_session):
        # Use the spare code TEST5678 so we can (a) succeed then (b) repeat → already_checked_in.
        code = "TEST5678"
        r1 = web_session.post(self.URL, json={"code": code}, timeout=15)
        assert r1.status_code in (200,), r1.text
        b1 = r1.json()
        # If already checked_in from a prior test-run, treat that as the "repeat" branch.
        if b1.get("status") == "already_checked_in":
            # still ok — the check-in endpoint is idempotent-detectable
            assert b1["ok"] is False
        else:
            assert b1["ok"] is True and b1["status"] == "checked_in", b1

        # Second call must always report already_checked_in.
        r2 = web_session.post(self.URL, json={"code": code}, timeout=15)
        assert r2.status_code == 200, r2.text
        b2 = r2.json()
        assert b2["ok"] is False and b2["status"] == "already_checked_in", b2

    def test_web_checkin_not_found(self, web_session):
        r = web_session.post(self.URL, json={"code": "NOPE9999ZZZ"}, timeout=15)
        assert r.status_code == 404, r.text
        body = r.json()
        code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")
        assert code == "ticket_not_found", body

    def test_mobile_checkin_flow(self, mobile_headers):
        code = "DEMO5678"
        r1 = requests.post(self.URL, json={"code": code}, headers=mobile_headers, timeout=15)
        assert r1.status_code == 200, r1.text
        b1 = r1.json()
        if b1.get("status") != "already_checked_in":
            assert b1["ok"] is True and b1["status"] == "checked_in", b1
        r2 = requests.post(self.URL, json={"code": code}, headers=mobile_headers, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["status"] == "already_checked_in", r2.json()
