"""Phase 18c — 10 tests: pacing, freq caps, attribution, hygiene, push."""
import asyncio, os, sys, time, secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motor.motor_asyncio import AsyncIOMotorClient

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN   = os.environ.get("DB_NAME",   "bigfm")

def run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed(): raise RuntimeError
    except RuntimeError:
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

NOW = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


# ─── PACING ───────────────────────────────────────────────────────
def test_pacing_status_ahead_when_spend_exceeds_time_progress():
    from services.pacing import pacing_status, pick_weight
    c = {"start_date": (NOW - timedelta(days=2)).isoformat(),
          "end_date":    (NOW + timedelta(days=8)).isoformat(),
          "budget_total_usd": 100.0, "spend_usd": 50.0}
    p = pacing_status(c, NOW)
    assert p["status"] == "ahead"
    assert p["time_progress"] < p["spend_progress"]
    assert pick_weight(c, NOW) < 1.0   # throttled


def test_pacing_status_behind_when_spend_lags_time_progress():
    from services.pacing import pacing_status, pick_weight
    c = {"start_date": (NOW - timedelta(days=8)).isoformat(),
          "end_date":    (NOW + timedelta(days=2)).isoformat(),
          "budget_total_usd": 100.0, "spend_usd": 10.0}
    p = pacing_status(c, NOW)
    assert p["status"] == "behind"
    assert pick_weight(c, NOW) > 1.0   # boosted


def test_pacing_takeover_bypass_returns_weight_1_even_when_ahead():
    from services.pacing import pick_weight
    c = {"start_date": (NOW - timedelta(days=2)).isoformat(),
          "end_date":    (NOW + timedelta(days=8)).isoformat(),
          "budget_total_usd": 100.0, "spend_usd": 90.0,
          "takeover_config": {"enabled": True}}
    assert pick_weight(c, NOW) == 1.0


def test_pacing_status_na_when_no_dates_configured():
    from services.pacing import pacing_status
    c = {"start_date": None, "end_date": None,
          "budget_total_usd": 100.0, "spend_usd": 10.0}
    p = pacing_status(c, NOW)
    assert p["status"] == "n_a"


# ─── FREQ CAPS ─────────────────────────────────────────────────────
def test_freq_cap_blocks_with_min_interval_reason_when_recent_serve():
    from services.freq_caps import check_caps
    db = AsyncIOMotorClient(MONGO)[DBN]
    uid = f"fctest_min_{secrets.token_hex(3)}"
    run(db.ad_serve_events.delete_many({"user_id": uid}))
    run(db.ad_serve_events.insert_one({
        "id": "x", "user_id": uid, "campaign_id": "any", "advertiser_id": "any",
        "channel_slug": "morning_masala", "served_at": datetime.now(timezone.utc)}))
    out = run(check_caps(db, user_id=uid,
                                      campaign={"id": "c1", "advertiser_id": "a1"},
                                      channel_slug="morning_masala"))
    assert out["blocked"] is True
    assert out["reason"] == "min_interval"


def test_freq_cap_blocks_with_hourly_reason_when_3_in_last_hour():
    from services.freq_caps import check_caps
    db = AsyncIOMotorClient(MONGO)[DBN]
    uid = f"fctest_h_{secrets.token_hex(3)}"
    run(db.ad_serve_events.delete_many({"user_id": uid}))
    # 3 events for same campaign, none in last 10 min so min_interval passes.
    old = datetime.now(timezone.utc) - timedelta(minutes=30)
    for i in range(3):
        run(db.ad_serve_events.insert_one({
            "id": f"e{i}", "user_id": uid, "campaign_id": "c_hourly",
            "advertiser_id": "a1", "channel_slug": "other_channel",
            "served_at": old - timedelta(minutes=i)}))
    out = run(check_caps(db, user_id=uid,
                                      campaign={"id": "c_hourly", "advertiser_id": "a1",
                                                    "frequency_caps": {"min_seconds_between": 60}},
                                      channel_slug="morning_masala"))
    assert out["blocked"] is True
    assert out["reason"] == "hourly"


def test_freq_cap_returns_ok_when_under_all_caps():
    from services.freq_caps import check_caps
    db = AsyncIOMotorClient(MONGO)[DBN]
    uid = f"fctest_ok_{secrets.token_hex(3)}"
    run(db.ad_serve_events.delete_many({"user_id": uid}))
    out = run(check_caps(db, user_id=uid,
                                      campaign={"id": "c_clean", "advertiser_id": "a_clean"},
                                      channel_slug="morning_masala"))
    assert out["blocked"] is False and out["reason"] is None


# ─── ATTRIBUTION ───────────────────────────────────────────────────
def test_serve_records_event_in_ad_serve_events_collection():
    from services.freq_caps import record_serve_event
    db = AsyncIOMotorClient(MONGO)[DBN]
    sid = f"serve_{secrets.token_hex(4)}"
    run(record_serve_event(db, serve_doc={
        "id": sid, "user_id": "u1", "campaign_id": "c1",
        "advertiser_id": "a1", "channel_slug": "morning_masala",
        "served_at": datetime.now(timezone.utc), "completed": False,
        "cost_usd": 0.005, "was_takeover": False}))
    evt = run(db.ad_serve_events.find_one({"id": sid}))
    assert evt is not None
    assert evt["serve_id"] == sid


# ─── HYGIENE ───────────────────────────────────────────────────────
def test_hygiene_prunes_stale_non_whitelisted_files_only(tmp_path):
    """Drop a stale file in a prune dir + a whitelisted ad creative,
    confirm only the stale + non-whitelisted file is deleted."""
    from services.hygiene18c import tick_daily, PRUNE_DIRS
    # Use static/ad_creatives (in the real PRUNE_DIRS list).
    target = Path("/app/backend/static/ad_creatives")
    target.mkdir(parents=True, exist_ok=True)
    stale = target / f"phase18c_stale_{secrets.token_hex(4)}.mp3"
    keep  = target / f"phase18c_keep_{secrets.token_hex(4)}.mp3"
    stale.write_bytes(b"x" * 256); keep.write_bytes(b"y" * 256)
    old = time.time() - 48 * 3600
    os.utime(stale, (old, old)); os.utime(keep, (old, old))
    db = AsyncIOMotorClient(MONGO)[DBN]
    # Whitelist `keep` by inserting an active ad_creatives row.
    cid = f"crt_hyg_test_{secrets.token_hex(3)}"
    run(db.ad_creatives.insert_one({
        "id": cid, "advertiser_id": "adv_demo_karak", "kind": "audio_15s",
        "title": "hyg", "status": "active",
        "audio_path": str(keep), "audio_url": f"/api/static/ad_creatives/{keep.name}",
        "created_at": datetime.now(timezone.utc)}))
    rec = run(tick_daily(db, ttl_hours=24))
    assert rec["deleted_count"] >= 1
    assert not stale.exists()
    assert keep.exists()
    run(db.ad_creatives.delete_one({"id": cid}))
    keep.unlink(missing_ok=True)


# ─── ENGAGEMENT PUSH ───────────────────────────────────────────────
def test_engagement_push_excludes_demo_and_admin_emails():
    from services.engagement_push import _user_excluded
    assert _user_excluded({"email": "demo@bigfm.dubai"})  is True
    assert _user_excluded({"email": "admin@bigfm.dubai"}) is True
    assert _user_excluded({"email": "real@user.com"})       is False
    assert _user_excluded({"email": "x", "is_demo": True})  is True


def test_engagement_push_next_bucket_flip_returns_future_datetime():
    from services.engagement_push import next_bucket_flip
    # Force a known anchor: 04:00 UTC → next flip is 05:00 (morning_commute).
    anchor = datetime(2026, 7, 1, 4, 0, 0, tzinfo=timezone.utc)
    when, label = next_bucket_flip(anchor)
    assert label == "morning_commute"
    assert when > anchor



# ─── ATTRIBUTION CHAIN E2E ────────────────────────────────────────
# Verifies the Phase 18c fix: coupon writers MUST persist
# attribution_serve_id / attribution_campaign_id / attribution_advertiser_id
# when the client passes a known serve_id via body field or
# `X-Attribution-Serve-Id` header, and the /attribution funnel must then
# count both the impression AND the resulting coupon save.

def _seed_attribution_fixture(db, *, suffix: str):
    """Insert one ad_serve_events row + one offer; return (serve_id, cid, aid,
    offer_id, user_id)."""
    sid = f"serve_attr_{suffix}"
    cid = f"cmp_attr_{suffix}"
    aid = f"adv_attr_{suffix}"
    oid = f"ofr_attr_{suffix}"
    uid = f"u_attr_{suffix}"
    run(db.ad_serve_events.delete_many({"id": sid}))
    run(db.coupons.delete_many({"user_id": uid}))
    run(db.offers.delete_many({"offer_id": oid}))
    run(db.ad_serve_events.insert_one({
        "id": sid, "serve_id": sid, "user_id": uid,
        "campaign_id": cid, "advertiser_id": aid,
        "channel_slug": "morning_masala", "completed": True,
        "cost_usd": 0.005, "was_takeover": False,
        "served_at": datetime.now(timezone.utc)}))
    run(db.offers.insert_one({
        "offer_id": oid, "business_id": "biz_attr_test",
        "title": "Attribution Test Offer", "description": "x",
        "discount_value_cents": 500, "status": "active"}))
    return sid, cid, aid, oid, uid


def test_attribution_chain_e2e_save_coupon_persists_campaign_and_advertiser():
    """Hits the patched `/api/ads/action/save_coupon` route handler directly:
    confirms the freshly-minted coupon doc has all 3 attribution fields, AND
    the `/attribution` funnel reports impressions>=1 + coupon_saves>=1."""
    from routes.ads_public import action_save_coupon
    from unittest.mock import MagicMock
    db = AsyncIOMotorClient(MONGO)[DBN]
    sid, cid, aid, oid, uid = _seed_attribution_fixture(
        db, suffix=secrets.token_hex(3))

    request = MagicMock()
    request.app.state.db = db
    request.headers = {}   # serve_id passed via body, not header
    user = {"user_id": uid}
    payload = {"ad_pod_id": f"pod_{secrets.token_hex(3)}",
                  "offer_id": oid, "attribution_serve_id": sid,
                  "campaign_id": cid}

    res = run(action_save_coupon(request, payload, user))
    assert res["ok"] is True
    coupon_id = res["coupon_id"]

    saved = run(db.coupons.find_one({"_id": coupon_id}))
    assert saved is not None
    assert saved["attribution_serve_id"]      == sid
    assert saved["attribution_campaign_id"]  == cid
    assert saved["attribution_advertiser_id"] == aid

    # /attribution funnel reads ad_serve_events + coupons.
    impressions = run(db.ad_serve_events.count_documents({"campaign_id": cid}))
    saves = run(db.coupons.count_documents(
        {"attribution_campaign_id": cid}))
    assert impressions >= 1
    assert saves         >= 1


def test_attribution_chain_e2e_redemption_status_flip_counts_in_funnel():
    """Same write path → flip coupon to `status=redeemed` → confirm the
    `/attribution` redemption query counts it."""
    from routes.ads_public import action_save_coupon
    from unittest.mock import MagicMock
    db = AsyncIOMotorClient(MONGO)[DBN]
    sid, cid, aid, oid, uid = _seed_attribution_fixture(
        db, suffix=secrets.token_hex(3))

    request = MagicMock()
    request.app.state.db = db
    request.headers = {"X-Attribution-Serve-Id": sid}   # header path this time
    user = {"user_id": uid}
    payload = {"ad_pod_id": f"pod_{secrets.token_hex(3)}", "offer_id": oid}
    res = run(action_save_coupon(request, payload, user))
    coupon_id = res["coupon_id"]

    # Simulate partner-side redemption (status flip).
    run(db.coupons.update_one(
        {"_id": coupon_id},
        {"$set": {"status": "redeemed",
                       "redeemed_at": datetime.now(timezone.utc)}}))

    saved = run(db.coupons.find_one({"_id": coupon_id}))
    assert saved["status"] == "redeemed"
    # Attribution fields must survive the redemption flip.
    assert saved["attribution_campaign_id"]  == cid
    assert saved["attribution_advertiser_id"] == aid

    redemptions = run(db.coupons.count_documents(
        {"attribution_campaign_id": cid, "status": "redeemed"}))
    assert redemptions >= 1


def test_attribution_chain_save_coupon_without_serve_id_is_silent_noop():
    """Missing or unknown serve_id must NOT 4xx — coupon is written without
    the attribution_* fields (so legacy non-ad coupon flows keep working)."""
    from routes.ads_public import action_save_coupon
    from unittest.mock import MagicMock
    db = AsyncIOMotorClient(MONGO)[DBN]
    _sid, _cid, _aid, oid, uid = _seed_attribution_fixture(
        db, suffix=secrets.token_hex(3))

    request = MagicMock()
    request.app.state.db = db
    request.headers = {}
    user = {"user_id": uid}
    # No `attribution_serve_id` in the payload AND no header.
    payload = {"ad_pod_id": f"pod_{secrets.token_hex(3)}", "offer_id": oid}
    res = run(action_save_coupon(request, payload, user))
    assert res["ok"] is True
    saved = run(db.coupons.find_one({"_id": res["coupon_id"]}))
    assert saved is not None
    assert "attribution_campaign_id" not in saved
    assert "attribution_serve_id"      not in saved
