"""Phase 13b — Conversion funnel + ROI tests."""
from __future__ import annotations
import asyncio
import os
from datetime import datetime as dt, timezone, timedelta

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")
DB = MongoClient(MONGO_URL)[DB_NAME]


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": email, "password": pw}, timeout=10)
    assert r.status_code == 200, r.text[:200]
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def free_session():
    return _login("test@bigfm.dubai", "TestUser123!")


def _now():
    return dt.now(timezone.utc)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── seed a send_log row with controllable tracking_id + state ──────
def _seed_row(*, cid: str, tracking_id: str = None,
                  user_id: str = "user_qa_funnel",
                  variant_slug=None, sent_offset_min=10,
                  opened=False, clicked=False, converted=False,
                  conv_value=0.0, channel="email"):
    tid = tracking_id or f"trk_qa_{os.urandom(6).hex()}"
    now = _now()
    doc = {
        "_id": f"sl_qa_{os.urandom(6).hex()}",
        "user_id": user_id, "campaign_id": cid,
        "channel": channel, "tracking_id": tid,
        "status": "sent",
        "sent_at": now - timedelta(minutes=sent_offset_min),
        "opened_at": now - timedelta(minutes=5) if opened else None,
        "clicked_at": now - timedelta(minutes=2) if clicked else None,
        "converted_at": now if converted else None,
        "conversion_value": conv_value if converted else None,
    }
    if variant_slug:
        doc["variant_slug"] = variant_slug
    DB.lifecycle_send_log.insert_one(doc)
    return doc


# ─── 1. Pixel writes opened_at ──────────────────────────────────────
def test_pixel_open_writes_opened_at():
    tid = f"trk_qa_pixel_{os.urandom(4).hex()}"
    _seed_row(cid="cmp_qa_pixel", tracking_id=tid)
    try:
        r = requests.get(f"{API}/r/{tid}/pixel.gif", timeout=10)
        assert r.status_code == 200, r.text[:200]
        row = DB.lifecycle_send_log.find_one({"tracking_id": tid})
        assert row.get("opened_at") is not None, row
    finally:
        DB.lifecycle_send_log.delete_many({"tracking_id": tid})


# ─── 2. Click redirect writes clicked_at ────────────────────────────
def test_click_redirect_writes_clicked_at():
    tid = f"trk_qa_click_{os.urandom(4).hex()}"
    _seed_row(cid="cmp_qa_click", tracking_id=tid)
    try:
        r = requests.get(f"{API}/r/{tid}/click?to=/",
                            allow_redirects=False, timeout=10)
        assert r.status_code in (302, 307), r.status_code
        row = DB.lifecycle_send_log.find_one({"tracking_id": tid})
        assert row.get("clicked_at") is not None, row
    finally:
        DB.lifecycle_send_log.delete_many({"tracking_id": tid})


# ─── 3. Explicit /converted endpoint ────────────────────────────────
def test_explicit_converted_endpoint_writes_converted_at():
    tid = f"trk_qa_conv_{os.urandom(4).hex()}"
    _seed_row(cid="cmp_qa_conv", tracking_id=tid, clicked=True)
    try:
        r = requests.post(f"{API}/r/{tid}/converted",
                              json={"value": 25.0,
                                      "event_type": "manual_test"},
                              timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["attributed"] is True
        row = DB.lifecycle_send_log.find_one({"tracking_id": tid})
        assert row.get("converted_at") is not None
        assert row.get("conversion_value") == 25.0
        assert row.get("conversion_event_type") == "manual_test"
    finally:
        DB.lifecycle_send_log.delete_many({"tracking_id": tid})


# ─── 4. /converted idempotent ───────────────────────────────────────
def test_converted_idempotent():
    tid = f"trk_qa_idem_{os.urandom(4).hex()}"
    _seed_row(cid="cmp_qa_idem", tracking_id=tid, clicked=True)
    try:
        r1 = requests.post(f"{API}/r/{tid}/converted",
                               json={"value": 10.0}, timeout=10).json()
        r2 = requests.post(f"{API}/r/{tid}/converted",
                               json={"value": 99.0}, timeout=10).json()
        assert r1["attributed"] is True
        assert r2["attributed"] is False, r2
        row = DB.lifecycle_send_log.find_one({"tracking_id": tid})
        # Value is NOT overwritten on the second call.
        assert row.get("conversion_value") == 10.0
    finally:
        DB.lifecycle_send_log.delete_many({"tracking_id": tid})


# ─── 5. Implicit conversion within window (real offer schema) ──────
def test_implicit_conversion_on_coupon_claim_within_window():
    """Phase 13b Hotfix #1: use the REAL offer schema (`value_amount` +
    `value_currency`), not the legacy `discount_value` key that previous
    versions of this test seeded — which masked the production bug."""
    from services import conversion as cs
    cid = f"cmp_qa_impl_{os.urandom(4).hex()}"
    uid = f"user_qa_impl_{os.urandom(4).hex()}"
    _seed_row(cid=cid, user_id=uid, clicked=True,
                  sent_offset_min=60 * 24)  # 1 day ago
    try:
        async def _go(db):
            return await cs.attribute_conversion(
                db, user_id=uid,
                event_type="coupon_claimed",
                value=15.0, currency="AED",
                conversion_id="cpn_qa_impl_1")
        async def _wrap():
            cli = AsyncIOMotorClient(MONGO_URL)
            try:
                return await _go(cli[DB_NAME])
            finally:
                cli.close()
        out = _run(_wrap())
        assert out is not None
        row = DB.lifecycle_send_log.find_one(
            {"campaign_id": cid, "user_id": uid})
        assert row.get("converted_at") is not None
        assert row.get("conversion_value") == 15.0
        assert row.get("conversion_currency") == "AED"
        assert row.get("conversion_id") == "cpn_qa_impl_1"
    finally:
        DB.lifecycle_send_log.delete_many({"user_id": uid})


# ─── 5b. End-to-end: real offer schema (value_amount) → real value ───
# Phase 13b Hotfix #1 regression test. Inserts an offer with ONLY
# `value_amount`/`value_currency` (the production schema — no
# `discount_value` key) and drives the FULL `claim_offer` service to
# prove the conversion_value matches the offer's discount, not zero.
def test_implicit_conversion_reads_value_amount_field():
    from services import local_commerce as lc
    cid = f"cmp_qa_va_{os.urandom(4).hex()}"
    uid = f"user_qa_va_{os.urandom(4).hex()}"
    biz_id = f"biz_qa_va_{os.urandom(4).hex()}"
    offer_id = f"ofr_qa_va_{os.urandom(4).hex()}"
    # Seed a clicked send_log row 1 day ago.
    _seed_row(cid=cid, user_id=uid, clicked=True,
                  sent_offset_min=60 * 24)
    # Seed a real-shaped business + offer.
    DB.businesses.insert_one({
        "_id": biz_id, "business_id": biz_id,
        "display_name": "QA Karak",
        "city": "dubai", "category": "cafe",
        "status": "active"})
    DB.offers.insert_one({
        "_id": offer_id, "offer_id": offer_id,
        "business_id": biz_id,
        "title": "5 AED off",
        "value_amount": 5.0,
        "value_currency": "AED",
        "max_redemptions": 1,
        "max_per_user": 1,
        "inventory_remaining": 10,
        "one_time_use": True,
        "status": "active",
        # NOTE: NO `discount_value` key on this doc — proves the
        # claim_offer path reads the real schema field.
    })
    try:
        async def _claim(db):
            return await lc.claim_offer(
                db, offer_id=offer_id, user_id=uid,
                claim_source="public_page")
        async def _wrap():
            cli = AsyncIOMotorClient(MONGO_URL)
            try:
                return await _claim(cli[DB_NAME])
            finally:
                cli.close()
        out = _run(_wrap())
        assert out and out.get("coupon_id"), out
        row = DB.lifecycle_send_log.find_one(
            {"campaign_id": cid, "user_id": uid})
        # The fix: conversion_value must equal the offer.value_amount
        # (5.0) — NOT 0.0 which is what the broken code returned.
        assert row.get("converted_at") is not None, row
        assert row.get("conversion_value") == 5.0, row
        assert row.get("conversion_currency") == "AED", row
        assert row.get("conversion_event_type") == "coupon_claimed", row
        assert row.get("conversion_id") == out["coupon_id"], row
    finally:
        DB.lifecycle_send_log.delete_many({"user_id": uid})
        DB.businesses.delete_one({"_id": biz_id})
        DB.offers.delete_one({"_id": offer_id})
        DB.coupons.delete_many({"user_id": uid})


# ─── 6. Implicit conversion OUTSIDE window not attributed ───────────
def test_implicit_conversion_outside_window_not_attributed():
    from services import conversion as cs
    cid = f"cmp_qa_oow_{os.urandom(4).hex()}"
    uid = f"user_qa_oow_{os.urandom(4).hex()}"
    # Click 8 days ago — past the default 7-day window.
    now = _now()
    DB.lifecycle_send_log.insert_one({
        "_id": f"sl_qa_oow_{os.urandom(6).hex()}",
        "user_id": uid, "campaign_id": cid,
        "channel": "email", "status": "sent",
        "sent_at": now - timedelta(days=10),
        "opened_at": now - timedelta(days=9),
        "clicked_at": now - timedelta(days=8),
        "converted_at": None})
    try:
        async def _wrap():
            cli = AsyncIOMotorClient(MONGO_URL)
            try:
                return await cs.attribute_conversion(
                    cli[DB_NAME], user_id=uid,
                    event_type="coupon_claimed", value=99.0,
                    conversion_id="cpn_qa_oow")
            finally:
                cli.close()
        out = _run(_wrap())
        assert out is None, "must NOT attribute beyond window"
        row = DB.lifecycle_send_log.find_one(
            {"campaign_id": cid, "user_id": uid})
        assert row.get("converted_at") is None
    finally:
        DB.lifecycle_send_log.delete_many({"user_id": uid})


# ─── 7. Funnel endpoint shape ───────────────────────────────────────
def test_funnel_endpoint_returns_aggregated_shape(admin_session):
    payload = {"name": "QA Funnel Shape",
                  "trigger": "inactive_7d",
                  "channels": ["email"],
                  "template": {"email_subject": "x",
                                    "email_body": "y"},
                  "active": False}
    r = admin_session.post(f"{API}/admin/retention/campaigns",
                                      json=payload, timeout=10)
    cid = r.json()["id"]
    # Seed 10 sent / 5 opened / 3 clicked / 2 converted ($20 total).
    rows = []
    for i in range(10):
        rows.append({"_id": f"sl_qa_fn_{i}",
                          "user_id": f"u{i}", "campaign_id": cid,
                          "channel": "email", "status": "sent",
                          "sent_at": _now() - timedelta(minutes=10),
                          "opened_at": _now() if i < 5 else None,
                          "clicked_at": _now() if i < 3 else None,
                          "converted_at": _now() if i < 2 else None,
                          "conversion_value": 10.0 if i < 2 else None})
    DB.lifecycle_send_log.insert_many(rows)
    try:
        r = admin_session.get(
            f"{API}/admin/retention/campaigns/{cid}/funnel"
            "?range=30d", timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["totals"]["sent"] == 10
        assert body["totals"]["opened"] == 5
        assert body["totals"]["clicked"] == 3
        assert body["totals"]["converted"] == 2
        assert body["totals"]["conversion_value_total"] == 20.0
        assert body["rates"]["open_rate"] == pytest.approx(0.5)
        assert body["rates"]["conv_rate"] == pytest.approx(0.2)
        assert body["roi"]["estimated_send_cost"] > 0
        assert body["roi"]["roi_multiple"] > 0
    finally:
        DB.lifecycle_campaigns.delete_one({"id": cid})
        DB.lifecycle_send_log.delete_many({"campaign_id": cid})


# ─── 8. Funnel admin-only ──────────────────────────────────────────
def test_funnel_endpoint_admin_only(free_session):
    r = free_session.get(
        f"{API}/admin/retention/campaigns/no-such/funnel", timeout=10)
    assert r.status_code == 403, r.text[:200]


# ─── 9. Per-variant breakdown with lift + p_value ──────────────────
def test_funnel_per_variant_breakdown(admin_session):
    payload = {"name": "QA Funnel Variants",
                  "trigger": "inactive_7d",
                  "channels": ["email"],
                  "template": {"email_subject": "B",
                                    "email_body": "b"},
                  "variants": [
                      {"slug": "A", "weight": 50,
                        "template_overrides": {"email_subject": "A"}},
                      {"slug": "B", "weight": 50,
                        "template_overrides": {"email_subject": "B"}}],
                  "active": False}
    r = admin_session.post(f"{API}/admin/retention/campaigns",
                                      json=payload, timeout=10)
    cid = r.json()["id"]
    bulk = []
    now = _now()
    # A: 300 sent, 30 conv (10%).
    for i in range(300):
        bulk.append({"_id": f"sl_qa_fv_A_{i}",
                          "user_id": f"ua{i}",
                          "campaign_id": cid, "channel": "email",
                          "status": "sent", "sent_at": now,
                          "variant_slug": "A",
                          "converted_at": now if i < 30 else None,
                          "conversion_value": 5.0 if i < 30 else None})
    # B: 300 sent, 75 conv (25%).
    for i in range(300):
        bulk.append({"_id": f"sl_qa_fv_B_{i}",
                          "user_id": f"ub{i}",
                          "campaign_id": cid, "channel": "email",
                          "status": "sent", "sent_at": now,
                          "variant_slug": "B",
                          "converted_at": now if i < 75 else None,
                          "conversion_value": 5.0 if i < 75 else None})
    DB.lifecycle_send_log.insert_many(bulk)
    try:
        r = admin_session.get(
            f"{API}/admin/retention/campaigns/{cid}/funnel"
            "?range=30d", timeout=10)
        body = r.json()
        by_slug = {v["slug"]: v for v in body["by_variant"]}
        assert by_slug["A"]["sent"] == 300
        assert by_slug["A"]["converted"] == 30
        assert by_slug["B"]["converted"] == 75
        assert by_slug["A"]["conv_rate"] == pytest.approx(0.10)
        assert by_slug["B"]["conv_rate"] == pytest.approx(0.25)
        # Control is the largest-weight; ties → first row in our impl,
        # which is A (insertion order). lift_vs_control on B should be
        # ~ +150%. p_value < 0.05.
        assert by_slug["B"]["lift_vs_control"] is not None
        assert by_slug["B"]["lift_vs_control"] > 0.5
        assert by_slug["B"]["p_value"] is not None
        assert by_slug["B"]["p_value"] < 0.05
        assert body["roi"]["winner_variant_slug"] == "B"
    finally:
        DB.lifecycle_campaigns.delete_one({"id": cid})
        DB.lifecycle_send_log.delete_many({"campaign_id": cid})


# ─── 10. ROI multiple calculation ──────────────────────────────────
def test_roi_multiple_calculation(admin_session):
    payload = {"name": "QA Funnel ROI",
                  "trigger": "inactive_7d",
                  "channels": ["email"],
                  "template": {"email_subject": "X",
                                    "email_body": "y"},
                  "active": False}
    r = admin_session.post(f"{API}/admin/retention/campaigns",
                                      json=payload, timeout=10)
    cid = r.json()["id"]
    # 1000 emails @ $0.001 each = $1.00 cost.
    # 50 conversions @ $5 each = $250 value.
    # ROI = 250.
    bulk = []
    for i in range(1000):
        bulk.append({"_id": f"sl_qa_roi_{i}",
                          "user_id": f"ur{i}",
                          "campaign_id": cid, "channel": "email",
                          "status": "sent", "sent_at": _now(),
                          "converted_at": _now() if i < 50 else None,
                          "conversion_value": 5.0 if i < 50 else None})
    DB.lifecycle_send_log.insert_many(bulk)
    try:
        body = admin_session.get(
            f"{API}/admin/retention/campaigns/{cid}/funnel"
            "?range=30d", timeout=10).json()
        # Cost = 1000 * 0.001 = 1.00. Value = 50 * 5 = 250.
        assert body["roi"]["estimated_send_cost"] == pytest.approx(1.0)
        assert body["roi"]["conversion_value_total"] == 250.0
        assert body["roi"]["roi_multiple"] == pytest.approx(250.0)
    finally:
        DB.lifecycle_campaigns.delete_one({"id": cid})
        DB.lifecycle_send_log.delete_many({"campaign_id": cid})


# ─── 11. Top campaigns endpoint ranks by metric ────────────────────
def test_top_campaigns_endpoint_ranks_by_metric(admin_session):
    cids = []
    seeded_user_ids = set()
    try:
        # Create 3 campaigns with widely different conv rates.
        for i, conv_count in enumerate([5, 50, 25]):
            payload = {"name": f"QA Top {i}",
                          "trigger": "inactive_7d",
                          "channels": ["email"],
                          "template": {"email_subject": "x",
                                            "email_body": "y"},
                          "active": False}
            r = admin_session.post(
                f"{API}/admin/retention/campaigns",
                json=payload, timeout=10)
            cid = r.json()["id"]
            cids.append(cid)
            bulk = []
            for j in range(100):
                uid = f"u_top_{i}_{j}"
                seeded_user_ids.add(uid)
                bulk.append({
                    "_id": f"sl_qa_top_{i}_{j}",
                    "user_id": uid,
                    "campaign_id": cid, "channel": "email",
                    "status": "sent", "sent_at": _now(),
                    "converted_at": _now()
                                          if j < conv_count else None,
                    "conversion_value": 10.0
                                              if j < conv_count else None})
            DB.lifecycle_send_log.insert_many(bulk)
        # Rank by conv_rate.
        body = admin_session.get(
            f"{API}/admin/retention/campaigns/top?range=30d"
            "&metric=conv_rate&limit=10", timeout=15).json()
        # Filter to only our 3 seeded campaigns.
        ours = [it for it in body["items"]
                  if it["campaign_id"] in cids]
        assert ours[0]["campaign_id"] == cids[1], ours
        # By roi (same as conv_rate ordering here since same cost+value).
        body2 = admin_session.get(
            f"{API}/admin/retention/campaigns/top?range=30d"
            "&metric=roi&limit=10", timeout=15).json()
        ours2 = [it for it in body2["items"]
                  if it["campaign_id"] in cids]
        assert ours2[0]["campaign_id"] == cids[1]
    finally:
        for cid in cids:
            DB.lifecycle_campaigns.delete_one({"id": cid})
            DB.lifecycle_send_log.delete_many({"campaign_id": cid})
