"""BigFM Dubai Phase 0 — backend API tests.

Covers radio flow (start/next/segment/session), voices, admin tracks, openapi.
"""
import os
import time
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

HINGLISH_TOKENS = [
    "kya", "aap", "hai", "yaar", "hain", "dil", "se", "dubai", "scene",
    "arre", "toh", "ka", "ki", "ke", "bhi", "namaste", "salaam",
    "bigfm", "metro", "karama", "jlt", "deira", "bur", "chai", "biryani",
]


@pytest.fixture(scope="module")
def session_data():
    """Start a radio session — shared across all tests in this module."""
    r = requests.post(f"{BASE_URL}/api/radio/start", json={"channel": "dubai_default"}, timeout=180)
    assert r.status_code == 200, f"radio/start failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert "session_id" in data and "segment" in data
    return data


# ---------- Health ----------
def test_health():
    r = requests.get(f"{BASE_URL}/api/health", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body.get("status") == "ok"
    assert body.get("service") == "bigfm-dubai"


# ---------- Voices ----------
def test_voices_lists_indian_dubai_voices():
    r = requests.get(f"{BASE_URL}/api/voices", timeout=15)
    assert r.status_code == 200
    body = r.json()
    keys = {v["key"] for v in body.get("voices", [])}
    assert "raj_dubai" in keys
    assert "priya_dubai" in keys
    assert body.get("default") in keys


# ---------- OpenAPI ----------
def test_openapi_includes_radio_and_admin_routes():
    r = requests.get(f"{BASE_URL}/api/openapi.json", timeout=15)
    assert r.status_code == 200
    spec = r.json()
    paths = set(spec.get("paths", {}).keys())
    for required in [
        "/api/health", "/api/voices",
        "/api/radio/start", "/api/radio/next", "/api/radio/skip",
        "/api/radio/session/{session_id}", "/api/radio/segment/{segment_id}",
        "/api/admin/tracks/upload", "/api/admin/tracks",
    ]:
        assert required in paths, f"missing route in openapi: {required}"


# ---------- Admin tracks ----------
def test_admin_tracks_list_has_seeded():
    r = requests.get(f"{BASE_URL}/api/admin/tracks", timeout=20)
    assert r.status_code == 200
    tracks = r.json()
    assert isinstance(tracks, list)
    assert len(tracks) >= 3, f"expected >=3 seeded tracks, got {len(tracks)}"
    for t in tracks[:3]:
        assert "id" in t and "title" in t and "artist" in t and "duration_sec" in t
        assert t["duration_sec"] > 0


# ---------- Radio start ----------
def test_radio_start_returns_hinglish_segment(session_data):
    seg = session_data["segment"]
    # Schema checks
    for k in ["segment_id", "segment_url", "duration_sec", "track_id",
              "track_title", "track_artist", "rj_voice_key", "rj_voice_name",
              "rj_script", "rj_start_sec", "next_ready"]:
        assert k in seg, f"missing key {k} in segment"
    # segment_url uses /api prefix
    assert seg["segment_url"].startswith("/api/radio/segment/"), (
        f"segment_url malformed: {seg['segment_url']}"
    )
    # Hinglish content sniff — RJ script should contain Hindi words OR Dubai reference
    script_low = seg["rj_script"].lower()
    assert any(tok in script_low for tok in HINGLISH_TOKENS), (
        f"rj_script doesn't look Hinglish/Dubai: {seg['rj_script'][:200]}"
    )
    assert seg["duration_sec"] > 5
    assert 0 <= seg["rj_start_sec"] <= seg["duration_sec"]


# ---------- Segment Range streaming ----------
def test_segment_range_request_206(session_data):
    seg_id = session_data["segment"]["segment_id"]
    url = f"{BASE_URL}/api/radio/segment/{seg_id}"
    r = requests.get(url, headers={"Range": "bytes=0-2000"}, timeout=60, stream=True)
    assert r.status_code == 206, f"expected 206, got {r.status_code}"
    cr = r.headers.get("Content-Range")
    assert cr is not None and cr.startswith("bytes 0-"), f"Content-Range header bad: {cr}"
    m = re.match(r"bytes 0-(\d+)/(\d+)", cr)
    assert m, f"Content-Range format unexpected: {cr}"
    end = int(m.group(1))
    total = int(m.group(2))
    assert end <= 2000
    assert total > end
    # Body should be ~2001 bytes
    body = r.content
    assert len(body) == end + 1


def test_segment_full_request_200(session_data):
    seg_id = session_data["segment"]["segment_id"]
    url = f"{BASE_URL}/api/radio/segment/{seg_id}"
    r = requests.head(url, timeout=30, allow_redirects=True)
    # HEAD might not be implemented — fallback to small GET
    if r.status_code in (405, 404):
        r = requests.get(url, timeout=60, stream=True)
        assert r.status_code == 200
    else:
        assert r.status_code == 200
    assert r.headers.get("Accept-Ranges") == "bytes"


# ---------- Session state + prefetch ----------
def test_session_state_prefetch_populated(session_data):
    sid = session_data["session_id"]
    pending = None
    deadline = time.time() + 90  # allow up to 90s for prefetch (RJ gen + TTS + ffmpeg)
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/radio/session/{sid}", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["session_id"] == sid
        assert body.get("current_segment_id") == session_data["segment"]["segment_id"]
        pending = body.get("pending_segment_id")
        if pending:
            break
        time.sleep(3)
    assert pending, "pending_segment_id never populated (background prefetch failed)"


# ---------- Radio next: fast because prefetched ----------
def test_radio_next_uses_prefetch_fast(session_data):
    sid = session_data["session_id"]
    # ensure prefetch is ready first
    deadline = time.time() + 90
    while time.time() < deadline:
        r = requests.get(f"{BASE_URL}/api/radio/session/{sid}", timeout=15)
        if r.json().get("pending_segment_id"):
            break
        time.sleep(3)
    t0 = time.time()
    r = requests.get(f"{BASE_URL}/api/radio/next", params={"session_id": sid}, timeout=180)
    elapsed = time.time() - t0
    assert r.status_code == 200
    seg = r.json()["segment"]
    assert seg["segment_id"] != session_data["segment"]["segment_id"]
    assert seg["segment_url"].startswith("/api/radio/segment/")
    # Generous threshold; the spec says <1s but network jitter on preview ingress varies
    assert elapsed < 5.0, f"radio/next took {elapsed:.2f}s — prefetch not being used"

    # Now next-2: wait for next prefetch then call /next again
    deadline = time.time() + 90
    while time.time() < deadline:
        s = requests.get(f"{BASE_URL}/api/radio/session/{sid}", timeout=15)
        if s.json().get("pending_segment_id"):
            break
        time.sleep(3)
    t1 = time.time()
    r2 = requests.get(f"{BASE_URL}/api/radio/next", params={"session_id": sid}, timeout=180)
    elapsed2 = time.time() - t1
    assert r2.status_code == 200
    seg2 = r2.json()["segment"]
    assert seg2["segment_id"] != seg["segment_id"]
    assert elapsed2 < 5.0, f"radio/next #2 took {elapsed2:.2f}s — prefetch chain broken"


# ---------- Invalid session ----------
def test_radio_next_invalid_session_404():
    r = requests.get(f"{BASE_URL}/api/radio/next", params={"session_id": "does-not-exist"}, timeout=15)
    assert r.status_code == 404


def test_segment_not_found_404():
    r = requests.get(f"{BASE_URL}/api/radio/segment/does-not-exist", timeout=15)
    assert r.status_code == 404
