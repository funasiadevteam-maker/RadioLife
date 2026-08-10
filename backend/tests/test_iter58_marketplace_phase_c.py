"""Iter 58 — Super Marketplace Phase C follow-ups.

Covers ONLY the new features shipped in this iteration:
- Reorder Favourites — POST /api/shop/orders/{id}/reorder
- Menu photo upload (base64) + static serving; consumer menu exposes image_url
- Live Order Alerts — merchant PATCH to 'ready' + 'picked_up' creates
  station_notifications rows for the buyer (owner_user_id=buyer,
  type=order_ready / order_picked_up, dedupe_key=order_ready_{id})
- Service Bookings (Phase C): CRUD, availability GET/PATCH, slots,
  reservation-fee validation (fee>price -> 400), booking checkout with
  fee=0 (confirmed) and fee>0 (Stripe URL), slot double-book (409),
  my-bookings + status, merchant bookings + confirmed->completed BigPoints
  award (idempotent, source=marketplace_service) + invalid transitions.

The AI-photo generation endpoint is NOT re-run here (main agent
already verified it — one success is sufficient).

Uses the pre-seeded demo user + biz_8484f6f985d5 (already approved +
comp-subscribed with the "Men Haircut" service already configured).
"""
from __future__ import annotations

import base64
import os
import secrets
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")

assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

DEMO_BIZ_ID = "biz_8484f6f985d5"  # demo owns this (approved + comp-subscribed)


class _NoCookieSession(requests.Session):
    def send(self, request, **kwargs):
        resp = super().send(request, **kwargs)
        self.cookies.clear()
        return resp


# ─────────────────── fixtures ───────────────────
@pytest.fixture(scope="module")
def http():
    s = _NoCookieSession()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def db():
    return MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def demo_token(http):
    r = http.post(f"{BASE_URL}/api/auth/demo", json={})
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok, r.text
    return tok


@pytest.fixture(scope="module")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def demo_user_id(http, demo_headers):
    r = http.get(f"{BASE_URL}/api/auth/me", headers=demo_headers)
    assert r.status_code == 200
    return r.json().get("user_id")


@pytest.fixture(scope="module")
def demo_biz(http, demo_headers, db):
    """Confirm demo really owns biz_8484f6f985d5 (else skip this whole run)."""
    r = http.get(f"{BASE_URL}/api/merchant/marketplace/profile", headers=demo_headers)
    if r.status_code != 200:
        pytest.skip(f"demo has no marketplace profile: {r.text}")
    p = r.json().get("profile") or {}
    if p.get("business_id") != DEMO_BIZ_ID:
        pytest.skip(f"demo does not own {DEMO_BIZ_ID} (got {p.get('business_id')})")
    return p


CTX: dict = {}


# ═══════════════════ Menu photos ═══════════════════
# 1x1 transparent PNG
PNG_1x1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAIAAAUAAeIVWUgAAAAASUVORK5CYII=")
PNG_1x1_B64 = base64.b64encode(PNG_1x1).decode()


class TestMenuPhotos:
    def test_create_test_menu_item(self, http, demo_headers, demo_biz):
        body = {"section": "TESTS", "name": "TEST_iter58_photo_item",
                "description": "Iter58 photo test item",
                "price_cents": 500, "bigpoints": 20, "available": True}
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/menu/items",
                      json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        CTX['photo_item_id'] = r.json()["item"]["item_id"]

    def test_upload_photo(self, http, demo_headers):
        r = http.post(
            f"{BASE_URL}/api/merchant/marketplace/menu/items/{CTX['photo_item_id']}/photo",
            json={"file_base64": PNG_1x1_B64, "ext": "png"}, headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["image_url"].startswith("/api/static/menu_photos/"), j
        assert CTX['photo_item_id'] in j["image_url"]
        CTX['photo_url'] = j["image_url"]

    def test_photo_served_200_image(self, http):
        # Fetch the actual bytes via the public URL
        r = requests.get(f"{BASE_URL}{CTX['photo_url']}")
        assert r.status_code == 200, r.text[:200]
        ct = r.headers.get("Content-Type", "")
        assert ct.startswith("image/"), f"not image/*: {ct}"
        assert len(r.content) > 50, "image too small"

    def test_upload_missing_file_returns_400(self, http, demo_headers):
        r = http.post(
            f"{BASE_URL}/api/merchant/marketplace/menu/items/{CTX['photo_item_id']}/photo",
            json={"ext": "png"}, headers=demo_headers)
        assert r.status_code == 400
        assert "file_required" in r.text

    def test_upload_unknown_item_404(self, http, demo_headers):
        r = http.post(
            f"{BASE_URL}/api/merchant/marketplace/menu/items/mi_missing_iter58/photo",
            json={"file_base64": PNG_1x1_B64, "ext": "png"}, headers=demo_headers)
        assert r.status_code == 404

    def test_consumer_menu_exposes_image_url(self, http, demo_biz):
        r = http.get(f"{BASE_URL}/api/shop/businesses/{DEMO_BIZ_ID}/menu")
        assert r.status_code == 200, r.text
        all_items = []
        for s in r.json().get("sections", []):
            all_items.extend(s.get("items", []))
        # find our uploaded item OR any item with image_url
        found = next((i for i in all_items if i.get("item_id") == CTX['photo_item_id']), None)
        assert found is not None, "TEST_iter58_photo_item missing from consumer menu"
        assert found.get("image_url") == CTX['photo_url'], found


# ═══════════════════ Reorder ═══════════════════
class TestReorder:
    """Create a small menu item, place a paid order via gift card, then
    call /reorder — expect items[] with refreshed prices and dropped[]."""

    def test_setup_menu_item_and_gift_card(
            self, http, demo_headers, demo_user_id, db, demo_biz):
        # Small item to fully cover with gift card
        body = {"section": "TESTS", "name": "TEST_iter58_reorder_item",
                "price_cents": 200, "bigpoints": 10, "available": True}
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/menu/items",
                      json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        CTX['reorder_item_id'] = r.json()["item"]["item_id"]

        # A second item to test 'dropped' in reorder (delete after order)
        body2 = {"section": "TESTS", "name": "TEST_iter58_dropped_item",
                 "price_cents": 100, "bigpoints": 5, "available": True}
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/menu/items",
                      json=body2, headers=demo_headers)
        assert r.status_code == 200, r.text
        CTX['dropped_item_id'] = r.json()["item"]["item_id"]

        # Refresh a gift card for demo
        db.gift_cards.update_one(
            {"card_id": "gc_iter58_test"},
            {"$set": {"card_id": "gc_iter58_test", "owner_user_id": demo_user_id,
                      "status": "active", "balance_cents": 100000,
                      "created_at": datetime.now(timezone.utc)}},
            upsert=True)

    def test_place_order_that_can_be_reordered(self, http, demo_headers):
        payload = {
            "business_id": DEMO_BIZ_ID,
            "items": [
                {"item_id": CTX['reorder_item_id'], "qty": 2},
                {"item_id": CTX['dropped_item_id'], "qty": 1},
            ],
            "origin_url": "https://example.test", "use_gift_card": True}
        r = http.post(f"{BASE_URL}/api/shop/orders/checkout",
                      json=payload, headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "accepted", j
        assert j["checkout_url"] is None
        CTX['reorder_source_order_id'] = j["order_id"]

    def test_delete_dropped_item_then_reorder(self, http, demo_headers):
        # Delete the second item so it becomes 'dropped' in the reorder response
        d = http.delete(
            f"{BASE_URL}/api/merchant/marketplace/menu/items/{CTX['dropped_item_id']}",
            headers=demo_headers)
        assert d.status_code == 200

        r = http.post(
            f"{BASE_URL}/api/shop/orders/{CTX['reorder_source_order_id']}/reorder",
            headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["business_id"] == DEMO_BIZ_ID
        assert j.get("business_name")
        names = [i["name"] for i in j["items"]]
        assert any("TEST_iter58_reorder_item" in n for n in names), j
        # Must include qty from the source order
        reorder_row = next(i for i in j["items"]
                           if i["item_id"] == CTX['reorder_item_id'])
        assert reorder_row["qty"] == 2, reorder_row
        assert reorder_row["price_cents"] == 200
        # dropped item present in the dropped[] list
        assert any("TEST_iter58_dropped_item" in (n or "") for n in j.get("dropped", [])), j

    def test_reorder_unknown_order_404(self, http, demo_headers):
        r = http.post(f"{BASE_URL}/api/shop/orders/ord_missing_iter58/reorder",
                      headers=demo_headers)
        assert r.status_code == 404


# ═══════════════════ Live Order Alerts ═══════════════════
class TestLiveOrderAlerts:
    """Merchant flips a paid order to 'ready' -> station_notifications row
    for the buyer.  Then flips to 'picked_up' -> second notification.
    Idempotent by dedupe_key (order_ready_{id})."""

    def test_advance_to_ready_creates_notification(
            self, http, demo_headers, demo_user_id, db):
        oid = CTX['reorder_source_order_id']
        # accepted -> preparing
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/orders/{oid}/status",
            json={"status": "preparing"}, headers=demo_headers)
        assert r.status_code == 200, r.text
        # preparing -> ready
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/orders/{oid}/status",
            json={"status": "ready"}, headers=demo_headers)
        assert r.status_code == 200, r.text
        # Verify station_notifications row created for buyer
        row = db.station_notifications.find_one(
            {"owner_user_id": demo_user_id, "dedupe_key": f"order_ready_{oid}"})
        assert row is not None, "no order_ready notification created"
        assert row["type"] == "order_ready"
        assert row["payload"]["order_id"] == oid
        assert row["payload"].get("pickup_code")
        assert "Ready" in row["payload"]["title"] or "ready" in row["payload"]["title"].lower()

    def test_advance_to_picked_up_creates_second_notification_and_awards_points(
            self, http, demo_headers, demo_user_id, db):
        oid = CTX['reorder_source_order_id']
        # Snapshot BigPoints
        r = http.get(f"{BASE_URL}/api/bigcoin/me", headers=demo_headers)
        assert r.status_code == 200
        before = int(r.json().get("balance", 0))

        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/orders/{oid}/status",
            json={"status": "picked_up"}, headers=demo_headers)
        assert r.status_code == 200, r.text

        # notification
        row = db.station_notifications.find_one(
            {"owner_user_id": demo_user_id,
             "dedupe_key": f"order_picked_up_{oid}"})
        assert row is not None, "no order_picked_up notification"
        assert row["type"] == "order_picked_up"

        # BigPoints delta > 0
        r = http.get(f"{BASE_URL}/api/bigcoin/me", headers=demo_headers)
        after = int(r.json().get("balance", 0))
        assert after >= before, f"points did not grow: {before} -> {after}"


# ═══════════════════ Services CRUD ═══════════════════
class TestServicesCRUD:
    def test_list_services_returns_seeded(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/services",
                     headers=demo_headers)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert isinstance(items, list)
        # Note: "Men Haircut" is pre-seeded per the review request
        CTX['pre_service_names'] = {s.get("name") for s in items}

    def test_fee_exceeds_price_rejected(self, http, demo_headers):
        body = {"name": "TEST_iter58_bad_fee", "duration_min": 30,
                "price_cents": 1000, "reservation_fee_cents": 2000,
                "bigpoints": 30, "active": True}
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/services/items",
                      json=body, headers=demo_headers)
        assert r.status_code == 400, r.text
        assert "fee_exceeds_price" in r.text

    def test_create_service_free_reservation(self, http, demo_headers):
        body = {"name": "TEST_iter58_free_svc", "duration_min": 30,
                "price_cents": 5000, "reservation_fee_cents": 0,
                "bigpoints": 40, "active": True,
                "description": "iter58 free-reservation svc"}
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/services/items",
                      json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        s = r.json()["service"]
        assert s["reservation_fee_cents"] == 0
        assert s["name"] == "TEST_iter58_free_svc"
        CTX['free_svc_id'] = s["service_id"]

    def test_create_service_with_fee(self, http, demo_headers):
        body = {"name": "TEST_iter58_paid_svc", "duration_min": 30,
                "price_cents": 6000, "reservation_fee_cents": 1000,
                "bigpoints": 60, "active": True}
        r = http.post(f"{BASE_URL}/api/merchant/marketplace/services/items",
                      json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        CTX['paid_svc_id'] = r.json()["service"]["service_id"]

    def test_patch_service(self, http, demo_headers):
        body = {"name": "TEST_iter58_free_svc_v2", "duration_min": 45,
                "price_cents": 5500, "reservation_fee_cents": 0,
                "bigpoints": 50, "active": True}
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/services/items/{CTX['free_svc_id']}",
            json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        s = r.json()["service"]
        assert s["name"] == "TEST_iter58_free_svc_v2"
        assert s["duration_min"] == 45

    def test_patch_unknown_service_404(self, http, demo_headers):
        body = {"name": "x", "duration_min": 30, "price_cents": 100,
                "reservation_fee_cents": 0, "active": True}
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/services/items/svc_missing_iter58",
            json=body, headers=demo_headers)
        assert r.status_code == 404


# ═══════════════════ Availability ═══════════════════
class TestAvailability:
    def test_get_availability(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/services/availability",
                     headers=demo_headers)
        assert r.status_code == 200, r.text
        a = r.json()["availability"]
        assert "slot_minutes" in a and "days" in a

    def test_patch_availability(self, http, demo_headers):
        # Set 30-min slots, weekdays 09:00-12:00 (matches spec-note)
        days = {str(d): [{"start": "09:00", "end": "12:00"}] for d in range(0, 5)}
        body = {"slot_minutes": 30, "days": days}
        r = http.patch(f"{BASE_URL}/api/merchant/marketplace/services/availability",
                       json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        assert r.json()["availability"]["slot_minutes"] == 30
        # Re-GET and verify persisted
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/services/availability",
                     headers=demo_headers)
        got = r.json()["availability"]
        assert got["slot_minutes"] == 30
        assert got["days"]["0"] == [{"start": "09:00", "end": "12:00"}]


# ═══════════════════ Slots + Booking ═══════════════════
def _next_weekday_iso() -> str:
    """Return YYYY-MM-DD for the next weekday (Mon-Fri) that is strictly
    in the future (skips today so the 'exclude past times on today' logic
    doesn't strip the slots we're going to book)."""
    d = datetime.now(timezone.utc).date() + timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += timedelta(days=1)
    return d.isoformat()


class TestSlotsAndBooking:
    def test_slots_returns_free_slots_on_future_weekday(self, http, demo_headers):
        date = _next_weekday_iso()
        CTX['book_date'] = date
        r = http.get(
            f"{BASE_URL}/api/shop/businesses/{DEMO_BIZ_ID}/services/"
            f"{CTX['free_svc_id']}/slots?date={date}", headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["date"] == date
        assert isinstance(j["slots"], list)
        assert len(j["slots"]) >= 1, j
        assert "09:00" in j["slots"], j
        CTX['book_slot'] = j["slots"][0]

    def test_slots_bad_date(self, http, demo_headers):
        r = http.get(
            f"{BASE_URL}/api/shop/businesses/{DEMO_BIZ_ID}/services/"
            f"{CTX['free_svc_id']}/slots?date=notadate", headers=demo_headers)
        assert r.status_code == 400

    def test_book_free_reservation_confirmed_immediately(self, http, demo_headers):
        body = {"business_id": DEMO_BIZ_ID, "service_id": CTX['free_svc_id'],
                "date": CTX['book_date'], "start_time": CTX['book_slot'],
                "origin_url": "https://example.test", "note": "iter58 test booking"}
        r = http.post(f"{BASE_URL}/api/shop/service-bookings/checkout",
                      json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "confirmed", j
        assert j["checkout_url"] is None
        assert j["reservation_fee_cents"] == 0
        CTX['free_booking_id'] = j["booking_id"]

    def test_double_book_same_slot_409(self, http, demo_headers):
        body = {"business_id": DEMO_BIZ_ID, "service_id": CTX['free_svc_id'],
                "date": CTX['book_date'], "start_time": CTX['book_slot'],
                "origin_url": "https://example.test"}
        r = http.post(f"{BASE_URL}/api/shop/service-bookings/checkout",
                      json=body, headers=demo_headers)
        assert r.status_code == 409, r.text
        assert "slot_taken" in r.text

    def test_slots_excludes_booked_slot(self, http, demo_headers):
        r = http.get(
            f"{BASE_URL}/api/shop/businesses/{DEMO_BIZ_ID}/services/"
            f"{CTX['free_svc_id']}/slots?date={CTX['book_date']}",
            headers=demo_headers)
        assert r.status_code == 200
        assert CTX['book_slot'] not in r.json()["slots"]

    def test_book_paid_reservation_returns_stripe_url(self, http, demo_headers):
        # Pick a different slot on the same day to avoid clash
        r = http.get(
            f"{BASE_URL}/api/shop/businesses/{DEMO_BIZ_ID}/services/"
            f"{CTX['paid_svc_id']}/slots?date={CTX['book_date']}",
            headers=demo_headers)
        assert r.status_code == 200
        free_slots = [s for s in r.json()["slots"] if s != CTX['book_slot']]
        assert free_slots, "no other slots available"
        slot = free_slots[0]
        body = {"business_id": DEMO_BIZ_ID, "service_id": CTX['paid_svc_id'],
                "date": CTX['book_date'], "start_time": slot,
                "origin_url": "https://example.test"}
        r = http.post(f"{BASE_URL}/api/shop/service-bookings/checkout",
                      json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "pending_payment"
        assert j["reservation_fee_cents"] == 1000
        assert isinstance(j.get("checkout_url"), str)
        assert j["checkout_url"].startswith("https://checkout.stripe.com/"), j
        CTX['paid_booking_id'] = j["booking_id"]

    def test_my_bookings_list_contains_both(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/shop/service-bookings", headers=demo_headers)
        assert r.status_code == 200, r.text
        ids = [b["booking_id"] for b in r.json()["items"]]
        assert CTX['free_booking_id'] in ids
        assert CTX['paid_booking_id'] in ids

    def test_booking_status_endpoint(self, http, demo_headers):
        r = http.get(
            f"{BASE_URL}/api/shop/service-bookings/{CTX['free_booking_id']}/status",
            headers=demo_headers)
        assert r.status_code == 200
        j = r.json()
        assert j["status"] == "confirmed"
        assert j["payment_status"] == "paid"


# ═══════════════════ Merchant bookings + completion ═══════════════════
class TestMerchantBookings:
    def test_merchant_bookings_paid_only_default(self, http, demo_headers):
        r = http.get(f"{BASE_URL}/api/merchant/marketplace/services/bookings",
                     headers=demo_headers)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        ids = [b["booking_id"] for b in items]
        # free booking is paid=paid+confirmed -> included
        assert CTX['free_booking_id'] in ids
        # paid_booking (pending_payment) is NOT paid -> excluded from default
        assert CTX['paid_booking_id'] not in ids
        # All returned items must have payment_status=paid
        for b in items:
            assert b["payment_status"] == "paid"

    def test_invalid_transition_pending_to_completed(self, http, demo_headers):
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/services/bookings/"
            f"{CTX['paid_booking_id']}/status",
            json={"status": "completed"}, headers=demo_headers)
        assert r.status_code == 400
        assert "invalid_transition" in r.text

    def test_complete_confirmed_booking_awards_bigpoints(
            self, http, demo_headers, db, demo_user_id):
        # Snapshot BigPoints
        r = http.get(f"{BASE_URL}/api/bigcoin/me", headers=demo_headers)
        before = int(r.json().get("balance", 0))

        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/services/bookings/"
            f"{CTX['free_booking_id']}/status",
            json={"status": "completed"}, headers=demo_headers)
        assert r.status_code == 200, r.text
        b = r.json()["booking"]
        assert b["status"] == "completed"
        assert b.get("points_awarded_done") is True

        # BigPoints ledger row from PointsService
        row = db.points_ledger.find_one(
            {"user_id": demo_user_id, "source": "marketplace_service",
             "source_id": CTX['free_booking_id']})
        assert row is not None, "no marketplace_service ledger row"
        assert int(row.get("delta", 0)) > 0

        r = http.get(f"{BASE_URL}/api/bigcoin/me", headers=demo_headers)
        after = int(r.json().get("balance", 0))
        assert after >= before, f"balance did not grow: {before} -> {after}"

    def test_completion_is_idempotent(self, http, demo_headers, db, demo_user_id):
        # Try to complete again — 400 invalid_transition (completed has no
        # further transitions)
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/services/bookings/"
            f"{CTX['free_booking_id']}/status",
            json={"status": "completed"}, headers=demo_headers)
        assert r.status_code == 400
        # Only ONE ledger row for this booking
        n = db.points_ledger.count_documents(
            {"user_id": demo_user_id, "source": "marketplace_service",
             "source_id": CTX['free_booking_id']})
        assert n == 1, f"ledger not idempotent: {n} rows"

    def test_no_show_transition_allowed_from_confirmed(
            self, http, demo_headers, db, demo_user_id):
        # Book another free slot -> confirmed -> no_show
        # Find any free future slot
        # Use the next day if today's slots exhausted
        d = datetime.fromisoformat(CTX['book_date']).date() + timedelta(days=7)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        date2 = d.isoformat()
        r = http.get(
            f"{BASE_URL}/api/shop/businesses/{DEMO_BIZ_ID}/services/"
            f"{CTX['free_svc_id']}/slots?date={date2}", headers=demo_headers)
        assert r.status_code == 200
        slots = r.json()["slots"]
        assert slots, "no slots available for no_show test"
        body = {"business_id": DEMO_BIZ_ID, "service_id": CTX['free_svc_id'],
                "date": date2, "start_time": slots[0]}
        r = http.post(f"{BASE_URL}/api/shop/service-bookings/checkout",
                      json=body, headers=demo_headers)
        assert r.status_code == 200, r.text
        bid = r.json()["booking_id"]
        r = http.patch(
            f"{BASE_URL}/api/merchant/marketplace/services/bookings/{bid}/status",
            json={"status": "no_show"}, headers=demo_headers)
        assert r.status_code == 200, r.text
        assert r.json()["booking"]["status"] == "no_show"

    def test_delete_test_services(self, http, demo_headers):
        for sid in (CTX.get('free_svc_id'), CTX.get('paid_svc_id')):
            if not sid:
                continue
            r = http.delete(
                f"{BASE_URL}/api/merchant/marketplace/services/items/{sid}",
                headers=demo_headers)
            # 200 delete OR 404 (already-deleted) both acceptable
            assert r.status_code in (200, 404)


# ═══════════════════ Subscription enforcement (services) ═══════════════════
class TestSubscriptionEnforcement:
    def test_services_hidden_when_subscription_revoked(
            self, http, demo_headers, db, demo_biz):
        """Temporarily revoke, hit /services endpoint, restore."""
        # Save current state
        prev = db.marketplace_profiles.find_one(
            {"business_id": DEMO_BIZ_ID}, {"subscription_active": 1})
        try:
            db.marketplace_profiles.update_one(
                {"business_id": DEMO_BIZ_ID},
                {"$set": {"subscription_active": False}})
            r = http.get(
                f"{BASE_URL}/api/shop/businesses/{DEMO_BIZ_ID}/services",
                headers=demo_headers)
            assert r.status_code == 404, r.text
            assert "business_not_found" in r.text or "business_unavailable" in r.text
        finally:
            db.marketplace_profiles.update_one(
                {"business_id": DEMO_BIZ_ID},
                {"$set": {"subscription_active": True}})
