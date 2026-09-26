"""Iteration 188 — ENH tests: Catalog Product Picker, Cover Art, Perk Sharing,
Perk Reminders (expiring_soon + notification lazy insert)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "demo@bigfm.dubai", "password": "DemoPass123!"})
    assert r.status_code == 200, r.text
    return s


# --- ENH1: Catalog products for the demo bar ---
def test_catalog_returns_seeded_products():
    r = requests.get(f"{BASE_URL}/api/shop/businesses/biz_demo_bar/products")
    assert r.status_code == 200, r.text
    data = r.json()
    prods = data.get("products", [])
    names = {p["name"] for p in prods}
    for expected in ("Neon Martini", "Sunset Spritz", "Craft Old Fashioned", "Bar Snack Platter"):
        assert expected in names, f"missing {expected}. got {names}"
    for p in prods:
        assert p["product_id"].startswith("prod_demobar_")
        assert p["price_cents"] > 0


# --- ENH2: cover_url flows through liveshow creation ---
def test_liveshow_create_with_cover_url(demo_session):
    from datetime import datetime, timezone, timedelta
    scheduled_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    payload = {
        "business_id": "biz_demo_bar",
        "title": "ITER188 test cover",
        "description": "cover test",
        "scheduled_at": scheduled_at,
        "cover_url": "https://example.com/cover.jpg",
        "products": [{"title": "Neon Martini", "price_cents": 4200, "product_id": "prod_demobar_0"}],
    }
    r = demo_session.post(f"{BASE_URL}/api/social/liveshows", json=payload)
    assert r.status_code in (200, 201), r.text
    show = r.json()
    assert show.get("cover_url") == "https://example.com/cover.jpg"
    # cleanup
    sid = show.get("id") or show.get("show_id") or show.get("_id")
    if sid:
        demo_session.delete(f"{BASE_URL}/api/social/liveshows/{sid}")


# --- ENH4: wallet returns expiring_soon flag + notification lazy insert ---
def test_wallet_expiring_soon_and_notification(demo_session):
    r = demo_session.get(f"{BASE_URL}/api/bar-games/wallet")
    assert r.status_code == 200, r.text
    data = r.json()
    items = data.get("items", data if isinstance(data, list) else [])
    codes = {i.get("code"): i for i in items}

    # BAR-SOON123 expiring-soon
    soon = codes.get("BAR-SOON123")
    assert soon is not None, f"BAR-SOON123 not present. codes={list(codes.keys())}"
    assert soon.get("expiring_soon") is True

    # BAR-NEON2FOR normal (not expiring soon)
    normal = codes.get("BAR-NEON2FOR")
    assert normal is not None
    assert normal.get("expiring_soon") in (False, None)

    # BAR-OLD999 expired
    expired = codes.get("BAR-OLD999")
    assert expired is not None
    assert expired.get("expired") is True

    # notification present
    n = demo_session.get(f"{BASE_URL}/api/social/notifications")
    assert n.status_code == 200
    notifs = n.json()
    notif_list = notifs.get("items", notifs if isinstance(notifs, list) else [])
    types = [x.get("notif_type") or x.get("type") for x in notif_list]
    assert "perk_expiring" in types, f"perk_expiring notif missing. types={types}"
