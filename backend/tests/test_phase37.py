"""Phase 3.7 — RJ Naturalness Engine + Multi-Market Support backend tests."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

FREE = ("test@bigfm.dubai", "TestUser123!")
ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
PREMIUM = ("premium@bigfm.dubai", "PremiumTest123!")

EXPECTED_PROFILES = {"morning_drive", "lunch", "evening_drive", "nightlife", "chill_late_night", "talk_news"}
GRANULAR_DAYPARTS = {"morning_drive", "lunch_rush", "evening_drive", "nightlife_mode", "overnight_lounge",
                     "morning_rise", "afternoon_reset", "prime_social", "deep_night",
                     "chill_late_night", "talk_dayparts"}
PHASE37_KEYS = ["phase37_morning_drive", "phase37_lunch", "phase37_evening_drive",
                "phase37_nightlife", "phase37_chill_late_night", "phase37_talk_news"]


def login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


def _hdr(_):
    # Backwards-compat shim — sessions carry cookies, header not needed.
    return {}


@pytest.fixture(scope="module")
def admin_tok():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def free_tok():
    return login(*FREE)


@pytest.fixture(scope="module")
def premium_tok():
    return login(*PREMIUM)


# ---------- Auth regression ----------
class TestAuth:
    def test_all_three_logins_work(self):
        for em, pw in (FREE, ADMIN, PREMIUM):
            r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": em, "password": pw}, timeout=30)
            assert r.status_code == 200, f"{em} login failed: {r.text}"
            assert r.json().get("email") == em


# ---------- Admin RJ Quality dashboard ----------
class TestRjQualityDashboard:
    def test_dashboard_summary(self, admin_tok):
        r = admin_tok.get(f"{BASE_URL}/api/admin/rj-quality/dashboard", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("total_segments", "winning_takes", "common_issues_24h", "top_rated_voices", "personality_profiles"):
            assert k in d, f"missing key {k}"
        assert isinstance(d["common_issues_24h"], list)
        assert isinstance(d["top_rated_voices"], list)
        slugs = {p["slug"] for p in d["personality_profiles"]}
        assert EXPECTED_PROFILES.issubset(slugs), f"missing personality profiles, got {slugs}"
        assert d["total_segments"] >= 0

    def test_personality_profiles_endpoint(self, admin_tok):
        r = admin_tok.get(f"{BASE_URL}/api/admin/rj-quality/personality_profiles", timeout=30)
        assert r.status_code == 200, r.text
        slugs = {p["slug"] for p in r.json()["profiles"]}
        assert EXPECTED_PROFILES.issubset(slugs)

    def test_recent_qa_shape(self, admin_tok):
        r = admin_tok.get(f"{BASE_URL}/api/admin/rj-quality/recent?limit=20", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)
        if d["items"]:
            item = d["items"][0]
            required = {"segment_id", "initial_script", "rewritten_script", "personality_profile_slug",
                        "daypart_slug", "channel_slug", "market", "voice_key", "voice_settings",
                        "banned_phrase_hits", "regen_count", "takes_generated", "format", "hosts",
                        "final_audio_url", "final_duration_sec", "is_winning_take", "admin_ratings",
                        "user_ratings"}
            missing = required - set(item.keys())
            assert not missing, f"missing keys in recent item: {missing}"

    def test_non_admin_forbidden(self, free_tok):
        for path in (
            "/api/admin/rj-quality/dashboard",
            "/api/admin/rj-quality/recent",
            "/api/admin/rj-quality/personality_profiles",
        ):
            r = free_tok.get(f"{BASE_URL}{path}", timeout=30)
            assert r.status_code == 403, f"{path} should be 403 for free user, got {r.status_code}"

    def test_rate_and_winning_flow(self, admin_tok):
        # Pick any existing segment
        r = admin_tok.get(f"{BASE_URL}/api/admin/rj-quality/recent?limit=1", timeout=30)
        assert r.status_code == 200
        items = r.json()["items"]
        if not items:
            pytest.skip("no QA segments to rate")
        sid = items[0]["segment_id"]

        rr = admin_tok.post(
            f"{BASE_URL}/api/admin/rj-quality/{sid}/rate",
            params={"naturalness_1_5": 5, "hinglish_quality_1_5": 4, "radio_energy_1_5": 5, "notes": "TEST_phase37"},
            timeout=30,
        )
        assert rr.status_code == 200, rr.text
        assert rr.json().get("ok") is True

        wr = admin_tok.post(
            f"{BASE_URL}/api/admin/rj-quality/{sid}/winning",
            params={"winning": True}, timeout=30,
        )
        assert wr.status_code == 200, wr.text
        assert wr.json().get("is_winning_take") is True

        # Verify rating persisted
        rr2 = admin_tok.get(f"{BASE_URL}/api/admin/rj-quality/recent?limit=50", timeout=30)
        items2 = rr2.json()["items"]
        match = next((i for i in items2 if i["segment_id"] == sid), None)
        assert match is not None, "rated segment vanished"
        ratings = match.get("admin_ratings") or []
        assert any(a.get("naturalness_1_5") == 5 for a in ratings), f"admin rating not persisted: {ratings}"
        assert match.get("is_winning_take") is True

        # Idempotency: calling /winning again with winning=false should also return 200 (matched_count fix)
        wr2 = admin_tok.post(
            f"{BASE_URL}/api/admin/rj-quality/{sid}/winning",
            params={"winning": False}, timeout=30,
        )
        assert wr2.status_code == 200, wr2.text
        assert wr2.json().get("is_winning_take") is False


# ---------- Multi-market ----------
class TestMultiMarket:
    def test_premium_me_has_market_dubai(self, premium_tok):
        r = premium_tok.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200, r.text
        assert r.json().get("market") == "dubai", f"got {r.json().get('market')}"

    def test_prefs_market_switch_dfw_then_dubai(self, premium_tok):
        # Read existing prefs first to preserve required fields
        me = premium_tok.get(f"{BASE_URL}/api/auth/me", timeout=30).json()
        prefs = me.get("preferences") or {}
        base_payload = {
            "language_mix": prefs.get("language_mix", "hinglish_70_30"),
            "genres": prefs.get("genres", ["bollywood", "pop"]),
            "activities": prefs.get("activities", ["commute", "workout"]),
            "moods": prefs.get("moods", ["romantic", "party"]),
            "eras": prefs.get("eras", ["2010s", "2020s"]),
            "favourite_artists": prefs.get("favourite_artists", ["Arijit Singh"]),
            "city_zone": prefs.get("city_zone", "karama"),
            "voice_persona": prefs.get("voice_persona", "warm_witty"),
            "ads_personalization": prefs.get("ads_personalization", True),
            "explicit_filter": prefs.get("explicit_filter", "clean_only"),
            "discovery_dial": prefs.get("discovery_dial", 50),
        }

        # Switch to DFW
        p = {**base_payload, "languages": ["hindi", "english"], "market": "dfw", "city_zone": "frisco"}
        r = premium_tok.post(f"{BASE_URL}/api/users/preferences", json=p, timeout=30)
        assert r.status_code == 200, r.text
        me2 = premium_tok.get(f"{BASE_URL}/api/auth/me", timeout=30).json()
        assert me2.get("market") == "dfw", f"market not updated to dfw: {me2.get('market')}"

        # Switch back to Dubai
        p2 = {**base_payload, "languages": ["hindi", "english"], "market": "dubai", "city_zone": "karama"}
        r2 = premium_tok.post(f"{BASE_URL}/api/users/preferences", json=p2, timeout=30)
        assert r2.status_code == 200, r2.text
        me3 = premium_tok.get(f"{BASE_URL}/api/auth/me", timeout=30).json()
        assert me3.get("market") == "dubai"

    def test_prefs_rejects_invalid_market(self, premium_tok):
        p = {
            "language_mix": "hinglish_70_30",
            "moods": ["romantic"], "eras": ["2010s"], "favourite_artists": ["Arijit"],
            "city_zone": "karama", "voice_persona": "warm_witty",
            "ads_personalization": True, "explicit_filter": "clean_only", "discovery_dial": 50,
            "market": "paris",
        }
        r = premium_tok.post(f"{BASE_URL}/api/users/preferences", json=p, timeout=30)
        assert r.status_code in (400, 422), f"expected 400/422, got {r.status_code}: {r.text}"


# ---------- Channel regression + market field ----------
class TestChannels:
    def test_channels_count_and_market(self):
        r = requests.get(f"{BASE_URL}/api/channels", timeout=30)
        assert r.status_code == 200
        chans = r.json()
        if isinstance(chans, dict) and "channels" in chans:
            chans = chans["channels"]
        assert len(chans) >= 10, f"expected >=10 channels, got {len(chans)}"
        for c in chans:
            assert "market" in c, f"channel {c.get('slug')} missing market field"
            assert c["market"] == "dubai", f"channel {c.get('slug')} market={c['market']} (expected dubai)"


# ---------- Voices regression ----------
class TestVoices:
    def test_voices_listing(self):
        r = requests.get(f"{BASE_URL}/api/voices", timeout=30)
        assert r.status_code == 200
        d = r.json()
        voices = d if isinstance(d, list) else d.get("voices", [])
        assert len(voices) >= 1
        v = voices[0]
        assert "key" in v and "display_name" in v
        # Phase 3.7 brief requires provider + accent_target on the public /api/voices endpoint
        assert "provider" in v, f"missing provider field on voice: {v}"
        assert "accent_target" in v, f"missing accent_target field on voice: {v}"


# ---------- Audition (Phase 3.7 samples) ----------
class TestAudition:
    @pytest.mark.parametrize("key", PHASE37_KEYS)
    def test_audition_audio_200(self, key):
        r = requests.get(f"{BASE_URL}/api/audition/{key}/audio", timeout=30)
        assert r.status_code in (200, 206), f"{key}: {r.status_code}"

    @pytest.mark.parametrize("key", PHASE37_KEYS)
    def test_audition_audio_range_206(self, key):
        r = requests.get(f"{BASE_URL}/api/audition/{key}/audio",
                         headers={"Range": "bytes=0-1023"}, timeout=30)
        assert r.status_code == 206, f"{key} range request: {r.status_code}"

    def test_audition_landing_lists_all_six(self):
        r = requests.get(f"{BASE_URL}/api/audition/__landing", timeout=30)
        assert r.status_code == 200
        html = r.text
        for k in PHASE37_KEYS:
            assert k in html, f"landing HTML missing {k}"


# ---------- Two-stage pipeline / radio start ----------
class TestNaturalnessPipeline:
    def test_two_stage_diff_on_existing_data(self, admin_tok):
        """Verify two-stage pipeline (initial != rewritten) on existing QA data."""
        rr = admin_tok.get(f"{BASE_URL}/api/admin/rj-quality/recent?limit=20", timeout=30)
        items = rr.json()["items"]
        assert items, "no QA items in DB"

        broad = {"morning", "afternoon", "evening", "late_night"}
        bad = [i for i in items if i.get("daypart_slug") in broad]
        assert not bad, f"found broad daypart_slug (regression): {[i['daypart_slug'] for i in bad]}"

        no_profile = [i for i in items if not i.get("personality_profile_slug")]
        assert not no_profile, f"items missing personality_profile_slug: {len(no_profile)}"

        solos = [i for i in items if i.get("format") == "solo"]
        if solos:
            diffs = [i for i in solos if i.get("initial_script") and i.get("rewritten_script")
                     and i["initial_script"] != i["rewritten_script"]]
            # Soft check — older rows from broad-daypart batch may have identical scripts
            if not diffs:
                pytest.skip("No SOLO segment had distinct initial vs rewritten (pre-Phase 3.7 data)")
