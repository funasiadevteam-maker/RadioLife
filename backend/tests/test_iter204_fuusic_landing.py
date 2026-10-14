"""iter_204 — FUUSIC public social-first landing: backend endpoints + admin config.

Covers:
  • GET /api/public/landing-config (default_theme=light, station_copy_text wiring)
  • GET /api/public/feed?limit=6 (SocialFeedCard shape, has_more, illustrative blend)
  • GET /api/public/people, /api/public/live-now, /api/public/promos
  • Admin: /api/admin/landing-config GET/PUT — station_copy=generic flips public text;
           disabling a house promo removes it from /api/public/promos.
  • Restores defaults (station_copy=thousands, promos.disabled=[]).
"""
import os
import pytest
import requests

def _load_backend_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not url:
        try:
            with open("/app/frontend/.env", "r") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip().strip('"')
                        break
        except Exception:
            pass
    return url.rstrip("/")

BASE_URL = _load_backend_url()
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"


# ── Public (anon) endpoints ─────────────────────────────────────────────
class TestPublicLandingConfig:
    def test_default_theme_light_and_station_copy(self):
        r = requests.get(f"{BASE_URL}/api/public/landing-config", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "new_landing_enabled" in data
        assert data.get("default_theme") == "light"
        assert "station_copy_text" in data
        # Should be either generic or thousands based on current config
        assert data["station_copy_text"] in {
            "Radio stations from around the world",
            "Thousands of radio stations. One world of sound.",
        }
        # Should NOT contain promos internals in public
        assert "promos" not in data
        hero = data.get("hero") or {}
        assert hero.get("headline") == "Everything You Love, Together."


class TestPublicFeed:
    def test_feed_shape(self):
        r = requests.get(f"{BASE_URL}/api/public/feed?limit=6&offset=0", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert "has_more" in data
        assert len(data["items"]) > 0
        card = data["items"][0]
        for key in ("id", "type", "actor", "created_at"):
            assert key in card, f"missing {key} in {card}"
        # No 50K anywhere
        body_text = r.text.lower()
        assert "50,000" not in body_text
        assert "50k" not in body_text

    def test_feed_has_illustrative_cards(self):
        r = requests.get(f"{BASE_URL}/api/public/feed?limit=20&offset=0", timeout=15)
        assert r.status_code == 200
        items = r.json().get("items") or []
        illus = [i for i in items if i.get("illustrative") is True]
        assert len(illus) >= 1, "expected at least one illustrative card"


class TestPublicPeople:
    def test_people_shape(self):
        r = requests.get(f"{BASE_URL}/api/public/people", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "people" in data and len(data["people"]) >= 1


class TestPublicLiveNow:
    def test_live_now_has_discover(self):
        r = requests.get(f"{BASE_URL}/api/public/live-now", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "live" in data and "discover" in data
        for d in data["discover"]:
            assert d.get("live") is False  # discover items must NOT be flagged live
        for liv in data["live"]:
            assert liv.get("live") is True


class TestPublicPromos:
    def test_promos_contains_house(self):
        r = requests.get(f"{BASE_URL}/api/public/promos", timeout=15)
        assert r.status_code == 200
        promos = r.json().get("promos") or []
        ids = [p.get("id") for p in promos]
        assert "premium" in ids
        assert "business" in ids
        # Sponsored items must be flagged sponsored=true
        for p in promos:
            if p.get("house") is False:
                assert p.get("sponsored") is True


# ── Admin round-trip ────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text[:200]}")
    return s


class TestAdminLandingConfig:
    def test_admin_get(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/landing-config", timeout=15)
        assert r.status_code == 200, r.text
        payload = r.json()
        assert "config" in payload and "options" in payload
        assert "themes" in payload["options"]
        assert "station_copy" in payload["options"]

    def test_admin_put_station_copy_generic_reflects_public(self, admin_session):
        # Switch to generic
        r = admin_session.put(f"{BASE_URL}/api/admin/landing-config",
                              json={"station_copy": "generic"}, timeout=15)
        assert r.status_code == 200, r.text
        cfg = r.json()["config"]
        assert cfg["station_copy"] == "generic"
        # Public endpoint should mirror new copy
        r2 = requests.get(f"{BASE_URL}/api/public/landing-config", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["station_copy_text"] == "Radio stations from around the world"

    def test_admin_disable_house_promo_hides_it(self, admin_session):
        # Disable "bigpoints" house promo
        r = admin_session.put(f"{BASE_URL}/api/admin/landing-config",
                              json={"promos": {"disabled": ["bigpoints"], "external": []}},
                              timeout=15)
        assert r.status_code == 200, r.text
        # Verify public /promos no longer includes it
        r2 = requests.get(f"{BASE_URL}/api/public/promos", timeout=15)
        assert r2.status_code == 200
        ids = [p.get("id") for p in r2.json().get("promos") or []]
        assert "bigpoints" not in ids

    def test_restore_defaults(self, admin_session):
        """Restore station_copy=thousands and clear disabled promos."""
        r = admin_session.put(f"{BASE_URL}/api/admin/landing-config",
                              json={"station_copy": "thousands",
                                    "promos": {"disabled": [], "external": []}},
                              timeout=15)
        assert r.status_code == 200, r.text
        r2 = requests.get(f"{BASE_URL}/api/public/landing-config", timeout=15)
        assert r2.json()["station_copy_text"] == "Thousands of radio stations. One world of sound."
        r3 = requests.get(f"{BASE_URL}/api/public/promos", timeout=15)
        ids = [p.get("id") for p in r3.json().get("promos") or []]
        assert "bigpoints" in ids
