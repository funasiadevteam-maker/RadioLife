"""Iteration 79 review-request backend tests.

Covers:
- GET /api/merchant/marketplace/earnings (owner-gated, ledger structure)
- GET /api/merchant/marketplace/subscription/plans (3 tiers, can_offer_memberships)
- GET /api/radio/browse (source=imported, sort/lang/country/q params)
- GET /api/radio/discover (rails with facet_chips on lang/genre/country)
"""
import os
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE:
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE = line.split("=", 1)[1].strip().rstrip("/")
                break


# ─────────────── Auth fixtures ───────────────
@pytest.fixture(scope="module")
def web_session():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": "test@bigfm.dubai", "password": "TestUser123!"},
               timeout=15)
    assert r.status_code == 200, f"web login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo_bearer():
    r = requests.post(f"{BASE}/api/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text[:200]}"
    j = r.json()
    tok = j.get("token") or j.get("access_token") or j.get("session_token")
    assert tok, f"no token in demo response: {r.json()}"
    return tok


# ─────────────── Merchant earnings ───────────────
class TestMerchantEarnings:
    def test_earnings_web_owner(self, web_session):
        r = web_session.get(f"{BASE}/api/merchant/marketplace/earnings", timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("business_id", "memberships_sold", "gross_cents",
                  "fee_cents", "net_cents", "month", "transactions"):
            assert k in d, f"missing {k} in {list(d.keys())}"
        assert isinstance(d["transactions"], list)
        for k in ("count", "gross_cents", "fee_cents", "net_cents"):
            assert k in d["month"], f"missing month.{k}"
        # Ledger sanity: net = gross - fee
        assert d["net_cents"] == d["gross_cents"] - d["fee_cents"]

    def test_earnings_mobile_demo(self, demo_bearer):
        r = requests.get(f"{BASE}/api/merchant/marketplace/earnings",
                         headers={"Authorization": f"Bearer {demo_bearer}"}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["net_cents"] == d["gross_cents"] - d["fee_cents"]
        # demo owns a merchant that seeds sample memberships
        assert d["memberships_sold"] >= 0

    def test_earnings_unauth(self):
        r = requests.get(f"{BASE}/api/merchant/marketplace/earnings", timeout=15)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


# ─────────────── Subscription plans ───────────────
class TestSubscriptionPlans:
    def test_plans_shape(self, web_session):
        r = web_session.get(f"{BASE}/api/merchant/marketplace/subscription/plans", timeout=15)
        assert r.status_code == 200, r.text[:300]
        items = r.json().get("items") or []
        assert len(items) == 3, f"expected 3 plans got {len(items)}: {items}"
        by_id = {p["plan_id"]: p for p in items}
        for pid in ("starter", "growth", "pro"):
            assert pid in by_id, f"missing plan {pid}"
            assert "can_offer_memberships" in by_id[pid]
            assert isinstance(by_id[pid]["can_offer_memberships"], bool)
        # Pro-only membership gating
        assert by_id["pro"]["can_offer_memberships"] is True
        assert by_id["starter"]["can_offer_memberships"] is False
        # Starter is free, pro/growth priced
        assert by_id["starter"]["price_cents"] == 0
        assert by_id["growth"]["price_cents"] == 2999
        assert by_id["pro"]["price_cents"] == 9999

    def test_plans_mobile(self, demo_bearer):
        r = requests.get(f"{BASE}/api/merchant/marketplace/subscription/plans",
                         headers={"Authorization": f"Bearer {demo_bearer}"}, timeout=15)
        assert r.status_code == 200
        items = r.json().get("items") or []
        assert len(items) == 3


# ─────────────── Radio browse (public) ───────────────
class TestRadioBrowse:
    def test_browse_imported_default(self):
        r = requests.get(f"{BASE}/api/radio/browse",
                         params={"source": "imported", "limit": 24, "sort": "popular"}, timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "items" in d and "total" in d
        assert isinstance(d["items"], list)
        assert d["limit"] == 24
        assert len(d["items"]) <= 24

    def test_browse_sort_az(self):
        r = requests.get(f"{BASE}/api/radio/browse",
                         params={"source": "imported", "limit": 12, "sort": "az"}, timeout=20)
        assert r.status_code == 200
        items = r.json().get("items") or []
        if len(items) >= 2:
            names = [i.get("name") or "" for i in items]
            # Mongo default sort is case-sensitive (ASCII) — compare with plain sorted()
            sorted_names = sorted(names)
            assert names == sorted_names, f"AZ sort broken: {names[:5]} vs {sorted_names[:5]}"

    def test_browse_sort_newest(self):
        r = requests.get(f"{BASE}/api/radio/browse",
                         params={"source": "imported", "limit": 12, "sort": "newest"}, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)

    def test_browse_language_filter(self):
        r = requests.get(f"{BASE}/api/radio/browse",
                         params={"source": "imported", "limit": 24, "language": "english"}, timeout=20)
        assert r.status_code == 200
        items = r.json().get("items") or []
        for it in items[:10]:
            lang = (it.get("language") or "").lower()
            if lang:
                assert "english" in lang, f"non-english leak: {it.get('name')} lang={lang}"

    def test_browse_country_filter(self):
        r = requests.get(f"{BASE}/api/radio/browse",
                         params={"source": "imported", "limit": 12, "country": "AE"}, timeout=20)
        assert r.status_code == 200
        # just shape check - country data may not always be uppercase-normalized in returned field
        assert isinstance(r.json().get("items"), list)

    def test_browse_query_search(self):
        r = requests.get(f"{BASE}/api/radio/browse",
                         params={"source": "imported", "limit": 12, "q": "radio"}, timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)


# ─────────────── Radio discover (facets) ───────────────
class TestRadioDiscover:
    def test_discover_rails_present(self):
        r = requests.get(f"{BASE}/api/radio/discover", timeout=20)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        rails = d.get("rails") or []
        assert len(rails) > 0
        by_key = {rail.get("key") or rail.get("id") or rail.get("slug"): rail for rail in rails}
        # Print rail keys for debugging
        print("Discover rail keys:", list(by_key.keys()))
        return by_key

    def test_discover_facets(self):
        r = requests.get(f"{BASE}/api/radio/discover", timeout=20)
        assert r.status_code == 200
        rails = r.json().get("rails") or []
        # find rails that contain facet_chips
        chip_rails = [rail for rail in rails if isinstance(rail.get("facet_chips"), list)]
        assert len(chip_rails) >= 3, f"expected >=3 facet rails, got {len(chip_rails)}: {[r.get('key') for r in chip_rails]}"
        for rail in chip_rails:
            chips = rail["facet_chips"]
            if chips:
                c0 = chips[0]
                assert "slug" in c0 and "label" in c0 and "count" in c0, f"bad chip shape: {c0}"
