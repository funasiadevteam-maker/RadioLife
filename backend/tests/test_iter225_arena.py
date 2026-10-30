"""Iter 225 — Arena (play-with-friends challenges + leaderboard) backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
FREE = {"email": "freeuser@bigfm.dubai", "password": "FreePass123!"}
FREE_UID = "user_b1106f71a18042bb"


def _login(creds):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=creds, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    j = r.json()
    # web uses cookie; also expose token header for mobile-style calls
    tok = j.get("session_token")
    if tok:
        s.headers.update({"Authorization": f"Bearer {tok}"})
    return s, j


@pytest.fixture(scope="module")
def demo_session():
    s, j = _login(DEMO)
    yield s, j


@pytest.fixture(scope="module")
def free_session():
    s, j = _login(FREE)
    yield s, j


# ── games catalogue ─────────────────────────────────────────────────
def test_games_catalogue(demo_session):
    s, _ = demo_session
    r = s.get(f"{API}/arena/games", timeout=15)
    assert r.status_code == 200, r.text
    games = r.json().get("games") or []
    keys = {g["key"] for g in games}
    assert {"trivia", "quiz"}.issubset(keys)


# ── validation errors ──────────────────────────────────────────────
def test_create_h2h_needs_one(demo_session):
    s, _ = demo_session
    r = s.post(f"{API}/arena/challenges",
               json={"game_key": "trivia", "mode": "h2h", "invitees": []}, timeout=15)
    assert r.status_code == 400
    body = r.json()
    assert "h2h_needs_one" in str(body)


def test_create_group_needs_two(demo_session):
    s, _ = demo_session
    r = s.post(f"{API}/arena/challenges",
               json={"game_key": "trivia", "mode": "group", "invitees": [FREE_UID]}, timeout=15)
    assert r.status_code == 400
    assert "group_needs_two" in str(r.json())


def test_create_unknown_game(demo_session):
    s, _ = demo_session
    r = s.post(f"{API}/arena/challenges",
               json={"game_key": "nope", "mode": "h2h", "invitees": [FREE_UID]}, timeout=15)
    assert r.status_code == 400


# ── end-to-end h2h flow ────────────────────────────────────────────
@pytest.fixture(scope="module")
def h2h_challenge(demo_session):
    s, _ = demo_session
    r = s.post(f"{API}/arena/challenges",
               json={"game_key": "trivia", "mode": "h2h", "invitees": [FREE_UID],
                     "title": "TEST_iter225 Arena"}, timeout=15)
    assert r.status_code == 200, r.text
    ch = r.json()
    assert ch["mode"] == "h2h"
    assert ch["status"] == "active"
    assert ch["is_host"] is True
    assert ch["question_count"] == 5
    return ch


def test_h2h_created(h2h_challenge):
    assert h2h_challenge["id"].startswith("ch_")
    assert h2h_challenge["prize_points"] >= 10


def test_invitee_sees_in_invites(h2h_challenge, free_session):
    s, _ = free_session
    r = s.get(f"{API}/arena/challenges", timeout=15)
    assert r.status_code == 200
    data = r.json()
    ids = {c["id"] for c in data["invites"]}
    assert h2h_challenge["id"] in ids


def test_quiz_no_leak_correct(h2h_challenge, demo_session):
    s, _ = demo_session
    r = s.get(f"{API}/arena/challenges/{h2h_challenge['id']}/quiz", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert len(body["questions"]) == 5
    for q in body["questions"]:
        assert "correct" not in q  # must NOT leak


def test_premature_finalize_blocked(h2h_challenge, demo_session):
    # Host submits before invitee accepts -> should not finalize (new behavior).
    s, _ = demo_session
    r = s.post(f"{API}/arena/challenges/{h2h_challenge['id']}/submit",
               json={"answers": [1, 2, 1, 3, 1], "time_ms": 12000}, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["finalized"] is False, "must wait for invitee"
    assert body["challenge"]["status"] == "active"


def test_invitee_accept_and_submit_finalizes(h2h_challenge, free_session):
    s, _ = free_session
    cid = h2h_challenge["id"]
    r = s.post(f"{API}/arena/challenges/{cid}/accept", timeout=15)
    assert r.status_code == 200, r.text
    ch = r.json()
    # after accept, user removed from invitees, added to participants
    pids = {p["user_id"] for p in ch.get("participants", [])}
    assert FREE_UID in pids
    inv_ids = {p["user_id"] for p in ch.get("invitees", [])}
    assert FREE_UID not in inv_ids

    # Now fetch quiz & submit (all correct for cleanliness).
    rq = s.get(f"{API}/arena/challenges/{cid}/quiz", timeout=15)
    assert rq.status_code == 200
    # answer deterministically — we don't know correct, so just submit all 0s
    r2 = s.post(f"{API}/arena/challenges/{cid}/submit",
                json={"answers": [0, 0, 0, 0, 0], "time_ms": 8000}, timeout=15)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["finalized"] is True, "both submitted + 2 participants + no pending invites"
    ch = body["challenge"]
    assert ch["status"] == "completed"
    assert ch.get("winner_id") is not None
    sb = ch.get("scoreboard") or []
    assert len(sb) == 2


# ── listing buckets ────────────────────────────────────────────────
def test_list_buckets(h2h_challenge, demo_session):
    s, _ = demo_session
    r = s.get(f"{API}/arena/challenges", timeout=15)
    assert r.status_code == 200
    d = r.json()
    completed_ids = {c["id"] for c in d["completed"]}
    assert h2h_challenge["id"] in completed_ids


# ── /score + leaderboard ───────────────────────────────────────────
def test_submit_score_feeds_leaderboard(demo_session):
    s, _ = demo_session
    r = s.post(f"{API}/arena/score", json={"game_key": "trivia", "score": 123}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_leaderboard_global(demo_session):
    s, _ = demo_session
    r = s.get(f"{API}/arena/leaderboard?scope=global&game_key=all", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "global"
    assert "items" in body
    assert isinstance(body["items"], list)


def test_leaderboard_friends(demo_session):
    s, _ = demo_session
    r = s.get(f"{API}/arena/leaderboard?scope=friends&game_key=trivia", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["scope"] == "friends"
    assert body["game_key"] == "trivia"


def test_leaderboard_per_game_quiz(demo_session):
    s, _ = demo_session
    r = s.get(f"{API}/arena/leaderboard?scope=global&game_key=quiz", timeout=15)
    assert r.status_code == 200
    assert r.json()["game_key"] == "quiz"
