"""MILESTONE 2 — Following ecosystem tests.

Covers:
- Who-to-Follow aggregated suggestions + reasons + actor_type filter.
- Suggestion dismissal (not_interested/hide) → suggestion never returns.
- Follow IMPORTED catalog station (imp_fun_talk_1003_uae) → appears in
  /social/following under 'stations' with station_kind='imported', then
  unfollow removes it.  /follow/status reflects state.
- M1 regression: moments post + feed-v2 'following' shows own post is_mine;
  wall like/save/share persist.
"""
import os
import time
import uuid
import pytest
import requests

def _read_env_backend():
    import pathlib
    for p in ("/app/frontend/.env", "/app/mobile/.env"):
        try:
            for line in pathlib.Path(p).read_text().splitlines():
                if "BACKEND_URL" in line and "=" in line:
                    v = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if v.startswith("http"):
                        return v
        except Exception:
            continue
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _read_env_backend() or "").rstrip("/")
assert BASE_URL, "BACKEND URL not found"
API = f"{BASE_URL}/api"

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
FREE_EMAIL = "freeuser@bigfm.dubai"
FREE_PASS = "FreePass123!"
IMPORTED_STATION_ID = "imp_fun_talk_1003_uae"


def _login(email, password):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo_client():
    return _login(DEMO_EMAIL, DEMO_PASS)


@pytest.fixture(scope="module")
def free_client():
    return _login(FREE_EMAIL, FREE_PASS)


# ──────────────────────────────────────────────────────────────────
# WHO-TO-FOLLOW
# ──────────────────────────────────────────────────────────────────
class TestWhoToFollow:
    def test_who_to_follow_returns_interleaved_suggestions(self, demo_client):
        r = demo_client.get(f"{API}/social/who-to-follow?limit=12", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        items = data["items"]
        assert len(items) > 0, "expected at least some suggestions for demo"
        # each item has required fields
        for it in items:
            for k in ("actor_type", "actor_id", "name", "avatar_url", "reason"):
                assert k in it, f"missing {k} in suggestion {it}"
            assert it["actor_type"] in {"person", "station", "advisor", "business", "club"}
            assert isinstance(it["reason"], str) and len(it["reason"]) > 0
        # interleaved: at least 2 distinct actor_types across the first 6 items
        kinds = {it["actor_type"] for it in items[:6]}
        assert len(kinds) >= 2, f"expected interleaved mix, got {kinds}"

    def test_who_to_follow_actor_type_filter_station(self, demo_client):
        r = demo_client.get(f"{API}/social/who-to-follow?limit=8&actor_type=station", timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) > 0, "expected station suggestions"
        for it in items:
            assert it["actor_type"] == "station"

    def test_freeuser_still_gets_suggestions(self, free_client):
        r = free_client.get(f"{API}/social/who-to-follow?limit=12", timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert len(items) >= 5, f"freeuser should see suggestions, got {len(items)}"

    def test_dismiss_not_interested_removes_from_subsequent_call(self, demo_client):
        # Get a station suggestion we can safely dismiss
        r = demo_client.get(f"{API}/social/who-to-follow?limit=20&actor_type=station", timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert items, "need at least one station suggestion to dismiss"
        target = items[0]
        actor_id = target["actor_id"]

        # Dismiss
        d = demo_client.post(f"{API}/social/suggestions/dismiss",
                             json={"actor_type": "station", "actor_id": actor_id,
                                   "action": "not_interested"}, timeout=30)
        assert d.status_code == 200, d.text[:300]
        assert d.json().get("ok") is True

        # Re-fetch — must NOT contain the dismissed id
        r2 = demo_client.get(f"{API}/social/who-to-follow?limit=40&actor_type=station", timeout=30)
        ids = [it["actor_id"] for it in r2.json().get("items", [])]
        assert actor_id not in ids, f"dismissed {actor_id} reappeared in suggestions"

    def test_dismiss_hide_action_also_works(self, demo_client):
        r = demo_client.get(f"{API}/social/who-to-follow?limit=20&actor_type=club", timeout=30)
        items = r.json().get("items", [])
        if not items:
            pytest.skip("no club suggestions available for hide test")
        tgt = items[0]
        d = demo_client.post(f"{API}/social/suggestions/dismiss",
                             json={"actor_type": "club", "actor_id": tgt["actor_id"],
                                   "action": "hide"}, timeout=30)
        assert d.status_code == 200
        r2 = demo_client.get(f"{API}/social/who-to-follow?limit=40&actor_type=club", timeout=30)
        ids = [it["actor_id"] for it in r2.json().get("items", [])]
        assert tgt["actor_id"] not in ids


# ──────────────────────────────────────────────────────────────────
# IMPORTED STATION FOLLOW
# ──────────────────────────────────────────────────────────────────
class TestImportedStationFollow:
    def test_follow_imported_station_then_appears_in_following(self, free_client):
        # Ensure a clean slate: unfollow first (idempotent)
        free_client.post(f"{API}/stations/{IMPORTED_STATION_ID}/unfollow", timeout=30)

        # Status should be false
        s0 = free_client.get(f"{API}/stations/{IMPORTED_STATION_ID}/follow/status", timeout=30)
        assert s0.status_code == 200
        assert s0.json().get("following") is False

        # Follow the imported catalog station
        f = free_client.post(f"{API}/stations/{IMPORTED_STATION_ID}/follow", timeout=30)
        assert f.status_code == 200, f.text[:300]
        body = f.json()
        assert body.get("ok") is True
        assert body.get("now_following") is True

        # Status should now be true
        s1 = free_client.get(f"{API}/stations/{IMPORTED_STATION_ID}/follow/status", timeout=30)
        assert s1.json().get("following") is True

        # Appears in /api/social/following under 'stations' with station_kind='imported'
        g = free_client.get(f"{API}/social/following", timeout=30)
        assert g.status_code == 200, g.text[:300]
        gdata = g.json()
        assert "stations" in gdata
        match = [s for s in gdata["stations"] if s.get("station_id") == IMPORTED_STATION_ID]
        assert match, f"imported station {IMPORTED_STATION_ID} not in following.stations"
        assert match[0].get("station_kind") == "imported"
        assert match[0].get("name"), "imported station missing name"

    def test_unfollow_imported_station_removes_it(self, free_client):
        u = free_client.post(f"{API}/stations/{IMPORTED_STATION_ID}/unfollow", timeout=30)
        assert u.status_code == 200
        assert u.json().get("now_following") is False
        s = free_client.get(f"{API}/stations/{IMPORTED_STATION_ID}/follow/status", timeout=30)
        assert s.json().get("following") is False
        g = free_client.get(f"{API}/social/following", timeout=30)
        ids = [s.get("station_id") for s in g.json().get("stations", [])]
        assert IMPORTED_STATION_ID not in ids

    def test_follow_nonexistent_station_404s(self, free_client):
        r = free_client.post(f"{API}/stations/does_not_exist_xyz_123/follow", timeout=30)
        assert r.status_code == 404


# ──────────────────────────────────────────────────────────────────
# M1 REGRESSION — moments post, feed-v2 following, wall actions
# ──────────────────────────────────────────────────────────────────
class TestM1Regression:
    def test_post_moment_and_appears_in_feed_v2(self, demo_client):
        marker = f"TEST_M2_{uuid.uuid4().hex[:8]}"
        body = {"caption": f"hello FUUSIC {marker}", "visibility": "public"}
        r = demo_client.post(f"{API}/social/moments", json=body, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        resp = r.json()
        post_id = resp.get("moment_id") or resp.get("id") or resp.get("post_id") or resp.get("mid") or resp.get("_id")
        time.sleep(0.6)
        f = demo_client.get(f"{API}/social/feed-v2?mode=following&limit=30", timeout=30)
        assert f.status_code == 200, f.text[:300]
        items = f.json().get("items") or f.json().get("posts") or []
        # Match by marker in any text/caption/body field
        found = next((it for it in items
                      if marker in (it.get("caption") or it.get("text") or it.get("body") or "")),
                     None)
        assert found, f"posted moment with marker {marker} not seen in feed-v2 following (n={len(items)})"
        assert found.get("is_mine") in (True, 1), f"own post should flag is_mine, got {found.get('is_mine')}"

    def test_wall_like_save_share_persist(self, demo_client):
        # Create a moment to act on
        marker = f"TEST_M2_ACT_{uuid.uuid4().hex[:6]}"
        r = demo_client.post(f"{API}/social/moments",
                             json={"caption": marker, "visibility": "public"}, timeout=30)
        assert r.status_code in (200, 201), r.text[:300]
        resp = r.json()
        mid = resp.get("moment_id") or resp.get("id") or resp.get("post_id") or resp.get("mid") or resp.get("_id")
        assert mid
        item_id = f"MOMENT:{mid}"

        for action in ("like", "save", "share"):
            a = demo_client.post(f"{API}/social/wall/{action}",
                                 json={"item_id": item_id}, timeout=30)
            assert a.status_code == 200, f"{action} failed: {a.status_code} {a.text[:200]}"
            adata = a.json()
            assert adata.get("ok") is True
            if action == "like":
                assert adata.get("liked") is True
            if action == "save":
                assert adata.get("saved") is True
            if action == "share":
                assert adata.get("shared") is True
                assert int(adata.get("share_count") or 0) >= 1
