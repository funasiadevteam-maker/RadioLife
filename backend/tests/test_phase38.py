"""Phase 3.8 — Station Imaging + DUO Naturalness Rewrite + DFW Launch."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
PREMIUM = {"email": "premium@bigfm.dubai", "password": "PremiumTest123!"}
FREE = {"email": "test@bigfm.dubai", "password": "TestUser123!"}


def _login(creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def premium_session():
    return _login(PREMIUM)


@pytest.fixture(scope="module")
def free_session():
    return _login(FREE)


# ---------- Imaging admin endpoints ----------
class TestImagingStations:
    def test_list_stations(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/imaging/stations")
        assert r.status_code == 200, r.text
        data = r.json()
        stations = {s["station_slug"]: s for s in data["stations"]}
        assert "bigfm_dubai" in stations
        assert "funasia_dfw" in stations
        b = stations["bigfm_dubai"]
        f = stations["funasia_dfw"]
        assert b["station_name"] == "BigFM Dubai"
        assert b["market"] == "dubai"
        assert f["station_name"] == "FunAsia AI Radio"
        assert f["market"] == "dfw"
        # asset_counts.total >= 50 per station
        assert b["asset_counts"]["total"] >= 50, f"bigfm_dubai total: {b['asset_counts']}"
        assert f["asset_counts"]["total"] >= 50, f"funasia_dfw total: {f['asset_counts']}"
        for st in (b, f):
            assert st.get("primary_voice_key")
            assert st.get("secondary_voice_key")
            assert isinstance(st.get("brand_words"), list)
            assert st.get("tagline")
            assert st.get("imaging_style_preset")

    def test_station_detail_bigfm(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/imaging/bigfm_dubai")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "branding" in data
        counts = data.get("asset_type_counts", [])
        types_present = {c["asset_type"] for c in counts}
        expected = {
            "brand_id_short", "brand_id_long", "daypart_opener", "top_of_hour",
            "sponsor_bumper", "game_stinger", "winner_stinger", "premium_id",
            "legal_id", "music_bed", "sweeper_short",
        }
        missing = expected - types_present
        assert not missing, f"Missing asset_types: {missing}; have: {types_present}"
        assert len(types_present) >= 11

    def test_assets_list_and_filter(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/imaging/bigfm_dubai/assets")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert len(data["items"]) > 0
        sample = data["items"][0]
        # Required keys
        for k in ("audio_url", "slug", "asset_type", "voice_key", "daypart", "energy",
                  "script", "duration_sec", "loudness_lufs", "peak_dbfs", "generation_status"):
            assert k in sample, f"missing key {k} in asset {sample.keys()}"

        # Filter
        r2 = admin_session.get(f"{BASE_URL}/api/admin/imaging/bigfm_dubai/assets?asset_type=brand_id_long")
        assert r2.status_code == 200
        items = r2.json()["items"]
        assert len(items) > 0
        for it in items:
            assert it["asset_type"] == "brand_id_long"

    def test_audio_streaming_full_and_range(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/imaging/bigfm_dubai/assets")
        items = r.json()["items"]
        ready = [it for it in items if it.get("generation_status") == "ready"]
        if not ready:
            pytest.skip("no ready assets in bigfm_dubai")
        asset_id = ready[0]["id"]

        # Full
        r1 = admin_session.get(f"{BASE_URL}/api/admin/imaging/bigfm_dubai/asset/{asset_id}/audio")
        assert r1.status_code == 200, r1.text
        assert r1.headers.get("content-type", "").startswith("audio/")
        # Range
        r2 = admin_session.get(
            f"{BASE_URL}/api/admin/imaging/bigfm_dubai/asset/{asset_id}/audio",
            headers={"Range": "bytes=0-2000"},
        )
        assert r2.status_code == 206, r2.text
        assert "content-range" in {k.lower() for k in r2.headers.keys()}

    def test_sonic_branding_upsert(self, admin_session):
        payload = {"tagline": "TEST tagline phase38", "brand_words": ["test38"]}
        r = admin_session.post(
            f"{BASE_URL}/api/admin/imaging/bigfm_dubai/sonic-branding", json=payload
        )
        assert r.status_code == 200, r.text
        # Verify
        r2 = admin_session.get(f"{BASE_URL}/api/admin/imaging/bigfm_dubai")
        b = r2.json()["branding"]
        assert b.get("tagline") == "TEST tagline phase38"
        assert "test38" in (b.get("brand_words") or [])

    def test_update_one_asset(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/imaging/bigfm_dubai/assets")
        items = r.json()["items"]
        asset_id = items[0]["id"]
        r2 = admin_session.post(
            f"{BASE_URL}/api/admin/imaging/bigfm_dubai/asset/{asset_id}",
            json={"weight": 2.0, "active": False},
        )
        assert r2.status_code == 200, r2.text
        a = r2.json()["asset"]
        assert a["weight"] == 2.0
        assert a["active"] is False
        # Restore
        admin_session.post(
            f"{BASE_URL}/api/admin/imaging/bigfm_dubai/asset/{asset_id}",
            json={"weight": 1.0, "active": True},
        )

    def test_regenerate_all(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/admin/imaging/bigfm_dubai/regenerate?limit=2"
        )
        assert r.status_code == 200
        assert r.json().get("kicked_off") is True

    def test_regenerate_one(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/imaging/bigfm_dubai/assets")
        items = r.json()["items"]
        # Pick one ready to keep gen fast
        ready = [it for it in items if it.get("generation_status") == "ready"]
        target = ready[0] if ready else items[0]
        asset_id = target["id"]
        r2 = admin_session.post(
            f"{BASE_URL}/api/admin/imaging/bigfm_dubai/asset/{asset_id}/regenerate",
            timeout=120,
        )
        assert r2.status_code == 200, r2.text
        assert "generation_status" in r2.json()["asset"]

    def test_non_admin_forbidden(self, free_session):
        for path in [
            "/api/admin/imaging/stations",
            "/api/admin/imaging/bigfm_dubai",
            "/api/admin/imaging/bigfm_dubai/assets",
        ]:
            r = free_session.get(f"{BASE_URL}{path}")
            assert r.status_code == 403, f"{path} expected 403 got {r.status_code}"


# ---------- Market filtering on /api/channels ----------
class TestMarketFiltering:
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
        assert r.status_code == 200, f"prefs switch to {market} failed: {r.status_code} {r.text}"

    def test_dubai_user_channels(self, premium_session):
        self._switch_market(premium_session, "dubai")
        r = premium_session.get(f"{BASE_URL}/api/channels")
        assert r.status_code == 200
        data = r.json()
        assert data.get("market") == "dubai"
        chans = data.get("channels", [])
        assert len(chans) >= 8
        for c in chans:
            assert c.get("market") != "dfw", f"unexpected DFW channel for Dubai user: {c.get('id')}"

    def test_dfw_user_channels(self, premium_session):
        self._switch_market(premium_session, "dfw")
        r = premium_session.get(f"{BASE_URL}/api/channels")
        assert r.status_code == 200
        data = r.json()
        assert data.get("market") == "dfw"
        chans = data.get("channels", [])
        ids = {(c.get("id") or c.get("slug") or c.get("channel_id") or c.get("name")) for c in chans}
        assert "dfw_bollywood_drive" in ids
        assert "dfw_garba_nights" in ids
        # Should be ONLY DFW channels
        for c in chans:
            assert c.get("market") == "dfw", f"non-DFW channel returned: {c.get('id')}"
        assert len(chans) == 2
        # restore
        premium_session.post(f"{BASE_URL}/api/users/preferences", json={"market": "dubai"})


# ---------- Audition samples (public) ----------
class TestAuditionPhase38:
    @pytest.mark.parametrize("key", [
        "phase38_morning_imaging",
        "phase38_nightlife_imaging",
        "phase38_late_night_chill",
    ])
    def test_audio_full_and_range(self, key):
        url = f"{BASE_URL}/api/audition/{key}/audio"
        r1 = requests.get(url, timeout=30)
        assert r1.status_code == 200, f"{key} full: {r1.status_code}"
        r2 = requests.get(url, headers={"Range": "bytes=0-2000"}, timeout=30)
        assert r2.status_code == 206, f"{key} range: {r2.status_code}"

    def test_landing_html(self):
        r = requests.get(f"{BASE_URL}/api/audition/__landing", timeout=30)
        assert r.status_code == 200
        html = r.text
        for k in ("phase38_morning_imaging", "phase38_nightlife_imaging",
                  "phase38_late_night_chill"):
            assert k in html, f"missing {k} on landing"


# ---------- DUO 2-stage rewrite ----------
class TestDuoRewrite:
    def test_duo_two_stage(self, premium_session, admin_session):
        # Ensure Dubai market
        premium_session.post(f"{BASE_URL}/api/users/preferences", json={"market": "dubai"})
        rs = premium_session.post(f"{BASE_URL}/api/radio/start",
                                  json={"channel": "party_dubai"})
        assert rs.status_code == 200, rs.text
        sid = rs.json().get("session_id")
        # Force 5 next calls
        for _ in range(5):
            premium_session.get(f"{BASE_URL}/api/radio/next?session_id={sid}", timeout=60)
            time.sleep(0.5)
        # Wait a bit for async QA writes
        time.sleep(3)
        r = admin_session.get(f"{BASE_URL}/api/admin/rj-quality/recent?limit=25")
        assert r.status_code == 200
        items = r.json().get("items", [])
        duo_items = [i for i in items if i.get("format") == "duo"]
        assert duo_items, "no duo items found in /rj-quality/recent"
        # find at least one with initial != rewritten and both having speaker tags
        good = []
        for it in duo_items:
            ini = it.get("initial_script") or ""
            rew = it.get("rewritten_script") or ""
            if ini and rew and ini != rew:
                if ("[" in ini and "]" in ini) and ("[" in rew and "]" in rew):
                    good.append(it)
        assert good, f"no duo item with initial != rewritten AND speaker tags. Examined {len(duo_items)} duo items"


# ---------- Regression: Phase 3.7 surfaces ----------
class TestPhase37Regression:
    def test_dashboard(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/rj-quality/dashboard")
        assert r.status_code == 200
        data = r.json()
        # 6 profiles expected
        profiles = data.get("profiles") or data.get("personality_profiles") or []
        assert len(profiles) >= 6, f"expected >=6 profiles, got {len(profiles)}: {data}"

    def test_recent_two_stage_solo(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/rj-quality/recent?limit=30")
        assert r.status_code == 200
        items = r.json().get("items", [])
        solo_two_stage = [
            i for i in items
            if i.get("format") == "solo"
            and i.get("initial_script") and i.get("rewritten_script")
            and i.get("initial_script") != i.get("rewritten_script")
        ]
        assert solo_two_stage, "no two-stage solo segments found"

    def test_rate_and_winning(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/rj-quality/recent?limit=5")
        items = r.json()["items"]
        if not items:
            pytest.skip("no items")
        qid = items[0].get("segment_id") or items[0].get("id") or items[0].get("_id")
        # rate (query params)
        rr = admin_session.post(
            f"{BASE_URL}/api/admin/rj-quality/{qid}/rate",
            params={"naturalness_1_5": 4, "hinglish_quality_1_5": 4, "radio_energy_1_5": 4,
                    "notes": "TEST_phase38"},
        )
        assert rr.status_code == 200, rr.text
        # winning toggle
        rw = admin_session.post(
            f"{BASE_URL}/api/admin/rj-quality/{qid}/winning",
            params={"winning": True},
        )
        assert rw.status_code == 200
        rw2 = admin_session.post(
            f"{BASE_URL}/api/admin/rj-quality/{qid}/winning",
            params={"winning": False},
        )
        assert rw2.status_code == 200
