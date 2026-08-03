"""Phase AD.8 — Daily Code Claim + Auction Insights Boost E2E tests."""
from __future__ import annotations
import os
import secrets
from datetime import datetime, timezone, timedelta

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
TEST_EMAIL = "test@bigfm.dubai"
TEST_PASS = "TestUser123!"

ADV_ID = "advv2_9fac10b21f5595"


# ─── Fixtures ───────────────────────────────────────────
@pytest.fixture(scope="session")
def db():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login failed {email}: {r.status_code} {r.text[:200]}")
    tok = r.json().get("token") or r.json().get("access_token") or r.json().get("session_token")
    if not tok:
        # inspect full body for token key
        pytest.skip(f"no token in login body: {r.json()}")
    return tok


@pytest.fixture(scope="session")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="session")
def demo_token():
    return _login(DEMO_EMAIL, DEMO_PASS)


@pytest.fixture(scope="session")
def test_token():
    return _login(TEST_EMAIL, TEST_PASS)


def _hdrs(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def _get_user_id(db, email):
    u = db.users.find_one({"email": email})
    return u.get("user_id") if u else None


# ─── /api/daily-code/current — anonymous + authed ───────
class TestDailyCodeCurrent:
    def test_current_anonymous(self):
        r = requests.get(f"{BASE_URL}/api/daily-code/current", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "code" in d and d["code"] and len(d["code"]) == 6
        assert d["already_claimed"] is False
        assert d["streak_days"] == 0
        assert d["next_multiplier"] == 1.0
        assert "estimated_points" in d
        assert "active_until" in d

    def test_current_authed_no_prior(self, db, demo_token):
        # Wipe any prior claims for demo user for deterministic test
        uid = _get_user_id(db, DEMO_EMAIL)
        assert uid
        db.daily_code_claims.delete_many({"user_id": uid})
        r = requests.get(f"{BASE_URL}/api/daily-code/current",
                         headers=_hdrs(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["already_claimed"] is False
        assert d["streak_days"] == 1
        assert d["next_multiplier"] == 1.0


# ─── Claim negative cases ───────────────────────────────
class TestClaimNegatives:
    def test_wrong_code(self, demo_token):
        r = requests.post(f"{BASE_URL}/api/daily-code/claim",
                          headers=_hdrs(demo_token),
                          json={"code": "ZZZZZZ"}, timeout=15)
        assert r.status_code == 400
        body = r.json()
        assert (body.get("detail") or {}).get("code") == "wrong_code"

    def test_invalid_format(self, demo_token):
        # 6 chars but empty spaces - Pydantic min/max 6 blocks <6, so send 6 spaces
        r = requests.post(f"{BASE_URL}/api/daily-code/claim",
                          headers=_hdrs(demo_token),
                          json={"code": "     X"}, timeout=15)
        # Pydantic passes 6-char string; service upper/strip → will be "X" wrong code
        # Wrong code expected here
        assert r.status_code == 400

    def test_short_code_422(self, demo_token):
        r = requests.post(f"{BASE_URL}/api/daily-code/claim",
                          headers=_hdrs(demo_token),
                          json={"code": "ABC"}, timeout=15)
        assert r.status_code in (400, 422)


# ─── Happy claim + idempotency ──────────────────────────
class TestClaimHappyAndIdempotent:
    def test_happy_and_double_claim(self, db, demo_token):
        uid = _get_user_id(db, DEMO_EMAIL)
        db.daily_code_claims.delete_many({"user_id": uid})

        # Get current code
        cur = requests.get(f"{BASE_URL}/api/daily-code/current",
                           headers=_hdrs(demo_token), timeout=15).json()
        code = cur["code"]
        pts_reward = cur["points_reward"]

        # baseline wallet
        w0 = requests.get(f"{BASE_URL}/api/wallet/me",
                          headers=_hdrs(demo_token), timeout=15)
        assert w0.status_code == 200, w0.text
        pb0 = w0.json().get("points_balance", 0)

        # First claim
        r1 = requests.post(f"{BASE_URL}/api/daily-code/claim",
                           headers=_hdrs(demo_token),
                           json={"code": code}, timeout=15)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["ok"] is True
        assert d1["streak_days"] == 1
        assert d1["streak_multiplier"] == 1.0
        assert d1["points_awarded"] == pts_reward

        # Wallet increased
        w1 = requests.get(f"{BASE_URL}/api/wallet/me",
                          headers=_hdrs(demo_token), timeout=15).json()
        assert w1.get("points_balance", 0) >= pb0 + pts_reward

        # Second claim → 409 already_claimed
        r2 = requests.post(f"{BASE_URL}/api/daily-code/claim",
                           headers=_hdrs(demo_token),
                           json={"code": code}, timeout=15)
        assert r2.status_code == 409
        assert (r2.json().get("detail") or {}).get("code") == "already_claimed"

        # Only 1 row in DB
        count = db.daily_code_claims.count_documents({"user_id": uid})
        assert count == 1, f"expected 1 claim row, got {count}"

        # Points not doubled
        w2 = requests.get(f"{BASE_URL}/api/wallet/me",
                          headers=_hdrs(demo_token), timeout=15).json()
        assert w2.get("points_balance", 0) == w1.get("points_balance", 0)


def _seed_backdated_claims(db, user_id, days_ago_list, daily_code_id="dcd_seed"):
    """Insert synthetic claims for each day in `days_ago_list` (each >=1)."""
    now = datetime.now(timezone.utc)
    docs = []
    for d_ago in days_ago_list:
        day = (now - timedelta(days=d_ago)).replace(hour=12, minute=0, second=0, microsecond=0)
        cid = f"dcl_seed_{secrets.token_hex(4)}"
        docs.append({
            "_id": cid, "claim_id": cid, "user_id": user_id,
            "daily_code_id": f"{daily_code_id}_{d_ago}",
            "date_effective": day.strftime("%Y-%m-%d"),
            "claimed_at": day, "points_awarded": 50,
            "streak_days": 1, "streak_multiplier": 1.0,
        })
    if docs:
        db.daily_code_claims.insert_many(docs)


# ─── Multi-day streak sequence ──────────────────────────
class TestStreakMultiDay:
    def test_3_prior_days_gives_streak4_mult_1_2(self, db, demo_token):
        uid = _get_user_id(db, DEMO_EMAIL)
        db.daily_code_claims.delete_many({"user_id": uid})
        _seed_backdated_claims(db, uid, [1, 2, 3])
        cur = requests.get(f"{BASE_URL}/api/daily-code/current",
                           headers=_hdrs(demo_token), timeout=15).json()
        r = requests.post(f"{BASE_URL}/api/daily-code/claim",
                          headers=_hdrs(demo_token),
                          json={"code": cur["code"]}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["streak_days"] == 4
        assert d["streak_multiplier"] == 1.2

    def test_7_prior_days_gives_streak8_mult_1_5(self, db, demo_token):
        uid = _get_user_id(db, DEMO_EMAIL)
        db.daily_code_claims.delete_many({"user_id": uid})
        _seed_backdated_claims(db, uid, list(range(1, 8)))
        cur = requests.get(f"{BASE_URL}/api/daily-code/current",
                           headers=_hdrs(demo_token), timeout=15).json()
        r = requests.post(f"{BASE_URL}/api/daily-code/claim",
                          headers=_hdrs(demo_token),
                          json={"code": cur["code"]}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["streak_days"] == 8
        assert d["streak_multiplier"] == 1.5

    def test_14_prior_days_gives_streak15_mult_2_0(self, db, demo_token):
        uid = _get_user_id(db, DEMO_EMAIL)
        db.daily_code_claims.delete_many({"user_id": uid})
        _seed_backdated_claims(db, uid, list(range(1, 15)))
        cur = requests.get(f"{BASE_URL}/api/daily-code/current",
                           headers=_hdrs(demo_token), timeout=15).json()
        r = requests.post(f"{BASE_URL}/api/daily-code/claim",
                          headers=_hdrs(demo_token),
                          json={"code": cur["code"]}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["streak_days"] == 15
        assert d["streak_multiplier"] == 2.0

        # History endpoint reflects totals
        h = requests.get(f"{BASE_URL}/api/user/daily-code/history",
                         headers=_hdrs(demo_token), timeout=15)
        assert h.status_code == 200, h.text
        hd = h.json()
        assert hd["totals"]["best_streak"] >= 15
        assert hd["totals"]["current_streak"] >= 15

    def test_streak_reset_when_yesterday_missing(self, db, demo_token):
        uid = _get_user_id(db, DEMO_EMAIL)
        db.daily_code_claims.delete_many({"user_id": uid})
        # Seed only day 3 ago (gap at yesterday and day 2)
        _seed_backdated_claims(db, uid, [3])
        cur = requests.get(f"{BASE_URL}/api/daily-code/current",
                           headers=_hdrs(demo_token), timeout=15).json()
        r = requests.post(f"{BASE_URL}/api/daily-code/claim",
                          headers=_hdrs(demo_token),
                          json={"code": cur["code"]}, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["streak_days"] == 1
        assert d["streak_multiplier"] == 1.0


# ─── Admin CRUD ─────────────────────────────────────────
class TestAdminDailyCode:
    def test_admin_duplicate_date(self, admin_token):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        r = requests.post(f"{BASE_URL}/api/admin/daily-codes",
                          headers=_hdrs(admin_token),
                          json={"date_effective": today, "points_reward": 50},
                          timeout=15)
        # today should already exist
        assert r.status_code == 400
        assert (r.json().get("detail") or {}).get("code") == "code_already_exists_for_date"

    def test_non_admin_forbidden(self, demo_token):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
        r = requests.post(f"{BASE_URL}/api/admin/daily-codes",
                          headers=_hdrs(demo_token),
                          json={"date_effective": future, "points_reward": 50},
                          timeout=15)
        assert r.status_code == 403
        assert (r.json().get("detail") or {}).get("code") == "admin_required"


# ─── Auction Insights RBAC + boost ──────────────────────
class TestAuctionInsights:
    def test_owner_can_view(self, demo_token):
        r = requests.get(f"{BASE_URL}/api/advertiser/{ADV_ID}/auction-insights",
                         headers=_hdrs(demo_token), timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and "count" in d and "by_reason" in d and "window_hours" in d

    def test_non_owner_forbidden(self, test_token):
        r = requests.get(f"{BASE_URL}/api/advertiser/{ADV_ID}/auction-insights",
                         headers=_hdrs(test_token), timeout=15)
        assert r.status_code == 403
        assert (r.json().get("detail") or {}).get("code") == "advertiser_owner_only"

    def test_admin_bypass_ownership(self, admin_token):
        r = requests.get(f"{BASE_URL}/api/advertiser/{ADV_ID}/auction-insights",
                         headers=_hdrs(admin_token), timeout=15)
        assert r.status_code == 200


def _seed_pw_sponsorship(db, advertiser_id, cpe_cents=100):
    """Ensure a predict_win_sponsorships row exists for the advertiser."""
    sid = f"pwsp_test_{secrets.token_hex(4)}"
    doc = {
        "_id": sid, "sponsorship_id": sid,
        "advertiser_id": advertiser_id,
        "pricing_model": "per_entry",
        "cpe_cents": cpe_cents,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }
    db.predict_win_sponsorships.insert_one(doc)
    return sid


def _seed_auction_loss(db, advertiser_id, campaign_id, ad_type, bid_cents, winner_bid_cents):
    ev = f"aev_test_{secrets.token_hex(4)}"
    db.auction_events.insert_one({
        "_id": ev, "event_id": ev,
        "ad_type": ad_type, "slot_id": "slot_test",
        "advertiser_id": advertiser_id, "campaign_id": campaign_id,
        "reason": "higher_cpm",
        "bid_cents": bid_cents,
        "winner_advertiser_id": "advv2_other",
        "winner_bid_cents": winner_bid_cents,
        "created_at": datetime.now(timezone.utc),
    })
    return ev


class TestBoostPWSponsorship:
    def test_large_change_triggers_pending_admin(self, db, demo_token):
        # Clean up any leftover
        db.predict_win_sponsorships.delete_many({"_id": {"$regex": "^pwsp_test_"}})
        db.auction_events.delete_many({"_id": {"$regex": "^aev_test_"}})

        sid = _seed_pw_sponsorship(db, ADV_ID, cpe_cents=100)
        _seed_auction_loss(db, ADV_ID, sid, "pw_sponsorship", 100, 150)

        r = requests.post(
            f"{BASE_URL}/api/advertiser/{ADV_ID}/auction-insights/boost",
            headers=_hdrs(demo_token),
            json={"ad_type": "pw_sponsorship", "campaign_id": sid, "new_bid_cents": 151},
            timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["old_bid_cents"] == 100
        assert d["new_bid_cents"] == 151
        assert d["change_pct"] == 51
        assert d["requires_reapproval"] is True

        row = db.predict_win_sponsorships.find_one({"sponsorship_id": sid})
        assert row["status"] == "pending_admin"
        assert row["cpe_cents"] == 151

    def test_small_change_no_pending_admin(self, db, demo_token):
        sid = _seed_pw_sponsorship(db, ADV_ID, cpe_cents=1000)
        _seed_auction_loss(db, ADV_ID, sid, "pw_sponsorship", 1000, 1050)

        r = requests.post(
            f"{BASE_URL}/api/advertiser/{ADV_ID}/auction-insights/boost",
            headers=_hdrs(demo_token),
            json={"ad_type": "pw_sponsorship", "campaign_id": sid, "new_bid_cents": 1100},
            timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["change_pct"] == 10
        assert d["requires_reapproval"] is False
        row = db.predict_win_sponsorships.find_one({"sponsorship_id": sid})
        assert row["status"] == "active"
        assert row["cpe_cents"] == 1100


class TestBoostBannerAndNotification:
    def test_banner(self, db, demo_token):
        cid = f"ban_test_{secrets.token_hex(4)}"
        db.banner_campaigns.insert_one({
            "_id": cid, "banner_id": cid,
            "advertiser_id": ADV_ID,
            "per_zone_cpm_cents": {"station_detail": 100, "home": 80},
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        })
        r = requests.post(
            f"{BASE_URL}/api/advertiser/{ADV_ID}/auction-insights/boost",
            headers=_hdrs(demo_token),
            json={"ad_type": "banner", "campaign_id": cid, "new_bid_cents": 110},
            timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["change_pct"] == 10
        row = db.banner_campaigns.find_one({"banner_id": cid})
        # zones scaled by factor 1.10
        assert row["per_zone_cpm_cents"]["station_detail"] == 110
        assert row["status"] == "active"

    def test_notification(self, db, demo_token):
        cid = f"notif_test_{secrets.token_hex(4)}"
        db.notification_campaigns.insert_one({
            "_id": cid, "notification_campaign_id": cid,
            "advertiser_id": ADV_ID,
            "cost_per_delivery_cents": 50,
            "status": "active",
            "created_at": datetime.now(timezone.utc),
        })
        r = requests.post(
            f"{BASE_URL}/api/advertiser/{ADV_ID}/auction-insights/boost",
            headers=_hdrs(demo_token),
            json={"ad_type": "notification", "campaign_id": cid, "new_bid_cents": 55},
            timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["change_pct"] == 10
        assert d["requires_reapproval"] is False
        row = db.notification_campaigns.find_one({"notification_campaign_id": cid})
        assert row["cost_per_delivery_cents"] == 55
        assert row["status"] == "active"


# ─── Regression ─────────────────────────────────────────
class TestRegression:
    def test_openapi_ok(self):
        r = requests.get(f"{BASE_URL}/api/openapi.json", timeout=15)
        assert r.status_code == 200
        assert "paths" in r.json()

    def test_wallet_me(self, demo_token):
        r = requests.get(f"{BASE_URL}/api/wallet/me",
                         headers=_hdrs(demo_token), timeout=15)
        assert r.status_code == 200
        assert "points_balance" in r.json() or "balance" in r.json()

    def test_login(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
        assert r.status_code == 200


# ─── Cleanup after suite ────────────────────────────────
@pytest.fixture(scope="session", autouse=True)
def _cleanup_after(db):
    yield
    try:
        # Clean up seeded data
        uid = _get_user_id(db, DEMO_EMAIL)
        if uid:
            db.daily_code_claims.delete_many({"user_id": uid,
                                              "_id": {"$regex": "^dcl_seed_"}})
        db.predict_win_sponsorships.delete_many({"_id": {"$regex": "^pwsp_test_"}})
        db.banner_campaigns.delete_many({"_id": {"$regex": "^ban_test_"}})
        db.notification_campaigns.delete_many({"_id": {"$regex": "^notif_test_"}})
        db.auction_events.delete_many({"_id": {"$regex": "^aev_test_"}})
    except Exception:
        pass
