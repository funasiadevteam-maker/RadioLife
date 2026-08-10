"""Backend tests for Marketplace Memberships (Phase E item 2)."""
import os
import pytest
import requests
from pathlib import Path


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not v:
        env = Path("/app/frontend/.env")
        if env.exists():
            for ln in env.read_text().splitlines():
                if ln.startswith("REACT_APP_BACKEND_URL="):
                    v = ln.split("=", 1)[1].strip()
                    break
    return v.rstrip("/")


BASE_URL = _load_backend_url()
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

BUSINESS_ID = "biz_8484f6f985d5"


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def existing_plan_id(demo_session):
    r = demo_session.get(f"{BASE_URL}/api/merchant/marketplace/memberships", timeout=15)
    assert r.status_code == 200
    items = r.json().get("items", [])
    assert items, "seeded Coffee Club plan should exist for demo merchant"
    return items[0]["plan_id"]


# ─── Merchant CRUD ───────────────────────────────────────────────────
class TestMerchantCRUD:
    def test_list_includes_member_count(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/merchant/marketplace/memberships", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert len(data["items"]) >= 1
        for it in data["items"]:
            assert "member_count" in it
            assert "plan_id" in it
            assert "entitlements" in it

    def test_create_plan_and_verify(self, demo_session):
        body = {
            "name": "TEST_Auto_Plan",
            "description": "auto-created",
            "price_cents": 999,
            "interval": "month",
            "entitlements": [
                {"label": "TEST_free_snack", "qty": 3, "period": "week",
                 "options": ["Apple", "Banana"]}
            ],
            "active": True,
        }
        r = demo_session.post(
            f"{BASE_URL}/api/merchant/marketplace/memberships/items",
            json=body, timeout=15)
        assert r.status_code == 200, r.text
        p = r.json()["plan"]
        assert p["name"] == "TEST_Auto_Plan"
        assert p["price_cents"] == 999
        assert p["interval"] == "month"
        assert len(p["entitlements"]) == 1
        ent = p["entitlements"][0]
        assert ent["label"] == "TEST_free_snack"
        assert ent["qty"] == 3
        assert ent["period"] == "week"
        assert ent["options"] == ["Apple", "Banana"]
        assert ent["benefit_id"]  # was auto-generated
        # verify via list
        lst = demo_session.get(f"{BASE_URL}/api/merchant/marketplace/memberships",
                               timeout=15).json()["items"]
        assert any(x["plan_id"] == p["plan_id"] for x in lst)
        # cleanup
        demo_session.delete(
            f"{BASE_URL}/api/merchant/marketplace/memberships/items/{p['plan_id']}",
            timeout=15)

    def test_update_plan_and_verify(self, demo_session):
        # create
        r = demo_session.post(
            f"{BASE_URL}/api/merchant/marketplace/memberships/items",
            json={"name": "TEST_UpdMe", "price_cents": 500, "interval": "month",
                  "entitlements": []},
            timeout=15)
        pid = r.json()["plan"]["plan_id"]
        # patch
        r2 = demo_session.patch(
            f"{BASE_URL}/api/merchant/marketplace/memberships/items/{pid}",
            json={"name": "TEST_Updated", "price_cents": 700, "interval": "week",
                  "entitlements": [{"label": "New", "qty": 1, "period": "day"}],
                  "active": True},
            timeout=15)
        assert r2.status_code == 200
        p = r2.json()["plan"]
        assert p["name"] == "TEST_Updated"
        assert p["price_cents"] == 700
        assert p["interval"] == "week"
        assert len(p["entitlements"]) == 1
        # cleanup
        demo_session.delete(
            f"{BASE_URL}/api/merchant/marketplace/memberships/items/{pid}",
            timeout=15)

    def test_delete_plan(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/merchant/marketplace/memberships/items",
            json={"name": "TEST_DelMe", "price_cents": 500, "interval": "month",
                  "entitlements": []},
            timeout=15)
        pid = r.json()["plan"]["plan_id"]
        r2 = demo_session.delete(
            f"{BASE_URL}/api/merchant/marketplace/memberships/items/{pid}",
            timeout=15)
        assert r2.status_code == 200
        # verify gone
        lst = demo_session.get(f"{BASE_URL}/api/merchant/marketplace/memberships",
                               timeout=15).json()["items"]
        assert not any(x["plan_id"] == pid for x in lst)

    def test_bad_interval_400(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/merchant/marketplace/memberships/items",
            json={"name": "TEST_BadInt", "price_cents": 500, "interval": "year",
                  "entitlements": []},
            timeout=15)
        assert r.status_code == 400
        assert r.json().get("detail", {}).get("code") == "bad_interval"


# ─── Consumer / business detail ─────────────────────────────────────
class TestConsumer:
    def test_business_detail_has_memberships(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shop/businesses/{BUSINESS_ID}",
                             timeout=15)
        assert r.status_code == 200
        biz = r.json().get("business", {})
        assert biz.get("has_memberships") is True

    def test_business_memberships_with_mine(self, demo_session):
        r = demo_session.get(
            f"{BASE_URL}/api/shop/businesses/{BUSINESS_ID}/memberships",
            timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("business_id") == BUSINESS_ID
        assert isinstance(data.get("items"), list)
        assert data.get("mine") is not None, "demo user should already be a member"
        mine = data["mine"]
        assert mine.get("status") == "active"
        assert isinstance(mine.get("benefits"), list) and len(mine["benefits"]) >= 2
        for b in mine["benefits"]:
            assert "used" in b and "remaining" in b and "period_key" in b
            assert b["remaining"] <= b["qty"]

    def test_subscribe_returns_already_member(self, demo_session, existing_plan_id):
        r = demo_session.post(
            f"{BASE_URL}/api/shop/memberships/subscribe",
            json={"plan_id": existing_plan_id,
                  "origin_url": BASE_URL},
            timeout=15)
        # DEMO user is already a member of that plan
        assert r.status_code == 400
        assert r.json().get("detail", {}).get("code") == "already_member"

    def test_subscribe_new_plan_returns_checkout(self, demo_session):
        # Create a NEW plan owned by demo merchant -> demo user can attempt subscribe
        # (they aren't a member of THIS new one). Should return stripe checkout_url.
        cr = demo_session.post(
            f"{BASE_URL}/api/merchant/marketplace/memberships/items",
            json={"name": "TEST_SubCheckout", "price_cents": 500,
                  "interval": "month", "entitlements": []},
            timeout=15)
        pid = cr.json()["plan"]["plan_id"]
        try:
            r = demo_session.post(
                f"{BASE_URL}/api/shop/memberships/subscribe",
                json={"plan_id": pid, "origin_url": BASE_URL},
                timeout=20)
            # Either checkout_url returned OR stripe unconfigured
            if r.status_code == 200:
                body = r.json()
                assert body.get("checkout_url", "").startswith("http")
                assert body.get("session_id")
                assert body.get("membership_id")
            else:
                # stripe not configured is acceptable
                assert r.status_code in (400, 503), r.text
        finally:
            demo_session.delete(
                f"{BASE_URL}/api/merchant/marketplace/memberships/items/{pid}",
                timeout=15)

    def test_mine_endpoint(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 1
        m = items[0]
        assert m.get("status") == "active"
        assert m.get("plan_name")
        assert isinstance(m.get("benefits"), list)

    def test_claim_option_required(self, demo_session):
        # get pastry benefit (has options)
        r = demo_session.get(
            f"{BASE_URL}/api/shop/businesses/{BUSINESS_ID}/memberships",
            timeout=15)
        mine = r.json()["mine"]
        mid = mine["membership_id"]
        pastry = next((b for b in mine["benefits"] if b.get("options")), None)
        assert pastry, "expected a benefit with options in seed"
        r2 = demo_session.post(
            f"{BASE_URL}/api/shop/memberships/{mid}/claim",
            json={"benefit_id": pastry["benefit_id"]}, timeout=15)
        assert r2.status_code == 400
        assert r2.json().get("detail", {}).get("code") == "option_required"

    def test_claim_option_invalid(self, demo_session):
        r = demo_session.get(
            f"{BASE_URL}/api/shop/businesses/{BUSINESS_ID}/memberships",
            timeout=15)
        mine = r.json()["mine"]
        mid = mine["membership_id"]
        pastry = next((b for b in mine["benefits"] if b.get("options")), None)
        assert pastry
        r2 = demo_session.post(
            f"{BASE_URL}/api/shop/memberships/{mid}/claim",
            json={"benefit_id": pastry["benefit_id"], "option": "NotAnOption"},
            timeout=15)
        assert r2.status_code == 400
        assert r2.json().get("detail", {}).get("code") == "option_required"

    def test_claim_pastry_with_option_and_decrement(self, demo_session):
        # weekly pastry - may or may not have remaining; verify decrement or limit_reached
        r = demo_session.get(
            f"{BASE_URL}/api/shop/businesses/{BUSINESS_ID}/memberships",
            timeout=15)
        mine = r.json()["mine"]
        mid = mine["membership_id"]
        pastry = next((b for b in mine["benefits"] if b.get("options")), None)
        assert pastry
        before_remaining = pastry["remaining"]
        opt = pastry["options"][0]
        r2 = demo_session.post(
            f"{BASE_URL}/api/shop/memberships/{mid}/claim",
            json={"benefit_id": pastry["benefit_id"], "option": opt},
            timeout=15)
        if before_remaining > 0:
            assert r2.status_code == 200, r2.text
            body = r2.json()
            assert body["remaining"] == before_remaining - 1
            # re-fetch and confirm persisted
            r3 = demo_session.get(
                f"{BASE_URL}/api/shop/businesses/{BUSINESS_ID}/memberships",
                timeout=15).json()
            new_pastry = next(b for b in r3["mine"]["benefits"]
                              if b["benefit_id"] == pastry["benefit_id"])
            assert new_pastry["remaining"] == before_remaining - 1
        else:
            assert r2.status_code == 400
            assert r2.json().get("detail", {}).get("code") == "limit_reached"

    def test_claim_daily_limit_reached_expected(self, demo_session):
        # Coffee has qty=1/day. Force to exhausted state by claiming until limit.
        r = demo_session.get(
            f"{BASE_URL}/api/shop/businesses/{BUSINESS_ID}/memberships",
            timeout=15)
        mine = r.json()["mine"]
        mid = mine["membership_id"]
        coffee = next((b for b in mine["benefits"] if not b.get("options")), None)
        assert coffee
        # Claim once if remaining
        if coffee["remaining"] > 0:
            demo_session.post(
                f"{BASE_URL}/api/shop/memberships/{mid}/claim",
                json={"benefit_id": coffee["benefit_id"]}, timeout=15)
        # Second attempt should be limit_reached
        r2 = demo_session.post(
            f"{BASE_URL}/api/shop/memberships/{mid}/claim",
            json={"benefit_id": coffee["benefit_id"]}, timeout=15)
        assert r2.status_code == 400
        assert r2.json().get("detail", {}).get("code") == "limit_reached"
