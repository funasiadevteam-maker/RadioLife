"""Iter 151 — Gift-card SPEND + Shop Redeem history endpoint tests."""
import os, requests, pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
GC_CODE = "BIGFM-GC-63SJ6T"
MERCHANT = "biz_fun_pizza_kitchen"
PIN = "4242"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS})
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code} {r.text[:200]}")
    return s


# --- Gift card spend endpoint ---
class TestGiftCardSpend:
    def test_spend_requires_auth(self):
        r = requests.post(f"{API}/games/gift-card/spend",
                          json={"code": GC_CODE, "amount_cents": 10})
        assert r.status_code == 401

    def test_spend_small_amount(self, auth_session):
        # Check initial balance
        w = auth_session.get(f"{API}/wallet/me").json()
        cards = [g for g in (w.get("gift_cards") or []) if g.get("code") == GC_CODE]
        if not cards:
            pytest.skip("demo user has no BIGFM-GC-63SJ6T gift card")
        initial = cards[0]["current_balance_cents"]
        spend = min(50, initial)  # 50 cents
        r = auth_session.post(f"{API}/games/gift-card/spend",
                              json={"code": GC_CODE, "amount_cents": spend})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["charged_cents"] == spend
        assert d["remaining_cents"] == initial - spend
        assert "status" in d
        # verify persistence
        w2 = auth_session.get(f"{API}/wallet/me").json()
        c2 = [g for g in (w2.get("gift_cards") or []) if g.get("code") == GC_CODE][0]
        assert c2["current_balance_cents"] == initial - spend

    def test_spend_overspend_returns_shortfall_and_depletes(self, auth_session):
        w = auth_session.get(f"{API}/wallet/me").json()
        cards = [g for g in (w.get("gift_cards") or []) if g.get("code") == GC_CODE]
        if not cards:
            pytest.skip("no gift card")
        remaining = cards[0]["current_balance_cents"]
        if remaining <= 0:
            pytest.skip("card already depleted")
        # try to spend more than available
        r = auth_session.post(f"{API}/games/gift-card/spend",
                              json={"code": GC_CODE, "amount_cents": remaining + 500})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["charged_cents"] == remaining
        assert d["remaining_cents"] == 0
        assert d.get("shortfall_cents", 0) == 500
        assert d.get("status") in ("depleted", "empty")

    def test_spend_on_depleted_card(self, auth_session):
        r = auth_session.post(f"{API}/games/gift-card/spend",
                              json={"code": GC_CODE, "amount_cents": 10})
        # depleted -> either 400/409 with code:depleted, or ok:false
        assert r.status_code in (400, 409, 422)
        body = r.json()
        code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("code")
        assert code == "depleted" or "deplet" in str(body).lower()

    def test_spend_bad_code(self, auth_session):
        r = auth_session.post(f"{API}/games/gift-card/spend",
                              json={"code": "BIGFM-GC-NOPE00", "amount_cents": 10})
        assert r.status_code in (404, 400)


# --- Shop redeem history endpoint ---
class TestRedemptionHistory:
    def test_history_bad_pin(self):
        r = requests.get(f"{API}/games/redemptions/today",
                         params={"merchant_id": MERCHANT, "pin": "0000"})
        assert r.status_code == 403

    def test_history_missing_pin(self):
        r = requests.get(f"{API}/games/redemptions/today",
                         params={"merchant_id": MERCHANT})
        assert r.status_code == 403

    def test_history_valid_pin_shape(self):
        r = requests.get(f"{API}/games/redemptions/today",
                         params={"merchant_id": MERCHANT, "pin": PIN})
        assert r.status_code == 200, r.text
        d = r.json()
        assert "totals" in d and "coupons" in d and "gift_cards" in d
        assert "coupons_count" in d["totals"]
        assert "gift_cards_count" in d["totals"]
        assert "gift_card_spend_cents" in d["totals"]
        assert isinstance(d["coupons"], list)
        assert isinstance(d["gift_cards"], list)

    def test_history_reflects_spend(self):
        # After the spend tests above ran, there should be at least one gift-card entry today
        r = requests.get(f"{API}/games/redemptions/today",
                         params={"merchant_id": MERCHANT, "pin": PIN})
        d = r.json()
        # We spent within this test module; ensure count >= 1 & total >= 50 cents
        assert d["totals"]["gift_cards_count"] >= 1
        assert d["totals"]["gift_card_spend_cents"] >= 50
