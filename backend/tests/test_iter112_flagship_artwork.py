"""Iteration 112 — Flagship AI cover-art (name + dial baked in) tests.

Verifies backend flows for /api/imported-stations flagship artwork:
 - POST /{sid}/artwork/generate for a flagship station returns queued
    and eventually completes with a `/api/static/station_artwork/flg-*.webp`
    badged composite image.
 - POST /ensure-flagship-art is idempotent.
 - POST /{sid}/artwork/upload sets art_source='owner' for an admin.
 - Non-flagship station generate still works (plain art, no flg- prefix).
 - The flagship prompt contains the station name + reserves the lower third.
"""
from __future__ import annotations

import io
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASSWORD = "AdminPass123!"

POLL_SECONDS = 90
POLL_INTERVAL = 3


# ── Fixtures ──────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def flagship_sid(admin_session):
    # Prefer the station named in the problem statement.
    r = admin_session.get(f"{BASE_URL}/api/admin/stations/flagship", timeout=15)
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert items, "No flagship stations seeded"
    # Pick imp_fun_big_1062_uae if present.
    for s in items:
        if s.get("id") == "imp_fun_big_1062_uae":
            return s["id"]
    return items[0]["id"]


@pytest.fixture(scope="module")
def non_flagship_sid(admin_session):
    # Grab any imported (non-flagship) station.
    r = admin_session.get(
        f"{BASE_URL}/api/live-radio/stations?limit=25", timeout=15)
    if r.status_code != 200:
        pytest.skip(f"Cannot list imported stations: {r.status_code}")
    data = r.json()
    items = data.get("items") if isinstance(data, dict) else data
    if not items:
        pytest.skip("No imported (non-flagship) stations available")
    for s in items:
        if not s.get("is_flagship") and not s.get("flagship_slug"):
            return s.get("id")
    pytest.skip("No non-flagship imported station found")


# ── Tests: flagship artwork generation ────────────────────────────────
class TestFlagshipArtworkGenerate:

    def test_generate_endpoint_queues(self, admin_session, flagship_sid):
        r = admin_session.post(
            f"{BASE_URL}/api/imported-stations/{flagship_sid}/artwork/generate",
            json={})
        assert r.status_code == 200, f"generate failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("ok") is True
        assert data.get("status") == "queued"
        # Prompt must include the station name.
        prompt = data.get("prompt") or ""
        assert prompt, "prompt missing in response"
        # The lower-third reservation directive should be present.
        assert "lower" in prompt.lower() and "third" in prompt.lower(), (
            f"Flagship prompt missing lower-third reservation. prompt={prompt!r}")
        # Store globally.
        TestFlagshipArtworkGenerate.prompt = prompt

    def test_prompt_contains_station_name(self, admin_session, flagship_sid):
        # Fetch station name and cross-check.
        r = admin_session.get(
            f"{BASE_URL}/api/admin/stations/flagship", timeout=15)
        items = r.json().get("items") or []
        name = next((s.get("name") for s in items if s.get("id") == flagship_sid),
                    None)
        assert name, "Could not resolve station name"
        prompt = getattr(TestFlagshipArtworkGenerate, "prompt", "")
        assert name.strip() in prompt, f"prompt missing name {name!r}: {prompt!r}"

    def test_status_completes_with_flg_image(self, admin_session, flagship_sid):
        deadline = time.time() + POLL_SECONDS
        last = None
        while time.time() < deadline:
            r = admin_session.get(
                f"{BASE_URL}/api/imported-stations/{flagship_sid}/artwork/status")
            assert r.status_code == 200
            last = r.json()
            if last.get("status") in ("complete", "failed"):
                break
            time.sleep(POLL_INTERVAL)
        assert last, "No status response"
        assert last.get("status") == "complete", f"Final status: {last}"
        url = last.get("image_url") or ""
        assert url, "image_url missing"
        assert "/api/static/station_artwork/flg-" in url, (
            f"image_url is not a flagship-badged (flg-*) key: {url}")
        # Confirm the file resolves to a real image.
        full = url if url.startswith("http") else f"{BASE_URL}{url}"
        rr = requests.get(full, timeout=20)
        assert rr.status_code == 200, f"art fetch {rr.status_code} {full}"
        ct = rr.headers.get("Content-Type", "")
        assert "image" in ct, f"Not an image content type: {ct}"
        assert len(rr.content) > 1024, "Image bytes suspiciously small"


# ── Tests: ensure-flagship-art idempotency ────────────────────────────
class TestEnsureFlagshipArt:
    def test_first_call_ok(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/imported-stations/ensure-flagship-art", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert "queued" in data and isinstance(data["queued"], int)

    def test_second_call_idempotent(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/imported-stations/ensure-flagship-art", json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert isinstance(data.get("queued"), int)


# ── Tests: manual upload alternative ──────────────────────────────────
class TestFlagshipManualUpload:
    def _tiny_png(self) -> bytes:
        try:
            from PIL import Image
        except Exception:
            pytest.skip("Pillow not available")
        buf = io.BytesIO()
        Image.new("RGB", (64, 64), (200, 60, 60)).save(buf, format="PNG")
        return buf.getvalue()

    def test_admin_upload_sets_owner_source(self, admin_session, flagship_sid):
        png = self._tiny_png()
        # Upload uses multipart/form-data, so drop the JSON header.
        s = requests.Session()
        s.cookies.update(admin_session.cookies)
        files = {"file": ("art.png", png, "image/png")}
        r = s.post(
            f"{BASE_URL}/api/imported-stations/{flagship_sid}/artwork/upload",
            files=files, timeout=30)
        assert r.status_code == 200, f"upload failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("ok") is True
        assert data.get("status") == "complete"
        assert data.get("url"), "no url on upload response"

        # Verify status endpoint reports owner source.
        st = admin_session.get(
            f"{BASE_URL}/api/imported-stations/{flagship_sid}/artwork/status")
        assert st.status_code == 200
        body = st.json()
        assert body.get("status") == "complete"
        assert body.get("art_source") == "owner", f"art_source={body.get('art_source')}"


# ── Tests: non-flagship regression ────────────────────────────────────
class TestNonFlagshipRegression:
    def test_plain_generate_no_flg_prefix(self, admin_session, non_flagship_sid):
        r = admin_session.post(
            f"{BASE_URL}/api/imported-stations/{non_flagship_sid}/artwork/generate",
            json={})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "queued"

        deadline = time.time() + POLL_SECONDS
        last = None
        while time.time() < deadline:
            rr = admin_session.get(
                f"{BASE_URL}/api/imported-stations/{non_flagship_sid}/artwork/status")
            last = rr.json()
            if last.get("status") in ("complete", "failed"):
                break
            time.sleep(POLL_INTERVAL)
        assert last and last.get("status") == "complete", f"final: {last}"
        url = last.get("image_url") or ""
        assert url, "no image_url"
        # Non-flagship art should not be the flg-* composite.
        assert "/flg-" not in url, f"non-flagship got flg composite key: {url}"
        assert "/api/static/station_artwork/" in url, url
