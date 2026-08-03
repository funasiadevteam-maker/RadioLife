"""Phase 8b — Gamification Distribution, Milestones, 3 New Games pytest suite.

Drives the live FastAPI server through `requests`. Covers:
  - Listener milestone auto-unlock engine (rules seeded, listening_minutes_daily)
  - Public game landing pages (/api/public/game/{slug} & QR PNG)
  - RJ game-announce candidate selector + frequency cap
  - 3 new game types: slot_machine, memory_match, word_puzzle (start → submit)
  - Asset upload (MIME / size whitelist)
  - Partner-token gated redemption (401 without token, 200 with valid)
"""
from __future__ import annotations

import asyncio
import io
import os
import uuid
from datetime import datetime, timezone, timedelta

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


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def user_session():
    return _login("test@bigfm.dubai", "TestUser123!")


@pytest.fixture(scope="module")
def advertiser_session():
    return _login("advertiser@bigfm.dubai", "AdvertiserP8!23")


# ====================================================================
# 1. Milestone auto-unlock engine
# ====================================================================
def test_01_unlock_rules_seeded():
    async def check():
        db = _mongo()
        n = await db.unlock_rules.count_documents({})
        active = await db.unlock_rules.count_documents({"active": True})
        return n, active
    n, active = _run(check())
    assert n == 10, f"expected 10 unlock_rules seeded, got {n}"
    # Phase 9a activated rule_commute_completed; now 9 active.
    assert active == 9


def test_02_admin_list_unlock_rules(admin_session):
    r = admin_session.get(f"{API}/games_v2/admin/unlock_rules", timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 10
    rule_ids = {x["rule_id"] for x in items}
    for must_have in ("rule_listen_15m", "rule_listen_30m",
                          "rule_listen_60m", "rule_lobby_join",
                          "rule_ad_save", "rule_referral"):
        assert must_have in rule_ids


def test_03_admin_toggle_unlock_rule(admin_session):
    # Toggle off then on, verify state
    r = admin_session.post(
        f"{API}/games_v2/admin/unlock_rules/rule_listen_15m/toggle_active",
        timeout=10)
    assert r.status_code == 200
    state1 = r.json()["active"]
    r = admin_session.post(
        f"{API}/games_v2/admin/unlock_rules/rule_listen_15m/toggle_active",
        timeout=10)
    state2 = r.json()["active"]
    assert state1 != state2  # toggled
    # Final: ensure rule_listen_15m ends up active
    async def ensure_active():
        db = _mongo()
        await db.unlock_rules.update_one(
            {"rule_id": "rule_listen_15m"}, {"$set": {"active": True}})
    _run(ensure_active())


def test_04_heartbeat_triggers_15m_unlock(user_session):
    """Simulate 15 fake heartbeat tx in bigcoin_transactions today, then
    POST /api/bigcoin/heartbeat to trigger the unlock evaluation hook."""
    uid = user_session._user_id
    async def setup():
        db = _mongo()
        # Wipe any existing daily unlocks for the user for rule_listen_15m
        bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        await db.user_game_unlocks.delete_many(
            {"user_id": uid, "rule_id": "rule_listen_15m", "period_bucket": bucket})
        # Insert 15 heartbeat tx rows for today
        now = datetime.now(timezone.utc)
        docs = [{"_id": f"tx_mock_{uuid.uuid4().hex[:10]}",
                  "user_id": uid, "amount": 1, "reason": "heartbeat",
                  "balance_after": 1, "created_at": now,
                  "metadata": {"mock": True}}
                 for _ in range(15)]
        await db.bigcoin_transactions.insert_many(docs)
        return bucket
    bucket = _run(setup())
    # Fire the heartbeat (which runs check_listening_unlocks)
    r = user_session.post(f"{API}/bigcoin/heartbeat",
                                 json={"session_id": "mock-session"}, timeout=15)
    assert r.status_code == 200
    # Validate: a user_game_unlocks row for rule_listen_15m today exists
    async def verify():
        db = _mongo()
        u = await db.user_game_unlocks.find_one(
            {"user_id": uid, "rule_id": "rule_listen_15m",
             "period_bucket": bucket})
        return u
    unlock = _run(verify())
    assert unlock is not None, "rule_listen_15m unlock not awarded"
    assert unlock["played"] is False
    assert unlock["campaign_id"]


def test_05_idempotent_unlock_no_dup(user_session):
    uid = user_session._user_id
    async def count_unlocks():
        db = _mongo()
        bucket = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return await db.user_game_unlocks.count_documents(
            {"user_id": uid, "rule_id": "rule_listen_15m",
             "period_bucket": bucket})
    n1 = _run(count_unlocks())
    # Fire heartbeat 3 more times — should NOT create new unlocks for the
    # same period bucket
    for _ in range(3):
        user_session.post(f"{API}/bigcoin/heartbeat",
                                 json={"session_id": "mock-session"}, timeout=15)
    n2 = _run(count_unlocks())
    assert n2 == n1, f"unlock duplicated! before={n1} after={n2}"


def test_06_me_unlocks_endpoint(user_session):
    r = user_session.get(f"{API}/games_v2/me/unlocks", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    # At least the 15m unlock from test 04 should appear
    rule_ids = [it.get("rule_id") for it in body["items"]]
    assert "rule_listen_15m" in rule_ids


# ====================================================================
# 2. RJ game-announce candidate + frequency cap
# ====================================================================
def test_10_announce_candidate_returns(user_session):
    # Reset frequency-cap state for this user
    uid = user_session._user_id
    async def reset():
        db = _mongo()
        await db.rj_game_mentions_log.delete_many({"user_id": uid})
    _run(reset())
    r = user_session.get(f"{API}/games_v2/me/active_game_announce", timeout=10)
    assert r.status_code == 200
    body = r.json()
    # Should return an announce (because we have a user_game_unlocks row OR
    # the user can play house games)
    assert "announce" in body
    if body["announce"]:
        a = body["announce"]
        assert a["campaign_id"]
        assert a["title"]
        assert a["source"] in ("unlock", "sponsored", "house")


def test_11_rj_mention_log_and_cooldown(user_session):
    uid = user_session._user_id
    # Log a mention
    r = user_session.post(f"{API}/games_v2/rj_mention_log",
                                 json={"campaign_id": "cmp_house_spin"},
                                 timeout=10)
    assert r.status_code == 200
    # Now the announce endpoint should respect the 30-min cooldown -> None
    r2 = user_session.get(f"{API}/games_v2/me/active_game_announce", timeout=10)
    assert r2.status_code == 200
    assert r2.json()["announce"] is None, "cooldown not honoured"
    # Verify mention_log row + analytics impression row
    async def verify():
        db = _mongo()
        m = await db.rj_game_mentions_log.find_one(
            {"user_id": uid, "campaign_id": "cmp_house_spin"},
            sort=[("ts", -1)])
        evt = await db.game_analytics_events.find_one(
            {"campaign_id": "cmp_house_spin", "event_type": "impression",
             "source_context_json.source": "rj_announce"})
        return m, evt
    m, evt = _run(verify())
    assert m is not None
    assert evt is not None


# ====================================================================
# 3. Public landing page (anonymous)
# ====================================================================
def _approve_house_campaign(admin_session, campaign_id: str) -> str:
    """Helper: ensure house campaign has a public_slug minted."""
    async def get_slug():
        db = _mongo()
        c = await db.game_campaigns.find_one({"campaign_id": campaign_id})
        return (c or {}).get("public_slug")
    slug = _run(get_slug())
    if slug:
        return slug
    # House campaigns are pre-approved.  ensure_public_slug is idempotent:
    async def ensure_slug():
        from services.games_v2 import ensure_public_slug
        db = _mongo()
        return await ensure_public_slug(db, campaign_id)
    return _run(ensure_slug())


def test_20_public_landing_returns(admin_session):
    slug = _approve_house_campaign(admin_session, "cmp_house_spin")
    assert slug
    # Anonymous fetch
    r = requests.get(f"{API}/public/game/{slug}", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == slug
    assert body["campaign_id"] == "cmp_house_spin"
    assert body["title"]
    assert "prizes" in body
    # IMPORTANT: prizes must NOT leak probability_weight
    for p in body["prizes"]:
        assert "probability_weight" not in p
        assert "inventory_remaining" not in p


def test_21_public_landing_qr_png(admin_session):
    slug = _approve_house_campaign(admin_session, "cmp_house_spin")
    r = requests.get(f"{API}/public/game/{slug}/qr.png", timeout=10)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 200, "qr png too small"


def test_22_public_landing_404_for_unknown_slug():
    r = requests.get(f"{API}/public/game/this-slug-does-not-exist", timeout=10)
    assert r.status_code == 404


def test_23_public_landing_records_impression(admin_session):
    slug = _approve_house_campaign(admin_session, "cmp_house_trivia")
    async def before():
        db = _mongo()
        return await db.game_analytics_events.count_documents(
            {"campaign_id": "cmp_house_trivia",
             "event_type": "impression",
             "source_context_json.source": "public_landing"})
    n_before = _run(before())
    requests.get(f"{API}/public/game/{slug}", timeout=10)
    n_after = _run(before())
    assert n_after == n_before + 1


# ====================================================================
# 4. Distribution endpoint
# ====================================================================
def test_30_advertiser_distribution_endpoint(admin_session):
    # admin counts as advertiser for this endpoint
    r = admin_session.get(
        f"{API}/games_v2/advertiser/campaigns/cmp_house_spin/distribution",
        timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["public_slug"]
    assert body["public_url"].startswith("/play/")
    assert body["qr_image_url"].endswith("/qr.png")
    assert "iframe" in body["embed_iframe"]


# ====================================================================
# 5. Asset upload
# ====================================================================
def _make_png_bytes(w=64, h=64) -> bytes:
    from PIL import Image
    img = Image.new("RGB", (w, h), (255, 45, 149))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_40_asset_upload_happy_path(admin_session):
    files = {"file": ("test.png", _make_png_bytes(), "image/png")}
    r = admin_session.post(f"{API}/games_v2/advertiser/assets/upload",
                                  files=files, timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith("/api/games_v2/assets/")
    assert body["asset_id"]
    assert body["width"] == 64
    # And fetch it back
    r2 = requests.get(f"{API.replace('/api', '')}{body['url']}", timeout=10)
    assert r2.status_code == 200
    assert r2.headers["content-type"].startswith("image/")


def test_41_asset_upload_rejects_bad_mime(admin_session):
    files = {"file": ("bad.txt", b"not an image", "text/plain")}
    r = admin_session.post(f"{API}/games_v2/advertiser/assets/upload",
                                  files=files, timeout=15)
    assert r.status_code == 400
    assert "unsupported_mime" in r.json()["detail"]


def test_42_asset_upload_rejects_unauth():
    files = {"file": ("test.png", _make_png_bytes(), "image/png")}
    r = requests.post(f"{API}/games_v2/advertiser/assets/upload",
                            files=files, timeout=10)
    assert r.status_code in (401, 403)


# ====================================================================
# 6. Partner-token gated redemption
# ====================================================================
def test_50_admin_issue_partner_token(admin_session):
    r = admin_session.post(f"{API}/games_v2/admin/partner_tokens",
                                  json={"partner_business_id": "biz_partner_test",
                                          "scopes": ["redeem_campaigns"]},
                                  timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["raw_secret"].startswith("ptk_")
    assert body["partner_token_id"].startswith("ptkid_")
    # Listing endpoint shows it (no secret exposed)
    lst = admin_session.get(f"{API}/games_v2/admin/partner_tokens", timeout=10)
    assert lst.status_code == 200
    found = [t for t in lst.json()["items"]
                if t["partner_token_id"] == body["partner_token_id"]]
    assert found
    assert "secret_hash" not in found[0]


def test_51_redeem_rejects_no_token():
    # Any fake QR token; the gate fires BEFORE QR resolution
    r = requests.post(f"{API}/games_v2/redeem/fakeqrtoken123", timeout=10)
    assert r.status_code == 401
    assert "partner_token_required" in r.json()["detail"]


def test_52_redeem_rejects_invalid_token():
    r = requests.post(f"{API}/games_v2/redeem/fakeqrtoken123",
                            headers={"Authorization": "Partner ptk_bogus_value"},
                            timeout=10)
    assert r.status_code == 401


def test_53_redeem_audit_log_written():
    # Each missing-auth attempt should produce a redemption_audit_log row
    async def count_audits():
        db = _mongo()
        return await db.redemption_audit_log.count_documents(
            {"outcome": "missing_auth"})
    n_before = _run(count_audits())
    requests.post(f"{API}/games_v2/redeem/fakeqrtoken123", timeout=10)
    n_after = _run(count_audits())
    assert n_after >= n_before + 1


def test_54_admin_audit_log_endpoint_4_state(admin_session, user_session):
    """End-to-end: drive the audit through all 4 outcomes
    (missing_auth, success, replay, revoked) and verify the admin
    endpoint lists & filters them."""
    # ── 1. Seed a known wallet item with QR directly (bypass game flow) ─
    cid = "cmp_house_spin"      # any approved house campaign
    uid = user_session._user_id
    wid = f"wi_audit_{uuid.uuid4().hex[:10]}"
    token = f"gqr_AUDIT_{uuid.uuid4().hex[:18]}"
    now = datetime.now(timezone.utc)
    async def seed():
        db = _mongo()
        await db.user_wallet_items.insert_one({
            "_id": wid, "wallet_item_id": wid,
            "user_id": uid, "campaign_id": cid,
            "prize_id": None,
            "title": "Audit Test Item",
            "value_amount": 5, "value_unit": "BC",
            "qr_token": token, "qr_token_prefix": token[:14],
            "status": "ready_to_redeem", "redeemed_at": None,
            "redemption_method": "in_app_wallet",
            "created_at": now, "expires_at": None,
        })
    _run(seed())

    # ── 2. State: missing_auth ─────────────────────────────────────────
    r = requests.post(f"{API}/games_v2/redeem/{token}", timeout=10)
    assert r.status_code == 401

    # ── 3. State: success (use a partner token) ────────────────────────
    pt = admin_session.post(
        f"{API}/games_v2/admin/partner_tokens",
        json={"partner_business_id": "biz_audit_test",
                "scopes": ["redeem_campaigns"]}, timeout=10).json()
    secret = pt["raw_secret"]
    ptid = pt["partner_token_id"]
    r = requests.post(
        f"{API}/games_v2/redeem/{token}",
        headers={"Authorization": f"Partner {secret}",
                  "User-Agent": "AuditTest/1.0"},
        timeout=10)
    assert r.status_code == 200, r.text
    assert r.json()["wallet_item"]["status"] == "redeemed"

    # ── 4. State: replay (same token, same partner) ────────────────────
    r = requests.post(
        f"{API}/games_v2/redeem/{token}",
        headers={"Authorization": f"Partner {secret}"},
        timeout=10)
    assert r.status_code == 400

    # ── 5. State: revoked (revoke the token then try again) ────────────
    admin_session.post(
        f"{API}/games_v2/admin/partner_tokens/{ptid}/revoke", timeout=10)
    r = requests.post(
        f"{API}/games_v2/redeem/{token}",
        headers={"Authorization": f"Partner {secret}"},
        timeout=10)
    assert r.status_code == 401

    # ── 6. Admin endpoint: list all audit rows for THIS wallet item ────
    r = admin_session.get(
        f"{API}/games_v2/admin/redemption_audit_log",
        params={"limit": 200}, timeout=10)
    assert r.status_code == 200
    all_items = r.json()["items"]
    items = [it for it in all_items if it.get("wallet_item_id") == wid]
    outcomes_seen = {it["outcome"] for it in items}
    for it in items:
        assert "audit_id" in it
        assert "ts" in it
        assert "qr_token_prefix" in it
    assert {"missing_auth", "success", "replay", "revoked"} <= outcomes_seen, \
            f"outcomes_seen={outcomes_seen}"

    # ── 7. Filter by outcome=success ───────────────────────────────────
    r = admin_session.get(
        f"{API}/games_v2/admin/redemption_audit_log",
        params={"outcome": "success", "partner_token_id": ptid}, timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    for it in items:
        assert it["outcome"] == "success"
        assert it["partner_token_id"] == ptid

    # ── 8. Filter by partner_token_id ──────────────────────────────────
    r = admin_session.get(
        f"{API}/games_v2/admin/redemption_audit_log",
        params={"partner_token_id": ptid}, timeout=10)
    items = r.json()["items"]
    assert all(it["partner_token_id"] == ptid for it in items)
    # success + replay + revoked attempts all carry the partner_token_id
    assert {"success", "replay", "revoked"} <= {it["outcome"] for it in items}

    # ── 9. Bad outcome filter -> 400 ───────────────────────────────────
    r = admin_session.get(
        f"{API}/games_v2/admin/redemption_audit_log",
        params={"outcome": "bogus"}, timeout=10)
    assert r.status_code == 400

    # ── 10. Pagination: limit=1 yields next_cursor that returns row 2 ──
    r = admin_session.get(
        f"{API}/games_v2/admin/redemption_audit_log",
        params={"partner_token_id": ptid, "limit": 1}, timeout=10)
    page1 = r.json()
    assert len(page1["items"]) == 1
    assert page1.get("next_cursor")
    r2 = admin_session.get(
        f"{API}/games_v2/admin/redemption_audit_log",
        params={"partner_token_id": ptid, "limit": 1,
                  "cursor": page1["next_cursor"]}, timeout=10)
    page2 = r2.json()
    assert len(page2["items"]) == 1
    assert page1["items"][0]["audit_id"] != page2["items"][0]["audit_id"]


def test_55_admin_audit_log_requires_admin():
    """Non-admin (anonymous) cannot read the audit log."""
    r = requests.get(f"{API}/games_v2/admin/redemption_audit_log",
                          timeout=10)
    assert r.status_code in (401, 403)


# ====================================================================
# Asset Content-Type
# ====================================================================
def test_56_asset_serve_exact_content_type(admin_session):
    """Phase 8b.1 — `/api/games_v2/assets/{filename}` must return the
    exact `image/png|jpeg|webp` MIME, never `image/*`."""
    # Upload one PNG and one JPEG and check each Content-Type
    png_files = {"file": ("test.png", _make_png_bytes(), "image/png")}
    png_resp = admin_session.post(
        f"{API}/games_v2/advertiser/assets/upload",
        files=png_files, timeout=15).json()
    png_url = png_resp["url"]

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (10, 200, 50)).save(buf, format="JPEG")
    jpeg_files = {"file": ("test.jpg", buf.getvalue(), "image/jpeg")}
    jpeg_resp = admin_session.post(
        f"{API}/games_v2/advertiser/assets/upload",
        files=jpeg_files, timeout=15).json()
    jpeg_url = jpeg_resp["url"]

    api_origin = API.replace("/api", "")
    head_png = requests.head(f"{api_origin}{png_url}", timeout=10)
    assert head_png.status_code == 200
    assert head_png.headers["content-type"] == "image/png", \
            f"png ct={head_png.headers.get('content-type')}"

    head_jpeg = requests.head(f"{api_origin}{jpeg_url}", timeout=10)
    assert head_jpeg.status_code == 200
    assert head_jpeg.headers["content-type"] == "image/jpeg", \
            f"jpeg ct={head_jpeg.headers.get('content-type')}"

    # Plus a GET confirms body still serves correctly
    get_png = requests.get(f"{api_origin}{png_url}", timeout=10)
    assert get_png.status_code == 200
    assert get_png.headers["content-type"] == "image/png"
    assert "image/*" not in get_png.headers["content-type"]



# ====================================================================
# 7. Three new games (Slot, Memory, Word Puzzle)
# ====================================================================
def _make_house_campaign(admin_session, template_id: str, title: str) -> str:
    """Create + auto-approve a campaign for a template we want to test."""
    # Use admin as advertiser
    r = admin_session.post(f"{API}/games_v2/advertiser/campaigns",
                                  json={"template_id": template_id,
                                          "title": title,
                                          "open_to_all": True,
                                          "prizes": [{
                                              "prize_type": "bigcoin",
                                              "title": "5 BigCoin",
                                              "value_amount": 5,
                                              "probability_weight": 100,
                                              "inventory_total": 1000,
                                              "redemption_method": "in_app_wallet",
                                          }],
                                          "compliance": {
                                              "terms_text": "Test terms",
                                              "odds_disclosure": "Odds vary",
                                              "no_purchase_necessary_text": "No purchase necessary",
                                          },
                                          "redemption_rules": {"expiration_days": 30}},
                                  timeout=15)
    assert r.status_code == 200, r.text
    cid = r.json()["campaign_id"]
    sub = admin_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/submit_for_approval",
        timeout=15)
    assert sub.status_code == 200, sub.text
    appr = admin_session.post(
        f"{API}/games_v2/admin/campaigns/{cid}/approve", timeout=15)
    assert appr.status_code == 200
    return cid


def test_60_slot_machine_happy_path(admin_session, user_session):
    cid = _make_house_campaign(admin_session, "tpl_slot_machine",
                                       "Test Slots 8b")
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                  json={}, timeout=15)
    assert s.status_code == 200, s.text
    sess = s.json()
    cfg = sess["render_config"]
    assert cfg["type"] == "slot_machine"
    assert "reels" in cfg
    assert "positions" in cfg
    assert len(cfg["positions"]) == len(cfg["reels"])
    # IMPORTANT: weights stripped from public reels payload
    for reel in cfg["reels"]:
        for sym in reel:
            assert "weight" not in sym
    # Submit (server already pinned the outcome — we just trigger eval)
    sub = user_session.post(
        f"{API}/games_v2/sessions/{sess['session_id']}/submit",
        json={}, timeout=15)
    assert sub.status_code == 200, sub.text
    body = sub.json()
    assert body["result"] in ("win", "lose")
    assert body["quiz_meta"]["symbols"]
    assert "win_combo_hit" in body["quiz_meta"]


def test_61_memory_match_happy_path(admin_session, user_session):
    cid = _make_house_campaign(admin_session, "tpl_memory_match",
                                       "Test Memory 8b")
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                  json={}, timeout=15)
    assert s.status_code == 200, s.text
    sess = s.json()
    cfg = sess["render_config"]
    assert cfg["type"] == "memory_match"
    assert "deck" in cfg and len(cfg["deck"]) == 16  # 4x4 grid
    # Sufficient pairs found
    sub = user_session.post(
        f"{API}/games_v2/sessions/{sess['session_id']}/submit",
        json={"pairs_found": 8, "time_spent_sec": 60}, timeout=15)
    assert sub.status_code == 200, sub.text
    body = sub.json()
    assert body["result"] == "win"
    assert body["quiz_meta"]["pairs_found"] == 8


def test_62_memory_match_loses_under_threshold(admin_session, user_session):
    cid = _make_house_campaign(admin_session, "tpl_memory_match",
                                       "Test Memory 8b - lose")
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                  json={}, timeout=15).json()
    sub = user_session.post(
        f"{API}/games_v2/sessions/{s['session_id']}/submit",
        json={"pairs_found": 1, "time_spent_sec": 60}, timeout=15)
    assert sub.status_code == 200
    assert sub.json()["result"] == "lose"


def test_63_word_puzzle_happy_path(admin_session, user_session):
    cid = _make_house_campaign(admin_session, "tpl_word_puzzle",
                                       "Test Word 8b")
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                  json={}, timeout=15)
    assert s.status_code == 200, s.text
    sess = s.json()
    cfg = sess["render_config"]
    assert cfg["type"] == "word_puzzle"
    assert "_" in cfg["masked"]
    assert cfg["max_strikes"] >= 1
    # Fetch the target phrase from DB so we can submit the correct answer
    async def get_target():
        db = _mongo()
        s = await db.game_sessions.find_one({"session_id": sess["session_id"]})
        return s["target_phrase"]
    target = _run(get_target())
    sub = user_session.post(
        f"{API}/games_v2/sessions/{sess['session_id']}/submit",
        json={"attempted_phrase": target, "strikes_used": 2}, timeout=15)
    assert sub.status_code == 200
    body = sub.json()
    assert body["result"] == "win"
    assert body["quiz_meta"]["solved"] is True


def test_64_word_puzzle_wrong_answer_loses(admin_session, user_session):
    cid = _make_house_campaign(admin_session, "tpl_word_puzzle",
                                       "Test Word 8b - wrong")
    s = user_session.post(f"{API}/games_v2/campaigns/{cid}/start",
                                  json={}, timeout=15).json()
    sub = user_session.post(
        f"{API}/games_v2/sessions/{s['session_id']}/submit",
        json={"attempted_phrase": "WRONG ANSWER", "strikes_used": 5}, timeout=15)
    assert sub.status_code == 200
    assert sub.json()["result"] == "lose"


# ====================================================================
# 8. Smoke regressions
# ====================================================================
def test_90_smoke_play_and_win_still_returns(user_session):
    r = user_session.get(f"{API}/games_v2/play_and_win", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "unlocked_for_you" in body
    assert "played_history" in body


def test_91_openapi_lists_8b_routes():
    r = requests.get(f"{API}/openapi.json", timeout=10)
    assert r.status_code == 200
    paths = list(r.json()["paths"].keys())
    must_have = [
        "/api/public/game/{slug}",
        "/api/public/game/{slug}/qr.png",
        "/api/games_v2/me/active_game_announce",
        "/api/games_v2/me/unlocks",
        "/api/games_v2/rj_mention_log",
        "/api/games_v2/admin/unlock_rules",
        "/api/games_v2/admin/partner_tokens",
        "/api/games_v2/advertiser/assets/upload",
        "/api/games_v2/advertiser/campaigns/{campaign_id}/distribution",
    ]
    missing = [m for m in must_have if m not in paths]
    assert not missing, f"missing 8b routes in openapi: {missing}"
