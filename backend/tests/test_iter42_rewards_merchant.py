"""Iteration 42 — Phase 2/3 AI Reward Engine, Coupon-Fraud, Merchant Loyalty,
Game Frequency Limits. See routes/rewards_merchant.py."""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
load_dotenv("/app/backend/.env")

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

_MONGO = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
_DB = _MONGO[os.environ.get("DB_NAME", "bigfm")]


# ────────────────── auth fixtures ──────────────────
@pytest.fixture(scope="module")
def demo_session():
    r = requests.post(f"{API}/auth/demo", json={}, timeout=20)
    assert r.status_code == 200, r.text
    d = r.json()
    tok = d.get("session_token") or d.get("token") or d.get("access_token")
    uid = (d.get("user") or {}).get("user_id") or d.get("user_id")
    assert tok and uid, d
    return {"token": tok, "user_id": uid,
            "headers": {"Authorization": f"Bearer {tok}",
                        "Content-Type": "application/json"}}


@pytest.fixture(scope="module")
def admin_session(demo_session):
    """Promote demo user to admin for the run, yield an admin session."""
    uid = demo_session["user_id"]
    prev = _DB.users.find_one({"user_id": uid}, {"role": 1}) or {}
    _DB.users.update_one({"user_id": uid}, {"$set": {"role": "admin"}})
    # relogin isn't needed if token derives role live; but many auth impls
    # inline role at issue time. To be safe, hit the same demo endpoint
    # (idempotent by design) and reuse the new token.
    r = requests.post(f"{API}/auth/demo", json={}, timeout=20)
    d = r.json()
    tok = d.get("session_token") or d.get("token") or d.get("access_token")
    yield {"token": tok, "user_id": uid,
           "headers": {"Authorization": f"Bearer {tok}",
                       "Content-Type": "application/json"}}
    if prev.get("role"):
        _DB.users.update_one({"user_id": uid}, {"$set": {"role": prev["role"]}})
    else:
        _DB.users.update_one({"user_id": uid}, {"$unset": {"role": ""}})


@pytest.fixture(scope="module")
def merchant_id():
    return f"m_TEST_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _reset_reward_state(demo_session):
    """Clear rewards + games state so tests are deterministic."""
    uid = demo_session["user_id"]
    _DB.users.update_one({"user_id": uid},
        {"$unset": {"rewards_thresholds_hit": "",
                    "bonus_games_unlocked": "",
                    "concert_pass_eligible": ""}})
    yield


# ────────────────── scan-earn ──────────────────
class TestScanEarn:
    def test_scan_earn_returns_points_multiplier_reason(self, demo_session, merchant_id):
        r = requests.post(f"{API}/rewards/scan-earn",
            headers=demo_session["headers"],
            json={"amount_usd": 20, "merchant_id": merchant_id,
                  "coupon_id": "TEST_c1"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d["points"], int) and d["points"] >= 1
        assert 1.0 <= float(d["multiplier"]) <= 3.0
        assert isinstance(d["reason"], str) and d["reason"]
        assert d["tier"] in ("Bronze", "Silver", "Gold")
        assert "bonuses" in d and "scans_in_window" in d
        assert d.get("show_event_id"), "merchant_id given → show event id"
        # log written
        ev = _DB.coupon_show_events.find_one({"event_id": d["show_event_id"]})
        assert ev and ev["merchant_id"] == merchant_id
        assert ev["redeemed"] is False

    def test_scan_earn_rejects_zero(self, demo_session):
        r = requests.post(f"{API}/rewards/scan-earn",
            headers=demo_session["headers"], json={"amount_usd": 0}, timeout=15)
        assert r.status_code == 400

    def test_scan_earn_logs_scan_earn_events(self, demo_session, merchant_id):
        before = _DB.scan_earn_events.count_documents({"user_id": demo_session["user_id"]})
        r = requests.post(f"{API}/rewards/scan-earn",
            headers=demo_session["headers"],
            json={"amount_usd": 5, "merchant_id": merchant_id}, timeout=30)
        assert r.status_code == 200
        after = _DB.scan_earn_events.count_documents({"user_id": demo_session["user_id"]})
        assert after == before + 1


# ────────────────── threshold bonuses ──────────────────
class TestThresholds:
    def test_threshold_bonus_grants_once_and_unlocks(self, demo_session, admin_session, merchant_id):
        # Configure a small threshold so we can hit it deterministically
        cfg_body = {
            "base_points_per_dollar": 1.0,
            "min_multiplier": 1.0, "max_multiplier": 1.0,  # deterministic
            "thresholds": [
                {"points": 25, "bonus_points": 7,
                 "unlock_bonus_games": True, "concert_pass": True},
            ],
        }
        r = requests.put(f"{API}/rewards/config",
            headers=admin_session["headers"], json=cfg_body, timeout=15)
        assert r.status_code == 200

        # zero lifetime baseline
        _DB.users.update_one({"user_id": demo_session["user_id"]},
            {"$set": {"bigcoin_lifetime": 0, "bigcoin_balance": 0,
                      "rewards_thresholds_hit": []}})

        r = requests.post(f"{API}/rewards/scan-earn",
            headers=demo_session["headers"],
            json={"amount_usd": 30, "merchant_id": merchant_id}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        b = d.get("bonuses") or {}
        assert b.get("bonus_points", 0) >= 7, d
        assert b.get("bonus_games_unlocked") is True, d
        assert b.get("concert_pass") is True, d

        # idempotent — second call, no bonus
        r2 = requests.post(f"{API}/rewards/scan-earn",
            headers=demo_session["headers"],
            json={"amount_usd": 30, "merchant_id": merchant_id}, timeout=30)
        assert r2.status_code == 200
        b2 = r2.json().get("bonuses") or {}
        assert b2.get("bonus_points", 0) == 0, r2.json()

        u = _DB.users.find_one({"user_id": demo_session["user_id"]})
        assert u.get("bonus_games_unlocked") is True
        assert u.get("concert_pass_eligible") is True
        assert 25 in (u.get("rewards_thresholds_hit") or [])

        # restore permissive config
        requests.put(f"{API}/rewards/config",
            headers=admin_session["headers"],
            json={"min_multiplier": 1.0, "max_multiplier": 3.0,
                  "thresholds": []}, timeout=15)


# ────────────────── coupon show + merchant redeem + admin fraud ──────────────────
class TestCouponAndRedeem:
    def test_coupon_show_logs(self, demo_session, merchant_id):
        r = requests.post(f"{API}/coupon-events/show",
            headers=demo_session["headers"],
            json={"merchant_id": merchant_id, "coupon_id": "TEST_c2",
                  "kind": "coupon"}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] and d["event_id"].startswith("cev_")
        assert _DB.coupon_show_events.find_one({"event_id": d["event_id"]})["redeemed"] is False

    def test_merchant_redeem_matches_show(self, demo_session, merchant_id):
        # Fresh show
        show = requests.post(f"{API}/coupon-events/show",
            headers=demo_session["headers"],
            json={"merchant_id": merchant_id, "coupon_id": "TEST_c3",
                  "kind": "coupon"}, timeout=15).json()
        assert show["event_id"]

        r = requests.post(f"{API}/merchant/redeem",
            headers=demo_session["headers"],
            json={"merchant_id": merchant_id,
                  "coupon_id": "TEST_c3",
                  "user_id": demo_session["user_id"]}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["matched_show_event"] is True
        loy = d["loyalty"]
        assert loy["merchant_id"] == merchant_id
        assert loy["redemptions_today"] >= 1
        assert loy["tier"] and isinstance(loy["rate"], (int, float))

        # Confirm the show was flipped to redeemed
        ev = _DB.coupon_show_events.find_one({"event_id": show["event_id"]})
        assert ev["redeemed"] is True

    def test_merchant_loyalty_endpoint(self, demo_session, merchant_id):
        r = requests.get(f"{API}/merchant/loyalty?merchant_id={merchant_id}",
            headers=demo_session["headers"], timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["merchant_id"] == merchant_id
        assert "redemptions_today" in d
        assert d["tier"] in ("Standard", "Silver", "Gold")
        assert isinstance(d["rate"], (int, float))
        # next_tier is None only when already Gold; usually a dict
        assert d.get("next_tier") is None or "min_daily" in d["next_tier"]

    def test_admin_coupon_fraud_report(self, admin_session, demo_session, merchant_id):
        # Create a merchant with lots of shows but no redemptions (fraud signal)
        fraud_mid = f"m_TEST_FRAUD_{uuid.uuid4().hex[:6]}"
        for _ in range(6):
            requests.post(f"{API}/coupon-events/show",
                headers=demo_session["headers"],
                json={"merchant_id": fraud_mid, "coupon_id": "TEST_x",
                      "kind": "coupon"}, timeout=15)

        r = requests.get(f"{API}/admin/coupon-fraud?min_shows=5&flag_rate=0.5",
            headers=admin_session["headers"], timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("items"), list) and d["total"] >= 1
        match = next((x for x in d["items"] if x["merchant_id"] == fraud_mid), None)
        assert match, f"fraud merchant missing from report: {d}"
        assert match["shows"] >= 6
        assert match["redemptions"] == 0
        assert match["unredeemed"] >= 6
        assert match["flagged"] is True


# ────────────────── admin: reward config & game limits ──────────────────
class TestAdminConfig:
    def test_get_and_put_reward_config_roundtrip(self, admin_session):
        r = requests.get(f"{API}/rewards/config",
            headers=admin_session["headers"], timeout=15)
        assert r.status_code == 200
        cfg = r.json()
        for k in ("base_points_per_dollar", "min_multiplier",
                  "max_multiplier", "thresholds", "merchant_tiers"):
            assert k in cfg, cfg

        r = requests.put(f"{API}/rewards/config",
            headers=admin_session["headers"],
            json={"base_points_per_dollar": 1.5}, timeout=15)
        assert r.status_code == 200
        assert r.json()["base_points_per_dollar"] == 1.5
        # restore
        requests.put(f"{API}/rewards/config",
            headers=admin_session["headers"],
            json={"base_points_per_dollar": 1.0}, timeout=15)

    def test_reward_config_requires_admin(self):
        # Unauthenticated request should be rejected (not a role check on demo,
        # since our demo fixture is promoted to admin for this module).
        r = requests.get(f"{API}/rewards/config", timeout=15)
        assert r.status_code in (401, 403), r.text


# ────────────────── game frequency limits ──────────────────
class TestGameLimits:
    def test_put_limit_and_eligibility_and_record_play(self, admin_session, demo_session):
        game_key = "daily_spin"
        # Clear prior plays for a clean count
        _DB.game_plays.delete_many({"user_id": demo_session["user_id"],
                                    "game_key": game_key})
        # Set cap = 2 per day
        r = requests.put(f"{API}/games/limits",
            headers=admin_session["headers"],
            json={"game_key": game_key, "max_plays": 2, "period": "day",
                  "enabled": True}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["ok"] is True

        # eligibility fresh → 0/2 eligible
        r = requests.get(f"{API}/games/play-eligibility/{game_key}",
            headers=demo_session["headers"], timeout=15)
        assert r.status_code == 200
        e = r.json()
        assert e["eligible"] is True
        assert e["plays_used"] == 0 and e["max_plays"] == 2

        # play twice
        for i in range(2):
            r = requests.post(f"{API}/games/record-play",
                headers=demo_session["headers"],
                json={"game_key": game_key}, timeout=15)
            assert r.status_code == 200, (i, r.text)

        # third should 429
        r = requests.post(f"{API}/games/record-play",
            headers=demo_session["headers"],
            json={"game_key": game_key}, timeout=15)
        assert r.status_code == 429, r.text
        detail = r.json().get("detail") or {}
        # HTTPException wraps into 'detail'
        assert (detail.get("code") == "play_limit_reached") or (
            "play_limit_reached" in str(r.json()))

    def test_admin_game_limits_list(self, admin_session):
        r = requests.get(f"{API}/games/limits",
            headers=admin_session["headers"], timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)
