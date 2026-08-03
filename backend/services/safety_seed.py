"""Phase 12c QA seed — idempotent canonical demo data so the
partner-redeem + fraud-guard double-redeem flow is reproducible.

Seeds:
    • `businesses.biz_demo_karak`  (canonical demo partner)
    • `offers.ofr_qa_onetime_demo` (one_time_use, max_per_user=1, active)
    • `partner_tokens.pt_qa_demo`  (already seeded out-of-band but we
       re-bcrypt on every boot so the QA token survives manual edits)
    • For `users.test@bigfm.dubai`: ensure exactly one CLAIMED coupon
       under that offer with `one_time_use: True` and a fresh qr_token.

Idempotent — re-running does not duplicate rows.
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt

logger = logging.getLogger("bigfm.safety_seed")

QA_BUSINESS_ID = "biz_demo_karak"
QA_OFFER_ID = "ofr_qa_onetime_demo"
QA_TOKEN_ID = "pt_qa_demo"
QA_TOKEN_RAW = "ptk_qa_demo_redeem_smoketoken_xyz"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_qa_seed(db) -> dict:
    out: dict = {}

    # 1. Business
    await db.businesses.update_one(
        {"business_id": QA_BUSINESS_ID},
        {"$setOnInsert": {
            "_id": QA_BUSINESS_ID, "business_id": QA_BUSINESS_ID,
            "name": "Karak Cafe Dubai (QA Demo)",
            "category": "cafe",
            "city": "dubai",
            "latitude": 25.197197, "longitude": 55.27437,
            "created_at": _now(),
        }, "$set": {"updated_at": _now(), "status": "active"}},
        upsert=True)
    out["business"] = QA_BUSINESS_ID

    # 2. Offer (one_time_use surrogate: max_per_user=1)
    now = _now()
    await db.offers.update_one(
        {"offer_id": QA_OFFER_ID},
        {"$setOnInsert": {
            "_id": QA_OFFER_ID, "offer_id": QA_OFFER_ID,
            "business_id": QA_BUSINESS_ID,
            "title": "QA Demo — One-time 50% off Karak",
            "description": "Phase 12c QA seed for partner-redeem flow.",
            "offer_type": "percent_off", "value_amount": 50,
            "value_currency": "AED", "original_price": None,
            "min_purchase": None, "terms_text": "One use per user.",
            "image_url": None,
            "start_at": now - timedelta(days=1),
            "redeem_window_seconds": 86400,
            "max_redemptions_total": 100,
            "max_per_user": 1,
            "inventory_remaining": 100,
            "redemption_method": "qr_code",
            "approved_at": now, "created_at": now,
        }, "$set": {
            "end_at": now + timedelta(days=180),
            "status": "active", "updated_at": now}},
        upsert=True)
    out["offer"] = QA_OFFER_ID

    # 3. Partner token — re-stamp bcrypt hash so the QA raw token is
    # always valid even if a prior run wrote a stale shape.
    sh = bcrypt.hashpw(QA_TOKEN_RAW.encode(), bcrypt.gensalt()).decode()
    await db.partner_tokens.update_one(
        {"partner_token_id": QA_TOKEN_ID},
        {"$set": {
            "_id": QA_TOKEN_ID, "partner_token_id": QA_TOKEN_ID,
            "secret_hash": sh,
            "partner_business_id": QA_BUSINESS_ID,
            "scopes": ["redeem_offers"],
            "status": "active",
            "revoked_at": None,
            "notes": "Phase 12c QA seed (idempotent)",
            "updated_at": _now(),
        }, "$setOnInsert": {"created_at": _now()},
          "$unset": {"token_hash": ""}},
        upsert=True)
    out["partner_token"] = QA_TOKEN_ID

    # 4. Ensure test@bigfm.dubai is business_partner so the redeem
    # endpoint accepts the request (route guards on role).
    # Phase 19a Part 4 follow-up: skip if user has been intentionally
    # promoted to creator or admin (see scripts/promote_test_user_to_creator.py).
    await db.users.update_one(
        {"email": "test@bigfm.dubai",
          "role": {"$nin": ["creator", "admin", "moderator"]}},
        {"$set": {"role": "business_partner"}})

    # 5. Ensure a fresh CLAIMED coupon exists for the QA user
    # (user_4abd359ab5b94f0f) so the tester can scan-redeem immediately.
    test_user = await db.users.find_one({"email": "test@bigfm.dubai"},
                                                            {"user_id": 1})
    if test_user:
        uid = test_user["user_id"]
        existing = await db.coupons.find_one({
            "user_id": uid, "offer_id": QA_OFFER_ID,
            "status": "claimed"})
        if not existing:
            cid = f"cpn_qa_{uuid.uuid4().hex[:14]}"
            qr = f"cqr_qa_{uuid.uuid4().hex[:14]}"
            await db.coupons.insert_one({
                "_id": cid, "coupon_id": cid,
                "user_id": uid,
                "business_id": QA_BUSINESS_ID,
                "offer_id": QA_OFFER_ID,
                "qr_token": qr,
                "status": "claimed",
                "one_time_use": True,
                "max_redemptions": 1,
                "redeemed_count": 0,
                "claimed_at": _now(),
                "expires_at": _now() + timedelta(days=180),
            })
            out["coupon_id"] = cid
            out["qr_token"] = qr
        else:
            out["coupon_id"] = existing["coupon_id"]
            out["qr_token"] = existing["qr_token"]
    logger.info(f"Phase 12c QA seed ready: {out}")
    return out
