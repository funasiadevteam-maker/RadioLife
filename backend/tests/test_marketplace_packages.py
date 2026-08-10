"""Phase E item 3 — Marketplace Packages tests.

Covers:
  Merchant CRUD: GET/POST/PATCH/DELETE /api/merchant/marketplace/packages
  Consumer: GET /api/shop/businesses/{id}/packages, POST /api/shop/packages/purchase,
            GET /api/shop/packages/purchase/{sid}/status, GET /api/shop/packages/mine,
            POST /api/shop/packages/{pid}/redeem
  business_detail.has_packages
"""
from __future__ import annotations
import os
import time
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE = _load_backend_url()
BIZ_ID = "biz_8484f6f985d5"


def created_pkg_current_credits(session, package_id):
    lst = session.get(f"{BASE}/api/merchant/marketplace/packages").json()["items"]
    for x in lst:
        if x["package_id"] == package_id:
            return x["credits"]
    return None


@pytest.fixture(scope="session")
def demo():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="session")
def created_pkg(demo):
    body = {
        "name": f"TEST_pkg_{int(time.time())}",
        "description": "auto pytest package",
        "price_cents": 500,
        "credits": 3,
        "allow_points": True,
        "allow_card": True,
        "active": True,
    }
    r = demo.post(f"{BASE}/api/merchant/marketplace/packages/items", json=body, timeout=15)
    assert r.status_code == 200, r.text
    pkg = r.json()["package"]
    yield pkg
    # cleanup
    demo.delete(f"{BASE}/api/merchant/marketplace/packages/items/{pkg['package_id']}", timeout=15)


# ─────────── Merchant CRUD ───────────
class TestMerchantCRUD:
    def test_list(self, demo):
        r = demo.get(f"{BASE}/api/merchant/marketplace/packages", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        for it in data["items"]:
            assert "package_id" in it and "sold_count" in it and "credits" in it

    def test_create(self, created_pkg):
        assert created_pkg["credits"] == 3
        assert created_pkg["price_cents"] == 500
        assert created_pkg["business_id"] == BIZ_ID
        assert created_pkg["package_id"].startswith("pkgprod")

    def test_update(self, demo, created_pkg):
        body = {
            "name": created_pkg["name"] + "_upd",
            "description": "updated",
            "price_cents": 700,
            "credits": 4,
            "allow_points": True,
            "allow_card": True,
            "active": True,
        }
        r = demo.patch(f"{BASE}/api/merchant/marketplace/packages/items/{created_pkg['package_id']}",
                       json=body, timeout=15)
        assert r.status_code == 200
        assert r.json()["package"]["credits"] == 4
        assert r.json()["package"]["price_cents"] == 700
        # verify via list
        lst = demo.get(f"{BASE}/api/merchant/marketplace/packages").json()["items"]
        found = next(x for x in lst if x["package_id"] == created_pkg["package_id"])
        assert found["credits"] == 4

    def test_update_unknown_404(self, demo):
        r = demo.patch(f"{BASE}/api/merchant/marketplace/packages/items/pkgprod_zzz_unknown",
                       json={"name": "x", "price_cents": 100, "credits": 1}, timeout=15)
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "package_not_found"

    def test_delete_unknown_404(self, demo):
        r = demo.delete(f"{BASE}/api/merchant/marketplace/packages/items/pkgprod_zzz_unknown",
                        timeout=15)
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "package_not_found"

    def test_validation_credits_min(self, demo):
        r = demo.post(f"{BASE}/api/merchant/marketplace/packages/items",
                      json={"name": "bad", "price_cents": 500, "credits": 0}, timeout=15)
        assert r.status_code == 422


# ─────────── Consumer flows ───────────
class TestConsumer:
    def test_business_packages(self, demo, created_pkg):
        r = demo.get(f"{BASE}/api/shop/businesses/{BIZ_ID}/packages", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["business_id"] == BIZ_ID
        assert d["points_per_dollar"] == 100
        assert isinstance(d["points_balance"], int)
        assert isinstance(d["items"], list)
        assert isinstance(d["mine"], list)
        # our created package should appear
        ids = [x["package_id"] for x in d["items"]]
        assert created_pkg["package_id"] in ids

    def test_business_detail_has_packages(self, demo):
        r = demo.get(f"{BASE}/api/shop/businesses/{BIZ_ID}", timeout=15)
        assert r.status_code == 200
        assert r.json()["business"]["has_packages"] is True

    def test_purchase_points_insufficient_or_success(self, demo):
        # Buy the seeded expensive $99 5-Haircuts package with points => insufficient
        listing = demo.get(f"{BASE}/api/shop/businesses/{BIZ_ID}/packages").json()
        expensive = next((x for x in listing["items"] if x["price_cents"] >= 5000
                          and x.get("allow_points")), None)
        if not expensive:
            pytest.skip("no expensive package available")
        r = demo.post(f"{BASE}/api/shop/packages/purchase",
                      json={"package_id": expensive["package_id"], "method": "points"}, timeout=15)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "insufficient_points"

    def test_purchase_points_success_cheap(self, demo, created_pkg):
        # created_pkg=500 cents => 500 points cost. Demo has ~1600 pts (per PS).
        r = demo.post(f"{BASE}/api/shop/packages/purchase",
                      json={"package_id": created_pkg["package_id"], "method": "points"}, timeout=15)
        # Either succeeds (200) or insufficient (unlikely given seeded balance).
        if r.status_code == 400 and r.json().get("detail", {}).get("code") == "insufficient_points":
            pytest.skip("demo balance too low for cheap package points purchase")
        assert r.status_code == 200
        body = r.json()
        assert body["method"] == "points"
        assert body["package"]["credits_remaining"] == created_pkg_current_credits(demo, created_pkg["package_id"])
        assert body["package"]["status"] == "active"
        # store for redeem test on class
        TestConsumer._active_purchase_id = body["package"]["purchase_id"]

    def test_purchase_card_returns_checkout_url(self, demo, created_pkg):
        r = demo.post(f"{BASE}/api/shop/packages/purchase",
                      json={"package_id": created_pkg["package_id"], "method": "card",
                            "origin_url": BASE}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["method"] == "card"
        assert d["checkout_url"].startswith("http")
        assert d["session_id"].startswith("cs_")

    def test_purchase_status_pending(self, demo, created_pkg):
        r = demo.post(f"{BASE}/api/shop/packages/purchase",
                      json={"package_id": created_pkg["package_id"], "method": "card",
                            "origin_url": BASE}, timeout=20)
        sid = r.json()["session_id"]
        st = demo.get(f"{BASE}/api/shop/packages/purchase/{sid}/status", timeout=15)
        assert st.status_code == 200
        assert st.json()["status"] in ("pending", "paid")

    def test_purchase_status_unknown_404(self, demo):
        r = demo.get(f"{BASE}/api/shop/packages/purchase/cs_unknown_zz/status", timeout=15)
        assert r.status_code == 404

    def test_purchase_unknown_package_404(self, demo):
        r = demo.post(f"{BASE}/api/shop/packages/purchase",
                      json={"package_id": "pkgprod_zzz", "method": "points"}, timeout=15)
        assert r.status_code == 404

    def test_purchase_bad_method(self, demo, created_pkg):
        r = demo.post(f"{BASE}/api/shop/packages/purchase",
                      json={"package_id": created_pkg["package_id"], "method": "bogus"}, timeout=15)
        assert r.status_code == 400

    def test_my_packages(self, demo):
        r = demo.get(f"{BASE}/api/shop/packages/mine", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)

    def test_redeem_flow(self, demo):
        pid = getattr(TestConsumer, "_active_purchase_id", None)
        if not pid:
            # try to find any active package
            mine = demo.get(f"{BASE}/api/shop/packages/mine").json()["items"]
            active = [m for m in mine if m["status"] == "active" and m["credits_remaining"] > 0]
            if not active:
                pytest.skip("no active package to redeem")
            pid = active[0]["purchase_id"]
        r = demo.post(f"{BASE}/api/shop/packages/{pid}/redeem", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["credits_remaining"] >= 0
        assert d["status"] in ("active", "used_up")

    def test_redeem_unknown_404(self, demo):
        r = demo.post(f"{BASE}/api/shop/packages/pkg_zzz_unknown/redeem", timeout=15)
        assert r.status_code == 404

    def test_redeem_depleted_no_credits(self, demo):
        # try the seeded fully-used purchase
        r = demo.post(f"{BASE}/api/shop/packages/pkg_test_redeem/redeem", timeout=15)
        assert r.status_code in (400, 404)
        if r.status_code == 400:
            assert r.json()["detail"]["code"] == "no_credits"
