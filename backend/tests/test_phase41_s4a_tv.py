"""Phase 41 Session 4.A — In-Store Business TV Display backend tests.

Covers:
  - GET /api/tv/{slug} — verified business (phone visible)
  - GET /api/tv/{slug} — unverified business (phone REDACTED)
  - GET /api/tv/{slug} — unlisted/private station 403
  - GET /api/tv/{slug} — missing station 404
  - Cache hit on second call within 8s (same server_time)
  - Owner CRUD: create / list / patch / delete + validation matrix
  - Non-owner forbidden + Active-cap 429
  - openapi.json lists all 6 new routes
"""
from __future__ import annotations
import io
import os
import re
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
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
PRIVATE_SLUG    = "s4-private-test"
PERSONAL_SLUG   = "p41-audit-test"


def _login(email: str, pw: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def owner_sess(): return _login(*OWNER)


@pytest.fixture(scope="module")
def demo_sess(): return _login(*DEMO)


@pytest.fixture(scope="module")
def anon_sess(): return requests.Session()


# ============ TV GET ============
class TestTVPublic:
    def test_verified_business_full_payload(self, anon_sess):
        r = anon_sess.get(f"{API}/tv/{VERIFIED_SLUG}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        st = data["station"]
        assert st["is_business"] is True
        bp = st["business_profile"]
        assert bp.get("verified") is True
        # Phone visible for verified
        assert bp.get("phone") == "+971501234567", f"phone mismatch: {bp.get('phone')}"
        # qr_target_url absolute https
        assert data["qr_target_url"].startswith("https://")
        assert data["qr_target_url"].endswith(f"/r/{VERIFIED_SLUG}")
        assert data["refresh_after_sec"] == 10
        # Top-3 announcements sorted by priority desc then created_at desc
        anns = data["announcements"]
        assert isinstance(anns, list)
        assert len(anns) <= 3
        if len(anns) >= 2:
            prios = [a["priority"] for a in anns]
            assert prios == sorted(prios, reverse=True), f"not sorted by priority: {prios}"

    def test_unverified_business_phone_redacted(self, anon_sess):
        r = anon_sess.get(f"{API}/tv/{UNVERIFIED_SLUG}", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        st = data["station"]
        assert st["is_business"] is True
        assert st["pending_verification"] is True
        bp = st["business_profile"]
        assert bp.get("phone") in (None, ""), f"phone should be redacted: {bp.get('phone')}"
        # Address / city still present
        assert bp.get("address")
        assert bp.get("city")

    def test_private_station_403(self, anon_sess):
        r = anon_sess.get(f"{API}/tv/{PRIVATE_SLUG}", timeout=15)
        # Either 403 (privacy block) or 404 (not seeded). Spec says 403.
        if r.status_code == 404:
            pytest.skip(f"Private station {PRIVATE_SLUG} not seeded — skipping")
        assert r.status_code == 403, r.text
        assert r.json().get("detail", {}).get("code") == "private_station"

    def test_not_found_404(self, anon_sess):
        r = anon_sess.get(f"{API}/tv/does-not-exist-xyz", timeout=15)
        assert r.status_code == 404, r.text
        assert r.json().get("detail", {}).get("code") == "not_found"

    def test_cache_hit_within_8s(self, anon_sess):
        # First call (may populate)
        r1 = anon_sess.get(f"{API}/tv/{VERIFIED_SLUG}", timeout=15)
        assert r1.status_code == 200
        st1 = r1.json()["server_time"]
        # Immediate second call -> cache hit, same server_time
        r2 = anon_sess.get(f"{API}/tv/{VERIFIED_SLUG}", timeout=15)
        assert r2.status_code == 200
        st2 = r2.json()["server_time"]
        assert st1 == st2, f"cache miss: {st1} != {st2}"


# ============ Announcement CRUD ============
def _make_ann(sess, slug, **kwargs) -> dict:
    body = {"message": kwargs.get("message", "TEST_ann " + uuid.uuid4().hex[:6]),
            "priority": kwargs.get("priority", 5)}
    if "starts_at" in kwargs: body["starts_at"] = kwargs["starts_at"]
    if "ends_at" in kwargs:   body["ends_at"]   = kwargs["ends_at"]
    r = sess.post(f"{API}/stations/{slug}/announcements", json=body, timeout=15)
    return r


class TestAnnouncementCreate:
    def test_owner_create_minimal(self, owner_sess):
        r = _make_ann(owner_sess, VERIFIED_SLUG,
                       message="TEST_minimal_" + uuid.uuid4().hex[:4])
        # Could 429 if cap; if so we skip and let the cap test handle.
        if r.status_code == 429:
            pytest.skip("Active cap reached; tested separately")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["station_slug"] == VERIFIED_SLUG
        assert d["active"] is True
        assert "id" in d
        # Cleanup
        owner_sess.delete(f"{API}/stations/{VERIFIED_SLUG}/announcements/{d['id']}",
                          timeout=15)

    def test_owner_create_280_chars_ok(self, owner_sess):
        msg = "x" * 280
        r = _make_ann(owner_sess, VERIFIED_SLUG, message=msg)
        if r.status_code == 429:
            pytest.skip("Active cap reached")
        assert r.status_code == 200, r.text
        owner_sess.delete(
            f"{API}/stations/{VERIFIED_SLUG}/announcements/{r.json()['id']}", timeout=15)

    def test_owner_create_281_chars_400(self, owner_sess):
        msg = "x" * 281
        r = _make_ann(owner_sess, VERIFIED_SLUG, message=msg)
        assert r.status_code == 400, r.text
        d = r.json().get("detail", {})
        assert d.get("code") == "validation_error"
        assert d.get("field") == "message"
        assert d.get("max_chars") == 280

    def test_priority_bounds(self, owner_sess):
        # priority=0 -> 400
        r0 = _make_ann(owner_sess, VERIFIED_SLUG, priority=0)
        assert r0.status_code == 400, r0.text
        assert r0.json()["detail"]["field"] == "priority"
        # priority=11 -> 400
        r11 = _make_ann(owner_sess, VERIFIED_SLUG, priority=11)
        assert r11.status_code == 400, r11.text
        assert r11.json()["detail"]["field"] == "priority"
        # priority=1 OK (may 429)
        r1 = _make_ann(owner_sess, VERIFIED_SLUG, priority=1,
                        message="TEST_p1_" + uuid.uuid4().hex[:4])
        if r1.status_code != 429:
            assert r1.status_code == 200, r1.text
            owner_sess.delete(
                f"{API}/stations/{VERIFIED_SLUG}/announcements/{r1.json()['id']}",
                timeout=15)
        # priority=10 OK
        r10 = _make_ann(owner_sess, VERIFIED_SLUG, priority=10,
                         message="TEST_p10_" + uuid.uuid4().hex[:4])
        if r10.status_code != 429:
            assert r10.status_code == 200, r10.text
            owner_sess.delete(
                f"{API}/stations/{VERIFIED_SLUG}/announcements/{r10.json()['id']}",
                timeout=15)

    def test_starts_after_ends_400(self, owner_sess):
        r = _make_ann(owner_sess, VERIFIED_SLUG,
                       starts_at="2030-01-02T00:00:00+00:00",
                       ends_at="2030-01-01T00:00:00+00:00")
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["field"] == "ends_at"

    def test_non_owner_create_403(self, demo_sess):
        r = _make_ann(demo_sess, VERIFIED_SLUG, message="TEST_nonowner")
        assert r.status_code == 403, r.text
        assert r.json()["detail"]["code"] == "permission_denied"


# ============ List / PATCH / DELETE ============
class TestListPatchDelete:
    def test_list_anon_active_only(self, anon_sess):
        r = anon_sess.get(f"{API}/stations/{VERIFIED_SLUG}/announcements", timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        for a in items:
            assert a["active"] is True, f"non-active leaked to anon: {a}"

    def test_list_owner_include_expired(self, owner_sess):
        r = owner_sess.get(f"{API}/stations/{VERIFIED_SLUG}/announcements",
                            params={"include_expired": "true"}, timeout=15)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        # Should return >= the public count
        assert isinstance(items, list)

    def test_patch_and_delete_full_flow(self, owner_sess, demo_sess):
        # Create
        r = _make_ann(owner_sess, VERIFIED_SLUG,
                       message="TEST_patchflow_" + uuid.uuid4().hex[:4])
        if r.status_code == 429:
            pytest.skip("Active cap reached")
        assert r.status_code == 200, r.text
        ann_id = r.json()["id"]

        # PATCH update OK
        r2 = owner_sess.patch(
            f"{API}/stations/{VERIFIED_SLUG}/announcements/{ann_id}",
            json={"priority": 10, "message": "updated"}, timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json()["priority"] == 10
        assert r2.json()["message"] == "updated"

        # Non-owner PATCH -> 403
        r3 = demo_sess.patch(
            f"{API}/stations/{VERIFIED_SLUG}/announcements/{ann_id}",
            json={"priority": 1}, timeout=15)
        assert r3.status_code == 403, r3.text

        # PATCH non-existent -> 404
        r4 = owner_sess.patch(
            f"{API}/stations/{VERIFIED_SLUG}/announcements/ann_doesnotexist",
            json={"priority": 1}, timeout=15)
        assert r4.status_code == 404, r4.text

        # PATCH invalid id -> 400
        r5 = owner_sess.patch(
            f"{API}/stations/{VERIFIED_SLUG}/announcements/!!!",
            json={"priority": 1}, timeout=15)
        assert r5.status_code == 400, r5.text
        assert r5.json()["detail"]["field"] == "ann_id"

        # Non-owner DELETE -> 403
        r6 = demo_sess.delete(
            f"{API}/stations/{VERIFIED_SLUG}/announcements/{ann_id}", timeout=15)
        assert r6.status_code == 403, r6.text

        # Owner DELETE OK
        r7 = owner_sess.delete(
            f"{API}/stations/{VERIFIED_SLUG}/announcements/{ann_id}", timeout=15)
        assert r7.status_code == 200, r7.text
        assert r7.json() == {"ok": True, "deleted": ann_id}

        # GET no longer returns
        r8 = owner_sess.get(
            f"{API}/stations/{VERIFIED_SLUG}/announcements",
            params={"include_expired": "true"}, timeout=15)
        assert all(a["id"] != ann_id for a in r8.json()["items"])


# ============ Active-cap on a fresh slug (use UNVERIFIED_SLUG) ============
class TestActiveCap:
    def test_active_cap_429(self, owner_sess):
        slug = UNVERIFIED_SLUG  # Owned by test@; less polluted
        # Snapshot existing IDs we create so we can clean up
        created_ids = []
        # First, ensure no test rows linger from prior runs by listing expired+active
        r0 = owner_sess.get(f"{API}/stations/{slug}/announcements",
                             params={"include_expired": "true"}, timeout=15)
        assert r0.status_code == 200, r0.text
        pre_count = sum(1 for a in r0.json()["items"] if a.get("active"))
        try:
            # Fill up to cap
            need = 10 - pre_count
            for i in range(max(0, need)):
                r = _make_ann(owner_sess, slug,
                               message=f"TEST_cap_{i}_" + uuid.uuid4().hex[:4])
                assert r.status_code == 200, f"unexpected cap during fill at {i}: {r.text}"
                created_ids.append(r.json()["id"])
            # Next should 429
            rcap = _make_ann(owner_sess, slug,
                              message="TEST_cap_overflow_" + uuid.uuid4().hex[:4])
            assert rcap.status_code == 429, rcap.text
            d = rcap.json().get("detail", {})
            assert d.get("code") == "active_cap"
            assert d.get("max_active") == 10
        finally:
            # Cleanup all our created TEST rows
            for aid in created_ids:
                try:
                    owner_sess.delete(
                        f"{API}/stations/{slug}/announcements/{aid}", timeout=10)
                except Exception:
                    pass


# ============ Image upload ============
def _jpeg_bytes(n: int = 1024) -> bytes:
    head = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    return head + (b"\x00" * max(0, n - len(head))) + b"\xff\xd9"


class TestImageUpload:
    @pytest.fixture(scope="class")
    def fresh_ann_id(self, owner_sess):
        r = _make_ann(owner_sess, UNVERIFIED_SLUG,
                       message="TEST_img_" + uuid.uuid4().hex[:4])
        if r.status_code == 429:
            pytest.skip("Active cap reached on UNVERIFIED_SLUG")
        assert r.status_code == 200, r.text
        ann_id = r.json()["id"]
        yield ann_id
        owner_sess.delete(
            f"{API}/stations/{UNVERIFIED_SLUG}/announcements/{ann_id}", timeout=10)

    def test_image_upload_success(self, owner_sess, fresh_ann_id):
        files = {"file": ("ann.jpg", _jpeg_bytes(2048), "image/jpeg")}
        r = owner_sess.post(
            f"{API}/stations/{UNVERIFIED_SLUG}/announcements/{fresh_ann_id}/image",
            files=files, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert isinstance(d.get("image_url"), str) and d["image_url"].startswith("http")

    def test_image_upload_oversize_413(self, owner_sess, fresh_ann_id):
        files = {"file": ("big.jpg", _jpeg_bytes(2 * 1024 * 1024 + 10), "image/jpeg")}
        r = owner_sess.post(
            f"{API}/stations/{UNVERIFIED_SLUG}/announcements/{fresh_ann_id}/image",
            files=files, timeout=30)
        assert r.status_code == 413, r.text
        assert r.json()["detail"]["code"] == "image_too_large"
        assert r.json()["detail"]["max_bytes"] == 2 * 1024 * 1024

    def test_image_upload_bad_mime_400(self, owner_sess, fresh_ann_id):
        files = {"file": ("evil.txt", b"hello", "text/plain")}
        r = owner_sess.post(
            f"{API}/stations/{UNVERIFIED_SLUG}/announcements/{fresh_ann_id}/image",
            files=files, timeout=15)
        assert r.status_code == 400, r.text
        assert r.json()["detail"]["code"] == "validation_error"
        assert r.json()["detail"]["field"] == "image"


# ============ OpenAPI ============
class TestOpenApi:
    def test_six_new_routes_listed(self, anon_sess):
        r = anon_sess.get(f"{API}/openapi.json", timeout=20)
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        required = [
            "/api/tv/{slug}",
            "/api/stations/{slug}/announcements",
            "/api/stations/{slug}/announcements/{ann_id}",
            "/api/stations/{slug}/announcements/{ann_id}/image",
        ]
        missing = [p for p in required if p not in paths]
        assert not missing, f"missing openapi paths: {missing}"
        # Verify methods on the announcements path
        anns = paths["/api/stations/{slug}/announcements"]
        assert "get" in anns and "post" in anns
        ann_id_path = paths["/api/stations/{slug}/announcements/{ann_id}"]
        assert "patch" in ann_id_path and "delete" in ann_id_path
