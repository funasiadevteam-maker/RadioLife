"""Iteration 113 — verify:
    (A) Tigris durability on non-flagship + flagship AI generation + owner upload
    (B) Self-heal endpoint POST /api/imported-stations/ensure-flagship-art
    (C) _static_asset_missing helper
    (D) Regression: non-flagship uses plain prompt; flagship uses lower-third prompt.

Loads /app/backend/.env so STORAGE_BACKEND=tigris + creds are available.
"""
from __future__ import annotations
import io
import os
import sys
import time
import pathlib
import requests
import pytest
from dotenv import load_dotenv

# Load backend env BEFORE importing services (needed for TIGRIS_* creds).
load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

FRONTEND_ENV = pathlib.Path("/app/frontend/.env").read_text()
BASE_URL = [ln.split("=", 1)[1].strip() for ln in FRONTEND_ENV.splitlines()
            if ln.startswith("REACT_APP_BACKEND_URL=")][0].rstrip("/")

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PW = "AdminPass123!"
NON_FLAGSHIP_SID = "imp_780122061aa111e9a8"  # MANGORADIO
FLAGSHIP_SID = "imp_fun_big_1062_uae"


# ── fixtures ─────────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def storage():
    from services.object_storage import get_storage, reset_storage
    reset_storage()
    st = get_storage()
    assert st.backend_name == "tigris", f"expected tigris backend, got {st.backend_name}"
    return st


# ── helpers ──────────────────────────────────────────────────────────
def _static_url_to_key(url: str) -> str:
    """/api/static/station_artwork/x.webp → static/station_artwork/x.webp"""
    assert url and url.startswith("/api/static/"), url
    return url.split("?", 1)[0][len("/api/"):]


def _poll_status(session: requests.Session, sid: str, timeout: int = 100) -> dict:
    end = time.time() + timeout
    last = None
    while time.time() < end:
        r = session.get(f"{BASE_URL}/api/imported-stations/{sid}/artwork/status", timeout=15)
        assert r.status_code == 200, r.text[:200]
        last = r.json()
        if last.get("status") in ("complete", "failed"):
            return last
        time.sleep(2.5)
    return last or {}


# ── (A) durability — non-flagship generate ───────────────────────────
def test_durability_nonflagship_generate(admin_session, storage):
    """POST generate on a non-flagship → resulting webp must exist in Tigris."""
    r = admin_session.post(
        f"{BASE_URL}/api/imported-stations/{NON_FLAGSHIP_SID}/artwork/generate",
        json={}, timeout=30)
    assert r.status_code == 200, f"generate failed: {r.status_code} {r.text[:200]}"
    body = r.json()
    assert body.get("ok") is True
    # Regression: non-flagship prompt must NOT include the lower-third reservation.
    prompt = body.get("prompt") or ""
    assert "lower third" not in prompt.lower(), \
        f"non-flagship prompt leaked flagship phrasing: {prompt}"

    st = _poll_status(admin_session, NON_FLAGSHIP_SID, timeout=100)
    assert st.get("status") == "complete", f"status did not complete: {st}"
    url = st.get("image_url")
    assert url and url.startswith("/api/static/station_artwork/"), url
    # NOT a flagship badge:
    assert "/flg-" not in url, f"non-flagship got flagship-badged key: {url}"

    key = _static_url_to_key(url)
    assert storage.exists(key=key), f"Tigris missing key {key} after non-flagship generate"


# ── (A) durability — flagship generate ───────────────────────────────
def test_durability_flagship_generate(admin_session, storage):
    """Flagship generate must produce flg-<hash>.webp AND persist to Tigris."""
    r = admin_session.post(
        f"{BASE_URL}/api/imported-stations/{FLAGSHIP_SID}/artwork/generate",
        json={}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body.get("ok") is True
    prompt = body.get("prompt") or ""
    assert "lower third" in prompt.lower(), \
        f"flagship prompt missing lower-third reservation: {prompt}"

    st = _poll_status(admin_session, FLAGSHIP_SID, timeout=100)
    assert st.get("status") == "complete", f"flagship status: {st}"
    url = st.get("image_url")
    assert url and "/flg-" in url, f"flagship did not produce badged key: {url}"

    key = _static_url_to_key(url)
    assert storage.exists(key=key), f"Tigris missing flagship key {key}"


# ── (A/B) cache-hit backfill: even 'cached' response uploads to Tigris ─
def test_durability_cache_hit_backfill(admin_session, storage):
    """Second generate for same station hits disk cache (source='cached')
    but still results in Tigris object present (opportunistic backfill).
    We simulate by deleting the object from Tigris then regenerating."""
    # Ensure the station has art
    r = admin_session.post(
        f"{BASE_URL}/api/imported-stations/{NON_FLAGSHIP_SID}/artwork/generate",
        json={}, timeout=30)
    assert r.status_code == 200
    st = _poll_status(admin_session, NON_FLAGSHIP_SID, timeout=100)
    assert st.get("status") == "complete", st
    url = st.get("image_url")
    key = _static_url_to_key(url)

    # Remove from Tigris, confirm gone, then regenerate → backfilled.
    storage.delete(key=key)
    assert not storage.exists(key=key), "delete didn't take effect"

    r2 = admin_session.post(
        f"{BASE_URL}/api/imported-stations/{NON_FLAGSHIP_SID}/artwork/generate",
        json={}, timeout=30)
    assert r2.status_code == 200
    st2 = _poll_status(admin_session, NON_FLAGSHIP_SID, timeout=100)
    assert st2.get("status") == "complete", st2
    # Same key expected (deterministic on prompt).
    key2 = _static_url_to_key(st2["image_url"])
    assert storage.exists(key=key2), \
        f"cache-hit backfill did not re-upload {key2}"


# ── (A) durability — owner upload ────────────────────────────────────
def test_durability_owner_upload(admin_session, storage):
    """Admin PNG upload → resulting art_url key must exist in Tigris."""
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new("RGB", (128, 128), (12, 200, 100))
    img.save(buf, format="PNG")
    buf.seek(0)

    r = admin_session.post(
        f"{BASE_URL}/api/imported-stations/{NON_FLAGSHIP_SID}/artwork/upload",
        files={"file": ("blob.png", buf, "image/png")}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body.get("ok") is True
    assert body.get("status") == "complete"
    url = body.get("url")
    assert url and url.startswith("/api/static/station_artwork/"), url

    key = _static_url_to_key(url)
    assert storage.exists(key=key), f"Tigris missing owner-uploaded key {key}"


# ── (D) helper: _static_asset_missing ────────────────────────────────
def test_static_asset_missing_helper():
    from routes.imported_station_artwork import _static_asset_missing
    # None → False
    assert _static_asset_missing(None) is False
    # External URL → False
    assert _static_asset_missing("https://ui-avatars.com/api/?name=X") is False
    assert _static_asset_missing("http://example.com/foo.jpg") is False
    # Bogus /api/static/ path → True
    assert _static_asset_missing(
        "/api/static/station_artwork/definitely-does-not-exist-xyz-123.webp") is True


def test_static_asset_missing_present_file(admin_session, storage):
    """A /api/static url that's present on disk OR in Tigris → False."""
    from routes.imported_station_artwork import _static_asset_missing
    # Fetch any existing station art via status endpoint
    r = admin_session.get(
        f"{BASE_URL}/api/imported-stations/{FLAGSHIP_SID}/artwork/status", timeout=15)
    assert r.status_code == 200
    url = r.json().get("image_url")
    if not url or not url.startswith("/api/static/"):
        pytest.skip("no flagship art_url available to test the present-file case")
    # Should be present in Tigris (from prior tests / previous iterations).
    assert _static_asset_missing(url) is False, \
        f"present asset falsely reported missing: {url}"


# ── (B) self-heal: idempotency + queues vanished art ─────────────────
def test_ensure_flagship_art_idempotent(admin_session):
    """Two consecutive calls: shape {ok:true, queued:int}, second call
    should NOT re-queue anything freshly queued by the first."""
    r1 = admin_session.post(f"{BASE_URL}/api/imported-stations/ensure-flagship-art", timeout=20)
    assert r1.status_code == 200, r1.text[:200]
    b1 = r1.json()
    assert b1.get("ok") is True
    assert isinstance(b1.get("queued"), int)

    r2 = admin_session.post(f"{BASE_URL}/api/imported-stations/ensure-flagship-art", timeout=20)
    assert r2.status_code == 200, r2.text[:200]
    b2 = r2.json()
    assert b2.get("ok") is True
    # Second call should not re-queue anything from the first.
    assert b2.get("queued", 0) <= b1.get("queued", 0), \
        f"second call queued more ({b2}) than first ({b1}) — not idempotent"


def test_ensure_flagship_art_regenerates_vanished(storage):
    """Set a flagship's art_url to a bogus /api/static path, hit ensure,
    confirm it queues, then restore the real url."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    async def run():
        s = await db.imported_radio_stations.find_one({"id": FLAGSHIP_SID})
        assert s, "flagship not found"
        original = {
            "art_url": s.get("art_url"),
            "flagship_art": s.get("flagship_art"),
            "art_gen_attempted": s.get("art_gen_attempted"),
            "artwork_status": s.get("artwork_status"),
        }
        try:
            bogus = "/api/static/station_artwork/does-not-exist-xyz-iter113.webp"
            await db.imported_radio_stations.update_one(
                {"id": FLAGSHIP_SID},
                {"$set": {"art_url": bogus, "flagship_art": bogus,
                          "art_gen_attempted": False,
                          "artwork_status": "complete"}})
            # POST ensure-flagship-art
            sess = requests.Session()
            login = sess.post(f"{BASE_URL}/api/auth/login",
                              json={"email": ADMIN_EMAIL, "password": ADMIN_PW}, timeout=15)
            assert login.status_code == 200
            r = sess.post(f"{BASE_URL}/api/imported-stations/ensure-flagship-art", timeout=20)
            assert r.status_code == 200, r.text[:200]
            body = r.json()
            assert body.get("ok") is True
            assert body.get("queued", 0) >= 1, \
                f"vanished flagship art was not queued: {body}"
        finally:
            # Restore original values.
            await db.imported_radio_stations.update_one(
                {"id": FLAGSHIP_SID}, {"$set": original})

    asyncio.get_event_loop().run_until_complete(run())
    client.close()
