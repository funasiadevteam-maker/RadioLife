"""Iteration 175 backend sanity: scratch play, wheel config for scratch_house, dream reflect + suggested-advisor."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}


@pytest.fixture(scope="module")
def token():
    # Mobile auth uses bearer via /api/auth/demo, but demo login endpoint works too
    r = requests.post(f"{API}/auth/demo", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    tok = d.get("session_token") or d.get("token")
    assert tok, f"no token in demo response: {list(d.keys())}"
    return tok


@pytest.fixture(scope="module")
def hdr(token):
    return {"Authorization": f"Bearer {token}"}


def test_scratch_config(hdr):
    r = requests.get(f"{API}/games/wheel/config?game_id=scratch_house", headers=hdr, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["game_id"] == "scratch_house"
    assert d["game_type"] == "scratch"
    assert "spins_left" in d
    assert isinstance(d["segments"], list) and len(d["segments"]) > 0


def test_scratch_play(hdr):
    r = requests.post(f"{API}/games/scratch/play", json={"game_id": "scratch_house"}, headers=hdr, timeout=15)
    if r.status_code == 429:
        # out of cards is acceptable
        body = r.json()
        assert "no_spins_left" in str(body)
        pytest.skip("Out of cards for the day - expected 429")
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("tiles", "win", "prize", "spins_left", "balance"):
        assert k in d, f"missing {k} in {d}"
    assert isinstance(d["tiles"], list) and len(d["tiles"]) == 3
    assert isinstance(d["win"], bool)
    # win iff all 3 tiles match
    if d["win"]:
        assert d["tiles"][0] == d["tiles"][1] == d["tiles"][2]
    else:
        assert not (d["tiles"][0] == d["tiles"][1] == d["tiles"][2])


def test_dream_reflect_and_suggested_advisor(hdr):
    # create a dream with tags likely to match advisor category
    payload = {
        "title": "Flying dream test",
        "description": "I was flying above the ocean and could see everything below.",
        "mood": "Peaceful",
        "tags": ["Flying", "Water"],
        "visibility": "public",
        "anonymous": False,
    }
    r = requests.post(f"{API}/social/dreams", json=payload, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    did = r.json()["dream_id"]

    # request reflection
    r2 = requests.post(f"{API}/social/dreams/{did}/reflect", headers=hdr, timeout=45)
    assert r2.status_code == 200, r2.text
    ref = r2.json()["ai_reflection"]
    assert "header" in ref
    assert "symbolic_readings" in ref

    # request suggested advisor
    r3 = requests.get(f"{API}/social/dreams/{did}/suggested-advisor", headers=hdr, timeout=15)
    assert r3.status_code == 200, r3.text
    body = r3.json()
    # advisor may be None if none approved — accept both shapes
    if body.get("advisor"):
        for k in ("reason", "category", "category_label"):
            assert k in body
        assert body["advisor"].get("advisor_id")
        assert body["advisor"].get("display_name")
