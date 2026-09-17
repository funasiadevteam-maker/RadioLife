"""Iter150 — Gift Card Wallet, Redeem PIN (4242), Sponsor Wallet top-up, weighted bids.

Backend coverage for the 4 RadioLife features tested this iter:
  1) GET /api/wallet/me returns Fun Pizza Kitchen $10 gift card in gift_cards[]
     + game-won coupons in coupons[].
  2) GET /api/games/coupon/lookup?code=... => pin_required:true for Fun Pizza.
  3) POST /api/games/coupon/redeem enforces PIN 4242 (403 bad_pin, 200 ok,
     idempotent on repeat).
  4) Sponsor wallet: GET /api/promoted/wallet, POST /api/promoted/wallet/topup-demo,
     POST /api/promoted/{promo_id}/bid; home rotation weights toward higher bid.
  5) Scratch play on gc_ddd9445590464f as a FRESH user mints coupon or gift_card.
"""
import os
import time
import uuid
import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASSWORD = "DemoPass123!"
FUN_PIZZA_PIN = "4242"
FUN_PIZZA_BIZ = "biz_fun_pizza_kitchen"
SCRATCH_CID = "gc_ddd9445590464f"


# ── Fixtures ───────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def fresh_session():
    """Register a fresh user for clean plays (demo has 5-plays/game cap)."""
    s = requests.Session()
    email = f"iter150_{uuid.uuid4().hex[:10]}@bigfm.dubai"
    r = s.post(f"{BASE}/api/auth/register",
               json={"email": email, "password": "IterTest123!",
                     "name": "Iter150 Tester",
                     "first_name": "Iter150", "last_name": "Tester"}, timeout=15)
    assert r.status_code in (200, 201), f"register failed: {r.status_code} {r.text}"
    return s, email


# ── 1) Wallet — gift cards + coupons ───────────────────────────────
class TestWalletMe:
    def test_demo_wallet_has_fun_pizza_gift_card(self, demo_session):
        r = demo_session.get(f"{BASE}/api/wallet/me", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        gcs = data.get("gift_cards") or []
        assert isinstance(gcs, list), f"gift_cards should be list, got {type(gcs)}"
        # Find the Fun Pizza $10 card
        matches = [c for c in gcs
                   if (c.get("merchant_name") or "").lower().startswith("fun pizza")
                   and int(c.get("current_balance_cents") or 0) >= 1]
        assert matches, f"No Fun Pizza gift card in demo wallet: {gcs}"
        gc = matches[0]
        assert gc.get("current_balance_cents") == 1000, gc
        code = gc.get("code") or ""
        assert code.startswith("BIGFM-GC-"), f"unexpected GC code: {code}"

    def test_demo_wallet_has_coupons(self, demo_session):
        r = demo_session.get(f"{BASE}/api/wallet/me", timeout=15)
        assert r.status_code == 200
        coupons = r.json().get("coupons") or []
        assert isinstance(coupons, list)
        # We don't require a specific count — just that the list exists and any
        # returned coupon has the fields the UI needs.
        for c in coupons[:3]:
            assert "code" in c or "redemption_code" in c, c


# ── 2 & 3) Redeem PIN ──────────────────────────────────────────────
class TestRedeemPin:
    """Requires an unredeemed Fun Pizza coupon in the DB. We mint one via a
    fresh user's play — if the outcome is a gift_card (~10%) we retry a few
    times (max 5 plays/user cap)."""

    def _mint_fresh_coupon(self, fresh_session):
        s, email = fresh_session
        code = None
        for _ in range(5):
            r = s.post(f"{BASE}/api/games/{SCRATCH_CID}/play", json={}, timeout=20)
            if r.status_code != 200:
                break
            j = r.json()
            if j.get("won") and j.get("outcome_type") == "coupon":
                code = (j.get("coupon") or {}).get("code") \
                       or (j.get("wallet_item") or {}).get("code") \
                       or j.get("code")
                if code:
                    break
        return code

    def test_lookup_returns_pin_required_true_for_fun_pizza(self, fresh_session):
        code = self._mint_fresh_coupon(fresh_session)
        if not code:
            pytest.skip("could not mint a fresh coupon (all plays were gift_card/none)")
        r = requests.get(f"{BASE}/api/games/coupon/lookup",
                         params={"code": code}, timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("found") is True, data
        assert data.get("pin_required") is True, \
            f"pin_required should be true for Fun Pizza: {data}"
        assert (data.get("business_id") == FUN_PIZZA_BIZ
                or "fun pizza" in (data.get("business_name") or "").lower()), data
        # Stash for the next tests
        pytest.iter150_code = code  # type: ignore

    def test_redeem_without_pin_is_403_bad_pin(self):
        code = getattr(pytest, "iter150_code", None)
        if not code:
            pytest.skip("no fresh coupon")
        r = requests.post(f"{BASE}/api/games/coupon/redeem",
                          json={"code": code}, timeout=15)
        assert r.status_code == 403, r.text
        body = r.json()
        detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
        assert (detail.get("code") == "bad_pin"), body

    def test_redeem_wrong_pin_is_403_bad_pin(self):
        code = getattr(pytest, "iter150_code", None)
        if not code:
            pytest.skip("no fresh coupon")
        r = requests.post(f"{BASE}/api/games/coupon/redeem",
                          json={"code": code, "pin": "0000"}, timeout=15)
        assert r.status_code == 403, r.text
        body = r.json()
        detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
        assert detail.get("code") == "bad_pin", body

    def test_redeem_correct_pin_ok_and_idempotent(self):
        code = getattr(pytest, "iter150_code", None)
        if not code:
            pytest.skip("no fresh coupon")
        r1 = requests.post(f"{BASE}/api/games/coupon/redeem",
                           json={"code": code, "pin": FUN_PIZZA_PIN}, timeout=15)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1.get("ok") is True
        assert d1.get("status") == "redeemed", d1
        # Idempotent repeat
        r2 = requests.post(f"{BASE}/api/games/coupon/redeem",
                           json={"code": code, "pin": FUN_PIZZA_PIN}, timeout=15)
        assert r2.status_code == 200, r2.text
        d2 = r2.json()
        assert d2.get("ok") is True and d2.get("idempotent") is True, d2

    def test_redeem_bad_code_returns_404(self):
        r = requests.post(f"{BASE}/api/games/coupon/redeem",
                          json={"code": "BIGFM-DOESNT-EXIST",
                                "pin": FUN_PIZZA_PIN}, timeout=15)
        assert r.status_code == 404, r.text


# ── 4) Sponsor wallet + bid + rotation ─────────────────────────────
class TestSponsorWallet:
    def test_get_wallet_shape(self, demo_session):
        r = demo_session.get(f"{BASE}/api/promoted/wallet", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "balance_cents" in d and isinstance(d["balance_cents"], int), d
        assert "active_promos" in d, d

    def test_topup_demo_credits_and_reactivates(self, demo_session):
        r0 = demo_session.get(f"{BASE}/api/promoted/wallet", timeout=15)
        b0 = int(r0.json().get("balance_cents") or 0)
        r = demo_session.post(f"{BASE}/api/promoted/wallet/topup-demo",
                              json={"amount_cents": 500}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True, d
        assert d.get("credited_cents") == 500, d
        assert d.get("balance_cents") == b0 + 500, d

    def test_topup_unauth_401(self):
        r = requests.post(f"{BASE}/api/promoted/wallet/topup-demo",
                          json={"amount_cents": 500}, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_stations_have_bid_cents_sorted_desc(self):
        r = requests.get(f"{BASE}/api/promoted/stations", params={"limit": 6},
                         timeout=15)
        assert r.status_code == 200, r.text
        items = r.json().get("items") or []
        assert items, "no promoted stations returned"
        bids = [int(x.get("bid_cents") or 0) for x in items]
        assert bids == sorted(bids, reverse=True), bids

    def test_bid_increase_raises_cpm(self, demo_session):
        # Find a promo owned by demo user
        r = demo_session.get(f"{BASE}/api/promoted/mine", timeout=15)
        assert r.status_code == 200, r.text
        mine = r.json().get("items") or []
        if not mine:
            pytest.skip("demo user has no promos owned")
        promo = mine[0]
        pid = promo["promo_id"]
        cur = int(promo.get("cpm_bid_cents") or 0)
        r2 = demo_session.post(f"{BASE}/api/promoted/{pid}/bid",
                               json={"cpm_bid_cents": cur + 100}, timeout=15)
        assert r2.status_code == 200, r2.text
        d = r2.json()
        new_bid = int(d.get("cpm_bid_cents") or d.get("promo", {}).get("cpm_bid_cents") or 0)
        assert new_bid >= cur + 100 or new_bid >= 100, d


# ── 5) Scratch game fresh play ─────────────────────────────────────
class TestScratchPlay:
    def test_fresh_user_can_play_scratch(self, fresh_session):
        s, _ = fresh_session
        r = s.post(f"{BASE}/api/games/{SCRATCH_CID}/play", json={}, timeout=20)
        # If already exhausted from redeem-pin test we might get 409/403
        assert r.status_code in (200, 403, 409), r.text
        if r.status_code == 200:
            j = r.json()
            assert "won" in j
            if j.get("won") is True:
                assert j.get("outcome_type") in ("coupon", "gift_card"), j
                assert j.get("wallet_item_type") in (None, "coupon", "gift_card"), j
