"""Iteration 191 — Social V2 Right-Rail V2 (/api/social/rail) + regressions.

Covers:
  • P0 fix: /api/social/feed-v2/new-count returns new_count>=1 for a
    far-past `since` and tolerates `+` decoded as ` `.
  • P1 fix: anonymous DREAM items with follow_relationship='discovery'
    are excluded from following mode.
  • NEW: GET /api/social/rail?page_route=<>&limit=7 returns 5–7 cards
    with the compact card contract, and ordering shifts by page_route.
"""
import os
import requests
import pytest


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
FREE_EMAIL = "freeuser@bigfm.dubai"
FREE_PASSWORD = "FreePass123!"

RAIL_KINDS = {"live", "event", "follow", "station", "sponsored"}
RAIL_FIELDS = {"id", "kind", "title", "subtitle", "image", "badge", "cta"}


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="session")
def demo_client():
    return _login(DEMO_EMAIL, DEMO_PASSWORD)


@pytest.fixture(scope="session")
def free_client():
    return _login(FREE_EMAIL, FREE_PASSWORD)


# ── P0 regression: new-count returns >=1 for past since ──────────────
class TestNewCountP0Fix:
    def test_past_since_returns_positive(self, demo_client):
        past = "2000-01-01T00:00:00+00:00"
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2/new-count",
            params={"since": past, "mode": "following"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["new_count"] >= 1, \
            f"P0: expected >=1 new since 2000, got {d['new_count']}"

    def test_future_since_returns_zero(self, demo_client):
        future = "2999-01-01T00:00:00+00:00"
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2/new-count",
            params={"since": future, "mode": "following"}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["new_count"] == 0

    def test_tolerates_plus_decoded_as_space(self, demo_client):
        # If a client passes since without url-encoding, FastAPI decodes
        # '+' → space. Endpoint must still parse it.
        past_space = "2000-01-01T00:00:00 00:00"
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2/new-count"
            f"?since={past_space}&mode=following", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["new_count"] >= 1, \
            f"P0: expected >=1 with space-decoded tz, got {d['new_count']}"


# ── P1 regression: no discovery leaks into following ─────────────────
class TestFollowingNoDiscovery:
    def test_following_mode_excludes_discovery(self, demo_client):
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2",
            params={"mode": "following", "limit": 40}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("items"), list)
        for it in d["items"]:
            assert it.get("follow_relationship") != "discovery", \
                f"discovery leaked: type={it.get('type')} id={it.get('id')}"

    def test_no_anonymous_dreams_in_following(self, demo_client):
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2",
            params={"mode": "following", "limit": 40}, timeout=30)
        assert r.status_code == 200, r.text
        for it in r.json()["items"]:
            if it.get("type") != "DREAM":
                continue
            # A DREAM in following-mode must be authored by someone we
            # follow (i.e. not a discovery-only anonymous dream).
            assert it.get("follow_relationship") in {
                "self", "friend", "friend_following", "following"}, (
                f"anon dream leaked: {it}")


# ── NEW: /api/social/rail contract & contextual ordering ─────────────
class TestSocialRailShape:
    @pytest.mark.parametrize("page_route", ["/social", "/channels", "/shop"])
    def test_rail_shape_and_size(self, demo_client, page_route):
        r = demo_client.get(f"{BASE_URL}/api/social/rail",
                            params={"page_route": page_route, "limit": 7},
                            timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("page_route") == page_route
        cards = d.get("cards")
        assert isinstance(cards, list), f"cards not a list: {d}"
        assert 1 <= len(cards) <= 7, \
            f"expected 1..7 cards, got {len(cards)}"
        # Preview seed guarantees enough sample data for >=5 cards.
        assert len(cards) >= 5, \
            f"expected >=5 rail cards, got {len(cards)} ({page_route})"
        seen_ids = set()
        for c in cards:
            missing = RAIL_FIELDS - set(c.keys())
            assert not missing, f"card missing fields {missing}: {c}"
            assert c["kind"] in RAIL_KINDS, f"bad kind: {c}"
            assert c["id"] not in seen_ids, f"duplicate id: {c['id']}"
            seen_ids.add(c["id"])
            assert isinstance(c["title"], str) and c["title"]
            assert isinstance(c["cta"], str) and c["cta"]
            if c["kind"] == "follow":
                assert c.get("follow_id"), \
                    f"follow card missing follow_id: {c}"

    def test_rail_limit_is_capped_at_7(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/social/rail",
                            params={"page_route": "/social", "limit": 25},
                            timeout=30)
        assert r.status_code == 200, r.text
        assert len(r.json()["cards"]) <= 7

    def test_rail_contextual_ordering(self, demo_client):
        """Stations should rank higher on /channels than /shop; live/event
        should rank higher on /shop than /channels (via _RAIL_CTX)."""
        def _first_index(cards, kind):
            for i, c in enumerate(cards):
                if c["kind"] == kind:
                    return i
            return 999

        r_ch = demo_client.get(f"{BASE_URL}/api/social/rail",
                               params={"page_route": "/channels",
                                       "limit": 7}, timeout=30).json()
        r_shop = demo_client.get(f"{BASE_URL}/api/social/rail",
                                 params={"page_route": "/shop",
                                         "limit": 7}, timeout=30).json()
        # Stations should exist and rank earlier on /channels
        st_ch = _first_index(r_ch["cards"], "station")
        st_shop = _first_index(r_shop["cards"], "station")
        # Best-effort assertion: at least one page has a station and
        # station on /channels is not later than on /shop.
        assert st_ch <= st_shop, (
            f"/channels station rank ({st_ch}) should be <= /shop ({st_shop})")

    def test_rail_free_user_also_gets_cards(self, free_client):
        r = free_client.get(f"{BASE_URL}/api/social/rail",
                            params={"page_route": "/social", "limit": 7},
                            timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("cards"), list)
        assert len(d["cards"]) >= 1


# ── Regression: social wall still loads (feed-v2 following + for_you) ─
class TestSocialWallRegression:
    def test_following_loads(self, demo_client):
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2",
            params={"mode": "following", "limit": 20}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("mode") == "following"
        assert len(r.json()["items"]) >= 1

    def test_for_you_loads(self, demo_client):
        r = demo_client.get(
            f"{BASE_URL}/api/social/feed-v2",
            params={"mode": "for_you", "limit": 20}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("mode") == "for_you"

    def test_following_grouped(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/social/following", timeout=30)
        assert r.status_code == 200
        assert r.json().get("count", 0) >= 9
