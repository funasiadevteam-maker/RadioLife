"""Phase 8a — Gamification Marketplace pytest suite.

Drives the live FastAPI server through `requests`.  Covers:
  - 4 game types × happy-path (start → submit → win/claim → QR → redeem)
  - probability weight validator on submit_for_approval
  - atomic inventory drain (concurrent burst against limited inventory)
  - driving mode → 423 + save_for_later
  - admin approve/reject/pause/inventory-adjust
  - Phase 5 migration idempotency
  - Old /api/games/* → 410 Gone
  - Wallet item appears after claim
  - max_per_user enforcement
  - Smoke: radio/billing/lobbies/bigcoin still 200
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

API = os.environ.get("PHASE7_API",
                       "https://mobile-games-v2.preview.emergentagent.com").rstrip("/") + "/api"
MONGO = os.environ.get("PHASE7_MONGO", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")


def _mongo():
    return AsyncIOMotorClient(MONGO)[DB_NAME]


def _run(coro):
    return asyncio.run(coro)


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.text}"
    s._user_id = r.json()["user_id"]
    return s


# ----------------------------------------------------------------------
async def _ensure_advertiser(email: str, name: str = "Advertiser Tester"):
    """Idempotent fixture: ensure a user with `is_advertiser=True` and a
    matching `advertisers` doc exists."""
    from auth import hash_password
    db = _mongo()
    u = await db.users.find_one({"email": email})
    if not u:
        uid = f"user_{uuid.uuid4().hex[:14]}"
        await db.users.insert_one({
            "_id": uid, "user_id": uid, "email": email, "name": name,
            "password_hash": hash_password("AdvertiserP8!23"),
            "role": "advertiser",
            "is_advertiser": True, "is_premium": False,
            "premium_tier": None, "premium_source": None,
            "billing_status": "active",
            "reward_multiplier": 1.0,
            "preference_vector": {"city": "Dubai"},
            "language": "en", "market": "dubai",
            "created_at": __import__("datetime").datetime.utcnow(),
        })
        u = await db.users.find_one({"user_id": uid})
    else:
        await db.users.update_one({"user_id": u["user_id"]},
                                       {"$set": {"is_advertiser": True}})
    adv = await db.advertisers.find_one({"user_id": u["user_id"],
                                              "advertiser_id": "adv_phase8a_tester"})
    if not adv:
        await db.advertisers.insert_one({
            "_id": "adv_phase8a_tester",
            "advertiser_id": "adv_phase8a_tester",
            "user_id": u["user_id"],
            "display_name": "Phase 8a Tester Co",
            "approval_status": "approved",
            "market": "dubai",
        })
    return u["user_id"]


@pytest.fixture(scope="module")
def advertiser_session():
    _run(_ensure_advertiser("advertiser@bigfm.dubai"))
    return _login("advertiser@bigfm.dubai", "AdvertiserP8!23")


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def user_session():
    return _login("test@bigfm.dubai", "TestUser123!")


@pytest.fixture(scope="module")
def premium_session():
    return _login("premium@bigfm.dubai", "PremiumTest123!")


# ----------------------------------------------------------------------
# Bootstrap / migration
# ----------------------------------------------------------------------
def test_01_templates_seeded():
    async def check():
        db = _mongo()
        return await db.game_templates.count_documents({}), \
                  await db.game_templates.count_documents({"active": True})
    total, active = _run(check())
    assert total == 7
    # Phase 8b activated slot/memory/word -> all 7 are now active
    assert active == 7


def test_02_house_campaigns_created():
    async def check():
        db = _mongo()
        return await db.game_campaigns.count_documents(
            {"is_platform_funded": True, "status": "active"})
    n = _run(check())
    assert n >= 3


def test_03_migration_idempotent(admin_session):
    r1 = admin_session.post(f"{API}/games_v2/admin/migrate_phase5_games",
                                  timeout=15).json()
    r2 = admin_session.post(f"{API}/games_v2/admin/migrate_phase5_games",
                                  timeout=15).json()
    assert r2["templates_created"] == 0
    assert r2["house_campaigns_created"] == 0
    assert r2["house_campaigns_existing"] >= 3
    # No duplicate house campaigns
    async def n_house():
        return await _mongo().game_campaigns.count_documents(
            {"is_platform_funded": True})
    assert _run(n_house()) == 3


def test_04_legacy_routes_410(user_session):
    r = user_session.post(f"{API}/games/spin/play", timeout=10)
    assert r.status_code == 410
    body = r.json()
    assert body["moved_to"].startswith("/api/games_v2/")


def test_05_play_and_win_lists_house_games(user_session):
    r = user_session.get(f"{API}/games_v2/play_and_win", timeout=10)
    assert r.status_code == 200
    body = r.json()
    titles = [c["title"] for c in body["unlocked_for_you"]]
    assert "BigFM Daily Spin" in titles
    assert "BigFM Music Trivia" in titles
    assert "BigFM Lyric Hunt" in titles
    assert "played_history" in body and "sponsored_near_you" in body


# ----------------------------------------------------------------------
# 4 game types × happy path
# ----------------------------------------------------------------------
def _make_campaign(advertiser_session, *, template_id, prizes_overrides=None,
                       extra_config=None, open_to_all=True):
    # Templates with min_prizes>=2 (spin_wheel) need at least 2 prize rows.
    default_prizes_2 = [
        {"prize_type": "bigcoin", "title": "20 BC", "value_amount": 20,
          "probability_weight": 70, "inventory_total": 1000,
          "redemption_method": "in_app_wallet"},
        {"prize_type": "bigcoin", "title": "50 BC", "value_amount": 50,
          "probability_weight": 30, "inventory_total": 1000,
          "redemption_method": "in_app_wallet"},
    ]
    default_prizes_1 = [
        {"prize_type": "bigcoin", "title": "20 BC", "value_amount": 20,
          "probability_weight": 100, "inventory_total": 1000,
          "redemption_method": "in_app_wallet"},
    ]
    if prizes_overrides is None:
        prizes_overrides = (default_prizes_2 if template_id == "tpl_spin_wheel"
                                else default_prizes_1)
    payload = {
        "template_id": template_id,
        "title": f"Test {template_id} {uuid.uuid4().hex[:4]}",
        "sponsor_name": "Test Sponsor",
        "open_to_all": open_to_all,
        "game_config_json": extra_config or {},
        "prizes": prizes_overrides,
        "redemption_rules": {"expiration_days": 30},
        "compliance": {
            "terms_text": "Standard T&C.",
            "odds_disclosure": "Win odds disclosed inside.",
            "no_purchase_necessary_text": "No purchase necessary.",
        },
    }
    r = advertiser_session.post(f"{API}/games_v2/advertiser/campaigns",
                                       json=payload, timeout=10)
    assert r.status_code == 200, r.text
    return r.json()["campaign_id"]


def _submit_for_approval(advertiser_session, cid):
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/submit_for_approval",
        timeout=10)
    assert r.status_code == 200, r.text


def _admin_approve(admin_session, cid):
    r = admin_session.post(f"{API}/games_v2/admin/campaigns/{cid}/approve",
                                timeout=10)
    assert r.status_code == 200, r.text


def test_06_spin_wheel_happy_path(advertiser_session, admin_session,
                                            user_session):
    cid = _make_campaign(advertiser_session,
                              template_id="tpl_spin_wheel",
                              extra_config={"segments": [
                                  {"label": "20 BC", "color": "#ff2d95",
                                   "probability_weight": 100}]},
                              # Force a single-prize pool so the bigcoin reward
                              # is deterministic.
                              prizes_overrides=[
                                  {"prize_type": "bigcoin", "title": "20 BC",
                                    "value_amount": 20,
                                    "probability_weight": 100,
                                    "inventory_total": 1000,
                                    "redemption_method": "in_app_wallet"},
                                  {"prize_type": "bigcoin", "title": "Filler",
                                    "value_amount": 0,
                                    "probability_weight": 0,
                                    "inventory_total": 1,
                                    "redemption_method": "in_app_wallet"}])
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    # Start
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                              json={}, timeout=10).json()
    sid = s["session_id"]
    # Submit (spin doesn't need client input)
    res = user_session.post(f"{API}/games_v2/sessions/{sid}/submit",
                                  json={}, timeout=10).json()
    assert res["result"] == "win"
    # Bigcoin auto-credited
    assert res["bigcoin_earned"] == 20


def test_07_scratch_card_happy_path(advertiser_session, admin_session,
                                              user_session):
    cid = _make_campaign(advertiser_session, template_id="tpl_scratch_card")
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                              json={}, timeout=10).json()
    res = user_session.post(f"{API}/games_v2/sessions/{s['session_id']}/submit",
                                  json={"scratched_pct": 0.8}, timeout=10).json()
    assert res["result"] == "win"


def test_08_quiz_happy_path(advertiser_session, admin_session, user_session):
    cid = _make_campaign(
        advertiser_session, template_id="tpl_quiz",
        extra_config={
            "questions": [
                {"prompt": "2+2 = ?", "options": ["3", "4", "5", "6"],
                  "correct_idx": 1},
                {"prompt": "Capital of UAE?",
                  "options": ["Cairo", "Dubai", "Abu Dhabi", "Doha"],
                  "correct_idx": 2},
            ],
            "min_correct_to_win": 2, "dynamic_pool": False,
        })
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                              json={}, timeout=10).json()
    # Win path
    win = user_session.post(f"{API}/games_v2/sessions/{s['session_id']}/submit",
                                  json={"answers": [1, 2]}, timeout=10).json()
    assert win["result"] == "win"
    # Lose path: new session, wrong answer
    s2 = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                 json={}, timeout=10).json()
    lose = user_session.post(f"{API}/games_v2/sessions/{s2['session_id']}/submit",
                                    json={"answers": [0, 0]}, timeout=10).json()
    assert lose["result"] == "lose"


def test_09_mystery_box_happy_path(advertiser_session, admin_session,
                                            user_session):
    cid = _make_campaign(advertiser_session, template_id="tpl_mystery_box")
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                              json={}, timeout=10).json()
    res = user_session.post(f"{API}/games_v2/sessions/{s['session_id']}/submit",
                                  json={"box_idx": 1}, timeout=10).json()
    assert res["result"] == "win"


# ----------------------------------------------------------------------
# Claim + QR + redeem flow
# ----------------------------------------------------------------------
def test_10_coupon_claim_qr_redeem_flow(advertiser_session, admin_session,
                                                 user_session):
    cid = _make_campaign(advertiser_session, template_id="tpl_spin_wheel",
                             extra_config={"segments": [
                                 {"label": "10% off coupon", "color": "#ff2d95",
                                  "probability_weight": 100}]},
                             prizes_overrides=[{
                                 "prize_type": "coupon",
                                 "title": "10% off at Karak Cafe",
                                 "description": "Show QR at any location",
                                 "value_amount": 1000, "value_currency": "AED",
                                 "probability_weight": 100,
                                 "inventory_total": 100,
                                 "redemption_method": "qr_code",
                             }, {
                                 # Filler: spin_wheel needs >=2 prizes
                                 "prize_type": "bigcoin",
                                 "title": "Better luck filler",
                                 "value_amount": 0, "probability_weight": 0,
                                 "inventory_total": 1,
                                 "redemption_method": "in_app_wallet",
                             }])
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                              json={}, timeout=10).json()
    sid = s["session_id"]
    sub = user_session.post(f"{API}/games_v2/sessions/{sid}/submit",
                                  json={}, timeout=10).json()
    assert sub["result"] == "win"
    # Claim to wallet
    c = user_session.post(f"{API}/games_v2/sessions/{sid}/claim_to_wallet",
                              timeout=10).json()
    assert c["wallet_item"] is not None
    wid = c["wallet_item"]["wallet_item_id"]
    # Generate QR
    qr = user_session.post(f"{API}/games_v2/wallet/{wid}/generate_qr",
                                 timeout=10).json()
    assert qr["qr_token"].startswith("gqr_")
    assert qr["qr_image_base64"]
    # Idempotent — second call returns same token
    qr2 = user_session.post(f"{API}/games_v2/wallet/{wid}/generate_qr",
                                  timeout=10).json()
    assert qr2["qr_token"] == qr["qr_token"]
    # Redeem (Phase 8b — now partner-token gated; missing header -> 401)
    no_token = requests.post(f"{API}/games_v2/redeem/{qr['qr_token']}",
                                    timeout=10)
    assert no_token.status_code == 401
    # With a valid partner token issued by admin, redemption works
    pt = admin_session.post(f"{API}/games_v2/admin/partner_tokens",
                                  json={"partner_business_id": "biz_test",
                                          "scopes": ["redeem_campaigns"]},
                                  timeout=10).json()
    raw_secret = pt["raw_secret"]
    red = requests.post(f"{API}/games_v2/redeem/{qr['qr_token']}",
                              headers={"Authorization": f"Partner {raw_secret}"},
                              timeout=10).json()
    assert red["ok"] is True
    assert red["wallet_item"]["status"] == "redeemed"
    # Cannot re-redeem (even with valid token)
    again = requests.post(f"{API}/games_v2/redeem/{qr['qr_token']}",
                                headers={"Authorization": f"Partner {raw_secret}"},
                                timeout=10)
    assert again.status_code == 400
    # Wallet items endpoint shows it
    items = user_session.get(f"{API}/wallet/items", timeout=10)
    assert items.status_code == 200
    found = [w for w in items.json().get("items", [])
                 if w.get("_id") == wid or w.get("id") == wid]
    assert len(found) >= 1


# ----------------------------------------------------------------------
# Probability weight validator
# ----------------------------------------------------------------------
def test_11_prize_weights_must_sum_to_100(advertiser_session):
    payload = {
        "template_id": "tpl_spin_wheel",
        "title": "Bad weights", "sponsor_name": "X",
        "prizes": [
            {"prize_type": "bigcoin", "title": "A", "value_amount": 1,
              "probability_weight": 40, "inventory_total": 10,
              "redemption_method": "in_app_wallet"},
            {"prize_type": "bigcoin", "title": "B", "value_amount": 2,
              "probability_weight": 30, "inventory_total": 10,
              "redemption_method": "in_app_wallet"},
        ],
        "compliance": {"terms_text": "x", "odds_disclosure": "x",
                         "no_purchase_necessary_text": "x"},
    }
    r = advertiser_session.post(f"{API}/games_v2/advertiser/campaigns",
                                       json=payload, timeout=10)
    cid = r.json()["campaign_id"]
    bad = advertiser_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/submit_for_approval",
        timeout=10)
    assert bad.status_code == 400
    assert "weights_must_sum_to_100" in bad.json()["detail"]


# ----------------------------------------------------------------------
# Atomic inventory drain
# ----------------------------------------------------------------------
def test_12_atomic_inventory_drain(advertiser_session, admin_session,
                                            premium_session, user_session):
    """Fire 20 concurrent submits against a 5-inventory campaign.
    Assert exactly 5 wins (the rest get re-weighted to a 'lose' since the
    sole prize is the only one in the pool)."""
    cid = _make_campaign(
        advertiser_session, template_id="tpl_spin_wheel",
        extra_config={"segments": [{"label": "Rare", "color": "#ff2d95",
                                          "probability_weight": 100}]},
        prizes_overrides=[{
            "prize_type": "bigcoin", "title": "Rare 1 BC",
            "value_amount": 1, "probability_weight": 100,
            "inventory_total": 5,
            "redemption_method": "in_app_wallet"},
            {"prize_type": "bigcoin", "title": "Filler",
              "value_amount": 0, "probability_weight": 0,
              "inventory_total": 1,
              "redemption_method": "in_app_wallet"}])
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)

    # Create 20 fake users + sessions (idempotent — wipe any leftovers first)
    from pymongo import MongoClient
    sdb = MongoClient(MONGO)[DB_NAME]
    sdb.users.delete_many({"email": {"$regex": r"^drain\d+@bigfm\.io$"}})
    db = _mongo()
    async def setup_users():
        users = []
        from auth import hash_password
        from datetime import datetime
        for i in range(20):
            uid = f"user_drain_{uuid.uuid4().hex[:10]}"
            await db.users.insert_one({
                "_id": uid, "user_id": uid,
                "email": f"drain{i}@bigfm.io",
                "password_hash": hash_password("DrainTest123!"),
                "name": f"Drain {i}", "role": "user",
                "is_premium": False, "billing_status": "active",
                "reward_multiplier": 1.0,
                "created_at": datetime.utcnow(),
            })
            users.append(uid)
        return users
    uids = _run(setup_users())

    def fire(uid):
        s = requests.Session()
        idx = uids.index(uid)
        s.post(f"{API}/auth/login",
                  json={"email": f"drain{idx}@bigfm.io",
                        "password": "DrainTest123!"}, timeout=10)
        start = s.post(f"{API}/games_v2/campaigns/{cid}/start",
                          json={}, timeout=10).json()
        sid = start.get("session_id")
        if not sid: return None
        sub = s.post(f"{API}/games_v2/sessions/{sid}/submit",
                        json={}, timeout=10).json()
        return sub.get("result")

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(fire, uids))
    wins = sum(1 for r in results if r == "win")
    print(f"drain test results: {results}, wins={wins}")
    assert wins == 5, f"expected exactly 5 wins, got {wins}: {results}"

    # Cleanup — use sync pymongo to avoid motor event-loop reuse issues
    from pymongo import MongoClient
    sdb = MongoClient(MONGO)[DB_NAME]
    sdb.users.delete_many({"user_id": {"$in": uids}})
    sdb.game_sessions.delete_many({"user_id": {"$in": uids}})


# ----------------------------------------------------------------------
# Driving mode
# ----------------------------------------------------------------------
def test_13_driving_mode_blocks_start(user_session):
    # Toggle ON
    on = user_session.post(f"{API}/games_v2/user/driving_mode",
                                 json={"on": True}, timeout=10).json()
    assert on["driving_mode_on"] is True
    # Start blocked
    r = user_session.post(
        f"{API}/games_v2/campaigns/cmp_house_spin/start",
        json={}, timeout=10)
    assert r.status_code == 423
    assert r.json()["detail"] == "driving_mode_active"
    # Toggle OFF
    off = user_session.post(f"{API}/games_v2/user/driving_mode",
                                  json={"on": False}, timeout=10).json()
    assert off["driving_mode_on"] is False
    # Start works
    r2 = user_session.post(
        f"{API}/games_v2/campaigns/cmp_house_spin/start",
        json={}, timeout=10)
    assert r2.status_code == 200
    sid = r2.json()["session_id"]
    # save_for_later
    sv = user_session.post(f"{API}/games_v2/sessions/{sid}/save_for_later",
                                  timeout=10)
    assert sv.status_code == 200


# ----------------------------------------------------------------------
# Admin lifecycle
# ----------------------------------------------------------------------
def test_14_admin_approve_reject_pause_resume(advertiser_session,
                                                          admin_session):
    cid = _make_campaign(advertiser_session, template_id="tpl_spin_wheel",
                              extra_config={"segments": [
                                  {"label": "X", "color": "#fff",
                                   "probability_weight": 100}]})
    # Submit
    _submit_for_approval(advertiser_session, cid)
    # Reject without reason → 400
    bad = admin_session.post(f"{API}/games_v2/admin/campaigns/{cid}/reject",
                                    json={}, timeout=10)
    assert bad.status_code == 400
    # Reject with reason → 200
    r = admin_session.post(f"{API}/games_v2/admin/campaigns/{cid}/reject",
                                 json={"reason": "Sponsor logo missing"},
                                 timeout=10)
    assert r.status_code == 200
    # Resubmit & approve
    edit = advertiser_session.patch(
        f"{API}/games_v2/advertiser/campaigns/{cid}",
        json={"sponsor_logo_url": "/static/test.png"}, timeout=10)
    assert edit.status_code == 200
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    # Pause
    p = admin_session.post(f"{API}/games_v2/admin/campaigns/{cid}/force_pause",
                                 timeout=10)
    assert p.status_code == 200
    # Resume
    rs = admin_session.post(f"{API}/games_v2/admin/campaigns/{cid}/resume",
                                  timeout=10)
    assert rs.status_code == 200


def test_15_admin_adjust_inventory(advertiser_session, admin_session):
    cid = _make_campaign(advertiser_session, template_id="tpl_spin_wheel",
                              extra_config={"segments": [{"label": "X",
                                                                "color": "#fff",
                                                                "probability_weight": 100}]})
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    async def first_prize_id():
        p = await _mongo().game_prizes.find_one({"campaign_id": cid})
        return p["prize_id"]
    pid = _run(first_prize_id())
    r = admin_session.post(
        f"{API}/games_v2/admin/campaigns/{cid}/adjust_inventory",
        json={"prize_id": pid, "delta": 500, "reason": "test"},
        timeout=10)
    assert r.status_code == 200
    assert r.json()["inventory_remaining"] >= 500
    # Ledger entry
    async def ledger_count():
        return await _mongo().game_inventory_ledger.count_documents(
            {"campaign_id": cid, "reason": "test"})
    assert _run(ledger_count()) == 1


def test_16_admin_queue_shows_pending(advertiser_session, admin_session):
    cid = _make_campaign(advertiser_session, template_id="tpl_spin_wheel",
                              extra_config={"segments": [{"label": "X",
                                                                "color": "#fff",
                                                                "probability_weight": 100}]})
    _submit_for_approval(advertiser_session, cid)
    q = admin_session.get(f"{API}/games_v2/admin/queue", timeout=10).json()
    assert any(c["campaign_id"] == cid for c in q["items"])


# ----------------------------------------------------------------------
# max_per_user
# ----------------------------------------------------------------------
def test_17_max_per_user_enforced(advertiser_session, admin_session,
                                          user_session):
    cid = _make_campaign(
        advertiser_session, template_id="tpl_spin_wheel",
        extra_config={"segments": [{"label": "X", "color": "#fff",
                                          "probability_weight": 100}]},
        prizes_overrides=[{
            "prize_type": "bigcoin", "title": "BC",
            "value_amount": 1, "probability_weight": 100,
            "inventory_total": 1000, "max_per_user": 2,
            "redemption_method": "in_app_wallet"},
            {"prize_type": "bigcoin", "title": "Filler",
              "value_amount": 0, "probability_weight": 0,
              "inventory_total": 1, "max_per_user": 0,
              "redemption_method": "in_app_wallet"}])
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    # Cleanup any prior sessions for this campaign + user
    async def cleanup():
        await _mongo().game_sessions.delete_many(
            {"user_id": user_session._user_id, "campaign_id": cid})
        await _mongo().game_rate_limits.delete_many(
            {"_id": {"$regex": f".*{cid}.*"}})
    _run(cleanup())
    # Play 2 → OK; 3rd start blocked
    for i in range(2):
        s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                  json={}, timeout=10)
        assert s.status_code == 200, f"play {i} failed: {s.text}"
        user_session.post(
            f"{API}/games_v2/sessions/{s.json()['session_id']}/submit",
            json={}, timeout=10)
    over = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                    json={}, timeout=10)
    assert over.status_code == 400
    assert over.json()["detail"] == "max_per_user_reached"


# ----------------------------------------------------------------------
# Smoke — no regression on the rest of the platform
# ----------------------------------------------------------------------
def test_18_smoke_no_regression(user_session, premium_session):
    # radio start (premium)
    r = premium_session.get(f"{API}/bigcoin/me", timeout=10)
    assert r.status_code == 200
    r = premium_session.get(f"{API}/billing/status", timeout=10)
    assert r.status_code == 200
    r = requests.get(f"{API}/lobbies/list", timeout=10)
    assert r.status_code == 200
    r = user_session.get(f"{API}/channels", timeout=10)
    assert r.status_code == 200


def test_19_clone_campaign(advertiser_session, admin_session):
    cid = _make_campaign(advertiser_session, template_id="tpl_spin_wheel",
                              extra_config={"segments": [{"label": "X",
                                                                "color": "#fff",
                                                                "probability_weight": 100}]})
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/clone", timeout=10)
    assert r.status_code == 200
    new_cid = r.json()["campaign_id"]
    assert new_cid != cid
    async def n_prizes(c):
        return await _mongo().game_prizes.count_documents({"campaign_id": c})
    assert _run(n_prizes(new_cid)) == _run(n_prizes(cid))


def test_20_analytics_endpoint(advertiser_session, admin_session,
                                       user_session):
    cid = _make_campaign(advertiser_session, template_id="tpl_spin_wheel",
                              extra_config={"segments": [{"label": "X",
                                                                "color": "#fff",
                                                                "probability_weight": 100}]})
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                              json={}, timeout=10).json()
    user_session.post(f"{API}/games_v2/sessions/{s['session_id']}/submit",
                          json={}, timeout=10)
    r = advertiser_session.get(
        f"{API}/games_v2/advertiser/campaigns/{cid}/analytics", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["counters"].get("start", 0) >= 1
    assert body["counters"].get("win", 0) >= 0
    assert isinstance(body["inventory"], list)


def test_21_template_inactive_blocks_create(advertiser_session, admin_session):
    # Phase 8b activated slot/memory/word; deactivate spin temporarily to
    # prove the gate still rejects inactive templates.  We re-activate
    # after the test so other suites are unaffected.
    target = "tpl_spin_wheel"
    admin_session.post(f"{API}/games_v2/admin/templates/{target}/deactivate",
                              timeout=10)
    try:
        bad = advertiser_session.post(f"{API}/games_v2/advertiser/campaigns",
                                              json={"template_id": target,
                                                    "title": "x"}, timeout=10)
        assert bad.status_code == 400
        assert "template_not_active" in bad.json()["detail"]
    finally:
        admin_session.post(f"{API}/games_v2/admin/templates/{target}/activate",
                                  timeout=10)


# ====================================================================
# Phase 8a.1 — three fixes from tester
# ====================================================================
def test_22_no_leaks_in_start_response_spin_wheel(advertiser_session,
                                                              admin_session,
                                                              user_session):
    """spin_wheel.segments must NOT include probability_weight or prize_id."""
    cid = _make_campaign(advertiser_session, template_id="tpl_spin_wheel",
                              extra_config={"segments": [
                                  {"label": "A", "color": "#fff",
                                   "probability_weight": 60, "prize_id": "leaked-1"},
                                  {"label": "B", "color": "#000",
                                   "probability_weight": 40, "prize_id": "leaked-2"}]})
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                              json={}, timeout=10).json()
    segments = s["render_config"]["segments"]
    blob = json.dumps(s)
    for seg in segments:
        assert "probability_weight" not in seg, f"LEAK: {seg}"
        assert "prize_id" not in seg, f"LEAK: {seg}"
    assert "probability_weight" not in blob
    assert "leaked-1" not in blob and "leaked-2" not in blob


def test_23_no_leaks_in_start_response_quiz_dynamic(user_session):
    """quiz dynamic-pool: render_config.questions[*] must NOT include correct_idx."""
    # House trivia uses dynamic_pool=True
    s = user_session.post(f"{API}/games_v2/campaigns/cmp_house_trivia/start",
                              json={}, timeout=10).json()
    qs = s["render_config"]["questions"]
    for q in qs:
        assert "correct_idx" not in q, f"LEAK: {q}"
    assert "correct_idx" not in json.dumps(s)


def test_24_no_leaks_in_start_response_quiz_static(advertiser_session,
                                                              admin_session,
                                                              user_session):
    """quiz static-pool: render_config.questions[*] must NOT include correct_idx."""
    cid = _make_campaign(
        advertiser_session, template_id="tpl_quiz",
        extra_config={
            "questions": [
                {"prompt": "Q1", "options": ["A", "B", "C", "D"],
                  "correct_idx": 2},
                {"prompt": "Q2", "options": ["W", "X", "Y", "Z"],
                  "correct_idx": 0},
            ],
            "min_correct_to_win": 1, "dynamic_pool": False,
        })
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                              json={}, timeout=10).json()
    for q in s["render_config"]["questions"]:
        assert "correct_idx" not in q
    assert "correct_idx" not in json.dumps(s["render_config"])


def test_25_no_leaks_in_start_response_mystery_box(advertiser_session,
                                                              admin_session,
                                                              user_session):
    """mystery_box.boxes must NOT include prize_id."""
    cid = _make_campaign(
        advertiser_session, template_id="tpl_mystery_box",
        extra_config={"boxes": [
            {"label": "Box A", "image_url": "/a.png", "prize_id": "leak-mb-1"},
            {"label": "Box B", "image_url": "/b.png", "prize_id": "leak-mb-2"},
            {"label": "Box C", "image_url": "/c.png", "prize_id": "leak-mb-3"},
        ]})
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                              json={}, timeout=10).json()
    blob = json.dumps(s)
    for b in s["render_config"]["boxes"]:
        assert "prize_id" not in b, f"LEAK: {b}"
    assert "leak-mb-1" not in blob


def test_26_no_leaks_in_start_response_scratch_card(advertiser_session,
                                                                admin_session,
                                                                user_session):
    """scratch_card: render_config must NOT contain any prize title/value
    before the user scratches.  Only generic cover/reveal foil URLs."""
    cid = _make_campaign(advertiser_session,
                              template_id="tpl_scratch_card")
    _submit_for_approval(advertiser_session, cid)
    _admin_approve(admin_session, cid)
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                              json={}, timeout=10).json()
    rc = s["render_config"]
    blob = json.dumps(rc)
    # No probability weights, no prize values, no prize titles
    assert "probability_weight" not in blob
    assert "value_amount" not in blob
    assert "20 BC" not in blob and "50 BC" not in blob   # default test prize titles


def test_27_save_for_later_round_trip(admin_session, user_session):
    """Phase 8a.1 — drive the full save-for-later cycle:
       driving ON → start blocked → save campaign for later → driving OFF
       → start succeeds → saved unlock flips to `played=True`."""
    target = user_session._user_id
    # House trivia (open_to_all) is fine for the test
    campaign_id = "cmp_house_trivia"
    # Ensure clean slate (no prior unlocks for this user on this campaign)
    from pymongo import MongoClient
    sdb = MongoClient(MONGO)[DB_NAME]
    sdb.user_game_unlocks.delete_many({"user_id": target, "campaign_id": campaign_id})
    sdb.game_sessions.delete_many({"user_id": target, "campaign_id": campaign_id})
    # 1. Driving ON
    on = user_session.post(f"{API}/games_v2/user/driving_mode",
                                 json={"on": True}, timeout=10).json()
    assert on["driving_mode_on"] is True
    # 2. Start blocked
    blocked = user_session.post(f"{API}/games_v2/campaigns/{campaign_id}/start",
                                       json={}, timeout=10)
    assert blocked.status_code == 423
    # 3. Save for later
    save = user_session.post(
        f"{API}/games_v2/campaigns/{campaign_id}/save_for_later",
        timeout=10).json()
    assert save["saved_for_later"] is True
    assert save["extended"] is False
    unlock_id = save["unlock_id"]
    # Second call extends, not duplicates
    save2 = user_session.post(
        f"{API}/games_v2/campaigns/{campaign_id}/save_for_later",
        timeout=10).json()
    assert save2["unlock_id"] == unlock_id
    assert save2["extended"] is True
    # 4. Driving OFF
    off = user_session.post(f"{API}/games_v2/user/driving_mode",
                                  json={"on": False}, timeout=10).json()
    assert off["driving_mode_on"] is False
    # 5. Start now succeeds
    started = user_session.post(f"{API}/games_v2/campaigns/{campaign_id}/start",
                                       json={}, timeout=10)
    assert started.status_code == 200, started.text
    sid = started.json()["session_id"]
    # Submit so the unlock flips to played=true
    user_session.post(f"{API}/games_v2/sessions/{sid}/submit",
                          json={"answer_idx": 0}, timeout=10)
    # 6. Verify unlock is consumed
    unlock = sdb.user_game_unlocks.find_one({"_id": unlock_id})
    assert unlock["played"] is True
    assert unlock["played_at"] is not None


def test_28_house_campaigns_are_immortal():
    """Phase 8a.1 — house campaigns must have end_at=None forever."""
    from pymongo import MongoClient
    sdb = MongoClient(MONGO)[DB_NAME]
    for cid in ("cmp_house_spin", "cmp_house_trivia", "cmp_house_lyric"):
        c = sdb.game_campaigns.find_one({"campaign_id": cid})
        assert c is not None, f"missing {cid}"
        assert c.get("end_at") is None, f"house {cid} has end_at={c.get('end_at')}"


def test_29_rate_limit_doc_matches_sliding_window():
    """Phase 8a.1 — confirm the 30/hour sliding-window semantics.
       NB: we don't fire 30 starts in a real HTTP loop (too slow); we
       seed the bucket directly with 30 recent timestamps and assert
       the next start raises rate_limited, then ageing out one
       timestamp lets the next call succeed."""
    from pymongo import MongoClient
    from datetime import datetime, timezone, timedelta
    import uuid
    sdb = MongoClient(MONGO)[DB_NAME]
    s = _login("test@bigfm.dubai", "TestUser123!")
    target = s._user_id
    cid = "cmp_house_trivia"
    bucket_key = f"{target}|{cid}|start"
    # Wipe state
    sdb.game_rate_limits.delete_one({"_id": bucket_key})
    sdb.user_game_unlocks.delete_many({"user_id": target, "campaign_id": cid})
    sdb.game_sessions.delete_many({"user_id": target, "campaign_id": cid})
    sdb.users.update_one({"user_id": target}, {"$set": {"driving_mode_on": False}})
    now = datetime.now(timezone.utc)
    # Seed 30 timestamps all within the last 5 minutes
    sdb.game_rate_limits.replace_one(
        {"_id": bucket_key},
        {"_id": bucket_key,
         "timestamps": [now - timedelta(seconds=10 * i) for i in range(30)],
         "ttl_at": now + timedelta(hours=1)},
        upsert=True,
    )
    # 31st start → must hit rate_limited (429)
    r = s.post(f"{API}/games_v2/campaigns/{cid}/start", json={}, timeout=10)
    assert r.status_code == 429, f"expected 429, got {r.status_code}: {r.text}"
    assert r.json()["detail"] == "rate_limited"
    # Age out all 30 (push them past the 1-hour window)
    sdb.game_rate_limits.update_one(
        {"_id": bucket_key},
        {"$set": {"timestamps": [now - timedelta(hours=2)]}},
    )
    ok = s.post(f"{API}/games_v2/campaigns/{cid}/start", json={}, timeout=10)
    assert ok.status_code == 200, ok.text
    # Cleanup
    sdb.game_rate_limits.delete_one({"_id": bucket_key})
