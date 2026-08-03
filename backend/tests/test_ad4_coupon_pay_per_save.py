"""
AD.4 — Coupon Pay-Per-Save end-to-end backend test.

Verifies:
  1. Live listing + basic save happy path (mints coupon + wallet + tx split 70/30).
  2. Duplicate save idempotency (no second debit).
  3. Inventory exhaustion → HTTP 410 + auto-pause.
  4. Wallet-drain auto-pause → HTTP 402 + auto-pause.
  5. Cross-scope redemption + race (merchant wins → advertiser 409).
  6. Advertiser + merchant roll-up endpoints reflect saves.
  7. OpenAPI exposes all AD.4 endpoints.
"""

import os
import sys
import asyncio
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone

def _read_frontend_env():
    with open("/app/frontend/.env") as fh:
        for line in fh:
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or _read_frontend_env()
BASE_URL = BASE_URL.rstrip("/")
MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ["DB_NAME"]

CAMPAIGN_ID = "cc_ad4_demo_karak"
ADVERTISER_ID = "advv2_9fac10b21f5595"
MERCHANT_ID = "biz_sc5_test_activated"
CPS = 10
STARTING_WALLET = 100000

CREDS = {
    "demo": ("demo@bigfm.dubai", "DemoPass123!"),
    "test": ("test@bigfm.dubai", "TestUser123!"),
    "predict": ("predictest@bigfm.dubai", "PredictTest123!"),
    "premium": ("premiumtest@bigfm.dubai", "PremiumTest123!"),
    "admin": ("admin@bigfm.dubai", "AdminPass123!"),
}


def login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


async def _reset_state(inventory=8, wallet=STARTING_WALLET):
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    await db.advertisers_v2.update_one(
        {"advertiser_id": ADVERTISER_ID},
        {"$set": {"budget_available_cents": wallet, "budget_spent_cents": 0}},
    )
    await db.coupon_campaigns.update_one(
        {"campaign_id": CAMPAIGN_ID},
        {"$set": {
            "status": "live",
            "saves_count": 0,
            "total_inventory": inventory,
            "auto_paused_reason": None,
            "auto_paused_at": None,
            "updated_at": datetime.now(timezone.utc),
        }},
    )
    await db.payment_transactions_v2.delete_many({"flow": "ad4_coupon_save_split"})
    await db.coupons.delete_many({"source_type": "ad4_coupon_save"})
    await db.user_wallet_items.delete_many({"source_type": "ad4_coupon_save"})


def reset_state(inventory=8, wallet=STARTING_WALLET):
    asyncio.get_event_loop().run_until_complete(_reset_state(inventory, wallet))


async def _mongo_fetch(coll, query):
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    return await db[coll].find_one(query)


def mongo_fetch(coll, query):
    return asyncio.get_event_loop().run_until_complete(_mongo_fetch(coll, query))


async def _mongo_count(coll, query):
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]
    return await db[coll].count_documents(query)


def mongo_count(coll, query):
    return asyncio.get_event_loop().run_until_complete(_mongo_count(coll, query))


# ---------- Tests ----------

def test_00_openapi_lists_ad4_endpoints():
    r = requests.get(f"{BASE_URL}/api/openapi.json", timeout=15)
    assert r.status_code == 200
    paths = r.json().get("paths", {})
    required = [
        "/api/admin/coupon-campaigns/pending",
        "/api/admin/coupon-campaigns/{campaign_id}/review",
        "/api/advertiser/{advertiser_id}/coupon-campaigns",
        "/api/advertiser/coupon-campaigns/{campaign_id}",
        "/api/advertiser/coupon-campaigns/{campaign_id}/publish",
        "/api/advertiser/{advertiser_id}/coupon-transactions",
        "/api/coupon-campaigns/live",
        "/api/coupon-campaigns/{campaign_id}/save",
        "/api/merchant/{merchant_id}/coupon-sponsorship-revenue",
    ]
    missing = [p for p in required if p not in paths]
    assert not missing, f"Missing endpoints in OpenAPI: {missing}"


def test_01_live_list_shows_demo_campaign():
    reset_state()
    demo = login(*CREDS["demo"])
    r = demo.get(f"{BASE_URL}/api/coupon-campaigns/live", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    campaigns = body.get("items") or body.get("campaigns") or (body if isinstance(body, list) else [])
    demo_c = next((c for c in campaigns if c.get("campaign_id") == CAMPAIGN_ID), None)
    assert demo_c is not None, f"demo campaign missing from live list: {r.json()}"
    sponsor = demo_c.get("sponsoring_merchant") or {}
    assert sponsor.get("name") == "SC5 Test Merchant", f"sponsor: {sponsor}"
    assert demo_c.get("inventory_remaining", 0) > 0


def test_02_save_happy_path_split_70_30():
    reset_state()
    demo = login(*CREDS["demo"])
    r = demo.post(f"{BASE_URL}/api/coupon-campaigns/{CAMPAIGN_ID}/save", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["gross_cents"] == 10
    assert body["merchant_cents"] == 7
    assert body["platform_cents"] == 3
    assert body["wallet_balance_cents_after"] == STARTING_WALLET - CPS
    assert body["coupon_id"].startswith("cpn_")
    assert body["transaction_id"].startswith("tx_ad4_")

    # Verify tx row
    tx = mongo_fetch("payment_transactions_v2", {"transaction_id": body["transaction_id"]})
    assert tx is not None
    assert tx["flow"] == "ad4_coupon_save_split"
    assert tx["application_fee_cents"] == 3
    assert tx["merchant_net_cents"] == 7
    # save_event_id format
    expected_evt = f"save_user_demo_8b88c27e0f_{CAMPAIGN_ID}"
    assert tx.get("ad4_save_event_id") == expected_evt, f"got {tx.get('ad4_save_event_id')}"

    # Advertiser wallet decremented
    adv = mongo_fetch("advertisers_v2", {"advertiser_id": ADVERTISER_ID})
    assert adv["budget_available_cents"] == STARTING_WALLET - CPS
    assert adv["budget_spent_cents"] == CPS


def test_03_duplicate_save_idempotent():
    # Continues from test_02 state — do explicit save first
    reset_state()
    demo = login(*CREDS["demo"])
    r1 = demo.post(f"{BASE_URL}/api/coupon-campaigns/{CAMPAIGN_ID}/save", timeout=15).json()
    r2 = demo.post(f"{BASE_URL}/api/coupon-campaigns/{CAMPAIGN_ID}/save", timeout=15)
    assert r2.status_code == 200
    b2 = r2.json()
    assert b2["ok"] is True
    assert b2.get("already_saved") is True
    assert b2["coupon_id"] == r1["coupon_id"]
    assert b2["transaction_id"] == r1["transaction_id"]

    # only one tx row for this campaign
    n = mongo_count("payment_transactions_v2", {"flow": "ad4_coupon_save_split"})
    assert n == 1, f"expected 1 tx row, got {n}"
    adv = mongo_fetch("advertisers_v2", {"advertiser_id": ADVERTISER_ID})
    assert adv["budget_available_cents"] == STARTING_WALLET - CPS


def test_04_inventory_exhaustion_auto_pause():
    reset_state(inventory=3)
    # 3 different users save successfully
    for user_key in ("demo", "test", "predict"):
        s = login(*CREDS[user_key])
        r = s.post(f"{BASE_URL}/api/coupon-campaigns/{CAMPAIGN_ID}/save", timeout=15)
        assert r.status_code == 200, f"{user_key}: {r.status_code} {r.text}"

    # campaign should be paused with inventory_exhausted
    camp = mongo_fetch("coupon_campaigns", {"campaign_id": CAMPAIGN_ID})
    assert camp["status"] == "paused", f"status={camp.get('status')}"
    assert camp.get("auto_paused_reason") == "inventory_exhausted"

    # 4th user gets 410 inventory_exhausted (precedence fix: intrinsic checks before paused-status check)
    s4 = login(*CREDS["premium"])
    r4 = s4.post(f"{BASE_URL}/api/coupon-campaigns/{CAMPAIGN_ID}/save", timeout=15)
    assert r4.status_code == 410, f"expected 410, got {r4.status_code} {r4.text}"
    body = r4.json()
    detail = body.get("detail", body)
    reason = detail.get("reason") if isinstance(detail, dict) else None
    assert reason == "inventory_exhausted", f"body={body}"
    campaign_paused = detail.get("campaign_paused") if isinstance(detail, dict) else None
    assert campaign_paused is True, f"expected campaign_paused=true, body={body}"


def test_05_wallet_drain_auto_pause():
    reset_state(inventory=8, wallet=5)  # below CPS
    demo = login(*CREDS["demo"])
    r = demo.post(f"{BASE_URL}/api/coupon-campaigns/{CAMPAIGN_ID}/save", timeout=15)
    assert r.status_code == 402, f"expected 402, got {r.status_code} {r.text}"
    body = r.json()
    detail = body.get("detail", body)
    reason = detail.get("reason") if isinstance(detail, dict) else None
    assert reason == "wallet_exhausted", f"body={body}"

    camp = mongo_fetch("coupon_campaigns", {"campaign_id": CAMPAIGN_ID})
    assert camp["status"] == "paused"
    assert camp.get("auto_paused_reason") == "wallet_exhausted"


def test_06_cross_scope_scan_both_sides():
    reset_state()
    demo = login(*CREDS["demo"])
    save_body = demo.post(f"{BASE_URL}/api/coupon-campaigns/{CAMPAIGN_ID}/save", timeout=15).json()
    code = save_body["short_code"]
    coupon_id = save_body["coupon_id"]

    # Merchant cashier scan-any
    r_m = demo.post(
        f"{BASE_URL}/api/merchant/{MERCHANT_ID}/cashier/scan-any",
        json={"code": code}, timeout=15,
    )
    assert r_m.status_code == 200, f"merchant scan: {r_m.status_code} {r_m.text}"
    mb = r_m.json()
    assert mb.get("ok") is True
    assert mb.get("type") == "coupon"
    assert mb.get("source_type") == "ad4_coupon_save"
    assert mb.get("ad_coupon_campaign_id") == CAMPAIGN_ID

    # Advertiser scan
    r_a = demo.post(
        f"{BASE_URL}/api/advertiser-app/{ADVERTISER_ID}/scan",
        json={"code": code}, timeout=15,
    )
    assert r_a.status_code == 200, f"adv scan: {r_a.status_code} {r_a.text}"
    ab = r_a.json()
    assert ab.get("ok") is True
    assert ab.get("status") == "saved"


def test_07_cross_scope_race_merchant_wins():
    reset_state()
    demo = login(*CREDS["demo"])
    sb = demo.post(f"{BASE_URL}/api/coupon-campaigns/{CAMPAIGN_ID}/save", timeout=15).json()
    coupon_id = sb["coupon_id"]
    code = sb["short_code"]

    # Merchant redeems first
    r_m = demo.post(
        f"{BASE_URL}/api/merchant/{MERCHANT_ID}/cashier/redeem",
        json={"coupon_id": coupon_id}, timeout=15,
    )
    assert r_m.status_code == 200, f"merchant redeem: {r_m.status_code} {r_m.text}"
    assert r_m.json().get("ok") is True

    # Advertiser tries → 409
    r_a = demo.post(
        f"{BASE_URL}/api/advertiser-app/{ADVERTISER_ID}/redeem",
        json={"code": code}, timeout=15,
    )
    assert r_a.status_code == 409, f"expected 409, got {r_a.status_code} {r_a.text}"
    detail = r_a.json().get("detail", {})
    code_val = detail.get("code") if isinstance(detail, dict) else None
    assert code_val in ("already_redeemed", "already_redeemed_race"), f"body={r_a.json()}"


def test_08_advertiser_coupon_transactions_totals():
    reset_state()
    # Two users save
    for u in ("demo", "test"):
        s = login(*CREDS[u])
        assert s.post(f"{BASE_URL}/api/coupon-campaigns/{CAMPAIGN_ID}/save", timeout=15).status_code == 200

    demo = login(*CREDS["demo"])
    r = demo.get(f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/coupon-transactions", timeout=15)
    assert r.status_code == 200, r.text
    totals = r.json().get("totals", {})
    assert totals.get("saves") == 2
    assert totals.get("gross_cents") == 20
    assert totals.get("merchant_cents") == 14
    assert totals.get("platform_cents") == 6


def test_09_merchant_sponsorship_revenue():
    # relies on state left by test_08 (2 saves)
    demo = login(*CREDS["demo"])
    r = demo.get(f"{BASE_URL}/api/merchant/{MERCHANT_ID}/coupon-sponsorship-revenue", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    totals = body.get("totals", {})
    assert totals.get("merchant_cents", 0) >= 14, f"totals={totals}"
    rolling = body.get("rolling_30d", {})
    assert rolling.get("saves", 0) >= 2
    assert rolling.get("merchant_cents", 0) >= 14


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
