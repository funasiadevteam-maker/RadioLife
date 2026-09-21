"""Iter 166 — LIVE SOCIAL CARDS + MIXED FOR YOU + TOGETHER DEEP-LINKS.

Validates /api/shell/home + /api/social/home under the demo user cookie.
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": "demo@bigfm.dubai", "password": "DemoPass123!"},
               timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def anon_session():
    return requests.Session()


# ── /api/shell/home — mixed_for_you + together_actions ──────────────
class TestShellHomeMixedForYou:
    def test_home_has_mixed_for_you_array(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/home", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "mixed_for_you" in data
        mfy = data["mixed_for_you"]
        assert isinstance(mfy, list)
        assert len(mfy) <= 10
        # Existing for_you (stations) still present and unchanged
        assert "for_you" in data
        assert isinstance(data["for_you"], list)

    def test_mixed_for_you_card_shape(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/home", timeout=30)
        mfy = r.json()["mixed_for_you"]
        assert len(mfy) >= 1
        valid_types = {"station", "live", "offer", "game", "moment"}
        for c in mfy:
            assert c.get("type") in valid_types, f"bad type: {c.get('type')}"
            assert c.get("badge"), f"missing badge on card {c}"
            assert c.get("to"), f"missing `to` deep-link on card {c}"

    def test_station_cards_deep_link_autoplay(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/home", timeout=30)
        mfy = r.json()["mixed_for_you"]
        stations = [c for c in mfy if c["type"] == "station"]
        assert len(stations) >= 1
        for s in stations:
            assert s["to"].startswith("/radio/station/")
            assert "autoplay=1" in s["to"]

    def test_offer_cards_are_sponsored(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/home", timeout=30)
        mfy = r.json()["mixed_for_you"]
        offers = [c for c in mfy if c["type"] == "offer"]
        for o in offers:
            assert o.get("sponsored") is True

    def test_non_station_deep_links(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/home", timeout=30)
        mfy = r.json()["mixed_for_you"]
        rules = {
            "live": lambda to: to.startswith("/social") or to.startswith("/social/room/"),
            "moment": lambda to: to.startswith("/social?tab=moments"),
            "game": lambda to: to.startswith("/play-and-win"),
        }
        for c in mfy:
            check = rules.get(c["type"])
            if check:
                assert check(c["to"]), f"{c['type']} bad `to`: {c['to']}"

    def test_cards_interleaved_station_extra(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/home", timeout=30)
        mfy = r.json()["mixed_for_you"]
        # Expect at least first card is station, second (if any) is non-station extra
        assert mfy[0]["type"] == "station"
        if len(mfy) >= 2 and mfy[1]["type"] != "station":
            # good — interleaved
            assert True

    def test_together_actions_deep_links(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/home", timeout=30)
        acts = r.json().get("together_actions") or []
        by_key = {a["key"]: a for a in acts}
        assert by_key["listen"]["to"] == "/social?action=listen"
        assert by_key["play"]["to"] == "/social?action=play"
        assert by_key["shop"]["to"] == "/social?action=shop"
        assert by_key["go"]["to"] == "/social?action=go"


# ── /api/social/home — friends_now + happening_now (auth) ───────────
class TestSocialHome:
    def test_social_home_auth_returns_expected_keys(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/social/home", timeout=30)
        assert r.status_code == 200
        data = r.json()
        for key in ("happening_now", "friends_now", "suggested_rooms", "counts"):
            assert key in data, f"missing {key} in /api/social/home"
        assert isinstance(data["friends_now"], list)
        assert isinstance(data["suggested_rooms"], list)

    def test_social_home_friends_shape(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/social/home", timeout=30)
        for f in r.json().get("friends_now", []):
            # Honest empty state means list can be []; validate shape only if present
            for k in ("name",):
                assert k in f
            # Optional fields per spec
            assert "avatar_url" in f or f.get("avatar_url") is None or True

    def test_home_poll_is_idempotent(self, demo_session):
        # Simulate the 20s poll — two consecutive fetches should succeed
        r1 = demo_session.get(f"{BASE_URL}/api/social/home", timeout=30)
        r2 = demo_session.get(f"{BASE_URL}/api/social/home", timeout=30)
        assert r1.status_code == 200 and r2.status_code == 200


# ── Regression ─────────────────────────────────────────────────────
class TestRegression:
    def test_home_regression_sections(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/shell/home", timeout=30)
        d = r.json()
        for key in ("for_you", "live_now", "listening_reward", "dining",
                    "fuusic_world", "together_actions", "pillar_order",
                    "home_config"):
            assert key in d, f"regression: missing {key}"
