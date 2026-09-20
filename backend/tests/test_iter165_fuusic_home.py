"""Iter165 — FUUSIC New Look V2 Home realignment backend tests.

Tests:
- GET /api/shell/home returns fuusic_world, together_actions, pillar_order,
  home_config, plus existing fields.
- GET/PUT /api/admin/home-config with admin auth (403 for non-admin/anon).
- Admin PUT validates pillar_order (drops invalid, appends missing).
- GET /api/social/home returns happening_now/friends_now/etc.
- POST /api/shell/home-events accepts new analytics events.
- Restores default pillar_order + together section on teardown.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN = {"email": "admin@bigfm.dubai", "password": "AdminPass123!"}
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
FREE = {"email": "freeuser@bigfm.dubai", "password": "FreePass123!"}

DEFAULT_ORDER = ["social", "listen", "live", "shop", "play", "dining", "earn", "explore"]


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login {creds['email']} failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login(ADMIN)


@pytest.fixture(scope="module")
def demo_session():
    return _login(DEMO)


@pytest.fixture(scope="module")
def free_session():
    try:
        return _login(FREE)
    except AssertionError:
        pytest.skip("free user unavailable")


# ---------- shell/home ----------
class TestShellHome:
    def test_home_new_fields(self, demo_session):
        r = demo_session.get(f"{API}/shell/home", timeout=15)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        # New fields
        assert "fuusic_world" in data and isinstance(data["fuusic_world"], list)
        assert len(data["fuusic_world"]) >= 4
        first = data["fuusic_world"][0]
        assert first.get("key") == "social", f"social must be first pillar: got {first.get('key')}"
        assert first.get("featured") is True, "social must be featured"
        assert "together_actions" in data and isinstance(data["together_actions"], list)
        assert len(data["together_actions"]) >= 3
        assert "pillar_order" in data and isinstance(data["pillar_order"], list)
        assert data["pillar_order"][0] == "social"
        assert "home_config" in data and isinstance(data["home_config"], dict)
        # shell/home flattens sections directly onto home_config (each entry
        # has {visible, title}); admin/home-config nests them under "sections".
        hc = data["home_config"]
        sections = hc.get("sections") if isinstance(hc.get("sections"), dict) else hc
        assert "together" in sections, f"missing together section: {list(sections.keys())}"
        assert sections["together"].get("title")
        # Backward-compat fields still there
        for k in ("for_you", "live_now", "is_premium"):
            assert k in data, f"missing legacy field {k}"


# ---------- admin/home-config ----------
class TestAdminHomeConfig:
    def test_get_forbidden_anon(self):
        r = requests.get(f"{API}/admin/home-config", timeout=15)
        assert r.status_code in (401, 403), f"anon should be blocked: {r.status_code}"

    def test_get_forbidden_non_admin(self, demo_session):
        r = demo_session.get(f"{API}/admin/home-config", timeout=15)
        assert r.status_code in (401, 403), f"non-admin should be blocked: {r.status_code}"

    def test_admin_get(self, admin_session):
        r = admin_session.get(f"{API}/admin/home-config", timeout=15)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert "pillar_order" in data
        assert "sections" in data
        assert "pillars" in data
        assert "social" in data["pillars"]
        assert data["pillars"]["social"].get("featured") is True

    def test_put_validates_and_reflects(self, admin_session):
        # Send invalid pillar + missing several; expect drop + fill
        body = {
            "pillar_order": ["listen", "bogus_key", "social"],
            "sections": {"together": {"visible": True, "title": "Do Something Together"}},
        }
        r = admin_session.put(f"{API}/admin/home-config", json=body, timeout=15)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        order = data["pillar_order"]
        assert "bogus_key" not in order
        assert order[:2] == ["listen", "social"]
        # missing pillars must be appended
        for k in DEFAULT_ORDER:
            assert k in order, f"missing pillar {k} not appended"
        # reflected via shell/home
        r2 = admin_session.get(f"{API}/shell/home", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["pillar_order"][:2] == ["listen", "social"]

    def test_restore_defaults(self, admin_session):
        body = {
            "pillar_order": DEFAULT_ORDER,
            "sections": {"together": {"visible": True, "title": "Do Something Together"}},
        }
        r = admin_session.put(f"{API}/admin/home-config", json=body, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["pillar_order"] == DEFAULT_ORDER
        assert data["sections"]["together"]["visible"] is True
        assert data["sections"]["together"]["title"] == "Do Something Together"


# ---------- social/home ----------
class TestSocialHome:
    def test_social_home_shape(self, demo_session):
        r = demo_session.get(f"{API}/social/home", timeout=15)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert "happening_now" in data
        hn = data["happening_now"] or {}
        for k in ("live_experiences", "friends_listening", "friends_online"):
            assert k in hn, f"missing happening_now.{k}"
        assert "friends_now" in data and isinstance(data["friends_now"], list)
        assert "suggested_rooms" in data and isinstance(data["suggested_rooms"], list)
        assert "counts" in data and isinstance(data["counts"], dict)
        assert "friends" in data["counts"]
        assert "do_together" in data and isinstance(data["do_together"], list)


# ---------- home-events analytics ----------
class TestHomeEvents:
    NEW_EVENTS = [
        "home_fuusic_world_view",
        "home_pillar_click",
        "home_social_click",
        "home_listen_click",
        "home_live_click",
        "home_shop_click",
        "home_play_click",
        "home_dining_click",
        "home_earn_click",
        "home_explore_click",
        "home_together_action_click",
        "home_whats_happening_click",
    ]

    def test_new_events_ok(self, demo_session):
        results = {}
        for ev in self.NEW_EVENTS:
            r = demo_session.post(
                f"{API}/shell/home-events",
                json={"event": ev, "data": {"src": "test"}},
                timeout=10,
            )
            results[ev] = (r.status_code, r.text[:120])
            assert r.status_code == 200, f"{ev}: {r.status_code} {r.text[:120]}"
            body = r.json()
            assert body.get("ok") is True, f"{ev} returned {body}"

    def test_unknown_event_rejected(self, demo_session):
        r = demo_session.post(
            f"{API}/shell/home-events",
            json={"event": "not_a_real_event_xyz"},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json().get("ok") is False


# ---------- final teardown: ensure defaults restored ----------
def test_final_defaults_restored():
    s = _login(ADMIN)
    body = {
        "pillar_order": DEFAULT_ORDER,
        "sections": {"together": {"visible": True, "title": "Do Something Together"}},
    }
    r = s.put(f"{API}/admin/home-config", json=body, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["pillar_order"] == DEFAULT_ORDER
    assert d["sections"]["together"]["visible"] is True
    assert d["sections"]["together"]["title"] == "Do Something Together"
