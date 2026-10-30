"""Phase 4 — Companion Memory + Sponsor Breaks backend tests.

Covers:
- /api/fun-ai/memory GET/PUT/POST/POST remove/POST clear (demo user)
- /api/fun-ai/news/break-event impression tracking
- /api/fun-ai/news/briefing 'breaks' array: opening (after_index=-1),
  mid (after_index=mid_after_segment) and closing (after_index=count) for
  non-premium when sponsor is enabled; empty [] for premium users.
- Sponsor DISABLED at teardown so no sponsor is left showing.
"""
import os
import time
import pytest
import requests

def _read_env(path, key):
    try:
        for line in open(path):
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    except OSError:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PW = "AdminPass123!"
DEMO_EMAIL = "demo@bigfm.dubai"   # PREMIUM
DEMO_PW = "DemoPass123!"
FREE_EMAIL = "freeuser@bigfm.dubai"
FREE_PW = "FreePass123!"


def _login(email, pw):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": pw}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok, f"no token for {email}: {r.text[:200]}"
    return tok


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def demo_token():
    return _login(DEMO_EMAIL, DEMO_PW)


@pytest.fixture(scope="module")
def free_token():
    return _login(FREE_EMAIL, FREE_PW)


@pytest.fixture(scope="module", autouse=True)
def _sponsor_lifecycle(admin_token):
    """Enable sponsor before tests; restore disabled afterwards."""
    enabled_body = {
        "enabled": True,
        "sponsor_name": "Oasis Water",
        "opening_line": "FUUSIC Interactive News is brought to you by Oasis Water.",
        "closing_line": "That was your news, powered by Oasis Water.",
        "opening_enabled": True,
        "closing_enabled": True,
        "mid_enabled": True,
        "mid_line": "Stay refreshed with Oasis Water.",
        "mid_after_segment": 2,
        "premium_ad_free": True,
    }
    r = requests.put(f"{BASE_URL}/api/admin/fun-ai/news-sponsor",
                     json=enabled_body,
                     headers={"Authorization": f"Bearer {admin_token}"},
                     timeout=20)
    assert r.status_code == 200, r.text
    time.sleep(0.3)
    yield
    disabled_body = {
        "enabled": False, "sponsor_name": "", "opening_line": "",
        "closing_line": "", "opening_enabled": True, "closing_enabled": True,
        "mid_enabled": False, "mid_line": "", "mid_after_segment": 3,
        "premium_ad_free": True,
    }
    requests.put(f"{BASE_URL}/api/admin/fun-ai/news-sponsor",
                 json=disabled_body,
                 headers={"Authorization": f"Bearer {admin_token}"},
                 timeout=20)


# --- Memory CRUD -------------------------------------------------------
class TestMemoryCRUD:
    def test_get_memory_defaults(self, demo_token):
        r = requests.get(f"{BASE_URL}/api/fun-ai/memory",
                         headers={"Authorization": f"Bearer {demo_token}"},
                         timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "enabled" in d and isinstance(d["enabled"], bool)
        for k in ("genres", "stations", "disliked", "languages", "interests"):
            assert k in d and isinstance(d[k], list)

    def test_memory_add_remove_persist(self, demo_token):
        H = {"Authorization": f"Bearer {demo_token}"}
        # clear first
        requests.post(f"{BASE_URL}/api/fun-ai/memory/clear", headers=H, timeout=20)

        # ensure enabled
        r = requests.put(f"{BASE_URL}/api/fun-ai/memory", json={"enabled": True},
                         headers=H, timeout=20)
        assert r.status_code == 200 and r.json().get("enabled") is True

        # add
        r = requests.post(f"{BASE_URL}/api/fun-ai/memory",
                          json={"kind": "genres", "value": "Bollywood"},
                          headers=H, timeout=20)
        assert r.status_code == 200
        assert "Bollywood" in r.json().get("genres", [])

        # GET verifies persistence
        g = requests.get(f"{BASE_URL}/api/fun-ai/memory", headers=H, timeout=20).json()
        assert "Bollywood" in g["genres"]

        # remove
        r = requests.post(f"{BASE_URL}/api/fun-ai/memory/remove",
                          json={"kind": "genres", "value": "Bollywood"},
                          headers=H, timeout=20)
        assert r.status_code == 200
        assert "Bollywood" not in r.json().get("genres", [])

    def test_memory_invalid_kind_400(self, demo_token):
        r = requests.post(f"{BASE_URL}/api/fun-ai/memory",
                          json={"kind": "notakind", "value": "foo"},
                          headers={"Authorization": f"Bearer {demo_token}"},
                          timeout=20)
        assert r.status_code == 400

    def test_memory_toggle_off_then_on(self, demo_token):
        H = {"Authorization": f"Bearer {demo_token}"}
        r = requests.put(f"{BASE_URL}/api/fun-ai/memory", json={"enabled": False},
                         headers=H, timeout=20)
        assert r.status_code == 200 and r.json().get("enabled") is False
        r = requests.put(f"{BASE_URL}/api/fun-ai/memory", json={"enabled": True},
                         headers=H, timeout=20)
        assert r.status_code == 200 and r.json().get("enabled") is True

    def test_memory_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/fun-ai/memory", timeout=20)
        assert r.status_code in (401, 403)


# --- Sponsor breaks on briefing ---------------------------------------
class TestBreaks:
    def test_briefing_breaks_for_free_user(self, free_token):
        r = requests.get(f"{BASE_URL}/api/fun-ai/news/briefing?mode=morning_briefing",
                         headers={"Authorization": f"Bearer {free_token}"},
                         timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "breaks" in d, f"breaks missing: {list(d.keys())}"
        breaks = d["breaks"]
        count = int(d.get("count") or 0)
        assert isinstance(breaks, list)
        # If program has content we must see opening + closing at minimum
        if count > 0:
            placements = [b.get("placement") for b in breaks]
            assert "opening" in placements, f"placements={placements}"
            assert "closing" in placements, f"placements={placements}"
            opening = next(b for b in breaks if b["placement"] == "opening")
            closing = next(b for b in breaks if b["placement"] == "closing")
            assert opening.get("after_index") == -1
            assert closing.get("after_index") == count
            assert opening.get("text")
            assert closing.get("text")
            # If mid present, after_index must equal min(mid_after_segment, count-1)
            mids = [b for b in breaks if b.get("placement") == "mid"]
            if mids and count > 1:
                mid_after = mids[0].get("after_index")
                assert 1 <= mid_after <= max(1, count - 1)

    def test_briefing_breaks_premium_adfree(self, demo_token):
        r = requests.get(f"{BASE_URL}/api/fun-ai/news/briefing?mode=morning_briefing",
                         headers={"Authorization": f"Bearer {demo_token}"},
                         timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("breaks") == [], f"premium user should be ad-free, got {d.get('breaks')}"


# --- Break-event impression -------------------------------------------
class TestBreakEvent:
    def test_break_event_impression(self, free_token):
        r = requests.post(f"{BASE_URL}/api/fun-ai/news/break-event",
                          json={"break_id": "opening", "kind": "impression",
                                "placement": "opening"},
                          headers={"Authorization": f"Bearer {free_token}"},
                          timeout=20)
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_break_event_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/fun-ai/news/break-event",
                          json={"break_id": "opening", "kind": "impression"},
                          timeout=20)
        assert r.status_code in (401, 403)
