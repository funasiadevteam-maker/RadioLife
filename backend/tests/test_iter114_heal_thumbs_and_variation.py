"""Iteration 114 — Heal All Thumbnails + Fresh Art Variations + regressions.

Covers:
  * POST /api/admin/channels/thumbnails/heal-all (admin-gated, idempotent,
    real regenerate after simulating missing files on disk + Tigris).
  * POST /api/imported-stations/{sid}/artwork/generate with {"variation":true}
    (prompt has 'alternate take' nonce; two calls yield DIFFERENT art urls;
    previous archived to artwork_history). Without variation, no nonce.
  * Regression: POST /api/imported-stations/ensure-flagship-art idempotent.
"""
import os
import sys
import time
import pathlib

# Load backend .env so services.object_storage picks the tigris backend
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

sys.path.insert(0, "/app/backend")

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "http://localhost:8001"
# Prefer external URL from /app/frontend/.env
try:
    for line in pathlib.Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
except Exception:
    pass

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"

FLAGSHIP_SID = "imp_fun_big_1062_uae"
NONFLAG_SID = "imp_780122061aa111e9a8"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


# ── Heal all thumbnails ─────────────────────────────────────────────
class TestHealAllThumbnails:
    def test_anon_forbidden(self, anon_session):
        r = anon_session.post(f"{BASE_URL}/api/admin/channels/thumbnails/heal-all", timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403 for anon, got {r.status_code}"

    def test_admin_returns_ok_shape(self, admin_session):
        r = admin_session.post(f"{BASE_URL}/api/admin/channels/thumbnails/heal-all", timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert "missing" in data and isinstance(data["missing"], int)
        assert "started" in data and isinstance(data["started"], bool)

    def test_idempotent_healthy_fleet(self, admin_session):
        # After first call above the fleet should be healthy — second call:
        # missing==0, started==False.
        r = admin_session.post(f"{BASE_URL}/api/admin/channels/thumbnails/heal-all", timeout=60)
        assert r.status_code == 200
        data = r.json()
        # Allow small race: if first call queued but async task not done,
        # re-poll a bit before asserting healthy.
        for _ in range(6):
            if data.get("missing", 1) == 0 and data.get("started") is False:
                break
            time.sleep(3)
            r = admin_session.post(f"{BASE_URL}/api/admin/channels/thumbnails/heal-all", timeout=60)
            data = r.json()
        assert data["missing"] == 0, f"expected healthy, got {data}"
        assert data["started"] is False

    def test_regenerates_after_missing_simulation(self, admin_session):
        """Delete both disk file and Tigris key for a channel with a
        thumbnail_prompt, verify heal-all detects+regenerates it."""
        from services.object_storage import get_storage
        from services import channel_thumbnails as ct

        slug = "vip_lounge"
        # Confirm prompt exists
        assert slug in ct.THUMBNAIL_PROMPTS

        disk_path = pathlib.Path(f"/app/backend/static/channel_thumbnails/{slug}.webp")
        tigris_key = f"static/channel_thumbnails/{slug}.webp"

        storage = get_storage()
        # Simulate missing: delete disk + Tigris copies.
        try:
            if disk_path.exists():
                disk_path.unlink()
        except Exception:
            pass
        try:
            storage.delete(key=tigris_key)
        except Exception:
            pass

        # Confirm probe says missing.
        assert ct._thumb_missing(slug) is True, "expected _thumb_missing True after deletion"

        # heal-all should now detect + queue.
        r = admin_session.post(f"{BASE_URL}/api/admin/channels/thumbnails/heal-all", timeout=60)
        assert r.status_code == 200
        data = r.json()
        assert data["missing"] >= 1, f"expected missing>=1 after deletion, got {data}"
        assert data["started"] is True

        # Poll _thumb_missing until it's False (regen is 5-70s per image).
        deadline = time.time() + 120
        healed = False
        while time.time() < deadline:
            if not ct._thumb_missing(slug):
                healed = True
                break
            time.sleep(4)
        assert healed, f"channel {slug} was not durably regenerated within 120s"

        # Also verify durable copy is actually in Tigris (not just disk).
        assert storage.exists(key=tigris_key), f"regen didn't land in Tigris: {tigris_key}"


# ── Fresh Art Variation ─────────────────────────────────────────────
def _poll_art_status(session, sid, timeout=120):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = session.get(f"{BASE_URL}/api/imported-stations/{sid}/artwork/status", timeout=30)
        if r.status_code == 200:
            last = r.json()
            if last.get("status") in ("complete", "failed"):
                return last
        time.sleep(3)
    return last


class TestFreshArtVariation:
    def test_variation_flag_adds_nonce_to_prompt_flagship(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/imported-stations/{FLAGSHIP_SID}/artwork/generate",
            json={"variation": True}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "alternate take" in (data.get("prompt") or "").lower(), \
            f"expected 'alternate take' in variation prompt, got: {data.get('prompt')[:200]}"
        # Wait for it to settle so subsequent tests don't collide.
        _poll_art_status(admin_session, FLAGSHIP_SID)

    def test_no_variation_no_nonce(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/imported-stations/{NONFLAG_SID}/artwork/generate",
            json={}, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "alternate take" not in (data.get("prompt") or "").lower()
        _poll_art_status(admin_session, NONFLAG_SID)

    def test_two_variations_yield_different_art(self, admin_session):
        # First variation
        r1 = admin_session.post(
            f"{BASE_URL}/api/imported-stations/{NONFLAG_SID}/artwork/generate",
            json={"variation": True}, timeout=60)
        assert r1.status_code == 200, r1.text
        p1 = r1.json().get("prompt")
        s1 = _poll_art_status(admin_session, NONFLAG_SID, timeout=140)
        assert s1 and s1.get("status") == "complete", f"first variation didn't complete: {s1}"
        url1 = s1.get("image_url")

        # Second variation (should be a different generation)
        r2 = admin_session.post(
            f"{BASE_URL}/api/imported-stations/{NONFLAG_SID}/artwork/generate",
            json={"variation": True}, timeout=60)
        assert r2.status_code == 200, r2.text
        p2 = r2.json().get("prompt")
        assert p1 != p2, "two variation prompts must differ (nonce)"
        s2 = _poll_art_status(admin_session, NONFLAG_SID, timeout=140)
        assert s2 and s2.get("status") == "complete", f"second variation didn't complete: {s2}"
        url2 = s2.get("image_url")

        assert url1 and url2 and url1 != url2, \
            f"expected different art URLs across two variations, got {url1} vs {url2}"

    def test_history_contains_previous_variation(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/imported-stations/{NONFLAG_SID}/artwork/history", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("ok") is True
        hist = data.get("history") or []
        assert len(hist) >= 1, "expected archived variation(s) in artwork_history"
        assert any(h.get("url") for h in hist)


# ── Regression: ensure-flagship-art still idempotent ────────────────
class TestEnsureFlagshipArtRegression:
    def test_ensure_flagship_art_idempotent(self, admin_session):
        r1 = admin_session.post(
            f"{BASE_URL}/api/imported-stations/ensure-flagship-art", timeout=60)
        assert r1.status_code == 200
        q1 = r1.json().get("queued", 0)
        # Sleep briefly then second call should not queue more than first.
        time.sleep(2)
        r2 = admin_session.post(
            f"{BASE_URL}/api/imported-stations/ensure-flagship-art", timeout=60)
        assert r2.status_code == 200
        q2 = r2.json().get("queued", 0)
        assert q2 <= q1, f"expected idempotent queued<=first, got q1={q1} q2={q2}"
