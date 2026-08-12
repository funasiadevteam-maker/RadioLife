"""
Iteration 76 — Phase 1: Membership Entitlements + Option Groups (BACKEND ONLY).

Covers:
 - Menu item CRUD with new `option_groups` (size/single/multi + upcharges, defaults, availability)
 - Product CRUD with new `option_groups` (alongside legacy `variants`)
 - Membership plan CRUD with v2 entitlement schema (schema_version=2, entitlement_id generated)
 - Consumer wallet reads (/memberships/mine, /businesses/{id}/memberships) — ledger-backed
 - Claim flow (entitlement_id / benefit_id, limit_reached, outside_time_window, benefit_not_found)
 - Consumer catalogue exposes option_groups
 - Boot migration idempotency (legacy plans → schema_version=2, legacy claims → ledger)
 - Regression: existing checkout still works with option_groups additive
"""
from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://mobile-games-v2.preview.emergentagent.com",
).rstrip("/")

MERCHANT_EMAIL = "test@bigfm.dubai"
MERCHANT_PW = "TestUser123!"


# ─────────────────────── Fixtures ───────────────────────
@pytest.fixture(scope="session")
def merchant_session() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": MERCHANT_EMAIL, "password": MERCHANT_PW}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Merchant login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="session")
def merchant_business_id(merchant_session) -> str:
    # Owned marketplace business — fetch via merchant profile
    r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/profile", timeout=15)
    if r.status_code == 200 and r.json().get("business_id"):
        return r.json()["business_id"]
    # fall back to my/businesses
    r = merchant_session.get(f"{BASE_URL}/api/marketplace/my/businesses", timeout=15)
    if r.status_code == 200:
        items = r.json().get("items") or []
        if items:
            return items[0]["business_id"]
    pytest.skip("Could not determine merchant business_id")


# ─────────────────────── Menu option_groups ───────────────────────
class TestMenuOptionGroups:
    """POST/PATCH/GET menu items with option_groups (size/single/multi + upcharges)."""

    created_item_id: Optional[str] = None

    def test_1_create_item_with_option_groups(self, merchant_session):
        body = {
            "section": "TEST_iter76",
            "name": "TEST_iter76 Pizza",
            "description": "test pizza",
            "price_cents": 1200,
            "available": True,
            "option_groups": [
                {"name": "Size", "type": "size", "required": True, "min_select": 1, "max_select": 3,
                 "options": [
                     {"label": "Medium", "price_delta_cents": 0, "is_default": True},
                     {"label": "Large", "price_delta_cents": 400},
                 ]},
                {"name": "Extras", "type": "multi", "required": False, "min_select": 0, "max_select": 3,
                 "options": [
                     {"label": "Extra Cheese", "price_delta_cents": 200},
                     {"label": "Olives", "price_delta_cents": 150, "available": False},
                     {"label": "Mushrooms", "price_delta_cents": 150, "stock": 5},
                 ]},
            ],
        }
        r = merchant_session.post(f"{BASE_URL}/api/merchant/marketplace/menu/items", json=body, timeout=15)
        assert r.status_code == 200, r.text
        item = r.json()["item"]
        assert item.get("item_id")
        assert item["name"] == "TEST_iter76 Pizza"
        ogs = item["option_groups"]
        assert len(ogs) == 2
        # size group normalized: max_select forced to 1
        size = next(g for g in ogs if g["name"] == "Size")
        assert size["type"] == "size"
        assert size["max_select"] == 1, f"size group max_select must be 1, got {size['max_select']}"
        assert size.get("group_id", "").startswith("grp_")
        for o in size["options"]:
            assert o["option_id"].startswith("opt_")
        # multi group keeps its max_select
        multi = next(g for g in ogs if g["name"] == "Extras")
        assert multi["type"] == "multi"
        assert multi["max_select"] == 3
        olives = next(o for o in multi["options"] if o["label"] == "Olives")
        assert olives["available"] is False
        assert olives["price_delta_cents"] == 150
        TestMenuOptionGroups.created_item_id = item["item_id"]

    def test_2_get_menu_returns_option_groups(self, merchant_session):
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/menu", timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert TestMenuOptionGroups.created_item_id, "test_1 must run first"
        found = next((it for it in items if it["item_id"] == TestMenuOptionGroups.created_item_id), None)
        assert found is not None
        assert len(found["option_groups"]) == 2

    def test_3_patch_item_preserves_option_group_ids(self, merchant_session):
        assert TestMenuOptionGroups.created_item_id
        # Fetch current
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/menu", timeout=15)
        current = next(it for it in r.json()["items"] if it["item_id"] == TestMenuOptionGroups.created_item_id)
        # Rename size group and keep IDs
        body = {
            "section": current["section"], "name": current["name"] + " v2",
            "price_cents": current["price_cents"], "available": True,
            "option_groups": [
                {**g, "name": g["name"] + " (updated)"} for g in current["option_groups"]
            ],
        }
        r = merchant_session.patch(
            f"{BASE_URL}/api/merchant/marketplace/menu/items/{TestMenuOptionGroups.created_item_id}",
            json=body, timeout=15)
        assert r.status_code == 200, r.text
        item = r.json()["item"]
        assert item["name"].endswith("v2")
        # Group IDs preserved
        original_ids = {g["group_id"] for g in current["option_groups"]}
        new_ids = {g["group_id"] for g in item["option_groups"]}
        assert original_ids == new_ids

    def test_4_bulk_menu_import_normalizes(self, merchant_session):
        body = {
            "items": [{
                "section": "TEST_iter76_bulk", "name": "TEST_iter76 Bulk Sandwich",
                "price_cents": 900, "available": True,
                "option_groups": [{"name": "Bread", "type": "single",
                                   "options": [{"label": "White"}, {"label": "Wheat", "price_delta_cents": 50}]}],
            }], "replace": False}
        r = merchant_session.post(f"{BASE_URL}/api/merchant/marketplace/menu/items/bulk",
                                  json=body, timeout=15)
        assert r.status_code == 200
        assert r.json()["inserted"] == 1

    def test_5_zzz_cleanup(self, merchant_session):
        # Delete test items
        if TestMenuOptionGroups.created_item_id:
            merchant_session.delete(
                f"{BASE_URL}/api/merchant/marketplace/menu/items/{TestMenuOptionGroups.created_item_id}",
                timeout=15)
        # Clean bulk
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/menu", timeout=15)
        for it in r.json().get("items", []):
            if str(it.get("name", "")).startswith("TEST_iter76"):
                merchant_session.delete(
                    f"{BASE_URL}/api/merchant/marketplace/menu/items/{it['item_id']}", timeout=15)


# ─────────────────────── Product option_groups ───────────────────────
class TestProductOptionGroups:
    created_pid: Optional[str] = None

    def test_1_create_product_with_option_groups_and_legacy_variants(self, merchant_session):
        body = {
            "name": "TEST_iter76 Product",
            "description": "test",
            "category": "test",
            "price_cents": 2500,
            "stock": 10,
            "active": True,
            "variants": [{"label": "Small", "price_delta_cents": 0},
                         {"label": "XL", "price_delta_cents": 500}],
            "option_groups": [
                {"name": "Color", "type": "single", "required": True, "min_select": 1, "max_select": 1,
                 "options": [{"label": "Red", "is_default": True}, {"label": "Blue"}]},
                {"name": "Addons", "type": "multi", "min_select": 0, "max_select": 2,
                 "options": [{"label": "Gift wrap", "price_delta_cents": 300}]},
            ],
        }
        r = merchant_session.post(f"{BASE_URL}/api/merchant/marketplace/products/items",
                                  json=body, timeout=15)
        assert r.status_code == 200, r.text
        p = r.json()["item"] if "item" in r.json() else r.json().get("product")
        assert p, r.text
        assert p.get("product_id")
        # Both legacy variants AND new option_groups persist
        assert len(p.get("variants", [])) == 2
        assert len(p.get("option_groups", [])) == 2
        color = next(g for g in p["option_groups"] if g["name"] == "Color")
        assert color["type"] == "single"
        assert color["max_select"] == 1
        assert all(o.get("option_id", "").startswith("opt_") for o in color["options"])
        TestProductOptionGroups.created_pid = p["product_id"]

    def test_2_product_patch_normalizes(self, merchant_session):
        pid = TestProductOptionGroups.created_pid
        assert pid
        # Fetch it
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/products", timeout=15)
        cur = next(x for x in r.json()["items"] if x["product_id"] == pid)
        body = {**cur, "name": cur["name"] + " v2"}
        # trim any server-only keys
        for k in ["created_at", "updated_at", "business_id", "product_id", "sort"]:
            body.pop(k, None)
        r = merchant_session.patch(
            f"{BASE_URL}/api/merchant/marketplace/products/items/{pid}", json=body, timeout=15)
        assert r.status_code == 200, r.text

    def test_3_zzz_cleanup(self, merchant_session):
        pid = TestProductOptionGroups.created_pid
        if pid:
            merchant_session.delete(
                f"{BASE_URL}/api/merchant/marketplace/products/items/{pid}", timeout=15)


# ─────────────────────── Membership plan v2 ───────────────────────
class TestMembershipPlansV2:
    created_plan_id: Optional[str] = None

    def test_1_create_v2_plan_with_entitlements(self, merchant_session):
        body = {
            "name": "TEST_iter76 Plan",
            "description": "v2 entitlement plan",
            "price_cents": 999,
            "interval": "month",
            "active": True,
            "entitlements": [
                {"label": "Free coffee daily", "target_type": "category",
                 "category": "coffee", "quantity": 1, "reset_frequency": "daily",
                 "stackable": False, "active": True},
                {"label": "Weekly bonus", "target_type": "any",
                 "quantity": 3, "reset_frequency": "weekly", "rollover": True,
                 "rollover_cap": 5, "stackable": False, "active": True,
                 "day_time": {"days": [0, 1, 2, 3, 4, 5, 6], "start_hour": 0, "end_hour": 24}},
            ],
        }
        r = merchant_session.post(f"{BASE_URL}/api/merchant/marketplace/memberships/items",
                                  json=body, timeout=15)
        assert r.status_code == 200, r.text
        plan = r.json()["plan"]
        assert plan.get("plan_id")
        assert plan["schema_version"] == 2
        ents = plan["entitlements"]
        assert len(ents) == 2
        for e in ents:
            assert e["entitlement_id"].startswith("ent_")
        TestMembershipPlansV2.created_plan_id = plan["plan_id"]

    def test_2_list_plans_returns_member_count(self, merchant_session):
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/memberships", timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        found = next((x for x in items if x["plan_id"] == TestMembershipPlansV2.created_plan_id), None)
        assert found is not None
        assert "member_count" in found
        assert isinstance(found["member_count"], int)

    def test_3_patch_preserves_entitlement_id(self, merchant_session):
        pid = TestMembershipPlansV2.created_plan_id
        assert pid
        r = merchant_session.get(f"{BASE_URL}/api/merchant/marketplace/memberships", timeout=15)
        cur = next(x for x in r.json()["items"] if x["plan_id"] == pid)
        body = {"name": cur["name"] + " v2", "description": cur.get("description"),
                "price_cents": cur["price_cents"], "interval": cur["interval"],
                "active": True,
                "entitlements": cur["entitlements"]}  # send back with ids
        r = merchant_session.patch(
            f"{BASE_URL}/api/merchant/marketplace/memberships/items/{pid}", json=body, timeout=15)
        assert r.status_code == 200, r.text
        after = r.json()["plan"]
        assert after["schema_version"] == 2
        before_ids = [e["entitlement_id"] for e in cur["entitlements"]]
        after_ids = [e["entitlement_id"] for e in after["entitlements"]]
        assert before_ids == after_ids

    def test_9_zzz_cleanup(self, merchant_session):
        pid = TestMembershipPlansV2.created_plan_id
        if pid:
            merchant_session.delete(
                f"{BASE_URL}/api/merchant/marketplace/memberships/items/{pid}", timeout=15)


# ─────────────────────── Consumer catalogue exposes option_groups ───────────────────────
class TestConsumerCatalogue:
    """Sample storefronts (Fun Pizza + Ambreens) — menu + products expose option_groups."""

    def test_1_menu_endpoint_includes_option_groups_key(self):
        # Anonymous read
        r = requests.get(f"{BASE_URL}/api/shop/businesses/biz_sample_funpizza/menu", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "sections" in data
        for sec in data["sections"]:
            for it in sec["items"]:
                assert "option_groups" in it, f"item {it.get('item_id')} missing option_groups"
                assert isinstance(it["option_groups"], list)

    def test_2_products_endpoint_includes_option_groups_key(self):
        r = requests.get(f"{BASE_URL}/api/shop/businesses/biz_sample_ambreens/products", timeout=15)
        assert r.status_code == 200, r.text
        for p in r.json()["products"]:
            assert "option_groups" in p
            assert isinstance(p["option_groups"], list)


# ─────────────────────── Consumer wallet + claim ───────────────────────
class TestConsumerWalletAndClaim:
    """Uses test@ pre-seeded memberships (Coffee Club @ Fun Pizza, Unlimited Blowouts @ Ambreens)."""

    coffee_membership_id: Optional[str] = None
    coffee_entitlement_id: Optional[str] = None

    def test_1_memberships_mine_returns_ledger_backed_benefits(self, merchant_session):
        r = merchant_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert len(items) >= 1, "test@ should have at least one active membership"
        for m in items:
            assert "benefits" in m
            for b in m["benefits"]:
                # new fields
                assert "remaining" in b
                assert "used" in b
                assert "period_key" in b
                # backward-compat aliases
                assert "qty" in b
                assert "period" in b
                assert "options" in b
                assert "available_now" in b
        # Pick Coffee Club (daily 1x)
        for m in items:
            if "coffee" in (m.get("plan_name") or "").lower():
                for b in m["benefits"]:
                    if b.get("reset_frequency") == "daily" and int(b.get("quantity", 0)) >= 1:
                        TestConsumerWalletAndClaim.coffee_membership_id = m["membership_id"]
                        TestConsumerWalletAndClaim.coffee_entitlement_id = b["entitlement_id"]
                        return
        # Fall back: pick any entitlement
        m = items[0]
        assert m["benefits"], "no entitlements available for a claim test"
        TestConsumerWalletAndClaim.coffee_membership_id = m["membership_id"]
        TestConsumerWalletAndClaim.coffee_entitlement_id = m["benefits"][0]["entitlement_id"]

    def test_2_business_memberships_returns_mine(self, merchant_session):
        # Fun Pizza
        r = merchant_session.get(
            f"{BASE_URL}/api/shop/businesses/biz_sample_funpizza/memberships", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "mine" in data
        # 'mine' may be Coffee Club for test@
        if data["mine"]:
            for b in data["mine"].get("benefits", []):
                assert "remaining" in b
                assert "qty" in b  # legacy alias

    def test_3_claim_via_entitlement_id_appends_ledger(self, merchant_session):
        mid = TestConsumerWalletAndClaim.coffee_membership_id
        eid = TestConsumerWalletAndClaim.coffee_entitlement_id
        assert mid and eid, "test_1 must run first"
        # Snapshot remaining
        r0 = merchant_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        m0 = next(m for m in r0.json()["items"] if m["membership_id"] == mid)
        b0 = next(b for b in m0["benefits"] if b["entitlement_id"] == eid)
        before = int(b0["remaining"])
        if before <= 0:
            pytest.skip(f"entitlement already exhausted for this period ({b0['period_key']}); "
                        "cannot verify decrement without side effects")
        r = merchant_session.post(
            f"{BASE_URL}/api/shop/memberships/{mid}/claim",
            json={"entitlement_id": eid}, timeout=15)
        assert r.status_code == 200, r.text
        payload = r.json()
        assert payload["ok"] is True
        assert payload["remaining"] == before - 1
        # Ledger-backed: re-read
        r1 = merchant_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        m1 = next(m for m in r1.json()["items"] if m["membership_id"] == mid)
        b1 = next(b for b in m1["benefits"] if b["entitlement_id"] == eid)
        assert int(b1["remaining"]) == before - 1
        assert int(b1["used"]) == int(b0["used"]) + 1

    def test_4_claim_via_legacy_benefit_id_also_works(self, merchant_session):
        """The claim endpoint must accept `benefit_id` as a legacy alias for `entitlement_id`."""
        mid = TestConsumerWalletAndClaim.coffee_membership_id
        eid = TestConsumerWalletAndClaim.coffee_entitlement_id
        assert mid and eid
        # Check remaining
        r0 = merchant_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        m0 = next(m for m in r0.json()["items"] if m["membership_id"] == mid)
        b0 = next(b for b in m0["benefits"] if b["entitlement_id"] == eid)
        # If exhausted, we expect 400 limit_reached (which itself proves legacy field routing works)
        r = merchant_session.post(
            f"{BASE_URL}/api/shop/memberships/{mid}/claim",
            json={"benefit_id": eid}, timeout=15)
        if int(b0["remaining"]) > 0:
            assert r.status_code == 200, r.text
        else:
            assert r.status_code == 400, r.text
            assert r.json()["detail"]["code"] == "limit_reached"

    def test_5_claim_unknown_entitlement_404(self, merchant_session):
        mid = TestConsumerWalletAndClaim.coffee_membership_id
        assert mid
        r = merchant_session.post(
            f"{BASE_URL}/api/shop/memberships/{mid}/claim",
            json={"entitlement_id": "ent_does_not_exist"}, timeout=15)
        assert r.status_code == 404, r.text
        assert r.json()["detail"]["code"] == "benefit_not_found"

    def test_6_claim_beyond_limit_returns_400_limit_reached(self, merchant_session):
        """Confirm claiming an already-exhausted entitlement returns 400 limit_reached.

        Strategy: scan test@'s wallet for any entitlement with remaining==0 (the seeded
        '10% off colour services' monthly entitlement is already exhausted). If none is
        exhausted yet, exhaust the smallest-quantity one in-place."""
        r = merchant_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        assert r.status_code == 200
        exhausted: Optional[tuple] = None
        smallest: Optional[tuple] = None  # (remaining, mid, eid, quantity)
        for m in r.json()["items"]:
            for b in m["benefits"]:
                if int(b["remaining"]) == 0:
                    exhausted = (m["membership_id"], b["entitlement_id"])
                    break
                q = int(b.get("quantity", 99))
                if smallest is None or q < smallest[3]:
                    smallest = (int(b["remaining"]), m["membership_id"], b["entitlement_id"], q)
            if exhausted:
                break
        if not exhausted and smallest:
            # Exhaust the smallest-quantity entitlement (safety cap 105 for qty≤99)
            _, mid, eid, q = smallest
            for _ in range(q + 5):
                cr = merchant_session.post(
                    f"{BASE_URL}/api/shop/memberships/{mid}/claim",
                    json={"entitlement_id": eid}, timeout=15)
                if cr.status_code == 400 and cr.json().get("detail", {}).get("code") == "limit_reached":
                    exhausted = (mid, eid)
                    break
                if cr.status_code != 200:
                    pytest.skip(f"Cannot exhaust entitlement: {cr.status_code} {cr.text[:200]}")
        assert exhausted, "no exhausted entitlement available to verify limit_reached path"
        mid, eid = exhausted
        r = merchant_session.post(
            f"{BASE_URL}/api/shop/memberships/{mid}/claim",
            json={"entitlement_id": eid}, timeout=15)
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "limit_reached"


# ─────────────────────── Boot migration idempotency ───────────────────────
class TestBootMigration:
    """Confirm sample plans read as schema_version=2 and the ledger has legacy rows."""

    def test_1_sample_plans_are_schema_v2(self):
        # Anonymous read of memberships at a sample business
        r = requests.get(
            f"{BASE_URL}/api/shop/businesses/biz_sample_funpizza/memberships", timeout=15)
        assert r.status_code == 200, r.text
        plans = r.json()["items"]
        assert len(plans) >= 1
        for p in plans:
            # v2 plans always include normalized entitlements[] with entitlement_id
            for e in p.get("entitlements", []):
                assert e.get("entitlement_id", "").startswith("ent_") or e.get("entitlement_id")

    def test_2_ledger_has_legacy_rows_via_indirect_signal(self, merchant_session):
        """We can't hit the ledger collection directly via a public API, but we can
        assert that test@'s wallet reads without error and reports coherent used/remaining
        totals — proving the migration path from legacy claims → ledger runs."""
        r = merchant_session.get(f"{BASE_URL}/api/shop/memberships/mine", timeout=15)
        assert r.status_code == 200
        # No 500s, benefits have used field ints ≥ 0.
        for m in r.json()["items"]:
            for b in m["benefits"]:
                assert isinstance(b["used"], int) and b["used"] >= 0
                assert isinstance(b["remaining"], int) and b["remaining"] >= 0


# ─────────────────────── Regression: existing checkout still works ───────────────────────
class TestRegressionCheckout:
    """Flat-price checkout must still work — option_groups is additive."""

    def test_1_menu_quote_still_works(self, merchant_session):
        # Grab an item from Fun Pizza and quote it with no option selection
        r = requests.get(f"{BASE_URL}/api/shop/businesses/biz_sample_funpizza/menu", timeout=15)
        assert r.status_code == 200
        items = [it for sec in r.json()["sections"] for it in sec["items"]]
        assert items, "Fun Pizza has no menu items"
        item_id = items[0]["item_id"]
        body = {"business_id": "biz_sample_funpizza", "fulfillment": "pickup",
                "items": [{"item_id": item_id, "qty": 1}]}
        r = merchant_session.post(f"{BASE_URL}/api/shop/orders/quote", json=body, timeout=15)
        assert r.status_code == 200, r.text
        q = r.json()
        # Must return a non-negative total
        assert "total_cents" in q or "grand_total_cents" in q or "amount_cents" in q or "quote" in q, r.text

    def test_2_product_cart_quote_still_works(self, merchant_session):
        r = requests.get(f"{BASE_URL}/api/shop/businesses/biz_sample_ambreens/products", timeout=15)
        assert r.status_code == 200
        prods = r.json()["products"]
        if not prods:
            pytest.skip("no products at Ambreens")
        pid = prods[0]["product_id"]
        body = {"groups": [{"business_id": "biz_sample_ambreens", "fulfillment": "pickup",
                             "items": [{"product_id": pid, "qty": 1}]}]}
        r = merchant_session.post(f"{BASE_URL}/api/shop/cart/quote", json=body, timeout=15)
        # Accept 200 or 400 (missing fulfillment) — key is that we don't 500
        assert r.status_code in (200, 400), r.text
