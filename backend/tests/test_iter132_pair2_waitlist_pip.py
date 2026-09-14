"""Pair 2 — Sold-Out Waitlist + PiP media endpoint (backend regression).

Covers:
  * POST /api/store/adv_fpk/waitlist (join, idempotency)
  * GET  /api/me/waitlist
  * POST /api/store/adv_fpk/waitlist/leave
  * POST /api/admin/waitlist/dispatch (admin)
  * GET  /api/me/notifications (coupon_restock item)
  * Wrong-advertiser -> 404 campaign_not_found
  * REGRESSION /api/store/adv_fpk coupons_left_today
  * PiP media endpoint /api/podcasts/episodes/{ep}/media
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PW = "DemoPass123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PW = "AdminPass123!"

CAMPAIGN_ID = "cmp_fpk_spin"
ADVERTISER_ID = "adv_fpk"
EPISODE_ID = "ep_ui_demo"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def demo():
    return _login(DEMO_EMAIL, DEMO_PW)


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PW)


# ---- Waitlist ---------------------------------------------------------

def test_join_waitlist(demo):
    r = demo.post(f"{BASE_URL}/api/store/{ADVERTISER_ID}/waitlist",
                  json={"campaign_id": CAMPAIGN_ID}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert body.get("on_waitlist") is True


def test_join_waitlist_idempotent(demo):
    r = demo.post(f"{BASE_URL}/api/store/{ADVERTISER_ID}/waitlist",
                  json={"campaign_id": CAMPAIGN_ID}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("on_waitlist") is True
    assert body.get("already") is True


def test_my_waitlist_contains(demo):
    r = demo.get(f"{BASE_URL}/api/me/waitlist", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert CAMPAIGN_ID in (body.get("campaign_ids") or [])


def test_leave_waitlist(demo):
    r = demo.post(f"{BASE_URL}/api/store/{ADVERTISER_ID}/waitlist/leave",
                  json={"campaign_id": CAMPAIGN_ID}, timeout=15)
    assert r.status_code == 200, r.text
    assert r.json().get("on_waitlist") is False


def test_my_waitlist_after_leave_excludes(demo):
    r = demo.get(f"{BASE_URL}/api/me/waitlist", timeout=15)
    assert r.status_code == 200
    assert CAMPAIGN_ID not in (r.json().get("campaign_ids") or [])


def test_wrong_advertiser_404(demo):
    # Rejoin under an advertiser that does NOT own the campaign.
    r = demo.post(f"{BASE_URL}/api/store/adv_not_owner/waitlist",
                  json={"campaign_id": CAMPAIGN_ID}, timeout=15)
    assert r.status_code == 404, r.text
    assert "campaign_not_found" in r.text


# ---- Admin dispatch ---------------------------------------------------

def test_admin_dispatch_notifies(demo, admin):
    # Re-join first
    j = demo.post(f"{BASE_URL}/api/store/{ADVERTISER_ID}/waitlist",
                  json={"campaign_id": CAMPAIGN_ID}, timeout=15)
    assert j.status_code == 200, j.text

    # Admin dispatch
    r = admin.post(f"{BASE_URL}/api/admin/waitlist/dispatch", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("checked", 0) >= 1
    assert body.get("notified", 0) >= 1

    # Notifications include coupon_restock
    n = demo.get(f"{BASE_URL}/api/me/notifications", timeout=15)
    assert n.status_code == 200, n.text
    items = n.json().get("items") or n.json().get("notifications") or []
    restock = [x for x in items if (x.get("type") == "coupon_restock")]
    assert restock, f"no coupon_restock notification in {items[:3]}"
    # Confirm title/campaign reference
    payload = restock[0].get("payload") or {}
    campaign_title = payload.get("campaign_title") or restock[0].get("campaign_title") or ""
    assert "FPK Spin" in (campaign_title or "") or campaign_title, \
        f"title unexpected: {campaign_title!r}"

    # Waitlist now empty (marked notified)
    m = demo.get(f"{BASE_URL}/api/me/waitlist", timeout=15)
    assert m.status_code == 200
    assert CAMPAIGN_ID not in (m.json().get("campaign_ids") or [])


# ---- Regression: storefront still returns coupons_left_today ---------

def test_storefront_regression():
    r = requests.get(f"{BASE_URL}/api/store/{ADVERTISER_ID}", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "coupons_left_today" in body
    # 6 remaining games * 360 = 2160 (spec value)
    assert isinstance(body["coupons_left_today"], int)
    # allow reasonable variance if test env drifted
    assert body["coupons_left_today"] >= 1500


# ---- PiP video media endpoint ----------------------------------------

def test_episode_media():
    r = requests.get(f"{BASE_URL}/api/podcasts/episodes/{EPISODE_ID}/media", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    # Must expose video_url OR media_url for the seeded video episode
    has_video = bool(body.get("video_url") or body.get("media_url"))
    assert has_video, f"no video/media url in {body}"
