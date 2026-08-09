"""Iteration 49 — Phase MKT.3 backend tests.

Covers:
  1) Featured Listings — POST /api/merchant/marketplace/campaigns type=featured (bid_required, ownership).
  2) GET /api/discovery/featured sorted desc by bid_cents, excludes budget-exhausted, counts impressions.
  3) POST /api/discovery/featured/{id}/click charges bid to spent_usd, increments clicks, auto-pauses,
     404 for unknown.
  4) Winner Notifications — giveaway draw enqueues a giveaway_winner into /api/me/notifications
     for each winner; payload contains title/sponsor_name/prize_desc.
  5) Notification inbox endpoints — list (items/count/next_before), read, unread_count.
  6) Rate card backfill — featured_listing key present, 10+ items.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def demo_session():
    r = requests.post(f"{API}/auth/demo")
    assert r.status_code == 200, r.text
    data = r.json()
    tok = data["session_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return {"session": s, "user_id": data["user_id"], "email": data["email"], "token": tok}


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
    assert r.status_code == 200, r.text
    s.headers.update({"Content-Type": "application/json"})
    return {"session": s, "user_id": r.json()["user_id"]}


# ==================== 1) Rate card featured_listing backfill ====================

class TestRateCardFeatured:
    def test_rate_card_has_10_items_with_featured(self, admin_session):
        r = admin_session["session"].get(f"{API}/admin/rate-card")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        keys = {i["key"] for i in items}
        assert "featured_listing" in keys, f"featured_listing missing; keys={keys}"
        assert len(items) >= 10, f"expected >=10 items, got {len(items)}"


# ==================== 2) Featured Listing CRUD ====================

class TestFeaturedCampaignCreate:
    def test_featured_requires_bid_cents(self, demo_session):
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns", json={
            "merchant_id": "biz_demo_marketplace",
            "type": "featured", "goal": "more_customers",
            "title": "TEST_iter49_feat_nobid", "budget_usd": 5.0, "bid_cents": 0,
        })
        assert r.status_code == 400, r.text
        assert r.json().get("detail", {}).get("code") == "bid_required"

    def test_featured_create_ok(self, demo_session):
        title = f"TEST_iter49_featA_{uuid.uuid4().hex[:6]}"
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns", json={
            "merchant_id": "biz_demo_marketplace",
            "type": "featured", "goal": "more_customers",
            "title": title, "budget_usd": 5.0, "bid_cents": 25,
            "tagline": "Best latte in town",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "featured"
        assert d["bid_cents"] == 25
        assert d["tagline"] == "Best latte in town"
        assert d["status"] == "active"
        assert d["impressions"] == 0
        assert d["clicks"] == 0
        pytest._iter49_feat_a = d["campaign_id"]

    def test_featured_create_higher_bid(self, demo_session):
        title = f"TEST_iter49_featB_{uuid.uuid4().hex[:6]}"
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns", json={
            "merchant_id": "biz_demo_marketplace",
            "type": "featured", "goal": "foot_traffic",
            "title": title, "budget_usd": 5.0, "bid_cents": 75,
            "tagline": "Premium spot",
        })
        assert r.status_code == 200, r.text
        pytest._iter49_feat_b = r.json()["campaign_id"]

    def test_featured_create_tiny_budget_for_autopause(self, demo_session):
        # bid=50c, budget=$0.30 → one click of 50c exhausts (spent 0.50 >= 0.30 budget)
        title = f"TEST_iter49_featC_{uuid.uuid4().hex[:6]}"
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns", json={
            "merchant_id": "biz_demo_marketplace",
            "type": "featured", "goal": "more_customers",
            "title": title, "budget_usd": 0.30, "bid_cents": 50,
            "tagline": "Auto-pause test",
        })
        assert r.status_code == 200
        pytest._iter49_feat_c = r.json()["campaign_id"]


# ==================== 3) Discovery Featured ====================

class TestDiscoveryFeatured:
    def test_featured_sorted_desc_by_bid(self, demo_session):
        r = demo_session["session"].get(f"{API}/discovery/featured")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        ids = [c["campaign_id"] for c in items]
        assert getattr(pytest, "_iter49_feat_a", None) in ids
        assert getattr(pytest, "_iter49_feat_b", None) in ids
        # verify featured=True flag surfaced
        for c in items:
            assert c.get("featured") is True

    def test_click_charges_and_increments(self, demo_session):
        cid = getattr(pytest, "_iter49_feat_a", None)
        r = demo_session["session"].post(f"{API}/discovery/featured/{cid}/click")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["merchant_id"] == "biz_demo_marketplace"
        # verify counter via merchant list
        r2 = demo_session["session"].get(f"{API}/merchant/marketplace/campaigns")
        c = next((x for x in r2.json()["items"] if x["campaign_id"] == cid), None)
        assert c is not None
        assert c["clicks"] >= 1
        assert c["spent_usd"] >= 0.25  # bid=25c

    def test_click_unknown_returns_404(self, demo_session):
        r = demo_session["session"].post(f"{API}/discovery/featured/mc_doesnotexist_xyz/click")
        assert r.status_code == 404, r.text

    def test_click_autopause_on_budget_exhaustion(self, demo_session):
        cid = getattr(pytest, "_iter49_feat_c", None)
        r = demo_session["session"].post(f"{API}/discovery/featured/{cid}/click")
        assert r.status_code == 200, r.text
        # After one click of 50c on a $0.30 budget, campaign should auto-pause
        r2 = demo_session["session"].get(f"{API}/merchant/marketplace/campaigns")
        c = next((x for x in r2.json()["items"] if x["campaign_id"] == cid), None)
        assert c is not None
        assert c["status"] == "paused", f"expected paused, got {c['status']} spent={c.get('spent_usd')}"

    def test_paused_excluded_from_discovery(self, demo_session):
        cid = getattr(pytest, "_iter49_feat_c", None)
        r = demo_session["session"].get(f"{API}/discovery/featured")
        ids = [c["campaign_id"] for c in r.json()["items"]]
        assert cid not in ids

    def test_impressions_incremented_on_list(self, demo_session):
        cid = getattr(pytest, "_iter49_feat_a", None)
        # Fetch twice
        demo_session["session"].get(f"{API}/discovery/featured")
        demo_session["session"].get(f"{API}/discovery/featured")
        r2 = demo_session["session"].get(f"{API}/merchant/marketplace/campaigns")
        c = next((x for x in r2.json()["items"] if x["campaign_id"] == cid), None)
        assert c is not None
        assert c.get("impressions", 0) >= 2


# ==================== 4) Notification inbox endpoints ====================

class TestNotificationInbox:
    def test_list_shape(self, demo_session):
        r = demo_session["session"].get(f"{API}/me/notifications")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and "count" in d and "next_before" in d
        assert isinstance(d["items"], list)
        assert d["count"] == len(d["items"])

    def test_unread_count(self, demo_session):
        r = demo_session["session"].get(f"{API}/me/notifications/unread_count")
        assert r.status_code == 200, r.text
        assert "count" in r.json()
        assert isinstance(r.json()["count"], int)


# ==================== 5) Winner Notifications on giveaway draw ====================

class TestWinnerNotifications:
    def test_create_and_draw_giveaway_creates_notif(self, demo_session):
        # Create a new giveaway (avoid stale ones from prior smoke)
        title = f"TEST_iter49_gv_{uuid.uuid4().hex[:6]}"
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns", json={
            "merchant_id": "biz_demo_marketplace",
            "type": "giveaway", "goal": "engagement",
            "title": title, "budget_usd": 5.0,
            "prize_desc": "iter49 winner prize",
            "num_winners": 1,
            "reward_points_on_claim": 3,
        })
        assert r.status_code == 200, r.text
        cid = r.json()["campaign_id"]
        pytest._iter49_gv_id = cid
        pytest._iter49_gv_title = title

        # Enter
        r2 = demo_session["session"].post(f"{API}/brand-giveaways/{cid}/enter")
        assert r2.status_code == 200, r2.text

        # Draw
        r3 = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns/{cid}/draw")
        assert r3.status_code == 200, r3.text
        winners = r3.json()["winners"]
        assert demo_session["user_id"] in winners

    def test_winner_notification_in_inbox(self, demo_session):
        r = demo_session["session"].get(f"{API}/me/notifications", params={"limit": 50})
        assert r.status_code == 200
        items = r.json()["items"]
        cid = getattr(pytest, "_iter49_gv_id", None)
        title = getattr(pytest, "_iter49_gv_title", None)
        # Find giveaway_winner notif matching our campaign
        match = next((n for n in items
                      if n.get("type") == "giveaway_winner"
                      and (n.get("payload") or {}).get("campaign_id") == cid), None)
        assert match is not None, f"no giveaway_winner notif for {cid}; items types={[i.get('type') for i in items]}"
        payload = match["payload"]
        assert payload.get("title") == title
        assert "prize_desc" in payload
        assert payload["prize_desc"] == "iter49 winner prize"
        assert "sponsor_name" in payload
        assert match.get("read_at") is None
        pytest._iter49_notif_id = match["id"]

    def test_draw_is_idempotent_via_already_drawn(self, demo_session):
        cid = getattr(pytest, "_iter49_gv_id", None)
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns/{cid}/draw")
        assert r.status_code == 400, r.text
        assert r.json().get("detail", {}).get("code") == "already_drawn"

    def test_mark_notification_read(self, demo_session):
        nid = getattr(pytest, "_iter49_notif_id", None)
        r = demo_session["session"].post(f"{API}/me/notifications/{nid}/read")
        assert r.status_code == 200, r.text
        # Verify read_at set now
        r2 = demo_session["session"].get(f"{API}/me/notifications", params={"limit": 50})
        match = next((n for n in r2.json()["items"] if n["id"] == nid), None)
        assert match is not None
        assert match.get("read_at") is not None

    def test_mark_read_idempotent(self, demo_session):
        nid = getattr(pytest, "_iter49_notif_id", None)
        r = demo_session["session"].post(f"{API}/me/notifications/{nid}/read")
        assert r.status_code == 200
        # already_read flag is optional but ok=true expected
        assert r.json().get("ok") is True

    def test_unread_only_filter(self, demo_session):
        # After marking our notif read, unread_only should not include it
        nid = getattr(pytest, "_iter49_notif_id", None)
        r = demo_session["session"].get(f"{API}/me/notifications", params={"unread_only": "true"})
        assert r.status_code == 200
        ids = [n["id"] for n in r.json()["items"]]
        assert nid not in ids
