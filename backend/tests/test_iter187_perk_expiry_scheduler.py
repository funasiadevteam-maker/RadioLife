"""Iteration 187 — ENH: Perk Expiry (wallet) + Owner Live Scheduler (bar).

Backend-only smoke pass. Uses cookie auth on the public preview URL.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
DEMO = {"email": "demo@bigfm.dubai", "password": "DemoPass123!"}
FREE = {"email": "freeuser@bigfm.dubai", "password": "FreePass123!"}
BAR_ID = "biz_demo_bar"


def _login(creds: dict) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def demo():
    return _login(DEMO)


@pytest.fixture(scope="module")
def free():
    return _login(FREE)


# ── Perk Expiry — GET /api/bar-games/wallet ──────────────────────────
class TestPerkExpiry:
    def test_wallet_shape_and_seeded_perk(self, demo):
        r = demo.get(f"{BASE_URL}/api/bar-games/wallet", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert "active" in data
        for it in data["items"]:
            assert "expires_at" in it
            assert "expired" in it
            assert isinstance(it["expired"], bool)
        # Seeded fresh perk BAR-NEON2FOR expected
        codes = [i.get("code") for i in data["items"]]
        assert "BAR-NEON2FOR" in codes, f"seeded perk missing; got={codes}"

    def test_active_excludes_expired_and_redeemed(self, demo):
        r = demo.get(f"{BASE_URL}/api/bar-games/wallet", timeout=15)
        d = r.json()
        expected_active = sum(1 for i in d["items"] if not i["redeemed"] and not i["expired"])
        assert d["active"] == expected_active

    def test_expired_perk_returns_400(self, demo):
        """Insert an expired play doc for demo user and confirm redeem returns 400."""
        mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = mongo[os.environ.get("DB_NAME", "bigfm")]
        # Look up demo user_id
        u = db.users.find_one({"email": DEMO["email"]}, {"user_id": 1})
        assert u
        play_id = f"bgp_test_{uuid.uuid4().hex[:8]}"
        past = datetime.now(timezone.utc) - timedelta(days=1)
        db.bar_game_plays.insert_one({
            "_id": play_id,
            "user_id": u["user_id"],
            "business_id": BAR_ID,
            "business_name": "Neon Nights Bar",
            "segment_index": 0,
            "label": "TEST_expired_perk",
            "emoji": "🍸",
            "win": True,
            "code": "BAR-TESTEXP",
            "redeemed": False,
            "expires_at": past,
            "created_at": past - timedelta(days=14),
        })
        try:
            # Wallet lists it as expired
            r = demo.get(f"{BASE_URL}/api/bar-games/wallet", timeout=15)
            item = next((i for i in r.json()["items"] if i["play_id"] == play_id), None)
            assert item is not None
            assert item["expired"] is True
            # Redeem must 400 with perk_expired code
            r2 = demo.post(f"{BASE_URL}/api/bar-games/plays/{play_id}/redeem", timeout=15)
            assert r2.status_code == 400, f"expected 400, got {r2.status_code} {r2.text}"
            body = r2.json()
            detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
            assert (detail or {}).get("code") == "perk_expired", body
        finally:
            db.bar_game_plays.delete_one({"_id": play_id})


# ── Owner Live Scheduler ──────────────────────────────────────────────
class TestOwnerLiveScheduler:
    def test_owner_creates_scheduled_show_and_pins_products(self, demo):
        when = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat()
        payload = {
            "title": "TEST_Scheduled Friday Cocktail Night",
            "description": "Automated test event",
            "business_name": "Neon Nights Bar",
            "scheduled_at": when,
        }
        r = demo.post(f"{BASE_URL}/api/social/liveshows", json=payload, timeout=15)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        show = r.json()
        sid = show.get("show_id") or show.get("id")
        assert sid, show

        # Pin a product
        prod = {"title": "TEST_Cocktail Kit", "price_cents": 4500, "offer": "-20%", "image_url": None}
        r2 = demo.post(f"{BASE_URL}/api/social/liveshows/{sid}/products", json=prod, timeout=15)
        assert r2.status_code in (200, 201), f"{r2.status_code} {r2.text}"

        # Show appears in ?status=scheduled
        r3 = demo.get(f"{BASE_URL}/api/social/liveshows?status=scheduled", timeout=15)
        assert r3.status_code == 200
        body = r3.json()
        shows = body if isinstance(body, list) else body.get("items", body.get("shows", []))
        ids = [(s.get("show_id") or s.get("id")) for s in shows]
        assert sid in ids, f"scheduled show not in list; got={ids[:10]}"

        # Clean up
        mongo = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
        db = mongo[os.environ.get("DB_NAME", "bigfm")]
        db.live_shows.delete_one({"show_id": sid})
        db.live_show_products.delete_many({"show_id": sid})

    def test_owner_flag_is_true_for_demo(self, demo):
        r = demo.get(f"{BASE_URL}/api/bar-games/{BAR_ID}", timeout=15)
        assert r.status_code == 200
        assert r.json().get("is_owner") is True

    def test_owner_flag_is_false_for_free(self, free):
        r = free.get(f"{BASE_URL}/api/bar-games/{BAR_ID}", timeout=15)
        assert r.status_code == 200
        assert r.json().get("is_owner") is False
