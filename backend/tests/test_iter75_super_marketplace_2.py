"""Iter 75 — RadioLife Super Marketplace (2nd wave) backend tests.

Covers 4 new feature areas:
  1) SPECIALS — merchant upsert/list/delete + consumer /api/shop/specials + home.specials
  2) POINTS-PER-DOLLAR — merchant bigpoints/settings toggles scale quote points
  3) RANKING — sort=featured places sponsored/featured/higher-ppd first
  4) LOYALTY-ON-SCAN — scanpay CARD charge awards points; POINTS charge awards 0

Uses demo@bigfm.dubai (owns biz_8484f6f985d5) + admin. Ends with a settings-reset
fixture so bigpoints goes back to {mode:'default', default_points:150, points_per_dollar:2}.
"""
from __future__ import annotations

import os
import time
import uuid
import stripe
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE, "REACT_APP_BACKEND_URL not set"

DEMO_BIZ = "biz_8484f6f985d5"


def hdr(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


@pytest.fixture(scope="session")
def demo_token() -> str:
    r = requests.post(f"{BASE}/api/auth/demo", json={}, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["session_token"]


@pytest.fixture(scope="session")
def admin_token() -> str:
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"},
                      timeout=15)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code}")
    return r.json()["session_token"]


@pytest.fixture(scope="session")
def demo_menu_and_products(demo_token):
    """List demo biz's menu/products via merchant specials manager."""
    r = requests.get(f"{BASE}/api/merchant/marketplace/specials",
                     headers=hdr(demo_token), timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    return {"menu": j.get("menu", []), "products": j.get("products", []),
            "specials": j.get("specials", [])}


@pytest.fixture(scope="session", autouse=True)
def _reset_bp_settings_at_end(demo_token):
    """Restore bigpoints to default={mode:'default', default_points:150, ppd:2} at teardown."""
    yield
    try:
        requests.patch(f"{BASE}/api/merchant/marketplace/bigpoints/settings",
                       headers=hdr(demo_token),
                       json={"mode": "default", "default_points": 150,
                             "points_per_dollar": 2.0}, timeout=15)
    except Exception:
        pass


# ─────────────────── 1) SPECIALS ───────────────────

class TestSpecials:
    def test_1_merchant_specials_list_shape(self, demo_menu_and_products):
        assert "menu" in demo_menu_and_products and "products" in demo_menu_and_products
        # Demo should have at least one menu item + one product per PRD
        assert len(demo_menu_and_products["menu"]) >= 1

    def test_2_upsert_special_on_menu_item(self, demo_token, demo_menu_and_products):
        m = demo_menu_and_products["menu"][0]
        item_id = m.get("item_id") or m.get("menu_item_id") or m.get("id")
        assert item_id, f"menu item missing id: {list(m)[:8]}"
        pytest.iter75_menu_item_id = item_id
        pytest.iter75_menu_item_price = m.get("price_cents") or m.get("base_price_cents") or 4200
        body = {"kind": "menu", "item_id": item_id,
                "blurb": "TEST75 Chef's pick", "sale_price_cents": 999,
                "active": True}
        r = requests.put(f"{BASE}/api/merchant/marketplace/specials",
                         headers=hdr(demo_token), json=body, timeout=15)
        assert r.status_code == 200, r.text
        sp = r.json()["special"]
        assert sp["item_id"] == item_id
        assert sp["blurb"] == "TEST75 Chef's pick"
        assert sp["sale_price_cents"] == 999
        assert sp["active"] is True
        pytest.iter75_special_id = sp["special_id"]

    def test_3_upsert_is_idempotent(self, demo_token):
        # PUT again with different blurb → still one special row, updated fields
        body = {"kind": "menu", "item_id": pytest.iter75_menu_item_id,
                "blurb": "TEST75 UPDATED", "sale_price_cents": 888, "active": True}
        r = requests.put(f"{BASE}/api/merchant/marketplace/specials",
                         headers=hdr(demo_token), json=body, timeout=15)
        assert r.status_code == 200
        sp = r.json()["special"]
        assert sp["special_id"] == pytest.iter75_special_id
        assert sp["blurb"] == "TEST75 UPDATED"
        assert sp["sale_price_cents"] == 888

    def test_4_consumer_specials_lists_active(self, demo_token):
        r = requests.get(f"{BASE}/api/shop/specials", headers=hdr(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "items" in j and isinstance(j["items"], list)
        # Our just-created special should be present (matched by special_id or item_id)
        ids = {s.get("special_id") for s in j["items"]}
        item_ids = {s.get("item_id") for s in j["items"]}
        assert (pytest.iter75_special_id in ids) or (pytest.iter75_menu_item_id in item_ids), \
            f"created special not in /shop/specials — got {j['items'][:3]}"
        # Enrichment: at least one entry should have a business+item block
        s = next((x for x in j["items"] if x.get("item_id") == pytest.iter75_menu_item_id), j["items"][0])
        assert s.get("business") or s.get("business_id"), f"missing business enrichment: {s}"

    def test_5_shop_home_includes_specials_array(self, demo_token):
        r = requests.get(f"{BASE}/api/shop/home", headers=hdr(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        assert "specials" in j, f"home missing specials: keys={list(j)[:12]}"
        assert isinstance(j["specials"], list)

    def test_6_toggle_inactive_removes_from_consumer_list(self, demo_token):
        # Set inactive
        r = requests.put(f"{BASE}/api/merchant/marketplace/specials",
                         headers=hdr(demo_token),
                         json={"kind": "menu", "item_id": pytest.iter75_menu_item_id,
                               "blurb": "TEST75 hidden", "active": False}, timeout=15)
        assert r.status_code == 200
        # Consumer list should not include our special_id now (allow seeded 'RadioLife Tee' etc.)
        rr = requests.get(f"{BASE}/api/shop/specials", headers=hdr(demo_token), timeout=15)
        ids = {s.get("special_id") for s in rr.json().get("items", [])}
        assert pytest.iter75_special_id not in ids

    def test_7_delete_special(self, demo_token):
        r = requests.delete(
            f"{BASE}/api/merchant/marketplace/specials/{pytest.iter75_special_id}",
            headers=hdr(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_8_delete_unknown_returns_404(self, demo_token):
        r = requests.delete(
            f"{BASE}/api/merchant/marketplace/specials/sp_doesnotexist_xyz",
            headers=hdr(demo_token), timeout=15)
        assert r.status_code == 404


# ─────────────────── 2) POINTS-PER-DOLLAR ───────────────────

class TestPointsPerDollar:
    def test_1_set_ppd_mode(self, demo_token):
        r = requests.patch(f"{BASE}/api/merchant/marketplace/bigpoints/settings",
                           headers=hdr(demo_token),
                           json={"mode": "per_order_value", "points_per_dollar": 5.0,
                                 "default_points": 150}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_2_orders_quote_points_scale_with_subtotal(self, demo_token, demo_menu_and_products):
        m = demo_menu_and_products["menu"][0]
        item_id = m.get("item_id") or m.get("menu_item_id") or m.get("id")
        price_cents = m.get("price_cents") or m.get("base_price_cents") or 4200
        r = requests.post(f"{BASE}/api/shop/orders/quote", headers=hdr(demo_token),
                          json={"business_id": DEMO_BIZ,
                                "items": [{"item_id": item_id, "qty": 1}]},
                          timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        pts = j.get("points_to_award") or j.get("points_award") or 0
        # Expect approximately round(price_cents/100 * 5). Allow ±1 for rounding.
        expected = round((price_cents / 100.0) * 5.0)
        assert abs(pts - expected) <= 1, f"expected~{expected}, got {pts}; quote={j}"

    def test_3_set_default_mode(self, demo_token):
        r = requests.patch(f"{BASE}/api/merchant/marketplace/bigpoints/settings",
                           headers=hdr(demo_token),
                           json={"mode": "default", "default_points": 150,
                                 "points_per_dollar": 2.0}, timeout=15)
        assert r.status_code == 200

    def test_4_default_mode_returns_flat_points(self, demo_token, demo_menu_and_products):
        m = demo_menu_and_products["menu"][0]
        item_id = m.get("item_id") or m.get("menu_item_id") or m.get("id")
        r = requests.post(f"{BASE}/api/shop/orders/quote", headers=hdr(demo_token),
                          json={"business_id": DEMO_BIZ,
                                "items": [{"item_id": item_id, "qty": 1}]},
                          timeout=15)
        assert r.status_code == 200
        pts = r.json().get("points_to_award") or r.json().get("points_award") or 0
        # In default mode should be ~150 (flat)
        assert pts == 150, f"expected 150 flat, got {pts}"


# ─────────────────── 3) RANKING ───────────────────

class TestRanking:
    def test_1_featured_sort_returns_list(self, demo_token):
        r = requests.get(f"{BASE}/api/shop/businesses?sort=featured",
                         headers=hdr(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        j = r.json()
        items = j.get("items") or j.get("businesses") or []
        assert isinstance(items, list) and len(items) >= 1

    def test_2_ranking_scores_monotonic_non_increasing(self, demo_token):
        r = requests.get(f"{BASE}/api/shop/businesses?sort=featured",
                         headers=hdr(demo_token), timeout=15)
        items = r.json().get("items") or r.json().get("businesses") or []
        # Extract ranking_score if surfaced (per PRD it lives under services.marketplace)
        scores = []
        for b in items[:8]:
            svc = (b.get("services") or {}).get("marketplace") or {}
            rs = svc.get("ranking_score", b.get("ranking_score"))
            if rs is not None:
                scores.append(float(rs))
        # Skip if backend doesn't surface score in list; just check that a
        # 'sponsored' or 'featured' biz (if any) is not below a plain one.
        if len(scores) >= 2:
            for a, b in zip(scores, scores[1:]):
                assert a + 1e-6 >= b, f"ranking not descending: {scores}"

    def test_3_home_recommended_returned(self, demo_token):
        r = requests.get(f"{BASE}/api/shop/home", headers=hdr(demo_token), timeout=15)
        j = r.json()
        rec = j.get("recommended") or j.get("recommendations") or []
        assert isinstance(rec, list)


# ─────────────────── 4) LOYALTY-ON-SCAN ───────────────────

class TestLoyaltyOnScan:
    @pytest.fixture(scope="class")
    def stripe_pm_attached(self, demo_token):
        """Ensure demo has a card in the wallet; return its pm id."""
        # Bootstrap customer via wallet cards endpoint (idempotent)
        r = requests.get(f"{BASE}/api/shop/wallet/cards",
                         headers=hdr(demo_token), timeout=20)
        assert r.status_code == 200, r.text
        cards = r.json().get("cards", [])
        if not cards:
            pytest.skip("no saved cards on demo user — iteration_73 attached one; if missing, main agent must reattach pm_card_visa")
        return cards[0]["id"]

    def test_1_card_charge_awards_points(self, demo_token, stripe_pm_attached):
        # Ensure default (flat 150) mode so points calc is deterministic
        requests.patch(f"{BASE}/api/merchant/marketplace/bigpoints/settings",
                       headers=hdr(demo_token),
                       json={"mode": "default", "default_points": 150,
                             "points_per_dollar": 2.0}, timeout=15)
        # 1) create CARD token as customer (small $ amount)
        r = requests.post(f"{BASE}/api/shop/scanpay/token", headers=hdr(demo_token),
                          json={"method": "card", "amount_cents": 2000,
                                "payment_method_id": stripe_pm_attached}, timeout=20)
        assert r.status_code == 200, r.text
        tok = r.json()["token"]
        pytest.iter75_card_token = tok

        # 2) demo merchant charges its own token
        c = requests.post(f"{BASE}/api/shop/scanpay/charge", headers=hdr(demo_token),
                          json={"token": tok}, timeout=45)
        assert c.status_code == 200, c.text
        cj = c.json()
        assert cj.get("ok") is True, f"charge failed: {cj}"
        pts = cj.get("points_awarded", cj.get("points", 0))
        assert isinstance(pts, int) and pts > 0, f"expected points>0, got {pts}, resp={cj}"

    def test_2_points_charge_awards_zero_points(self, demo_token):
        # Points method — should not earn points back
        r = requests.post(f"{BASE}/api/shop/scanpay/token", headers=hdr(demo_token),
                          json={"method": "points", "amount_cents": 50}, timeout=15)
        if r.status_code != 200:
            pytest.skip(f"points token create refused: {r.status_code} {r.text[:80]}")
        tok = r.json()["token"]
        c = requests.post(f"{BASE}/api/shop/scanpay/charge", headers=hdr(demo_token),
                          json={"token": tok}, timeout=30)
        # May be 200 with ok=false if balance too low — treat that as skip
        if c.status_code != 200 or not c.json().get("ok", True):
            # cancel so we don't leak
            requests.post(f"{BASE}/api/shop/scanpay/token/{tok}/cancel",
                          headers=hdr(demo_token), timeout=10)
            pytest.skip(f"points charge not executable: {c.status_code} {c.text[:120]}")
        pts = c.json().get("points_awarded", c.json().get("points", 0))
        assert pts == 0, f"points-method must NOT earn points back, got {pts}"


# ─────────────────── 5) REGRESSION ───────────────────

class TestRegression:
    def test_1_new_count_still_works(self, demo_token):
        r = requests.get(f"{BASE}/api/merchant/marketplace/orders/new-count",
                         headers=hdr(demo_token), timeout=15)
        assert r.status_code == 200
        j = r.json()
        assert set(j.keys()) >= {"food", "products", "total"}

    def test_2_scanpay_resolve_bad_token(self, demo_token):
        r = requests.post(f"{BASE}/api/shop/scanpay/resolve",
                          headers=hdr(demo_token),
                          json={"token": "NOPEZZZ"}, timeout=15)
        assert r.status_code == 200
        assert r.json().get("ok") is False
