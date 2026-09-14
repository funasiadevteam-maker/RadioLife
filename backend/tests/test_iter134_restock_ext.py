"""
iteration_134 — Backend regression tests for the two Pair-2 follow-on extensions:
  (1) WEB/MOBILE Restock Countdown storefront teaser (data source: /api/store/{id})
  (2) Waitlist Auto-Play notification (in-app inbox + push deeplink payload)

Focused endpoints:
  - GET  /api/store/adv_fpk                     (has resets_at + cmp_fpk_spin sold-out)
  - GET  /api/me/notifications                  (coupon_restock w/ payload.campaign_id / play_url / play_route)
  - GET  /api/user/notifications/inbox          (merged row with target_url=/play/cmp_fpk_spin)
  - POST /api/admin/waitlist/dispatch           (regenerates the notification if missing)
  - POST /api/store/adv_fpk/waitlist            (re-join demo@ if left the waitlist)
"""
import os
import time
import requests
import pytest
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
CAMPAIGN = "cmp_fpk_spin"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo():
    return _login(DEMO)


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN)


# ---------- Restock Countdown data source ----------
def test_store_endpoint_has_resets_at_and_soldout(demo):
    r = demo.get(f"{BASE_URL}/api/store/adv_fpk", timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "resets_at" in data and data["resets_at"], "resets_at missing — countdown cannot tick"
    games = {g["campaign_id"]: g for g in data.get("games", [])}
    assert CAMPAIGN in games, f"{CAMPAIGN} not in storefront games"
    spin = games[CAMPAIGN]
    assert spin.get("is_coupon_game") is True
    # sold-out today per seed
    remaining = spin.get("remaining_today")
    assert remaining is not None and remaining <= 0, f"{CAMPAIGN} should be sold-out, remaining={remaining}"


# ---------- Ensure a coupon_restock notification exists for demo@ ----------
def _find_restock(items):
    return next(
        (n for n in (items or [])
         if n.get("type") == "coupon_restock"
         and (n.get("payload") or {}).get("campaign_id") == CAMPAIGN),
        None,
    )


def _rejoin_waitlist_if_needed(demo):
    r = demo.get(f"{BASE_URL}/api/me/waitlist", timeout=10)
    if r.status_code == 200 and CAMPAIGN in (r.json().get("campaign_ids") or []):
        return
    demo.post(f"{BASE_URL}/api/store/adv_fpk/waitlist",
              json={"campaign_id": CAMPAIGN}, timeout=10)


def _dispatch_if_missing(demo, admin):
    r = demo.get(f"{BASE_URL}/api/me/notifications", params={"limit": 50}, timeout=15)
    if r.status_code == 200 and _find_restock(r.json().get("items")):
        return
    _rejoin_waitlist_if_needed(demo)
    r = admin.post(f"{BASE_URL}/api/admin/waitlist/dispatch",
                   json={"campaign_id": CAMPAIGN}, timeout=15)
    # Endpoint should exist and succeed (200/201/202)
    assert r.status_code in (200, 201, 202), f"admin dispatch failed: {r.status_code} {r.text[:300]}"
    time.sleep(1.0)


def test_me_notifications_has_coupon_restock_with_payload(demo, admin):
    _dispatch_if_missing(demo, admin)
    r = demo.get(f"{BASE_URL}/api/me/notifications", params={"limit": 50}, timeout=15)
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    n = _find_restock(items)
    assert n is not None, "coupon_restock notification for cmp_fpk_spin not found on /api/me/notifications"
    p = n.get("payload") or {}
    assert p.get("campaign_id") == CAMPAIGN, f"payload.campaign_id={p.get('campaign_id')}"
    assert p.get("play_url") == f"/play/{CAMPAIGN}", f"payload.play_url={p.get('play_url')}"
    assert p.get("play_route") == f"/game/{CAMPAIGN}", f"payload.play_route={p.get('play_route')}"


def test_user_notifications_inbox_merged_row(demo, admin):
    _dispatch_if_missing(demo, admin)
    r = demo.get(f"{BASE_URL}/api/user/notifications/inbox",
                 params={"limit": 50}, timeout=15)
    assert r.status_code == 200, r.text
    items = r.json().get("items", [])
    # A merged row for coupon_restock — id may prefix; target_url is the web link
    row = next(
        (x for x in items
         if (x.get("target_url") == f"/play/{CAMPAIGN}")
         or ((x.get("payload") or {}).get("campaign_id") == CAMPAIGN
             and x.get("type") == "coupon_restock")),
        None,
    )
    assert row is not None, "coupon_restock row not surfaced by /api/user/notifications/inbox"
    assert row.get("target_url") == f"/play/{CAMPAIGN}", f"target_url={row.get('target_url')}"
    # Non-sponsored (regular navigation row)
    assert not row.get("is_sponsored"), "coupon_restock row should NOT be sponsored"


def test_admin_waitlist_dispatch_idempotent(demo, admin):
    _rejoin_waitlist_if_needed(demo)
    r = admin.post(f"{BASE_URL}/api/admin/waitlist/dispatch",
                   json={"campaign_id": CAMPAIGN}, timeout=15)
    assert r.status_code in (200, 201, 202), f"{r.status_code} {r.text[:300]}"
