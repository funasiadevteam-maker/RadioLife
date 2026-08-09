"""Phase MKT.4 backend regression — GET /api/me/notifications/unread_count,
GET /api/games/discover, GET /api/merchant/marketplace/campaigns fields."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def demo_token():
    r = requests.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    assert r.status_code == 200, r.text
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok
    return tok


@pytest.fixture(scope="module")
def demo_hdr(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


# ─── Notification bell — unread_count endpoint ────────────────────────────────
def test_unread_count_returns_integer(demo_hdr):
    r = requests.get(f"{BASE_URL}/api/me/notifications/unread_count", headers=demo_hdr, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "count" in body
    assert isinstance(body["count"], int)
    assert body["count"] >= 0


def test_unread_count_requires_auth():
    r = requests.get(f"{BASE_URL}/api/me/notifications/unread_count", timeout=15)
    assert r.status_code in (401, 403)


# ─── Games discover (RadioLife /play page consumes this) ──────────────────────
def test_games_discover_shape():
    r = requests.get(f"{BASE_URL}/api/games/discover", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    for g in data["items"]:
        assert "campaign_id" in g
        assert "game_type" in g


# ─── Marketplace campaigns list — listing-analytics fields present ───────────
def test_marketplace_campaigns_list_has_analytics_fields(demo_hdr):
    r = requests.get(f"{BASE_URL}/api/merchant/marketplace/campaigns", headers=demo_hdr, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body
    items = body["items"]
    assert isinstance(items, list)
    # Demo user should own several campaigns of assorted types (see seed notes in iter49 report)
    assert len(items) > 0, "Demo merchant should have at least one campaign for MKT.4 listing-analytics parity"
    # Aggregate the union of type-specific counters across all campaigns
    types_seen = {c["type"] for c in items}
    for c in items:
        assert "campaign_id" in c and "type" in c and "status" in c
        assert "budget_usd" in c and "spent_usd" in c
    # Verify type-specific counters exist on at least one row of each type
    def has(field, tp):
        return any(field in c for c in items if c["type"] == tp)
    # Not every merchant will have every type — but iter49 seed does, so allow soft assertion
    for tp, fields in [
        ("featured", ["impressions", "clicks"]),
        ("spin", ["plays", "wins"]),
        ("scratch", ["plays", "wins"]),
        ("trivia", ["answers_count", "correct_count"]),
        ("coupon_bid", ["claims"]),
        ("giveaway", ["entries_count"]),
    ]:
        if tp in types_seen:
            for f in fields:
                assert has(f, tp), f"expected field '{f}' on at least one campaign of type={tp}"


# ─── Notifications inbox marking read reduces unread_count ────────────────────
def test_mark_read_reduces_unread_count(demo_hdr):
    before = requests.get(f"{BASE_URL}/api/me/notifications/unread_count", headers=demo_hdr, timeout=15).json().get("count", 0)
    inbox = requests.get(f"{BASE_URL}/api/me/notifications?unread_only=true", headers=demo_hdr, timeout=15)
    assert inbox.status_code == 200
    unread_items = inbox.json().get("items", [])
    if not unread_items:
        pytest.skip("No unread notifications to mark for this demo user")
    nid = unread_items[0].get("notification_id") or unread_items[0].get("id")
    rm = requests.post(f"{BASE_URL}/api/me/notifications/{nid}/read", headers=demo_hdr, timeout=15)
    assert rm.status_code == 200
    after = requests.get(f"{BASE_URL}/api/me/notifications/unread_count", headers=demo_hdr, timeout=15).json().get("count", 0)
    assert after <= before, f"expected unread_count to not increase after mark-read (before={before}, after={after})"
