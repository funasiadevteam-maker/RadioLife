"""Phase AD.2 — Sponsored Games Revenue Split — backend E2E tests.

Covers: impression billing arithmetic, idempotency, daily cap, wallet
exhaustion auto-pause, RBAC on GET endpoints, admin PATCH commission
rule, non-sponsored game short-circuit.
"""
from __future__ import annotations

import os
import uuid
import asyncio
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone

load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADVERTISER_ID = "advv2_9fac10b21f5595"
AD_CAMPAIGN_ID = "adcv2_1cf5ba69c4d1ed"
GAME_CAMPAIGN_ID = "gc_404c2699a52746"
MERCHANT_ID = "biz_sc5_test_activated"
NON_SPONSORED_GC = "cmp_house_spin"

DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PW = "DemoPass123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PW = "AdminPass123!"
TEST_EMAIL = "test@bigfm.dubai"
TEST_PW = "TestUser123!"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                          json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login {email} → {r.status_code} {r.text[:200]}"
    return s


# ─── Fixtures ───────────────────────────────────────────────────
@pytest.fixture(scope="module")
def db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


async def _reset_fixture(db, budget_cents=1000):
    now = datetime.now(timezone.utc)
    await db.advertisers_v2.update_one(
        {"advertiser_id": ADVERTISER_ID},
        {"$set": {"budget_available_cents": budget_cents,
                          "budget_spent_cents": 0, "updated_at": now}})
    await db.ad_campaigns_v2.update_one(
        {"campaign_id": AD_CAMPAIGN_ID},
        {"$set": {"status": "active", "updated_at": now,
                          "impressions_count": 0, "clicks_count": 0},
          "$unset": {"auto_paused_reason": "", "paused_at": ""}})
    await db.game_campaigns.update_one(
        {"campaign_id": GAME_CAMPAIGN_ID},
        {"$set": {"sponsored_by_ad_campaign_id": AD_CAMPAIGN_ID,
                          "sponsor_advertiser_id": ADVERTISER_ID,
                          "sponsor_pricing_model": "cpm",
                          "sponsor_cpm_bid_cents": 5000,
                          "sponsor_daily_impression_cap_per_user": 3,
                          "sponsor_pause_when_wallet_empty": True,
                          "sponsor_paused_reason": None,
                          "updated_at": now}})
    await db.payment_transactions_v2.delete_many(
        {"flow": "ad2_sponsored_game_split"})


@pytest.fixture
def reset_all(db):
    asyncio.get_event_loop().run_until_complete(_reset_fixture(db, 1000))


@pytest.fixture(scope="module")
def demo():
    return _login(DEMO_EMAIL, DEMO_PW)


@pytest.fixture(scope="module")
def admin():
    return _login(ADMIN_EMAIL, ADMIN_PW)


@pytest.fixture(scope="module")
def test_user():
    return _login(TEST_EMAIL, TEST_PW)


# ─── Tests ──────────────────────────────────────────────────────
class TestImpressionArithmetic:
    def test_single_impression_split(self, reset_all, demo, db):
        eid = f"ev_test_{uuid.uuid4().hex}"
        r = demo.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                                    json={"event_type": "impression", "event_id": eid})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True and j["billed"] is True
        assert j["gross_cents"] == 5, j
        # 30% platform = 1.5¢ → banker's rounded to 2¢
        assert j["platform_cents"] == 2, j
        assert j["merchant_cents"] == 3, j
        assert j["wallet_balance_cents_after"] == 995
        assert j["campaign_paused"] is False
        assert j["transaction_id"].startswith("tx_ad2_")
        # DB check: ledger row shape
        loop = asyncio.get_event_loop()
        row = loop.run_until_complete(
            db.payment_transactions_v2.find_one(
                {"transaction_id": j["transaction_id"]}))
        assert row["flow"] == "ad2_sponsored_game_split"
        assert row["merchant_net_cents"] == 3
        assert row["application_fee_cents"] == 2
        assert row["advertiser_id"] == ADVERTISER_ID
        assert row["merchant_id"] == MERCHANT_ID
        assert row["game_event_id"] == eid
        # wallet check
        adv = loop.run_until_complete(db.advertisers_v2.find_one(
            {"advertiser_id": ADVERTISER_ID}))
        assert adv["budget_available_cents"] == 995


class TestIdempotency:
    def test_duplicate_event_id(self, reset_all, demo):
        eid = f"ev_dup_{uuid.uuid4().hex}"
        r1 = demo.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                                      json={"event_type": "impression", "event_id": eid})
        assert r1.status_code == 200
        j1 = r1.json()
        assert j1["billed"] is True

        r2 = demo.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                                      json={"event_type": "impression", "event_id": eid})
        assert r2.status_code == 200
        j2 = r2.json()
        assert j2["billed"] is False
        assert j2["reason"] == "duplicate_event"
        assert j2["transaction_id"] == j1["transaction_id"]


class TestDailyCap:
    def test_cap_and_different_user(self, reset_all, demo, test_user, db):
        # 3 successful billed events for demo
        for i in range(3):
            r = demo.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                                        json={"event_type": "impression",
                                                    "event_id": f"ev_cap_demo_{i}_{uuid.uuid4().hex}"})
            j = r.json()
            assert r.status_code == 200 and j.get("billed") is True, j

        # 4th same user → daily_cap_reached
        r4 = demo.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                                      json={"event_type": "impression",
                                                  "event_id": f"ev_cap_demo_4_{uuid.uuid4().hex}"})
        j4 = r4.json()
        assert r4.status_code == 200
        assert j4["billed"] is False
        assert j4["reason"] == "daily_cap_reached"
        assert j4["cap"] == 3

        # Different user's first event resets their own cap
        r5 = test_user.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                                                    json={"event_type": "impression",
                                                                "event_id": f"ev_cap_test_1_{uuid.uuid4().hex}"})
        j5 = r5.json()
        assert r5.status_code == 200, r5.text
        assert j5["billed"] is True, j5


class TestNonSponsored:
    def test_non_sponsored_game(self, demo):
        r = demo.post(f"{API}/games/{NON_SPONSORED_GC}/impression",
                                    json={"event_type": "impression",
                                                "event_id": f"ev_ns_{uuid.uuid4().hex}"})
        assert r.status_code == 200
        j = r.json()
        assert j["billed"] is False
        assert j["reason"] == "not_sponsored"


class TestWalletExhaustion:
    def test_exhaustion_auto_pause(self, db, demo):
        # Set budget = 10¢, so 2 events (2 × 5¢) drain the wallet.
        loop = asyncio.get_event_loop()
        loop.run_until_complete(_reset_fixture(db, budget_cents=10))

        e1 = demo.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                                      json={"event_type": "impression",
                                                  "event_id": f"ev_wx_1_{uuid.uuid4().hex}"}).json()
        assert e1["billed"] is True and e1["campaign_paused"] is False

        e2 = demo.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                                      json={"event_type": "impression",
                                                  "event_id": f"ev_wx_2_{uuid.uuid4().hex}"}).json()
        assert e2["billed"] is True, e2
        assert e2["campaign_paused"] is True, e2
        assert e2["wallet_balance_cents_after"] == 0

        # Verify DB state transitions
        ad = loop.run_until_complete(db.ad_campaigns_v2.find_one(
            {"campaign_id": AD_CAMPAIGN_ID}))
        assert ad["status"] == "paused"
        assert ad.get("auto_paused_reason") == "wallet_exhausted"
        gc = loop.run_until_complete(db.game_campaigns.find_one(
            {"campaign_id": GAME_CAMPAIGN_ID}))
        assert gc.get("sponsored_by_ad_campaign_id") is None
        assert gc.get("sponsor_paused_reason") == "wallet_exhausted"

        # Subsequent impression → not_sponsored
        e3 = demo.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                                      json={"event_type": "impression",
                                                  "event_id": f"ev_wx_3_{uuid.uuid4().hex}"}).json()
        assert e3["billed"] is False
        assert e3["reason"] == "not_sponsored"


class TestAdvertiserGetRBAC:
    def test_owner_ok_and_totals(self, reset_all, demo):
        # Fire one billable event so we have data.
        demo.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                          json={"event_type": "impression",
                                      "event_id": f"ev_rbac_{uuid.uuid4().hex}"})
        r = demo.get(f"{API}/advertiser/{ADVERTISER_ID}/game-transactions")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["advertiser_id"] == ADVERTISER_ID
        assert "per_campaign" in j and "recent_events" in j and "totals" in j
        assert j["totals"]["events"] >= 1
        assert j["totals"]["gross_cents"] >= 5

    def test_admin_ok(self, admin):
        r = admin.get(f"{API}/advertiser/{ADVERTISER_ID}/game-transactions")
        assert r.status_code == 200

    def test_other_user_forbidden(self, test_user):
        r = test_user.get(f"{API}/advertiser/{ADVERTISER_ID}/game-transactions")
        assert r.status_code == 403, r.text


class TestMerchantGetRBAC:
    def test_owner_ok(self, reset_all, demo):
        demo.post(f"{API}/games/{GAME_CAMPAIGN_ID}/impression",
                          json={"event_type": "impression",
                                      "event_id": f"ev_mrbac_{uuid.uuid4().hex}"})
        r = demo.get(f"{API}/merchant/{MERCHANT_ID}/game-revenue")
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["merchant_id"] == MERCHANT_ID
        assert "per_campaign" in j and "rolling_30d" in j and "totals" in j
        assert j["totals"]["events"] >= 1
        assert j["totals"]["merchant_cents"] >= 3

    def test_admin_ok(self, admin):
        r = admin.get(f"{API}/merchant/{MERCHANT_ID}/game-revenue")
        assert r.status_code == 200

    def test_other_user_forbidden(self, test_user):
        r = test_user.get(f"{API}/merchant/{MERCHANT_ID}/game-revenue")
        assert r.status_code == 403


class TestAdminCommissionRule:
    def test_patch_and_restore(self, admin, demo, db):
        # PATCH to 80%
        r = admin.patch(f"{API}/admin/commission-rules/sponsored-game",
                                        json={"merchant_share_pct": 80})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["ok"] is True
        assert j["merchant_share_pct"] == 80
        assert j["platform_percent"] == 20

        # Verify persistence in DB
        loop = asyncio.get_event_loop()
        rule = loop.run_until_complete(db.commission_rules.find_one(
            {"business_category": "*", "transaction_type": "sponsored_game",
              "market": None}))
        assert rule is not None
        assert rule["commission_percent"] == 20.0

        # Restore to 70/30
        r2 = admin.patch(f"{API}/admin/commission-rules/sponsored-game",
                                          json={"merchant_share_pct": 70})
        assert r2.status_code == 200
        rule = loop.run_until_complete(db.commission_rules.find_one(
            {"business_category": "*", "transaction_type": "sponsored_game",
              "market": None}))
        assert rule["commission_percent"] == 30.0

    def test_non_admin_forbidden(self, demo):
        r = demo.patch(f"{API}/admin/commission-rules/sponsored-game",
                                      json={"merchant_share_pct": 50})
        assert r.status_code in (401, 403)
