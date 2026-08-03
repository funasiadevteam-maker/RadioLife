"""Phase 4.5 retest — targeted verification of the AI sponsor-read preview fix.

The HIGH bug from iteration_10: AI sponsor read returned audio_url=/api/ads/creative/<id>/audio
but the public /audio route filters {active:true}, returning 404 for AI drafts inserted
with active=False.

Fix: services.sponsor_read now returns audio_url=/api/ads/creative/<id>/preview, and a new
route /preview was added that:
  - requires auth (admin or owner advertiser)
  - DOES NOT filter on active
  - returns 200/206 audio/mpeg
  - returns 403 for other advertisers, 404 if creative doesn't exist

Regression: the original /audio route still filters active=True for public listener stream.
"""
from __future__ import annotations
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
FREE = {"email": "test@bigfm.dubai", "password": "TestUser123!"}
BIZ_ID = "biz_karak_cafe_karama"
ACTIVE_CREATIVE_ID = "crv_cmp_karak_20off"  # seeded active=True creative


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def free_sess():
    return _login(FREE)


@pytest.fixture(scope="module")
def ai_creative(admin_sess):
    """Generate an AI sponsor read once, reuse for multiple tests."""
    r = admin_sess.post(
        f"{BASE_URL}/api/advertiser/creative/ai_sponsor_read",
        json={
            "business_id": BIZ_ID,
            "brief": "Friday brunch buffet 50 percent off",
            "voice_key": "aanya_hindi",
            "duration_sec": 15,
            "tone": "warm-energetic",
        },
        timeout=120,
    )
    assert r.status_code == 200, f"sponsor read gen failed: {r.status_code} {r.text[:400]}"
    body = r.json()
    assert body.get("creative_id"), body
    assert body.get("audio_url"), body
    return body


# =========================================================
# PRIMARY: sponsor read returns /preview path
# =========================================================
class TestAISponsorReadPreviewURL:
    def test_audio_url_points_to_preview(self, ai_creative):
        """audio_url must now be /api/ads/creative/<id>/preview, not /audio."""
        url = ai_creative["audio_url"]
        cid = ai_creative["creative_id"]
        assert url == f"/api/ads/creative/{cid}/preview", (
            f"audio_url should be /preview path, got: {url}"
        )

    def test_response_shape(self, ai_creative):
        assert ai_creative.get("creative_id")
        assert ai_creative.get("transcript")
        assert ai_creative.get("duration_sec")


# =========================================================
# PRIMARY: GET /preview works for admin (200/206 audio/mpeg)
# =========================================================
class TestPreviewRoute:
    def test_preview_admin_can_stream(self, admin_sess, ai_creative):
        audio_url = BASE_URL + ai_creative["audio_url"]
        r = admin_sess.get(audio_url, timeout=20, stream=True)
        assert r.status_code in (200, 206), (
            f"preview should be streamable by admin, got {r.status_code}: {r.text[:200]}"
        )
        ctype = r.headers.get("Content-Type", "")
        assert "audio/mpeg" in ctype, f"expected audio/mpeg, got {ctype}"
        # Pull at least a chunk to confirm the body streams
        chunk = next(r.iter_content(chunk_size=1024), b"")
        assert len(chunk) > 0, "no audio bytes received"
        r.close()

    def test_preview_with_range_returns_206(self, admin_sess, ai_creative):
        audio_url = BASE_URL + ai_creative["audio_url"]
        r = admin_sess.get(audio_url, headers={"Range": "bytes=0-1023"}, timeout=20, stream=True)
        assert r.status_code == 206, f"Range request should return 206, got {r.status_code}"
        assert "Content-Range" in r.headers
        r.close()

    def test_preview_requires_auth(self, ai_creative):
        """Unauthenticated request must be rejected (401/403)."""
        audio_url = BASE_URL + ai_creative["audio_url"]
        r = requests.get(audio_url, timeout=15, allow_redirects=False)
        assert r.status_code in (401, 403), (
            f"preview must require auth, got {r.status_code}: {r.text[:200]}"
        )

    def test_preview_forbidden_for_other_advertiser(self, free_sess, ai_creative):
        """Free user (not the owning advertiser, not admin) should get 403."""
        audio_url = BASE_URL + ai_creative["audio_url"]
        r = free_sess.get(audio_url, timeout=15, allow_redirects=False)
        # 403 (not owner / not admin) — but free_sess user may not be an advertiser at all,
        # in which case the lookup adv=None → 403 still. Accept 401 too in case auth is
        # rejected upstream.
        assert r.status_code in (401, 403), (
            f"non-owner non-admin should be 401/403, got {r.status_code}: {r.text[:200]}"
        )

    def test_preview_404_for_missing_creative(self, admin_sess):
        r = admin_sess.get(
            f"{BASE_URL}/api/ads/creative/crv_does_not_exist_xyz/preview",
            timeout=10,
        )
        assert r.status_code == 404, f"missing creative should be 404, got {r.status_code}"


# =========================================================
# REGRESSION: /audio still works for active creative
# =========================================================
class TestPublicAudioRouteUnchanged:
    def test_active_creative_audio_still_streams(self):
        """The public /audio route should still serve ACTIVE creatives (no auth required)."""
        url = f"{BASE_URL}/api/ads/creative/{ACTIVE_CREATIVE_ID}/audio"
        r = requests.get(url, timeout=20, stream=True)
        assert r.status_code in (200, 206), (
            f"/audio for active creative should return 200/206, got {r.status_code}: {r.text[:200]}"
        )
        ctype = r.headers.get("Content-Type", "")
        assert "audio/mpeg" in ctype, f"expected audio/mpeg, got {ctype}"
        chunk = next(r.iter_content(chunk_size=1024), b"")
        assert len(chunk) > 0
        r.close()

    def test_inactive_ai_creative_audio_route_still_404(self, ai_creative):
        """The /audio route (active=True filter) should still 404 for inactive AI drafts.
        This proves the separation: /audio = listener stream (active only),
        /preview = advertiser/admin audit (any state)."""
        cid = ai_creative["creative_id"]
        url = f"{BASE_URL}/api/ads/creative/{cid}/audio"
        r = requests.get(url, timeout=15, allow_redirects=False)
        assert r.status_code == 404, (
            f"/audio for inactive AI creative should remain 404 (active filter), got {r.status_code}"
        )
