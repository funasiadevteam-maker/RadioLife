"""Phase 3.8 v2 — Imaging engine WIRED into live segment builds.

Tests:
- Live wiring: /api/radio/start populates station_flow_logs with brand_id_short
  (preroll) + music_bed (underlay) within ~25s.
- Debug sponsor-bumper inject endpoint arms next segment + fires preroll.
- flow-logs/recent + flow-logs/live-summary admin endpoints.
- 3 audition phase38_* samples stream the live-pipeline mp3s.
- Non-admin 403 on debug/admin imaging routes.
- ffprobe duration of the seeded live segment > 145s.
- Phase 3.8 v1 regression (DUO 2-stage + market filter + 3 phase38 audition).
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
PREMIUM = {"email": "premium@bigfm.dubai", "password": "PremiumTest123!"}
FREE = {"email": "test@bigfm.dubai", "password": "TestUser123!"}

SEEDED_LIVE_SEGMENT = "/app/backend/storage/segments/67a9ab2c-1af5-4d55-98c1-b179d11270fc.mp3"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
    assert r.status_code == 200, f"login {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def premium_session():
    s = _login(PREMIUM)
    # Ensure premium user is on dubai market for these tests
    s.post(f"{BASE_URL}/api/users/preferences", json={"market": "dubai"}, timeout=30)
    return s


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE)


@pytest.fixture(scope="module")
def live_session(premium_session, admin_session):
    """Start a single radio session for live-imaging tests; wait for first build."""
    r = premium_session.post(
        f"{BASE_URL}/api/radio/start",
        json={"channel": "bollywood_mehfil"},
        timeout=60,
    )
    assert r.status_code == 200, f"radio/start failed: {r.status_code} {r.text}"
    data = r.json()
    sid = data.get("session_id")
    assert sid, f"no session_id in start response: {data}"
    # Wait for the first segment build to complete + log writes.
    time.sleep(25)
    return {"session_id": sid, "start_response": data}


# ---------- Live wiring: imaging fires on first segment build ----------
class TestLiveImagingWiring:
    def test_flow_logs_recent_has_preroll_and_underlay(self, admin_session, live_session):
        sid = live_session["session_id"]
        # Allow a couple of retries for async writes to settle
        items = []
        for _ in range(3):
            r = admin_session.get(
                f"{BASE_URL}/api/admin/imaging/flow-logs/recent",
                params={"session_id": sid, "limit": 20},
                timeout=30,
            )
            assert r.status_code == 200, r.text
            items = r.json().get("items", [])
            if len(items) >= 2:
                break
            time.sleep(5)

        assert items, f"NO station_flow_logs rows for session {sid} — live wiring broken"

        item_types = {it.get("item_type") for it in items}
        transition_types = {it.get("transition_type") for it in items}

        # MUST contain music_bed underlay AND brand_id_short preroll (first segment 100%)
        assert "imaging.music_bed" in item_types, \
            f"missing imaging.music_bed in {item_types}"
        assert "imaging.brand_id_short" in item_types, \
            f"missing imaging.brand_id_short (first-segment guarantee) in {item_types}"
        assert any("underlay" in (t or "") for t in transition_types), \
            f"no underlay.* transition_type in {transition_types}"
        assert any("preroll" in (t or "") for t in transition_types), \
            f"no preroll.* transition_type in {transition_types}"

    def test_flow_log_row_schema(self, admin_session, live_session):
        sid = live_session["session_id"]
        r = admin_session.get(
            f"{BASE_URL}/api/admin/imaging/flow-logs/recent",
            params={"session_id": sid, "limit": 5},
            timeout=30,
        )
        items = r.json().get("items", [])
        assert items, "no flow log items"
        sample = items[0]
        # required fields per spec
        for k in ("item_type", "transition_type", "asset_slug", "asset_type",
                  "station_slug", "played_at", "segment_id", "user_id", "session_id"):
            assert k in sample, f"missing {k} in flow log row: {sample.keys()}"
        # loudness_lufs should be present (None or float)
        assert "loudness_lufs" in sample

    def test_live_summary_aggregation(self, admin_session, live_session):
        # the live_session fixture already produced >= 2 inserts in last minute
        r = admin_session.get(
            f"{BASE_URL}/api/admin/imaging/flow-logs/live-summary",
            params={"minutes": 60},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("minutes") == 60
        assert isinstance(data.get("total_inserts"), int)
        assert data["total_inserts"] >= 2, f"expected >=2 inserts in last 60min, got {data}"
        by_type = data.get("by_item_type", [])
        types = {row["_id"] for row in by_type}
        assert "imaging.music_bed" in types or "imaging.brand_id_short" in types, \
            f"no imaging item_type in live-summary: {types}"


# ---------- Debug: inject sponsor bumper ----------
class TestSponsorBumperInject:
    def test_inject_then_next_fires_sponsor_bumper(
            self, admin_session, premium_session, live_session):
        sid = live_session["session_id"]
        # 1) Arm next segment
        r = admin_session.post(
            f"{BASE_URL}/api/admin/imaging/debug/inject-sponsor",
            params={"session_id": sid, "sponsor_id": "funasia_test"},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("next_segment_sponsor_id") == "funasia_test", body

        # 2) Trigger next segment build
        rn = premium_session.get(
            f"{BASE_URL}/api/radio/next?session_id={sid}", timeout=120
        )
        assert rn.status_code == 200, rn.text

        # 3) Allow segment + log writes to flush
        time.sleep(22)

        # 4) Verify sponsor_bumper appears in flow logs
        sponsor_found = False
        for _ in range(3):
            r2 = admin_session.get(
                f"{BASE_URL}/api/admin/imaging/flow-logs/recent",
                params={"session_id": sid, "limit": 50},
                timeout=30,
            )
            items = r2.json().get("items", [])
            for it in items:
                if it.get("item_type") == "imaging.sponsor_bumper":
                    sponsor_found = True
                    assert "preroll" in (it.get("transition_type") or ""), \
                        f"sponsor_bumper transition_type wrong: {it}"
                    break
            if sponsor_found:
                break
            time.sleep(5)
        assert sponsor_found, \
            "imaging.sponsor_bumper not found in flow logs after debug-inject + next"


# ---------- Auth gating ----------
class TestImagingDebugAuth:
    def test_non_admin_forbidden_debug_inject(self, free_session):
        r = free_session.post(
            f"{BASE_URL}/api/admin/imaging/debug/inject-sponsor",
            params={"session_id": "x", "sponsor_id": "y"},
            timeout=15,
        )
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text}"

    def test_non_admin_forbidden_live_summary(self, free_session):
        r = free_session.get(
            f"{BASE_URL}/api/admin/imaging/flow-logs/live-summary",
            params={"minutes": 60}, timeout=15,
        )
        assert r.status_code == 403

    def test_non_admin_forbidden_flow_logs_recent(self, free_session):
        r = free_session.get(
            f"{BASE_URL}/api/admin/imaging/flow-logs/recent",
            params={"limit": 5}, timeout=15,
        )
        assert r.status_code == 403


# ---------- Audition phase38_* live imaging samples ----------
class TestAuditionPhase38LiveImaging:
    @pytest.mark.parametrize("key", [
        "phase38_morning_imaging",
        "phase38_nightlife_imaging",
        "phase38_late_night_chill",
    ])
    def test_audio_streams_and_size(self, key):
        url = f"{BASE_URL}/api/audition/{key}/audio"
        r = requests.get(url, timeout=120, stream=True)
        assert r.status_code in (200, 206), f"{key} status {r.status_code}"
        # Read content length if present
        cl = r.headers.get("content-length")
        if cl:
            assert int(cl) > 1_000_000, f"{key} content-length too small: {cl}"
        # Range support
        r2 = requests.get(url, headers={"Range": "bytes=0-2000"}, timeout=60)
        assert r2.status_code == 206

    def test_landing_html_has_phase38_v2_keys(self):
        r = requests.get(f"{BASE_URL}/api/audition/__landing", timeout=30)
        assert r.status_code == 200
        html = r.text
        for k in ("phase38_morning_imaging", "phase38_nightlife_imaging",
                  "phase38_late_night_chill"):
            assert k in html, f"missing {k} in audition landing"


# ---------- Direct file checks ----------
class TestSeededLiveSegmentFile:
    def test_segment_file_exists(self):
        assert os.path.exists(SEEDED_LIVE_SEGMENT), f"missing {SEEDED_LIVE_SEGMENT}"
        size = os.path.getsize(SEEDED_LIVE_SEGMENT)
        assert size > 3_000_000, f"segment file too small: {size} bytes"

    def test_segment_duration_via_ffprobe(self):
        import subprocess
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", SEEDED_LIVE_SEGMENT],
            capture_output=True, text=True, timeout=30,
        )
        assert out.returncode == 0, out.stderr
        dur = float(out.stdout.strip())
        assert dur > 145.0, f"segment duration too short: {dur}s"


# ---------- Phase 3.8 v1 regression sanity (light) ----------
class TestPhase38v1Regression:
    def test_two_stations_with_assets(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/imaging/stations", timeout=20)
        assert r.status_code == 200
        stations = {s["station_slug"]: s for s in r.json()["stations"]}
        assert "bigfm_dubai" in stations and "funasia_dfw" in stations
        assert stations["bigfm_dubai"]["asset_counts"]["total"] >= 50

    @staticmethod
    def _switch_market(session, market: str):
        me = session.get(f"{BASE_URL}/api/auth/me", timeout=30).json()
        prefs = me.get("preferences") or {}
        payload = {
            "language_mix": prefs.get("language_mix", "hinglish_70_30"),
            "genres": prefs.get("genres", ["bollywood", "pop"]),
            "activities": prefs.get("activities", ["commute", "workout"]),
            "moods": prefs.get("moods", ["romantic", "party"]),
            "eras": prefs.get("eras", ["2010s", "2020s"]),
            "favourite_artists": prefs.get("favourite_artists", ["Arijit Singh"]),
            "voice_persona": prefs.get("voice_persona", "warm_witty"),
            "ads_personalization": prefs.get("ads_personalization", True),
            "explicit_filter": prefs.get("explicit_filter", "clean_only"),
            "discovery_dial": prefs.get("discovery_dial", 50),
            "languages": ["hindi", "english"],
            "market": market,
            "city_zone": "frisco" if market == "dfw" else "karama",
        }
        r = session.post(f"{BASE_URL}/api/users/preferences", json=payload, timeout=30)
        assert r.status_code == 200, f"prefs switch {market}: {r.status_code} {r.text}"

    def test_dfw_market_filter(self, premium_session):
        self._switch_market(premium_session, "dfw")
        try:
            r = premium_session.get(f"{BASE_URL}/api/channels", timeout=30)
            assert r.status_code == 200
            data = r.json()
            assert data.get("market") == "dfw"
            assert len(data.get("channels", [])) == 2
        finally:
            self._switch_market(premium_session, "dubai")
