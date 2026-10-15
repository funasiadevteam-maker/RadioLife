"""Iteration 215 — MILESTONE 3: Station Highlights + Clip&Share + Daily Readings + Business Posts/Boost.

Shared FastAPI backend tested via the external REACT_APP_BACKEND_URL. Verifies:
 - feed-v2 following returns RADIO_CLIP cards from followed stations (seeded)
 - clip-eligibility allowed vs non-policy station returns allowed:false
 - radio/clips/share creates user_clip + idempotency returns duplicate:true
 - daily-readings PRIVACY: owner sees own READING, other user NEVER does
 - re-call does not regenerate (cached per day)
 - BUSINESS_POST visible to follower (demo follows biz_demo_karak)
 - PREMIUM demo sees ZERO SPONSORED_POST (ad-free)
 - FREE user sees a SPONSORED labelled card; hide-ad dismiss suppresses it
"""
import os
import time
import uuid
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return s, r.json().get("user_id") or r.json().get("id")


@pytest.fixture(scope="module")
def demo():
    s, uid = _login("demo@bigfm.dubai", "DemoPass123!")
    return s, uid


@pytest.fixture(scope="module")
def freeuser():
    s, uid = _login("freeuser@bigfm.dubai", "FreePass123!")
    return s, uid


def _feed(sess, mode="following", limit=80):
    r = sess.get(f"{BASE}/api/social/feed-v2", params={"mode": mode, "limit": limit}, timeout=25)
    assert r.status_code == 200, r.text
    j = r.json()
    return j.get("cards") or j.get("items") or []


# ───────── Station Highlights ─────────
class TestStationHighlights:
    def test_feed_contains_radio_clip_for_demo(self, demo):
        sess, _ = demo
        cards = _feed(sess)
        rc = [c for c in cards if c.get("card_type") == "RADIO_CLIP" or c.get("type") == "RADIO_CLIP"]
        assert len(rc) >= 1, f"Expected RADIO_CLIP cards; cards types={[c.get('card_type') for c in cards[:30]]}"
        # audio_url present
        sample = rc[0]
        au = (sample.get("media_url") or sample.get("audio_url")
              or (sample.get("media") or {}).get("audio_url")
              or (sample.get("meta") or {}).get("audio_url"))
        assert au, f"RADIO_CLIP missing audio url: {sample}"
        assert sample.get("media_type") == "audio"

    def test_daily_highlights_groups(self, demo):
        sess, _ = demo
        r = sess.get(f"{BASE}/api/social/daily-highlights", timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert "groups" in j
        assert j["station_count"] >= 1

    def test_highlights_publish_idempotent_requires_owner(self, demo):
        # Not station owner => 403; still verifies route is wired
        sess, _ = demo
        r = sess.post(
            f"{BASE}/api/stations/some_unknown_station/highlights",
            json={"show_name": "x", "title": "y", "audio_url": "https://a/b.mp3"},
            timeout=15,
        )
        assert r.status_code in (403, 404)


# ───────── Clip & Share ─────────
class TestClipShare:
    def _followed_station(self, sess):
        cards = _feed(sess)
        for c in cards:
            if (c.get("card_type") == "RADIO_CLIP" or c.get("type") == "RADIO_CLIP"):
                sid = c.get("station_id") or (c.get("meta") or {}).get("station_id") or (c.get("actor") or {}).get("id")
                if sid:
                    return sid
        return None

    def test_eligibility_allowed_for_seeded_station(self, demo):
        sess, _ = demo
        sid = self._followed_station(sess)
        assert sid, "No followed-station RADIO_CLIP found to test eligibility"
        r = sess.get(f"{BASE}/api/stations/{sid}/clip-eligibility", timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert j["allowed"] is True
        assert j["max_seconds"] == 30
        assert j.get("buffer_audio_url")

    def test_eligibility_denied_for_station_without_policy(self, demo):
        sess, _ = demo
        # Try a random imported station that very likely has no policy
        r = sess.get(f"{BASE}/api/stations/imp_fun_luv_1071_uae/clip-eligibility", timeout=20)
        # If station doesn't exist => 404; if exists and no policy => allowed:false
        if r.status_code == 200:
            assert r.json()["allowed"] is False
        else:
            assert r.status_code == 404

    def test_clip_share_and_idempotency(self, demo):
        sess, _ = demo
        sid = self._followed_station(sess)
        assert sid
        key = f"TEST_idem_{uuid.uuid4().hex[:10]}"
        payload = {"station_id": sid, "start_offset": 10, "duration_seconds": 30,
                   "comment": "TEST clip from pytest", "visibility": "public",
                   "idempotency_key": key}
        r1 = sess.post(f"{BASE}/api/radio/clips/share", json=payload, timeout=25)
        assert r1.status_code == 200, r1.text
        j1 = r1.json()
        assert j1.get("ok") and j1.get("clip_id")
        clip_id = j1["clip_id"]

        # Status endpoint
        rs = sess.get(f"{BASE}/api/radio/clips/{clip_id}/status", timeout=15)
        assert rs.status_code == 200
        assert rs.json()["status"] == "published"

        # Duplicate idempotency
        r2 = sess.post(f"{BASE}/api/radio/clips/share", json=payload, timeout=25)
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2.get("duplicate") is True
        assert j2.get("clip_id") == clip_id


# ───────── Daily Readings (privacy critical) ─────────
class TestDailyReadings:
    def test_subscribe_tarot_generates_reading(self, demo):
        sess, _ = demo
        r = sess.put(f"{BASE}/api/social/daily-readings/tarot",
                     json={"enabled": True, "frequency": "daily"}, timeout=30)
        assert r.status_code == 200, r.text

        r2 = sess.get(f"{BASE}/api/social/daily-readings", timeout=20)
        assert r2.status_code == 200
        today = r2.json().get("today") or []
        tarot_today = [t for t in today if t.get("reading_type") == "tarot"]
        assert tarot_today, f"Expected a tarot reading today; got {today}"
        assert tarot_today[0].get("body"), "Reading body missing"
        assert tarot_today[0].get("disclaimer"), "Disclaimer must be set"

    def test_my_readings_lists(self, demo):
        sess, _ = demo
        r = sess.get(f"{BASE}/api/social/my-readings", timeout=20)
        assert r.status_code == 200
        j = r.json()
        assert j["count"] >= 1
        assert j.get("disclaimer")

    def test_reading_cached_not_regenerated(self, demo):
        sess, _ = demo
        r1 = sess.get(f"{BASE}/api/social/daily-readings", timeout=20)
        t1 = next((t for t in r1.json()["today"] if t["reading_type"] == "tarot"), None)
        assert t1
        # Toggle again -> should NOT regenerate (same id/date)
        sess.put(f"{BASE}/api/social/daily-readings/tarot",
                 json={"enabled": True, "frequency": "daily"}, timeout=20)
        r2 = sess.get(f"{BASE}/api/social/daily-readings", timeout=20)
        t2 = next((t for t in r2.json()["today"] if t["reading_type"] == "tarot"), None)
        assert t2 and t2["id"] == t1["id"] and t2["body"] == t1["body"]

    def test_feed_shows_own_reading_card(self, demo):
        sess, _ = demo
        cards = _feed(sess)
        readings = [c for c in cards if (c.get("card_type") == "READING" or c.get("type") == "READING")]
        assert readings, "Owner should see their own READING card in feed-v2 following"
        r0 = readings[0]
        # is_mine + private flags expected
        assert r0.get("is_mine") in (True, None) or (r0.get("meta") or {}).get("is_mine")
        assert r0.get("private") in (True, None) or (r0.get("meta") or {}).get("private")

    def test_other_user_never_sees_demo_reading(self, freeuser):
        sess, _ = freeuser
        cards = _feed(sess)
        readings = [c for c in cards if (c.get("card_type") == "READING" or c.get("type") == "READING")]
        for r in readings:
            owner = r.get("owner_user_id") or (r.get("meta") or {}).get("user_id") or (r.get("actor") or {}).get("id")
            # Any reading seen by freeuser must belong to freeuser, not demo
            assert owner != "user_eeb941588d134d0d", f"PRIVACY LEAK: freeuser saw demo's reading: {r}"


# ───────── Business Posts + Boost / Sponsored ─────────
class TestBusinessPostsAndSponsored:
    def test_demo_follower_sees_business_post(self, demo):
        sess, _ = demo
        cards = _feed(sess)
        bps = [c for c in cards if (c.get("card_type") == "BUSINESS_POST" or c.get("type") == "BUSINESS_POST")]
        assert bps, "Demo (follower of biz_demo_karak) should see at least 1 BUSINESS_POST"

    def test_premium_demo_sees_zero_sponsored(self, demo):
        sess, _ = demo
        cards = _feed(sess, limit=120)
        sp = [c for c in cards
              if (c.get("card_type") == "SPONSORED_POST" or c.get("type") == "SPONSORED_POST"
                  or c.get("sponsored") is True)]
        assert len(sp) == 0, f"Premium user must be ad-free; saw {len(sp)} sponsored cards"

    def test_freeuser_sees_sponsored_card_with_label(self, freeuser):
        sess, _ = freeuser
        cards = _feed(sess, limit=120)
        sp = [c for c in cards
              if (c.get("card_type") == "SPONSORED_POST" or c.get("type") == "SPONSORED_POST"
                  or c.get("sponsored") is True
                  or ((c.get("meta") or {}).get("sponsored_label") == "Sponsored"))]
        assert sp, "Freeuser should see a sponsored card in following feed"
        s0 = sp[0]
        lbl = (s0.get("meta") or {}).get("sponsored_label") or s0.get("sponsored_label")
        assert lbl == "Sponsored" or s0.get("sponsored") is True

    def test_freeuser_hide_ad_removes_sponsored(self, freeuser):
        sess, _ = freeuser
        cards = _feed(sess, limit=120)
        sp = [c for c in cards
              if (c.get("card_type") == "SPONSORED_POST" or c.get("type") == "SPONSORED_POST"
                  or c.get("sponsored") is True)]
        if not sp:
            pytest.skip("No sponsored card to hide (seed may be empty)")
        s0 = sp[0]
        pid = (s0.get("meta") or {}).get("post_id") or s0.get("post_id") or s0.get("id") or (s0.get("actor") or {}).get("id")
        r = sess.post(f"{BASE}/api/social/suggestions/dismiss",
                      json={"actor_type": "sponsored_post", "actor_id": pid}, timeout=20)
        assert r.status_code in (200, 201, 204), r.text
        # Refetch — the SAME post_id must no longer appear as sponsored
        cards2 = _feed(sess, limit=120)
        still = [c for c in cards2
                 if ((c.get("meta") or {}).get("post_id") == pid
                     or c.get("post_id") == pid)
                 and (c.get("card_type") == "SPONSORED_POST" or c.get("sponsored") is True)]
        assert not still, f"Hidden sponsored post {pid} must not reappear"
