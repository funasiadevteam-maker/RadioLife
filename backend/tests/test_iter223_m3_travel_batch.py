"""Iteration 223 — Milestone 3 (Follow Channel + Share Segment) + Travel Price Alerts + My Trips Saved CRUD.
Backend regression tests for the new features."""
import os
import uuid
import pytest
import requests

def _load_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not url:
        try:
            with open("/app/frontend/.env") as f:
                for ln in f:
                    if ln.startswith("REACT_APP_BACKEND_URL="):
                        url = ln.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return url.rstrip("/")


BASE_URL = _load_url()
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "demo@bigfm.dubai", "password": "DemoPass123!"})
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:200]}"
    return s


# -------- M3: Channel Follow + Share-Segment ------------------------------
class TestChannelFollow:
    SLUG = "fuusic-pop-ai"

    def test_follow_channel(self, session):
        r = session.post(f"{BASE_URL}/api/radio/channels/{self.SLUG}/follow",
                         json={"channel_name": "FUUSIC Pop AI",
                               "channel_logo": "https://example.com/x.png"})
        assert r.status_code == 200, r.text
        assert r.json().get("now_following") is True

    def test_follow_status_true(self, session):
        r = session.get(f"{BASE_URL}/api/radio/channels/{self.SLUG}/follow-status")
        assert r.status_code == 200
        assert r.json().get("following") is True

    def test_unfollow(self, session):
        r = session.post(f"{BASE_URL}/api/radio/channels/{self.SLUG}/unfollow")
        assert r.status_code == 200
        assert r.json().get("now_following") is False
        r2 = session.get(f"{BASE_URL}/api/radio/channels/{self.SLUG}/follow-status")
        assert r2.json().get("following") is False


class TestShareSegment:
    def test_external_url_blocked_403(self, session):
        r = session.post(f"{BASE_URL}/api/radio/clips/share-segment", json={
            "channel_slug": "test-ch",
            "channel_name": "Test",
            "segment_audio_url": "https://external.example.com/foo.mp3",
            "comment": "nope",
            "visibility": "public",
            "duration_seconds": 30,
        })
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"

    def test_fuusic_owned_ok(self, session):
        key = f"iter223_{uuid.uuid4().hex[:8]}"
        r = session.post(f"{BASE_URL}/api/radio/clips/share-segment", json={
            "channel_slug": "test-ch",
            "channel_name": "FUUSIC Test",
            "segment_audio_url": "/api/radio/segment/test",
            "comment": "TEST_iter223 clip",
            "visibility": "public",
            "duration_seconds": 30,
            "idempotency_key": key,
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("clip_id", "").startswith("uc_")


class TestFeedPreferencesIncludesChannel:
    SLUG = "iter223-ch"

    def test_feed_prefs_lists_followed_channel(self, session):
        # follow a channel first
        session.post(f"{BASE_URL}/api/radio/channels/{self.SLUG}/follow",
                     json={"channel_name": "Iter223 Channel"})
        r = session.get(f"{BASE_URL}/api/social/feed-preferences")
        assert r.status_code == 200, r.text
        body = r.json()
        # followed may be under 'following' or 'followed' depending on service
        # pull all station ids out of common keys
        text = str(body)
        assert f"ch_{self.SLUG}" in text, f"ch_{self.SLUG} not in feed-preferences: {text[:300]}"
        # cleanup
        session.post(f"{BASE_URL}/api/radio/channels/{self.SLUG}/unfollow")


# -------- Price Alerts CRUD ------------------------------------------------
class TestPriceWatches:
    def test_crud_cycle(self, session):
        # Create watch
        r = session.post(f"{BASE_URL}/api/travel/watches", json={
            "origin": "DXB", "destination": "SIN", "price": 500,
            "deep_link": "https://aviasales.com/x"
        })
        assert r.status_code == 200, r.text
        wid = r.json().get("watch_id")
        assert wid

        # List
        r2 = session.get(f"{BASE_URL}/api/travel/watches")
        assert r2.status_code == 200
        data = r2.json()
        assert data.get("alert_drop_pct") == 5 or data.get("alert_drop_pct") == 5.0
        items = data.get("items") or []
        row = next((x for x in items if x.get("watch_id") == wid), None)
        assert row is not None, f"watch {wid} not in list"
        # must have current_price, drop_pct, dropped
        assert "current_price" in row
        assert "drop_pct" in row
        assert "dropped" in row
        assert isinstance(row["dropped"], bool)

        # Delete
        r3 = session.delete(f"{BASE_URL}/api/travel/watches/{wid}")
        assert r3.status_code == 200
        r4 = session.get(f"{BASE_URL}/api/travel/watches")
        assert not any(x.get("watch_id") == wid for x in (r4.json().get("items") or []))


# -------- My Trips Saved CRUD ---------------------------------------------
class TestSavedTrips:
    def test_save_flight_hotel_car_and_list(self, session):
        created = []
        for tt, title in [("flight", "TEST_iter223 flight DXB→SIN"),
                          ("hotel", "TEST_iter223 Dubai hotel"),
                          ("car", "TEST_iter223 car DXB")]:
            r = session.post(f"{BASE_URL}/api/travel/saved", json={
                "trip_type": tt, "title": title,
                "subtitle": "sub", "deep_link": "https://x", "price_label": "$100"
            })
            assert r.status_code == 200, r.text
            sid = r.json().get("saved_id")
            assert sid
            created.append((tt, sid))

        r = session.get(f"{BASE_URL}/api/travel/saved")
        assert r.status_code == 200
        data = r.json()
        assert "flights" in data and "hotels" in data and "cars" in data
        all_ids = {s["saved_id"] for s in
                   data["flights"] + data["hotels"] + data["cars"]}
        for _, sid in created:
            assert sid in all_ids

        # cleanup
        for _, sid in created:
            session.delete(f"{BASE_URL}/api/travel/saved/{sid}")
