"""Iteration 118 — POST /api/radio/feedback (like / less / bad action / auth)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "test@bigfm.dubai"
DEMO_PASS = "TestUser123!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code} {r.text[:200]}")
    return s


# ---------- happy paths ----------
def test_like_adds_favorite_artist(session):
    r = session.post(f"{API}/radio/feedback",
                     json={"action": "like", "track_artist": "TEST_ARTIST_A", "genre": "pop"},
                     timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["action"] == "like"
    assert isinstance(body["favorite_artists"], int)
    assert body["favorite_artists"] >= 1


def test_less_moves_to_disliked(session):
    # like first to seed
    session.post(f"{API}/radio/feedback",
                 json={"action": "like", "track_artist": "TEST_ARTIST_B"}, timeout=15)
    r = session.post(f"{API}/radio/feedback",
                     json={"action": "less", "track_artist": "TEST_ARTIST_B"}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["action"] == "less"
    assert body["disliked_artists"] >= 1


def test_persistence_via_me(session):
    session.post(f"{API}/radio/feedback",
                 json={"action": "like", "track_artist": "TEST_ARTIST_C"}, timeout=15)
    r = session.get(f"{API}/auth/me", timeout=15)
    assert r.status_code == 200
    pv = (r.json() or {}).get("preference_vector") or {}
    favs = [a.lower() for a in (pv.get("favorite_artists") or [])]
    assert "test_artist_c" in favs


# ---------- validation / auth ----------
def test_bad_action_returns_400(session):
    r = session.post(f"{API}/radio/feedback",
                     json={"action": "boost", "track_artist": "TEST_ARTIST_X"}, timeout=15)
    assert r.status_code == 400, r.text
    body = r.json()
    # FastAPI wraps HTTPException(detail=dict) as {"detail": {...}}
    detail = body.get("detail") if isinstance(body, dict) else None
    assert (detail == {"code": "bad_action"}) or (body == {"code": "bad_action"})


def test_requires_auth():
    r = requests.post(f"{API}/radio/feedback",
                      json={"action": "like", "track_artist": "TEST_ARTIST_Y"}, timeout=15)
    assert r.status_code in (401, 403)
