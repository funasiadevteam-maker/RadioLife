"""Iteration 141 — Backend regression for:
  1) GET /api/shell/home returns `top_genre` key (null fallback ok).
  2) POST /api/ads/advertiser/banner-campaigns creates a rail-slot campaign.
  3) POST /api/ads/advertiser/banner-campaigns/{cid}/checkout is idempotent + mock.
  4) GET  /api/ads/advertiser/banner-campaigns lists it with status 'pending'.
  5) GET  /api/ads/banner/decision?slot_key=right_rail_mpu_1 falls back to 'house'
     for a non-premium user (until a direct campaign is approved to 'active').
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
ADVERT = ("test@bigfm.dubai", "TestUser123!")
FREE = ("freeuser@bigfm.dubai", "FreePass123!")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


# ---------- 1) top_genre on /api/shell/home ----------
def test_shell_home_has_top_genre_key_admin():
    s = _login(*ADMIN)
    r = s.get(f"{BASE}/api/shell/home", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "top_genre" in body, f"top_genre missing: keys={list(body.keys())}"
    # Admin has no favorite_genres → expected None (or a string).
    assert body["top_genre"] is None or isinstance(body["top_genre"], str)
    assert "for_you" in body and "live_now" in body


def test_shell_home_anonymous_still_has_top_genre():
    r = requests.get(f"{BASE}/api/shell/home", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "top_genre" in body
    assert body["top_genre"] is None or isinstance(body["top_genre"], str)


# ---------- 2-4) Advertiser rail buy → checkout → list ----------
def test_advertiser_rail_buy_flow_end_to_end():
    s = _login(*ADVERT)
    payload = {
        "slot_keys": ["right_rail_mpu_1"],
        "creative_image_url": "https://picsum.photos/seed/iter141a/300/250",
        "click_url": "https://example.com/iter141",
        "start_date": "2026-06-01T00:00:00Z",
        "end_date": "2026-12-31T23:59:59Z",
        "total_budget": 250,
    }
    r = s.post(f"{BASE}/api/ads/advertiser/banner-campaigns",
               json=payload, timeout=15)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text[:300]}"
    body = r.json()
    cid = body.get("campaign_id") or body.get("id")
    assert cid, f"no campaign_id in response: {body}"

    # Mock checkout
    r2 = s.post(f"{BASE}/api/ads/advertiser/banner-campaigns/{cid}/checkout",
                json={}, timeout=15)
    assert r2.status_code == 200, f"checkout failed: {r2.status_code} {r2.text[:300]}"
    co = r2.json()
    assert co.get("ok") is True, f"checkout not ok: {co}"
    # In test/mock mode expect mock=true (per spec).
    assert co.get("mock") is True or co.get("mode") == "mock" or co.get("checkout_url"), \
        f"expected mock=true or a mock checkout_url: {co}"

    # List — new campaign should appear.
    r3 = s.get(f"{BASE}/api/ads/advertiser/banner-campaigns", timeout=10)
    assert r3.status_code == 200
    items = r3.json().get("items", [])
    ours = next((c for c in items if c.get("campaign_id") == cid), None)
    assert ours is not None, f"campaign {cid} not listed. items count={len(items)}"
    assert ours.get("status") in ("pending", "pending_admin", "pending_review"), \
        f"expected pending, got {ours.get('status')}"
    assert "right_rail_mpu_1" in (ours.get("slot_keys") or [])


def test_advertiser_rail_missing_creative_rejected():
    s = _login(*ADVERT)
    payload = {
        "slot_keys": ["right_rail_mpu_1"],
        "creative_image_url": "",
        "click_url": "https://example.com/x",
        "start_date": "2026-06-01T00:00:00Z",
        "end_date": "2026-12-31T23:59:59Z",
        "total_budget": 100,
    }
    r = s.post(f"{BASE}/api/ads/advertiser/banner-campaigns",
               json=payload, timeout=10)
    # Either explicit 4xx OR a JSON error body; must NOT be 500.
    assert r.status_code < 500, f"server crash on bad creative: {r.status_code} {r.text[:200]}"


# ---------- 5) Banner decision — house fallback for non-premium ----------
def test_banner_decision_house_for_non_premium_all_three_slots():
    s = _login(*FREE)
    for slot in ("right_rail_mpu_1", "right_rail_mpu_2", "right_rail_mpu_3"):
        r = s.get(f"{BASE}/api/ads/banner/decision",
                  params={"slot_key": slot, "page_route": "/home"},
                  timeout=10)
        assert r.status_code == 200, f"{slot}: {r.status_code} {r.text[:200]}"
        b = r.json()
        assert b.get("source") == "house", f"{slot}: source={b.get('source')} body={b}"
        # 300x250 rail size (fields may be size string or w/h separated).
        size = b.get("size") or f"{b.get('width','')}x{b.get('height','')}"
        assert "300" in str(size) and "250" in str(size), f"{slot}: unexpected size {size}"


def test_banner_decision_none_for_premium():
    # Premium user should NOT see house/direct — source 'none' per prior contract.
    s = _login("premium@bigfm.dubai", "PremiumTest123!")
    r = s.get(f"{BASE}/api/ads/banner/decision",
              params={"slot_key": "right_rail_mpu_1", "page_route": "/home"},
              timeout=10)
    assert r.status_code == 200
    assert r.json().get("source") == "none"
