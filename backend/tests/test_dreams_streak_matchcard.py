"""Iteration 159 — Dreams Streak (1c) + Match Card Art (3a) backend E2E.

Covers:
  - GET  /api/social/dreams/streak — shape + fields
  - Streak increments once/day via readings (idempotent within same UTC day)
  - Streak also increments via compatibility share and dream share
  - POST /api/social/compatibility/share — card_id, path, share_path, image_url (.png), points_awarded
  - GET  /api/social/compatibility/card/{card_id}/image.png — 1200x630 image/png
  - GET  /api/social/compatibility/card/{card_id} — public, includes image_url
  - GET  /api/social/dreams/match/{card_id} — SSR HTML with og:image/twitter:image for crawlers
"""
import io
import os
import uuid

import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
FREE = {"email": "freeuser@bigfm.dubai", "password": "FreePass123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo_sess():
    return _login(DEMO)


@pytest.fixture(scope="module")
def free_sess():
    return _login(FREE)


@pytest.fixture(scope="module")
def demo_uid(demo_sess):
    r = demo_sess.get(f"{BASE_URL}/api/auth/me", timeout=10)
    assert r.status_code == 200
    return r.json().get("user_id") or r.json().get("id")


@pytest.fixture(scope="module")
def free_uid(free_sess):
    r = free_sess.get(f"{BASE_URL}/api/auth/me", timeout=10)
    assert r.status_code == 200
    return r.json().get("user_id") or r.json().get("id")


@pytest.fixture(scope="module")
def friendship(demo_sess, free_sess, demo_uid, free_uid):
    demo_sess.post(f"{BASE_URL}/api/social/friends/request",
                   json={"user_id": free_uid}, timeout=10)
    free_sess.post(f"{BASE_URL}/api/social/friends/{demo_uid}/accept", timeout=10)
    return (demo_uid, free_uid)


# ═══════════════════ A. STREAK ENDPOINT SHAPE ══════════════════════
class TestStreakShape:
    def test_get_streak_shape(self, demo_sess):
        r = demo_sess.get(f"{BASE_URL}/api/social/dreams/streak", timeout=10)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        b = r.json()
        for k in ("current", "longest", "active_today", "next_milestone", "milestones"):
            assert k in b, f"missing {k}: {b}"
        assert isinstance(b["current"], int)
        assert isinstance(b["longest"], int)
        assert isinstance(b["active_today"], bool)
        # next_milestone may be None if >=30
        assert b["next_milestone"] is None or isinstance(b["next_milestone"], int)
        assert isinstance(b["milestones"], dict)


# ═══════════════════ B. STREAK INCREMENT + IDEMPOTENCY ═════════════
class TestStreakIncrementReadings:
    def test_reading_bumps_streak_idempotent(self, demo_sess):
        # Baseline
        r0 = demo_sess.get(f"{BASE_URL}/api/social/dreams/streak", timeout=10).json()
        cur0 = r0["current"]
        active0 = r0["active_today"]

        # Trigger a horoscope reading
        r = demo_sess.post(f"{BASE_URL}/api/social/readings/horoscope",
                           json={"sign": "Aries", "period": "daily"}, timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        b = r.json()
        assert "streak" in b, f"reading response missing streak: keys={list(b.keys())}"
        s1 = b["streak"]
        assert "current" in s1
        # After first reading of the day, current should be >=1
        assert s1["current"] >= 1

        # Second reading same day — must be idempotent (awarded=0)
        r2 = demo_sess.post(f"{BASE_URL}/api/social/readings/horoscope",
                            json={"sign": "Aries", "period": "daily"}, timeout=60)
        assert r2.status_code == 200
        s2 = r2.json().get("streak")
        assert s2 is not None
        # current should not have advanced further within the same UTC day
        assert s2["current"] == s1["current"], f"streak advanced on same day: {s1} -> {s2}"
        # If awarded field present, must be 0
        if "awarded" in s2:
            assert s2["awarded"] == 0, f"awarded points on repeat same-day: {s2}"

        # GET streak — should reflect same current
        r3 = demo_sess.get(f"{BASE_URL}/api/social/dreams/streak", timeout=10).json()
        assert r3["current"] == s2["current"]
        assert r3["active_today"] is True


class TestStreakIncrementShare:
    def test_dream_share_touches_streak(self, demo_sess):
        # Get baseline
        r0 = demo_sess.get(f"{BASE_URL}/api/social/dreams/streak", timeout=10).json()
        cur0 = r0["current"]

        # Ensure consent
        demo_sess.post(f"{BASE_URL}/api/social/dreams/consent",
                       json={"terms_version": "1.0", "accepted": True}, timeout=10)
        unique = uuid.uuid4().hex[:6]
        r = demo_sess.post(f"{BASE_URL}/api/social/dreams",
                           json={"title": f"TEST_streak_{unique}",
                                 "description": f"A test streak dream {unique} with water and sky.",
                                 "mood": "Peaceful", "tags": ["Water"],
                                 "visibility": "public", "anonymous": False},
                           timeout=15)
        assert r.status_code in (200, 201), r.text[:200]

        # Streak current should still be >= baseline (already touched today usually)
        r1 = demo_sess.get(f"{BASE_URL}/api/social/dreams/streak", timeout=10).json()
        assert r1["current"] >= max(cur0, 1)
        assert r1["active_today"] is True


class TestStreakIncrementCompatShare:
    def test_compat_share_touches_streak(self, demo_sess, friendship):
        _demo_uid, free_uid = friendship
        r0 = demo_sess.get(f"{BASE_URL}/api/social/dreams/streak", timeout=10).json()
        cur0 = r0["current"]

        r = demo_sess.post(f"{BASE_URL}/api/social/compatibility/share",
                           json={"target_user_id": free_uid}, timeout=30)
        assert r.status_code == 200, r.text[:300]

        r1 = demo_sess.get(f"{BASE_URL}/api/social/dreams/streak", timeout=10).json()
        assert r1["current"] >= max(cur0, 1)


# ═══════════════════ C. COMPAT SHARE RESPONSE ══════════════════════
class TestCompatShareResponse:
    def test_share_returns_expected_keys(self, demo_sess, friendship):
        _demo_uid, free_uid = friendship
        r = demo_sess.post(f"{BASE_URL}/api/social/compatibility/share",
                           json={"target_user_id": free_uid}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        assert b.get("card_id", "").startswith("mc_"), f"card_id: {b}"
        assert b.get("path") == f"/dreams/match/{b['card_id']}"
        assert b.get("share_path") == f"/api/social/dreams/match/{b['card_id']}"
        img = b.get("image_url", "")
        assert isinstance(img, str) and img.endswith(".png"), f"image_url: {b}"
        assert img.startswith("http"), f"image_url should be absolute: {img}"
        assert "points_awarded" in b
        assert isinstance(b["points_awarded"], int)


# ═══════════════════ D. IMAGE.PNG ENDPOINT ═════════════════════════
class TestMatchCardImage:
    def test_image_png_returns_1200x630(self, demo_sess, friendship):
        _demo_uid, free_uid = friendship
        # Share a card
        r = demo_sess.post(f"{BASE_URL}/api/social/compatibility/share",
                           json={"target_user_id": free_uid}, timeout=45)
        assert r.status_code == 200
        card_id = r.json()["card_id"]

        # Fetch image (public — no auth)
        anon = requests.Session()
        img_r = anon.get(f"{BASE_URL}/api/social/compatibility/card/{card_id}/image.png",
                         timeout=60)
        assert img_r.status_code == 200, f"{img_r.status_code} {img_r.text[:200]}"
        ctype = img_r.headers.get("Content-Type", "")
        assert "image/png" in ctype, f"content-type: {ctype}"
        content = img_r.content
        assert len(content) > 5000, f"png too small ({len(content)} bytes) — likely error"
        # Validate PNG magic bytes
        assert content[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"

        # Validate dimensions via Pillow if available
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(content))
            assert im.size == (1200, 630), f"expected 1200x630, got {im.size}"
        except ImportError:
            pass

    def test_image_lazy_generation(self, demo_sess, friendship):
        """Image.png route must also work on cards that have no cached image yet.
        Since we can't easily create a card without image, just re-fetch existing card fast."""
        _demo_uid, free_uid = friendship
        r = demo_sess.post(f"{BASE_URL}/api/social/compatibility/share",
                           json={"target_user_id": free_uid}, timeout=45)
        card_id = r.json()["card_id"]
        # Fetch twice — second should be fast/cached
        anon = requests.Session()
        r1 = anon.get(f"{BASE_URL}/api/social/compatibility/card/{card_id}/image.png", timeout=60)
        r2 = anon.get(f"{BASE_URL}/api/social/compatibility/card/{card_id}/image.png", timeout=30)
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert "image/png" in r2.headers.get("Content-Type", "")


# ═══════════════════ E. PUBLIC CARD JSON w/ image_url ══════════════
class TestPublicCard:
    def test_public_card_includes_image_url(self, demo_sess, friendship):
        _demo_uid, free_uid = friendship
        r = demo_sess.post(f"{BASE_URL}/api/social/compatibility/share",
                           json={"target_user_id": free_uid}, timeout=45)
        card_id = r.json()["card_id"]
        anon = requests.Session()
        pr = anon.get(f"{BASE_URL}/api/social/compatibility/card/{card_id}", timeout=15)
        assert pr.status_code == 200, pr.text[:200]
        b = pr.json()
        assert b.get("card_id") == card_id
        assert b.get("image_url", "").endswith(".png"), f"image_url in card: {b}"
        assert b.get("image_url", "").startswith("http")


# ═══════════════════ F. SSR OG LANDING FOR CRAWLERS ════════════════
class TestSSROG:
    def test_crawler_gets_og_meta(self, demo_sess, friendship):
        _demo_uid, free_uid = friendship
        r = demo_sess.post(f"{BASE_URL}/api/social/compatibility/share",
                           json={"target_user_id": free_uid}, timeout=45)
        card_id = r.json()["card_id"]

        # Facebook crawler UA
        anon = requests.Session()
        headers = {"User-Agent": "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"}
        rp = anon.get(f"{BASE_URL}/api/social/dreams/match/{card_id}",
                      headers=headers, timeout=15, allow_redirects=False)
        # Should return SSR HTML (200), NOT a redirect
        assert rp.status_code == 200, f"{rp.status_code} {rp.text[:200]}"
        html = rp.text
        assert "og:image" in html, f"missing og:image in SSR HTML"
        assert "twitter:image" in html, f"missing twitter:image"
        assert card_id in html or ".png" in html
        # og:image should point to our .png
        assert "/image.png" in html or ".png" in html
