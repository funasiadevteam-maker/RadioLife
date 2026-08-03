"""Phase 41 Session 3.A — Business Radio backend tests.

Covers:
  - Business draft creation w/ business_profile
  - Owner update of business_profile (preserves verified/asset fields)
  - Logo upload (success, oversize 413, bad MIME 400)
  - Cover upload (success)
  - Non-owner 403 on profile update + uploads
  - Non-admin 403 on admin verify
  - Admin verify flip-on / flip-off
  - by-slug redaction matrix (verified, unverified anon, unverified owner)
  - discover ?filter=business|personal
  - openapi.json surfaces the 4 new routes
"""
from __future__ import annotations
import io
import os
import re
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback to frontend env (tests run inside /app)
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass
API = f"{BASE_URL}/api"

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
OWNER = ("test@bigfm.dubai",  "TestUser123!")
DEMO  = ("demo@bigfm.dubai",  "DemoPass123!")

VERIFIED_SLUG   = "s3a-smoke-karak"
UNVERIFIED_SLUG = "s3a-unverified-bar"


# -------- fixtures --------
def _login(email: str, pw: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_sess():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def owner_sess():
    return _login(*OWNER)


@pytest.fixture(scope="module")
def demo_sess():
    return _login(*DEMO)


@pytest.fixture(scope="module")
def anon_sess():
    return requests.Session()


# -------- 1) Business draft creation --------
class TestBusinessDraft:
    def test_create_business_draft(self, owner_sess):
        unique = f"TEST_s3a_draft_{uuid.uuid4().hex[:6]}"
        body = {
            "name": unique,
            "page_type": "business",  # alias should map to business_radio
            "tagline": "Test bar",
            "business_profile": {
                "legal_name": "Test Bar LLC",
                "display_name": "Test Bar",
                "category": "cafe",
                "address": "1 Test Street",
                "city": "Dubai",
                "country": "AE",
                "postal_code": "00000",
                "phone": "+971500000000",
                "website": "https://test.example",
                "hours": {
                    "mon": {"open": "08:00", "close": "22:00", "closed": False},
                    "tue": {"open": "08:00", "close": "22:00", "closed": False},
                    "wed": {"open": "08:00", "close": "22:00", "closed": False},
                    "thu": {"open": "08:00", "close": "22:00", "closed": False},
                    "fri": {"open": "08:00", "close": "22:00", "closed": False},
                    "sat": {"open": "09:00", "close": "23:00", "closed": False},
                    "sun": {"closed": True},
                },
            },
        }
        r = owner_sess.post(f"{API}/stations/draft", json=body, timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "slug" in data or "station_id" in data
        slug = data.get("slug")
        # Slug should derive from name (slugified) — verify via by-slug
        if slug:
            r2 = owner_sess.get(f"{API}/stations/by-slug/{slug}", timeout=15)
            assert r2.status_code == 200, r2.text
            s = r2.json()
            assert s.get("page_type") == "business_radio"
            assert s.get("is_business") is True
            assert (s.get("business_profile") or {}).get("legal_name") == "Test Bar LLC"


# -------- 2) Owner profile update --------
class TestOwnerProfileUpdate:
    def test_owner_can_update_business_profile(self, owner_sess):
        # Fetch existing to preserve invariants
        r0 = owner_sess.get(f"{API}/stations/by-slug/{VERIFIED_SLUG}", timeout=15)
        assert r0.status_code == 200, r0.text
        before = r0.json().get("business_profile") or {}
        old_logo = before.get("logo_url")
        old_verified = before.get("verified")
        new_tagline = f"updated-{uuid.uuid4().hex[:4]}"
        payload = {
            "legal_name": before.get("legal_name") or "S3A Smoke Karak",
            "display_name": before.get("display_name") or "S3A Smoke Karak",
            "category": before.get("category") or "cafe",
            "address": before.get("address") or "1 SZR",
            "city": before.get("city") or "Dubai",
            "country": before.get("country") or "AE",
            "postal_code": before.get("postal_code"),
            "phone": before.get("phone") or "+971501234567",
            "website": new_tagline,
            "hours": before.get("hours") or {},
        }
        r = owner_sess.post(f"{API}/stations/{VERIFIED_SLUG}/business_profile",
                            json=payload, timeout=15)
        assert r.status_code == 200, r.text
        bp = r.json()["business_profile"]
        # Verified flag + logo preserved (admin/asset-managed)
        assert bp.get("verified") == old_verified
        # Note: logo_url may be re-signed, but storage_key (real key) is preserved
        # We only assert that we didn't accidentally null logo_url
        assert (bp.get("logo_url") is None) == (old_logo is None)


# -------- 3) Logo upload --------
def _jpeg_bytes(n: int = 1024) -> bytes:
    # minimal JPEG header + padding (server checks MIME, not content)
    head = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    return head + (b"\x00" * max(0, n - len(head))) + b"\xff\xd9"


class TestLogoUpload:
    def test_logo_upload_success(self, owner_sess):
        files = {"image": ("logo.jpg", _jpeg_bytes(2048), "image/jpeg")}
        r = owner_sess.post(f"{API}/stations/{VERIFIED_SLUG}/business_profile/logo",
                            files=files, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert isinstance(data.get("logo_url"), str) and data["logo_url"].startswith("http")

    def test_logo_upload_oversize_413(self, owner_sess):
        big = _jpeg_bytes(2 * 1024 * 1024 + 10)
        files = {"image": ("big.jpg", big, "image/jpeg")}
        r = owner_sess.post(f"{API}/stations/{VERIFIED_SLUG}/business_profile/logo",
                            files=files, timeout=30)
        assert r.status_code == 413, r.text
        assert r.json().get("detail", {}).get("code") == "image_too_large"

    def test_logo_upload_bad_mime_400(self, owner_sess):
        files = {"image": ("evil.txt", b"hello world", "text/plain")}
        r = owner_sess.post(f"{API}/stations/{VERIFIED_SLUG}/business_profile/logo",
                            files=files, timeout=15)
        assert r.status_code == 400, r.text
        assert r.json().get("detail", {}).get("code") == "validation_error"


# -------- 4) Cover upload --------
class TestCoverUpload:
    def test_cover_upload_success(self, owner_sess):
        files = {"image": ("cover.jpg", _jpeg_bytes(4096), "image/jpeg")}
        r = owner_sess.post(f"{API}/stations/{VERIFIED_SLUG}/business_profile/cover",
                            files=files, timeout=30)
        assert r.status_code == 200, r.text
        assert isinstance(r.json().get("cover_url"), str)


# -------- 5) Non-owner 403 --------
class TestNonOwnerForbidden:
    def test_non_owner_profile_update_403(self, demo_sess):
        r = demo_sess.post(f"{API}/stations/{VERIFIED_SLUG}/business_profile",
                           json={"legal_name": "X", "category": "cafe",
                                 "address": "x", "city": "x", "country": "x"},
                           timeout=15)
        assert r.status_code == 403, r.text
        assert r.json().get("detail", {}).get("code") == "permission_denied"

    def test_non_owner_logo_403(self, demo_sess):
        files = {"image": ("logo.jpg", _jpeg_bytes(512), "image/jpeg")}
        r = demo_sess.post(f"{API}/stations/{VERIFIED_SLUG}/business_profile/logo",
                           files=files, timeout=15)
        assert r.status_code == 403, r.text

    def test_non_owner_cover_403(self, demo_sess):
        files = {"image": ("cover.jpg", _jpeg_bytes(512), "image/jpeg")}
        r = demo_sess.post(f"{API}/stations/{VERIFIED_SLUG}/business_profile/cover",
                           files=files, timeout=15)
        assert r.status_code == 403, r.text


# -------- 6) Non-admin verify 403 --------
class TestAdminGuard:
    def test_non_admin_verify_403(self, owner_sess):
        r = owner_sess.post(f"{API}/admin/stations/{VERIFIED_SLUG}/verify_business",
                            json={"verified": True}, timeout=15)
        assert r.status_code == 403, r.text
        assert r.json().get("detail", {}).get("code") == "permission_denied"


# -------- 7) Admin verify flip --------
class TestAdminVerifyFlip:
    def test_admin_verify_flip_on_then_off(self, admin_sess):
        # Flip ON
        r = admin_sess.post(f"{API}/admin/stations/{VERIFIED_SLUG}/verify_business",
                            json={"verified": True, "verification_method": "manual"},
                            timeout=15)
        assert r.status_code == 200, r.text
        bp = r.json()["business_profile"]
        assert bp["verified"] is True
        assert bp["verification_method"] == "manual"
        assert bp["verified_at"]
        # Flip OFF
        r2 = admin_sess.post(f"{API}/admin/stations/{VERIFIED_SLUG}/verify_business",
                             json={"verified": False}, timeout=15)
        assert r2.status_code == 200, r2.text
        bp2 = r2.json()["business_profile"]
        assert bp2["verified"] is False
        assert bp2.get("verification_method") is None
        assert bp2.get("verified_at") is None
        # Restore ON for downstream tests
        r3 = admin_sess.post(f"{API}/admin/stations/{VERIFIED_SLUG}/verify_business",
                             json={"verified": True, "verification_method": "manual"},
                             timeout=15)
        assert r3.status_code == 200


# -------- 8) by-slug redaction matrix --------
class TestBySlugRedaction:
    def test_verified_business_phone_visible(self, anon_sess, admin_sess):
        # Ensure verified
        admin_sess.post(f"{API}/admin/stations/{VERIFIED_SLUG}/verify_business",
                        json={"verified": True, "verification_method": "manual"},
                        timeout=15)
        r = anon_sess.get(f"{API}/stations/by-slug/{VERIFIED_SLUG}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("pending_verification") is False
        bp = data.get("business_profile") or {}
        assert bp.get("phone"), "phone should be visible for verified business"

    def test_unverified_anon_sees_redacted_phone(self, anon_sess):
        r = anon_sess.get(f"{API}/stations/by-slug/{UNVERIFIED_SLUG}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("pending_verification") is True
        bp = data.get("business_profile") or {}
        assert bp.get("phone") in (None, ""), f"phone should be redacted for anon, got {bp.get('phone')}"
        # Other fields preserved
        assert bp.get("address")
        assert bp.get("city")

    def test_unverified_listener_sees_redacted_phone(self, demo_sess):
        r = demo_sess.get(f"{API}/stations/by-slug/{UNVERIFIED_SLUG}", timeout=15)
        assert r.status_code == 200, r.text
        bp = r.json().get("business_profile") or {}
        assert bp.get("phone") in (None, "")

    def test_unverified_owner_sees_full_phone(self, owner_sess):
        r = owner_sess.get(f"{API}/stations/by-slug/{UNVERIFIED_SLUG}", timeout=15)
        assert r.status_code == 200, r.text
        bp = r.json().get("business_profile") or {}
        assert bp.get("phone"), "owner must see their own phone on unverified business"


# -------- 9) Discover filter --------
class TestDiscoverFilter:
    def test_discover_business_only(self, anon_sess):
        r = anon_sess.get(f"{API}/stations/discover", params={"filter": "business"},
                          timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        # Response shape: featured/trending/recent buckets — assert every
        # surfaced row is a business.
        items = []
        for k in ("featured", "trending", "recent", "items"):
            v = data.get(k)
            if isinstance(v, list):
                items.extend(v)
        assert items, f"discover business returned no rows: {data}"
        for s in items:
            assert s.get("is_business") is True or s.get("page_type") == "business_radio", \
                f"non-business leaked into business filter: {s.get('slug')}"

    def test_discover_personal_only(self, anon_sess):
        r = anon_sess.get(f"{API}/stations/discover", params={"filter": "personal"},
                          timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        items = []
        for k in ("featured", "trending", "recent", "items"):
            v = data.get(k)
            if isinstance(v, list):
                items.extend(v)
        for s in items:
            assert not s.get("is_business"), \
                f"business leaked into personal filter: {s.get('slug')}"

    def test_discover_no_filter_mixed(self, anon_sess):
        r = anon_sess.get(f"{API}/stations/discover", timeout=15)
        assert r.status_code == 200


# -------- 10) OpenAPI routes --------
class TestOpenApi:
    def test_new_routes_in_openapi(self, anon_sess):
        r = anon_sess.get(f"{API}/openapi.json", timeout=20)
        assert r.status_code == 200, r.text
        paths = r.json().get("paths", {})
        required = [
            "/api/stations/{slug}/business_profile",
            "/api/stations/{slug}/business_profile/logo",
            "/api/stations/{slug}/business_profile/cover",
            "/api/admin/stations/{slug}/verify_business",
        ]
        missing = [p for p in required if p not in paths]
        assert not missing, f"missing openapi paths: {missing}"
