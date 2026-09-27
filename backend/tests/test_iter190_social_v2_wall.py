"""Iteration 190 — Social V2 Phase 1+2 backend regression.

Covers:
  • GET /api/social/following — grouped follows + total count ≥ 9 for demo
  • GET /api/social/feed-v2?mode=following — item shape (id/type/actor/cta/
    follow_relationship), pagination fields, followed-only filter
  • GET /api/social/feed-v2?mode=for_you — broader candidate set
  • GET /api/social/feed-v2/new-count?since=…&mode=following
  • POST /api/social/feed-events — allowlist behavior
  • GET /api/social/home — counts.following + happening_now.following present
"""
import os
import requests
import pytest
from datetime import datetime, timezone

def _read_env(path, key):
    try:
        with open(path) as f:
            for ln in f:
                if ln.startswith(f"{key}="):
                    return ln.split("=", 1)[1].strip()
    except FileNotFoundError:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASSWORD = "DemoPass123!"

ALLOWED_TYPES = {"MOMENT", "LIVE_VIDEO", "BUSINESS_LIVE", "EVENT",
                 "LISTEN_ROOM", "DREAM", "TAROT_SHARE", "CLUB_POST",
                 "STATION_ACTIVITY"}


@pytest.fixture(scope="session")
def demo_client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
               timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# ── /api/social/following ────────────────────────────────────────────
class TestFollowing:
    def test_following_grouped_and_count(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/social/following", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for key in ("count", "people", "creators", "advisors",
                    "businesses", "stations", "clubs"):
            assert key in d, f"missing key {key} in following response"
            if key != "count":
                assert isinstance(d[key], list)
        # Demo user is seeded to follow 6+ advisors + ≥1 club (dream club
        # members) + stations best-effort → expect at least 9.
        assert d["count"] >= 9, (
            f"expected count>=9, got {d['count']} "
            f"(advisors={len(d['advisors'])}, clubs={len(d['clubs'])}, "
            f"stations={len(d['stations'])}, people={len(d['people'])}, "
            f"creators={len(d['creators'])}, businesses={len(d['businesses'])})")
        assert len(d["advisors"]) >= 6, \
            f"expected >=6 advisors, got {len(d['advisors'])}"


# ── /api/social/feed-v2 ──────────────────────────────────────────────
class TestFeedV2Following:
    def test_following_mode_shape(self, demo_client):
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2?mode=following&limit=20",
            timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("mode") == "following"
        assert "items" in d and isinstance(d["items"], list)
        assert "has_more" in d
        assert "next_cursor" in d
        assert len(d["items"]) >= 1, \
            f"expected some following-mode items, got 0"
        types = set()
        for it in d["items"]:
            for f in ("id", "type", "actor", "cta",
                      "follow_relationship", "created_at"):
                assert f in it, f"item missing '{f}': {it}"
            assert it["type"] in ALLOWED_TYPES, \
                f"unexpected type {it['type']}"
            # following mode must never surface pure discovery.
            assert it["follow_relationship"] != "discovery", \
                f"discovery leaked into following: {it}"
            types.add(it["type"])
        # Seed guarantees MOMENT + TAROT_SHARE from a followed advisor.
        assert "MOMENT" in types or "TAROT_SHARE" in types or "DREAM" in types, \
            f"expected MOMENT/TAROT_SHARE/DREAM in following feed, got {types}"


class TestFeedV2ForYou:
    def test_for_you_broader(self, demo_client):
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2?mode=for_you&limit=20",
            timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("mode") == "for_you"
        assert isinstance(d.get("items"), list)
        for it in d["items"]:
            assert it["type"] in ALLOWED_TYPES


class TestFeedV2NewCount:
    def test_new_count_with_future_since(self, demo_client):
        # Future timestamp → no new items.
        future = "2999-01-01T00:00:00+00:00"
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2/new-count"
            f"?since={future}&mode=following", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "new_count" in d and "latest" in d
        assert d["new_count"] == 0

    def test_new_count_with_past_since(self, demo_client):
        past = "2000-01-01T00:00:00+00:00"
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2/new-count"
            f"?since={past}&mode=following", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["new_count"] >= 1, \
            f"expected new items since 2000, got {d['new_count']}"


class TestFeedEvents:
    def test_allowlisted_event_ok(self, demo_client):
        r = demo_client.post(f"{BASE_URL}/api/social/feed-events",
                             json={"event": "social_feed_view",
                                   "mode": "following"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json() == {"ok": True}

    def test_non_allowlisted_event_rejected(self, demo_client):
        r = demo_client.post(f"{BASE_URL}/api/social/feed-events",
                             json={"event": "nope_not_allowed"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is False
        assert d.get("reason") == "event_not_allowed"


class TestSocialHome:
    def test_home_has_following_counts(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/social/home", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "counts" in d and "happening_now" in d
        assert "following" in d["counts"], \
            f"counts.following missing: {d['counts']}"
        assert "following" in d["happening_now"], \
            f"happening_now.following missing: {d['happening_now']}"
        assert d["counts"]["following"] >= 9
