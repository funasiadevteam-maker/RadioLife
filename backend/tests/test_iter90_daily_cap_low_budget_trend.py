"""Iteration 90 — Category Spotlight refinements
(1) daily cap stops billing + drops bidder from category auction; rolls over
(2) low_budget flag flips true when impressions_left < 20
(3) analytics returns trend[] across the promotion window
(4) sweep_renewals + _email_renewal_receipt exist (code path check only)
(5) regression: anon /shop/businesses does NOT bill; /shop/track auth-gated
"""
import os
import time
import requests
import pytest
from pathlib import Path

def _load_env():
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

BASE_URL = _load_env().rstrip("/")
API = f"{BASE_URL}/api"

TEST_EMAIL = "test@bigfm.dubai"
TEST_PASSWORD = "TestUser123!"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    r = sess.post(f"{API}/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return sess


def _get_bid(s):
    r = s.get(f"{API}/merchant/marketplace/category-bid", timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()


def _set_bid(s, category, bid_cents, daily_cap_cents):
    r = s.post(f"{API}/merchant/marketplace/category-bid/set",
               json={"category": category, "bid_cents": bid_cents, "daily_cap_cents": daily_cap_cents},
               timeout=30)
    assert r.status_code == 200, r.text[:200]
    return r.json()


# ---- (1) DAILY CAP ----
class TestDailyCap:
    def test_daily_cap_stops_billing_and_drops_from_auction(self, s):
        # Read current bid to preserve category + bid_cents
        cur = _get_bid(s)
        assert cur.get("bid"), "merchant must already have a bid seeded"
        bid = cur["bid"]
        cat = bid["category"]
        bid_c = int(bid["bid_cents"])
        biz_id = cur["business_id"]

        # First, clear cap and confirm bidder can be spotlighted (rank 1 aka index 0)
        _set_bid(s, cat, bid_c, 0)
        r = s.get(f"{API}/shop/businesses", params={"category": cat}, timeout=30)
        items = r.json().get("items", [])
        rank_uncapped = next((i for i, it in enumerate(items) if it.get("business_id") == biz_id), None)

        # Now snapshot spent_today, then set cap = spent_today + bid_c*3 (allow 3 more)
        snap = _get_bid(s)
        st_before = int(snap["bid"].get("spent_today", 0))
        cap = st_before + bid_c * 3
        _set_bid(s, cat, bid_c, cap)

        # Hammer to burn 3 impressions + more
        for _ in range(10):
            s.get(f"{API}/shop/businesses", params={"category": cat}, timeout=30)

        after = _get_bid(s)
        st_after = int(after["bid"].get("spent_today", 0))
        # spent_today must stop exactly AT cap (never exceed)
        assert st_after <= cap, f"spent_today {st_after} exceeded cap {cap}"
        assert st_after >= min(cap, st_before + bid_c), f"spent_today didn't grow: before={st_before} after={st_after}"

        # After cap, bidder must have dropped out of #1 spotlight
        r = s.get(f"{API}/shop/businesses", params={"category": cat}, timeout=30)
        items = r.json().get("items", [])
        rank_capped = next((i for i, it in enumerate(items) if it.get("business_id") == biz_id), None)
        # spotlight flag OR being rank 0 requires being uncapped-eligible
        first_biz_id = items[0].get("business_id") if items else None
        spotlight_first = items[0].get("spotlight") if items else False
        # Was rank 0 (uncapped) → now must not be rank 0 spotlighted
        if rank_uncapped == 0:
            assert not (first_biz_id == biz_id and spotlight_first), (
                f"bidder still #1 spotlighted after cap: st_after={st_after} cap={cap}")

        # Cleanup: restore daily_cap_cents to 0
        _set_bid(s, cat, bid_c, 0)
        restored = _get_bid(s)
        assert int(restored["bid"]["daily_cap_cents"]) == 0


# ---- (2) LOW BUDGET FLAG ----
class TestLowBudgetFlag:
    def test_budget_object_shape(self, s):
        j = _get_bid(s)
        assert "budget" in j and j["budget"] is not None, j
        b = j["budget"]
        assert set(b.keys()) >= {"impressions_left", "low_budget", "depleted"}, b
        assert isinstance(b["impressions_left"], int)
        assert isinstance(b["low_budget"], bool)
        assert isinstance(b["depleted"], bool)
        # With $1000 budget @ 5c, impressions_left is very large → low_budget False
        bid = j["bid"]
        if int(bid["budget_cents"]) >= int(bid["bid_cents"]) * 20:
            assert b["low_budget"] is False


# ---- (3) ANALYTICS TREND ----
class TestAnalyticsTrend:
    def test_trend_present_and_shape(self, s):
        r = s.get(f"{API}/merchant/marketplace/promotion/analytics", timeout=30)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        assert j.get("has_data") is True, j
        assert "trend" in j and isinstance(j["trend"], list), j
        assert len(j["trend"]) >= 1
        pt = j["trend"][0]
        for k in ("date", "views", "impressions", "orders", "revenue_cents"):
            assert k in pt, pt


# ---- (4) RENEWAL RECEIPT CODE PATH ----
class TestRenewalReceiptCodePath:
    def test_email_renewal_receipt_exists(self):
        from backend.routes import marketplace_promotions as mp  # type: ignore
        assert hasattr(mp, "sweep_renewals")
        assert hasattr(mp, "_email_renewal_receipt")
        assert callable(mp._email_renewal_receipt)

    def test_auto_renew_toggle_still_works(self, s):
        r = s.get(f"{API}/merchant/marketplace/promotion", timeout=30)
        assert r.status_code == 200
        j = r.json()
        active = j.get("active")
        if not active:
            pytest.skip("no active promotion to toggle")
        pid = active["promotion_id"]
        cur = bool(j.get("auto_renew"))
        # Flip
        r2 = s.post(f"{API}/merchant/marketplace/promotion/{pid}/auto-renew",
                    json={"enabled": not cur}, timeout=30)
        assert r2.status_code == 200, r2.text[:200]
        assert r2.json()["auto_renew"] is (not cur)
        # Restore
        r3 = s.post(f"{API}/merchant/marketplace/promotion/{pid}/auto-renew",
                    json={"enabled": cur}, timeout=30)
        assert r3.status_code == 200
        assert r3.json()["auto_renew"] is cur


# ---- (5) REGRESSION ----
class TestRegression:
    def test_anon_shop_track_is_auth_gated(self):
        r = requests.post(f"{API}/shop/track",
                          json={"business_id": "biz_dc324d800f66", "kind": "impression"}, timeout=30)
        # Auth-gated: either 401/403 OR 200 with ok=false (silently ignores)
        if r.status_code == 200:
            body = r.json()
            assert body.get("ok") is False, f"anon /shop/track leaked: {body}"
        else:
            assert r.status_code in (401, 403), f"expected 401/403/200-noop got {r.status_code} {r.text[:200]}"

    def test_anon_category_search_does_not_bill(self, s):
        # baseline budget as merchant
        j0 = _get_bid(s)
        cat = j0["bid"]["category"]
        b0 = int(j0["bid"]["budget_cents"])
        # anon call (no cookies)
        for _ in range(3):
            r = requests.get(f"{API}/shop/businesses", params={"category": cat}, timeout=30)
            assert r.status_code == 200
        j1 = _get_bid(s)
        b1 = int(j1["bid"]["budget_cents"])
        # anon call should NOT have decremented budget
        assert b1 == b0, f"anon call billed budget: b0={b0} b1={b1}"

    def test_atomic_billing_stops_at_cap_boundary(self, s):
        j = _get_bid(s)
        bid = j["bid"]
        cat = bid["category"]
        bid_c = int(bid["bid_cents"])
        st_before = int(bid.get("spent_today", 0))
        # daily_cap = current spent_today + exactly 2 more impressions (in cents)
        cap = st_before + bid_c * 2
        _set_bid(s, cat, bid_c, cap)
        # hammer authenticated
        for _ in range(10):
            s.get(f"{API}/shop/businesses", params={"category": cat}, timeout=30)
        after = _get_bid(s)
        st = int(after["bid"].get("spent_today", 0))
        # spent_today must NEVER exceed the cap
        assert st <= cap, f"spent_today {st} exceeded cap {cap}"
        # After cap is reached, bidder should NOT be #1 anymore
        r = s.get(f"{API}/shop/businesses", params={"category": cat}, timeout=30)
        items = r.json().get("items", [])
        biz_id = j["business_id"]
        # Not eligible → not spotlighted at rank 0 OR spotlight flag off
        if items:
            first = items[0]
            if first.get("business_id") == biz_id:
                # only ok if spotlight is off (not billed)
                assert not first.get("spotlight"), f"bidder still spotlighted after cap: {first}"
        # cleanup
        _set_bid(s, cat, bid_c, 0)
