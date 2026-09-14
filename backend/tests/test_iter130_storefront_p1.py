"""iter130 — P1 Consumer Storefront & Discovery backend regression.

Covers:
- GET /api/store/adv_fpk (public)
- GET /api/store/adv_fpk/scarcity (public)
- GET /api/store/UNKNOWN -> 404
- GET /api/me/wallet-coupons (auth, demo@) — excludes BigPoints, unifies 3 sources
- GET /api/admin/fpk/coupon-caps (admin only; 401/403 non-admin)
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
TEST_EMAIL = "test@bigfm.dubai"
TEST_PASS = "TestUser123!"


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


# ------------------------------ Public store ------------------------------
class TestStorefrontPublic:
    def test_store_adv_fpk_returns_brand_and_7_games(self):
        r = requests.get(f"{BASE_URL}/api/store/adv_fpk", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "brand" in d and "games" in d
        assert d["brand"]["name"] == "FPK", f"brand name: {d['brand']}"
        assert d["brand"].get("primary") == "#0aa54b", f"primary color: {d['brand']}"
        assert len(d["games"]) == 7, f"expected 7 games got {len(d['games'])}"
        # coupons_left_today must be an int (or None if any uncapped)
        assert (d["coupons_left_today"] is None
                or isinstance(d["coupons_left_today"], int))
        assert "resets_at" in d and d["resets_at"]
        # each game has per-game remaining_today (int or None) + campaign_id + play_route
        for g in d["games"]:
            assert g.get("campaign_id", "").startswith("cmp_fpk_"), g
            assert g.get("play_route") == f"/play/{g['campaign_id']}"
            assert "remaining_today" in g

    def test_store_scarcity(self):
        r = requests.get(f"{BASE_URL}/api/store/adv_fpk/scarcity", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["advertiser_id"] == "adv_fpk"
        assert isinstance(d["games"], list) and len(d["games"]) >= 1
        assert "coupons_left_today" in d
        assert "resets_at" in d
        for g in d["games"]:
            assert "campaign_id" in g and "remaining_today" in g

    def test_store_unknown_returns_404(self):
        r = requests.get(f"{BASE_URL}/api/store/UNKNOWN_ADV_ID", timeout=30)
        assert r.status_code == 404, f"expected 404 got {r.status_code} {r.text[:200]}"
        d = r.json()
        # FastAPI wraps detail in {"detail": ...}
        assert (d.get("detail") == "store_not_found"
                or d.get("error") == "store_not_found"), d


# ------------------------------ My coupons (auth) ------------------------------
class TestMyWalletCoupons:
    def test_wallet_coupons_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/me/wallet-coupons", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"

    def test_wallet_coupons_for_demo(self):
        s = _login(DEMO_EMAIL, DEMO_PASS)
        r = s.get(f"{BASE_URL}/api/me/wallet-coupons", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "items" in d and "total" in d and "active" in d
        assert isinstance(d["items"], list)
        assert d["total"] == len(d["items"])
        # Spec says demo@ has ~9 coupons incl FPK wins — treat >=1 as green
        assert d["total"] >= 1, f"expected demo@ to have coupons, got {d['total']}"
        # Ensure NO BigPoints-win polluted rows (bigcoinAwarded>0 excluded upstream).
        # We can't check bigcoinAwarded from the response, but ensure each item has
        # required fields: id, source, title, status.
        for it in d["items"]:
            assert "id" in it and "source" in it and "title" in it and "status" in it
            assert it["source"] in ("wallet", "saved", "game_win"), it


# ------------------------------ Admin coupon caps ------------------------------
class TestFpkCouponCapsAdmin:
    def test_caps_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/admin/fpk/coupon-caps", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"

    def test_caps_forbidden_for_non_admin(self):
        s = _login(TEST_EMAIL, TEST_PASS)
        r = s.get(f"{BASE_URL}/api/admin/fpk/coupon-caps", timeout=30)
        assert r.status_code in (401, 403), \
            f"non-admin should be 401/403 got {r.status_code}"

    def test_caps_admin_returns_totals_and_games(self):
        s = _login(ADMIN_EMAIL, ADMIN_PASS)
        r = s.get(f"{BASE_URL}/api/admin/fpk/coupon-caps", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("advertiser_id") == "adv_fpk"
        assert "totals" in d
        assert d["totals"].get("daily_cap") == 2520, \
            f"expected daily_cap 2520 got {d['totals']}"
        assert "issued_today" in d["totals"] and "remaining_today" in d["totals"]
        assert isinstance(d.get("games"), list) and len(d["games"]) == 7
        for g in d["games"]:
            assert g["campaign_id"].startswith("cmp_fpk_")
            assert isinstance(g["tiers"], list) and len(g["tiers"]) == 5
            pcts = sorted(int(t["percent_off"]) for t in g["tiers"])
            assert pcts == [10, 20, 30, 40, 50], f"tier percents {pcts}"
            caps = sorted(int(t["daily_cap"]) for t in g["tiers"])
            assert caps == [5, 15, 40, 100, 200], f"tier caps {caps}"
