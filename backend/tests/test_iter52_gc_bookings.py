"""Iter 52 — Gift Cards + Bookings + Podcast episode media (chapters) backend tests.

Runs against the live shared backend using demo listener auth.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL must be set")

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{API}/auth/demo", timeout=30)
    assert r.status_code == 200, f"demo auth failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok, f"no token in demo response: {r.text}"
    return tok


@pytest.fixture(scope="module")
def hdrs(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


# ────────── Gift Cards ──────────
class TestGiftCards:
    def test_catalog_shape(self, hdrs):
        r = requests.get(f"{API}/giftcards/catalog", headers=hdrs, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and "points_balance" in d and "points_per_dollar" in d
        assert isinstance(d["items"], list) and len(d["items"]) >= 3
        # Seeded defaults present
        pids = {p["product_id"] for p in d["items"]}
        assert {"gc_grind_coffee", "gc_frisco_eats", "gc_spa_bliss"}.issubset(pids)
        # Sanity on shape
        for p in d["items"]:
            assert isinstance(p["denominations_cents"], list) and p["denominations_cents"]
            assert "sponsor_name" in p and "category" in p
        assert d["points_per_dollar"] == 100
        assert isinstance(d["points_balance"], int)

    def test_catalog_requires_auth(self):
        r = requests.get(f"{API}/giftcards/catalog", timeout=15)
        assert r.status_code in (401, 403)

    def test_purchase_bad_denomination(self, hdrs):
        r = requests.post(f"{API}/giftcards/purchase", headers=hdrs,
                          json={"product_id": "gc_grind_coffee", "amount_cents": 1234,
                                "method": "points"}, timeout=30)
        assert r.status_code == 400
        assert (r.json().get("detail") or {}).get("code") == "bad_denomination"

    def test_purchase_unknown_product(self, hdrs):
        r = requests.post(f"{API}/giftcards/purchase", headers=hdrs,
                          json={"product_id": "gc_nope", "amount_cents": 1000,
                                "method": "points"}, timeout=30)
        assert r.status_code == 404
        assert (r.json().get("detail") or {}).get("code") == "product_not_found"

    def test_purchase_points_flow(self, hdrs):
        # Top up demo user points via admin adjust if available; else assume balance
        cat = requests.get(f"{API}/giftcards/catalog", headers=hdrs, timeout=30).json()
        balance = cat["points_balance"]
        # Grab smallest denom of grind_coffee (1000 cents = 1000 points)
        prod = next(p for p in cat["items"] if p["product_id"] == "gc_grind_coffee")
        denom = min(prod["denominations_cents"])  # 1000
        need_pts = int(denom / 100 * 100)
        if balance < need_pts:
            pytest.skip(f"demo balance {balance} < {need_pts}, skip points purchase")
        r = requests.post(f"{API}/giftcards/purchase", headers=hdrs,
                          json={"product_id": "gc_grind_coffee", "amount_cents": denom,
                                "method": "points"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True and d["method"] == "points"
        assert d["points_spent"] == need_pts
        card = d["card"]
        assert card["balance_cents"] == denom and card["amount_cents"] == denom
        assert card["status"] == "active" and card["code"].startswith("RL-")
        # Verify appears in /mine
        mine = requests.get(f"{API}/giftcards/mine", headers=hdrs, timeout=30).json()
        ids = {c["card_id"] for c in mine.get("items", [])}
        assert card["card_id"] in ids

    def test_purchase_card_returns_checkout_url(self, hdrs):
        r = requests.post(f"{API}/giftcards/purchase", headers=hdrs,
                          json={"product_id": "gc_frisco_eats", "amount_cents": 2500,
                                "method": "card", "origin_url": BASE_URL}, timeout=45)
        # If Stripe unconfigured, allow 503 but that's a fail vs. spec
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["method"] == "card" and d.get("checkout_url", "").startswith("http")
        assert d.get("session_id", "").startswith("cs_")

    def test_mine_shape(self, hdrs):
        r = requests.get(f"{API}/giftcards/mine", headers=hdrs, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "sent" in d and "total" in d


# ────────── Bookings ──────────
class TestBookings:
    def test_available_shape(self, hdrs):
        r = requests.get(f"{API}/bookings/available", headers=hdrs, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)
        # If any active booking campaigns, verify shape
        for v in d["items"]:
            assert "campaign_id" in v and "title" in v and "booking_type" in v
            assert isinstance(v.get("slots"), list)

    def test_available_requires_auth(self):
        r = requests.get(f"{API}/bookings/available", timeout=15)
        assert r.status_code in (401, 403)

    def test_book_flow(self, hdrs):
        avail = requests.get(f"{API}/bookings/available", headers=hdrs, timeout=30).json()
        items = avail.get("items", [])
        if not items:
            pytest.skip("No active booking campaigns — parity note: expected in demo env")
        v = items[0]
        slot = (v.get("slots") or ["7:00 PM"])[0]
        r = requests.post(f"{API}/bookings/{v['campaign_id']}/book", headers=hdrs,
                          json={"slot": slot, "party_size": 2,
                                "name": f"TEST_{uuid.uuid4().hex[:6]}", "phone": "555-0100"},
                          timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True and d["booking"]["slot"] == slot


# ────────── Podcast episode media / chapters ──────────
class TestEpisodeMedia:
    def test_media_shape_has_chapters(self, hdrs):
        # Seeded ep_ui_demo from prior iterations
        r = requests.get(f"{API}/podcasts/episodes/ep_ui_demo/media",
                         headers=hdrs, timeout=30)
        if r.status_code == 404:
            pytest.skip("ep_ui_demo not seeded in this env")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "chapters" in d and isinstance(d["chapters"], list)
        assert "duration_seconds" in d
        # Chapters sorted by start_seconds
        starts = [c.get("start_seconds", 0) for c in d["chapters"]]
        assert starts == sorted(starts)

    def test_media_404_unknown(self, hdrs):
        r = requests.get(f"{API}/podcasts/episodes/ep_does_not_exist_xyz/media",
                         headers=hdrs, timeout=15)
        assert r.status_code == 404
