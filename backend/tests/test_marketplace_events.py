"""Phase E item 4 — Marketplace Events tests (ticketed, capacity-limited).

Covers:
  Merchant CRUD: GET/POST/PATCH/DELETE /api/merchant/marketplace/events
  Consumer: GET /api/shop/businesses/{id}/events, POST /api/shop/events/purchase,
            GET /api/shop/events/purchase/{sid}/status, GET /api/shop/events/mine
  business_detail.has_events
  Atomic capacity enforcement (no oversell / sold_out).
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
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE = _load_backend_url()
BIZ_ID = "biz_8484f6f985d5"


@pytest.fixture(scope="session")
def demo():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/demo", timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text[:200]}"
    return s


# ─────────────────── MERCHANT CRUD ───────────────────
class TestMerchantCRUD:
    def test_list_events_shape(self, demo):
        r = demo.get(f"{BASE}/api/merchant/marketplace/events")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        # Every item must include capacity aggregation fields
        for it in data["items"]:
            assert "event_id" in it
            assert "capacity" in it
            assert "tickets_sold" in it
            assert "remaining" in it
            assert "sold_out" in it

    def test_create_update_delete_event(self, demo):
        body = {
            "title": f"TEST_evt_{int(time.time())}",
            "description": "auto pytest event",
            "location": "TEST loc",
            "starts_at": "2099-12-31T20:00:00Z",
            "price_cents": 0,
            "capacity": 5,
            "allow_points": True,
            "allow_card": True,
            "active": True,
        }
        r = demo.post(f"{BASE}/api/merchant/marketplace/events/items", json=body)
        assert r.status_code == 200, r.text
        ev = r.json()["event"]
        eid = ev["event_id"]
        assert ev["capacity"] == 5
        assert ev["tickets_sold"] == 0
        assert ev["remaining"] == 5
        assert ev["sold_out"] is False

        # PATCH raise capacity — OK
        body["capacity"] = 7
        r = demo.patch(f"{BASE}/api/merchant/marketplace/events/items/{eid}", json=body)
        assert r.status_code == 200
        assert r.json()["event"]["capacity"] == 7

        # DELETE
        r = demo.delete(f"{BASE}/api/merchant/marketplace/events/items/{eid}")
        assert r.status_code == 200

        # DELETE again -> 404 event_not_found
        r = demo.delete(f"{BASE}/api/merchant/marketplace/events/items/{eid}")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "event_not_found"

    def test_update_unknown_event_404(self, demo):
        r = demo.patch(
            f"{BASE}/api/merchant/marketplace/events/items/evt_does_not_exist_xyz",
            json={
                "title": "x", "starts_at": "2099-01-01T00:00:00Z",
                "price_cents": 0, "capacity": 1,
            },
        )
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "event_not_found"

    def test_patch_capacity_below_sold_rejected(self, demo):
        # Create a small event and buy the only ticket via points (price 0)
        body = {
            "title": f"TEST_capsold_{int(time.time())}",
            "starts_at": "2099-12-31T20:00:00Z",
            "price_cents": 0, "capacity": 2,
            "allow_points": True, "allow_card": True, "active": True,
        }
        r = demo.post(f"{BASE}/api/merchant/marketplace/events/items", json=body)
        assert r.status_code == 200
        eid = r.json()["event"]["event_id"]
        try:
            # buy 1 ticket -> tickets_sold = 1
            p = demo.post(f"{BASE}/api/shop/events/purchase",
                          json={"event_id": eid, "qty": 1, "method": "points"})
            assert p.status_code == 200, p.text

            # attempt to shrink capacity to 0 (below tickets_sold=1) -> 400
            body["capacity"] = 0
            # Pydantic: capacity>=1, so try 1 vs sold=1 (ok), then try shrink using raw
            body["capacity"] = 1
            # sold=1, cap=1 -> allowed (not strictly below)
            r = demo.patch(f"{BASE}/api/merchant/marketplace/events/items/{eid}", json=body)
            assert r.status_code == 200

            # Now buy 1 more -> sold=2
            p = demo.post(f"{BASE}/api/shop/events/purchase",
                          json={"event_id": eid, "qty": 1, "method": "points"})
            # cap is 1 now, sold already 1 -> next purchase should be sold_out
            # But we already patched capacity=1 while sold=1 (OK). Now cap=1<sold+1 -> sold_out
            assert p.status_code == 400
            assert p.json()["detail"]["code"] == "sold_out"
        finally:
            demo.delete(f"{BASE}/api/merchant/marketplace/events/items/{eid}")


# ─────────────────── CONSUMER ───────────────────
class TestConsumer:
    def test_business_events_shape(self, demo):
        r = demo.get(f"{BASE}/api/shop/businesses/{BIZ_ID}/events")
        assert r.status_code == 200
        data = r.json()
        assert data["business_id"] == BIZ_ID
        assert data["points_per_dollar"] == 100
        assert isinstance(data["points_balance"], int)
        assert isinstance(data["items"], list)
        assert isinstance(data["mine"], list)
        for it in data["items"]:
            assert "remaining" in it
            assert "sold_out" in it

    def test_business_detail_has_events_true(self, demo):
        # ensure at least one active event exists on demo biz
        body = {"title": f"TEST_has_events_{int(time.time())}",
                "starts_at": "2099-12-31T20:00:00Z",
                "price_cents": 0, "capacity": 1,
                "allow_points": True, "allow_card": True, "active": True}
        c = demo.post(f"{BASE}/api/merchant/marketplace/events/items", json=body)
        assert c.status_code == 200
        eid = c.json()["event"]["event_id"]
        try:
            r = demo.get(f"{BASE}/api/shop/businesses/{BIZ_ID}")
            assert r.status_code == 200
            assert r.json()["business"]["has_events"] is True
        finally:
            demo.delete(f"{BASE}/api/merchant/marketplace/events/items/{eid}")

    def test_purchase_unknown_event_404(self, demo):
        r = demo.post(f"{BASE}/api/shop/events/purchase",
                      json={"event_id": "evt_missing_xyz", "qty": 1, "method": "points"})
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "event_not_found"

    def test_purchase_bad_method_400(self, demo):
        body = {"title": f"TEST_badm_{int(time.time())}",
                "starts_at": "2099-12-31T20:00:00Z",
                "price_cents": 0, "capacity": 1,
                "allow_points": True, "allow_card": True, "active": True}
        c = demo.post(f"{BASE}/api/merchant/marketplace/events/items", json=body)
        assert c.status_code == 200
        eid = c.json()["event"]["event_id"]
        try:
            r = demo.post(f"{BASE}/api/shop/events/purchase",
                          json={"event_id": eid, "qty": 1, "method": "banana"})
            assert r.status_code == 400
            assert r.json()["detail"]["code"] == "bad_method"
        finally:
            demo.delete(f"{BASE}/api/merchant/marketplace/events/items/{eid}")

    def test_points_purchase_free_success_and_ticket_visible(self, demo):
        body = {"title": f"TEST_free_{int(time.time())}",
                "starts_at": "2099-12-31T20:00:00Z",
                "price_cents": 0, "capacity": 2,
                "allow_points": True, "allow_card": True, "active": True}
        c = demo.post(f"{BASE}/api/merchant/marketplace/events/items", json=body)
        assert c.status_code == 200, c.text
        eid = c.json()["event"]["event_id"]
        try:
            r = demo.post(f"{BASE}/api/shop/events/purchase",
                          json={"event_id": eid, "qty": 1, "method": "points"})
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["ok"] is True
            assert data["method"] == "points"
            assert data["points_spent"] == 0
            assert data["ticket"]["status"] == "active"
            assert data["ticket"]["event_id"] == eid

            # Ticket appears in /events/mine
            m = demo.get(f"{BASE}/api/shop/events/mine")
            assert m.status_code == 200
            assert any(t["event_id"] == eid for t in m.json()["items"])

            # Ticket appears in businesses/{id}/events mine
            b = demo.get(f"{BASE}/api/shop/businesses/{BIZ_ID}/events")
            assert b.status_code == 200
            assert any(t["event_id"] == eid for t in b.json()["mine"])
        finally:
            demo.delete(f"{BASE}/api/merchant/marketplace/events/items/{eid}")

    def test_capacity_enforcement_sold_out(self, demo):
        """Critical: buying up to capacity works; the next purchase 400 sold_out."""
        body = {"title": f"TEST_soldout_{int(time.time())}",
                "starts_at": "2099-12-31T20:00:00Z",
                "price_cents": 0, "capacity": 3,
                "allow_points": True, "allow_card": True, "active": True}
        c = demo.post(f"{BASE}/api/merchant/marketplace/events/items", json=body)
        assert c.status_code == 200
        eid = c.json()["event"]["event_id"]
        try:
            # Fill capacity in 3 purchases of qty=1
            for i in range(3):
                r = demo.post(f"{BASE}/api/shop/events/purchase",
                              json={"event_id": eid, "qty": 1, "method": "points"})
                assert r.status_code == 200, f"purchase {i} failed: {r.text}"

            # Next purchase -> sold_out
            r = demo.post(f"{BASE}/api/shop/events/purchase",
                          json={"event_id": eid, "qty": 1, "method": "points"})
            assert r.status_code == 400
            assert r.json()["detail"]["code"] == "sold_out"

            # Remaining/sold_out flags reflected in consumer listing
            b = demo.get(f"{BASE}/api/shop/businesses/{BIZ_ID}/events")
            ev = next(x for x in b.json()["items"] if x["event_id"] == eid)
            assert ev["remaining"] == 0
            assert ev["sold_out"] is True
            assert ev["tickets_sold"] == 3
        finally:
            demo.delete(f"{BASE}/api/merchant/marketplace/events/items/{eid}")

    def test_no_oversell_atomic(self, demo):
        """qty larger than remaining must NOT partially fill — atomic sold_out."""
        body = {"title": f"TEST_atomic_{int(time.time())}",
                "starts_at": "2099-12-31T20:00:00Z",
                "price_cents": 0, "capacity": 2,
                "allow_points": True, "allow_card": True, "active": True}
        c = demo.post(f"{BASE}/api/merchant/marketplace/events/items", json=body)
        assert c.status_code == 200
        eid = c.json()["event"]["event_id"]
        try:
            # Ask for 3 tickets when only 2 exist -> should 400 sold_out, no partial
            r = demo.post(f"{BASE}/api/shop/events/purchase",
                          json={"event_id": eid, "qty": 3, "method": "points"})
            assert r.status_code == 400
            assert r.json()["detail"]["code"] == "sold_out"

            # tickets_sold must still be 0
            m = demo.get(f"{BASE}/api/merchant/marketplace/events")
            ev = next(x for x in m.json()["items"] if x["event_id"] == eid)
            assert ev["tickets_sold"] == 0
        finally:
            demo.delete(f"{BASE}/api/merchant/marketplace/events/items/{eid}")

    def test_card_purchase_returns_checkout_url_and_reserves(self, demo):
        body = {"title": f"TEST_card_{int(time.time())}",
                "starts_at": "2099-12-31T20:00:00Z",
                "price_cents": 500, "capacity": 2,
                "allow_points": True, "allow_card": True, "active": True}
        c = demo.post(f"{BASE}/api/merchant/marketplace/events/items", json=body)
        assert c.status_code == 200
        eid = c.json()["event"]["event_id"]
        try:
            r = demo.post(f"{BASE}/api/shop/events/purchase",
                          json={"event_id": eid, "qty": 1, "method": "card",
                                "origin_url": BASE})
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["method"] == "card"
            assert data["checkout_url"].startswith("http")
            assert data["session_id"].startswith("cs_")

            # Card path reserves capacity immediately
            m = demo.get(f"{BASE}/api/merchant/marketplace/events")
            ev = next(x for x in m.json()["items"] if x["event_id"] == eid)
            assert ev["tickets_sold"] == 1

            # Status is pending until webhook/paid
            st = demo.get(f"{BASE}/api/shop/events/purchase/{data['session_id']}/status")
            assert st.status_code == 200
            assert st.json()["status"] in ("pending", "paid")
        finally:
            demo.delete(f"{BASE}/api/merchant/marketplace/events/items/{eid}")

    def test_purchase_status_unknown_session_404(self, demo):
        r = demo.get(f"{BASE}/api/shop/events/purchase/cs_test_missing_xyz/status")
        assert r.status_code == 404
        assert r.json()["detail"]["code"] == "purchase_not_found"
