"""Phase AD.1 — Advertiser Self-Service Dashboard MVP.

Parallel to legacy Phase-18a advertiser stack (services/advertisers.py) — this
one uses `_v2` collections so both systems coexist without schema clash:

    advertisers_v2       — brands (self-service signup, admin approval)
    ad_campaigns_v2   — campaigns (display banner / sponsored game / audio preroll stub)
    ad_impressions_v2 — append-only, stub for future real ad serving
    ad_payments        — top-up ledger, credits via Stripe Checkout webhook

Two-stage approval gate: brand → admin approve → active.  Campaign → admin
approve → active.  Sponsored-game campaigns link to PG.1 `game_campaigns`
via a nullable `sponsored_by_ad_campaign_id` field stamped on approval.

`record_impression` is a stub for future real serving; kept here so all
AD.1 endpoints stay in one place.
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger("bigfm.ad1_advertiser")

CAMPAIGN_TYPES = {"display_banner", "sponsored_game", "audio_preroll_stub"}
PRICING_MODELS = {"cpm", "cpc", "flat"}
CAMPAIGN_STATUSES = {"draft", "pending_approval", "active", "paused",
                                          "ended", "rejected"}
ADVERTISER_STATUSES = {"draft", "pending_approval", "active",
                                              "suspended", "rejected"}
USER_SEGMENTS = {"all", "free", "premium"}
DAYPARTS = {"morning", "afternoon", "evening", "night"}


def _now() -> datetime: return datetime.now(timezone.utc)
def _iso(dt): return dt.isoformat() if isinstance(dt, datetime) else dt
def _gen(prefix: str) -> str: return f"{prefix}_{secrets.token_hex(7)}"


def _clean(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k != "_id"}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


# ─── indexes ─────────────────────────────────────────────────────
async def ensure_ad1_indexes(db) -> None:
    try:
        await db.advertisers_v2.create_index("advertiser_id", unique=True)
        await db.advertisers_v2.create_index([("owner_user_id", 1), ("status", 1)])
        await db.ad_campaigns_v2.create_index("campaign_id", unique=True)
        await db.ad_campaigns_v2.create_index([("advertiser_id", 1),
                                                                              ("status", 1),
                                                                              ("created_at", -1)])
        await db.ad_impressions_v2.create_index("imp_id", unique=True)
        await db.ad_impressions_v2.create_index([("campaign_id", 1),
                                                                                  ("timestamp", -1)])
        await db.ad_payments.create_index("payment_id", unique=True)
        await db.ad_payments.create_index("stripe_checkout_session_id",
                                                                  unique=True, sparse=True)
        await db.ad_payments.create_index([("advertiser_id", 1),
                                                                        ("status", 1),
                                                                        ("created_at", -1)])
    except Exception as e:
        logger.warning("[ad1] ensure_indexes: %s", e)


# ─── ownership helpers ──────────────────────────────────────────
async def get_advertiser(db, *, advertiser_id: str) -> Optional[dict]:
    return await db.advertisers_v2.find_one({"advertiser_id": advertiser_id})


async def assert_owner(db, *, advertiser_id: str, user: dict) -> dict:
    """Returns advertiser doc OR raises PermissionError."""
    adv = await get_advertiser(db, advertiser_id=advertiser_id)
    if not adv:
        raise LookupError("advertiser_not_found")
    if user.get("role") == "admin":
        return adv
    if adv.get("owner_user_id") != user.get("user_id"):
        raise PermissionError("not_advertiser_owner")
    return adv


# ─── Advertiser CRUD ────────────────────────────────────────────
async def create_advertiser(db, *, owner_user_id: str,
                                                              name: str, contact_email: str,
                                                              contact_name: Optional[str] = None,
                                                              phone: Optional[str] = None,
                                                              website: Optional[str] = None,
                                                              industry: Optional[str] = None,
                                                              logo_url: Optional[str] = None) -> dict:
    if not name or not name.strip():
        raise ValueError("name_required")
    if not contact_email or "@" not in contact_email:
        raise ValueError("contact_email_invalid")
    aid = _gen("advv2")
    doc = {
        "advertiser_id":               aid,
        "name":                              name.strip(),
        "contact_email":              contact_email.strip().lower(),
        "contact_name":               (contact_name or "").strip() or None,
        "phone":                            (phone or "").strip() or None,
        "website":                        (website or "").strip() or None,
        "industry":                      (industry or "").strip() or None,
        "logo_url":                      logo_url or None,
        "status":                          "draft",
        "owner_user_id":              owner_user_id,
        "budget_available_cents": 0,
        "created_at":                  _now(),
        "updated_at":                _now(),
    }
    await db.advertisers_v2.insert_one(doc)
    return _clean(doc)


async def update_advertiser(db, *, advertiser_id: str,
                                                              patch: dict, user: dict) -> dict:
    adv = await assert_owner(db, advertiser_id=advertiser_id, user=user)
    if adv.get("status") == "active" and user.get("role") != "admin":
        # Once active, allow only cosmetic changes.
        allowed = {"logo_url", "contact_name", "phone", "website"}
    else:
        allowed = {"name", "contact_email", "contact_name", "phone",
                            "website", "industry", "logo_url"}
    upd = {k: v for k, v in (patch or {}).items() if k in allowed}
    if not upd:
        return _clean(adv)
    upd["updated_at"] = _now()
    await db.advertisers_v2.update_one(
        {"advertiser_id": advertiser_id}, {"$set": upd})
    return _clean(await get_advertiser(db, advertiser_id=advertiser_id))


async def submit_advertiser_for_approval(db, *, advertiser_id: str,
                                                                                          user: dict) -> dict:
    adv = await assert_owner(db, advertiser_id=advertiser_id, user=user)
    if adv["status"] not in ("draft", "rejected"):
        raise ValueError(f"cannot_submit_from_{adv['status']}")
    await db.advertisers_v2.update_one(
        {"advertiser_id": advertiser_id},
        {"$set": {"status":         "pending_approval",
                          "submitted_at":  _now(),
                          "updated_at":   _now()}})
    return {"advertiser_id": advertiser_id, "status": "pending_approval"}


async def approve_advertiser(db, *, advertiser_id: str,
                                                          admin_user_id: str) -> dict:
    r = await db.advertisers_v2.update_one(
        {"advertiser_id": advertiser_id},
        {"$set": {"status":              "active",
                          "approved_at":     _now(),
                          "approved_by":     admin_user_id,
                          "rejected_reason": None,
                          "updated_at":       _now()}})
    if r.matched_count == 0:
        raise LookupError("advertiser_not_found")
    return {"advertiser_id": advertiser_id, "status": "active"}


async def reject_advertiser(db, *, advertiser_id: str,
                                                          admin_user_id: str, reason: str) -> dict:
    r = await db.advertisers_v2.update_one(
        {"advertiser_id": advertiser_id},
        {"$set": {"status":                "rejected",
                          "rejected_reason":  reason,
                          "approved_by":       admin_user_id,
                          "updated_at":         _now()}})
    if r.matched_count == 0:
        raise LookupError("advertiser_not_found")
    return {"advertiser_id": advertiser_id, "status": "rejected", "reason": reason}


async def list_admin_advertisers(db, *, status: Optional[str] = None,
                                                                      limit: int = 100) -> list[dict]:
    q = {}
    if status:
        q["status"] = status
    docs = await db.advertisers_v2.find(q).sort([("created_at", -1)]).to_list(limit)
    return [_clean(d) for d in docs]


async def list_mine(db, *, owner_user_id: str) -> list[dict]:
    docs = await db.advertisers_v2.find(
        {"owner_user_id": owner_user_id}
    ).sort([("created_at", -1)]).to_list(50)
    return [_clean(d) for d in docs]


# ─── Campaign CRUD ─────────────────────────────────────────────
def _validate_campaign_payload(payload: dict) -> None:
    ct = payload.get("campaign_type")
    if ct not in CAMPAIGN_TYPES:
        raise ValueError(f"invalid_campaign_type:{ct}")
    if not payload.get("name") or not str(payload["name"]).strip():
        raise ValueError("name_required")
    budget = int(payload.get("budget_total_cents") or 0)
    if budget <= 0:
        raise ValueError("budget_total_cents_required")
    pm = payload.get("pricing_model") or "cpm"
    if pm not in PRICING_MODELS:
        raise ValueError(f"invalid_pricing_model:{pm}")
    if pm == "cpm" and int(payload.get("cpm_bid_cents") or 0) <= 0:
        raise ValueError("cpm_bid_cents_required_for_cpm")
    if pm == "cpc" and int(payload.get("cpc_bid_cents") or 0) <= 0:
        raise ValueError("cpc_bid_cents_required_for_cpc")
    targeting = payload.get("targeting") or {}
    seg = targeting.get("user_segments") or ["all"]
    if not set(seg).issubset(USER_SEGMENTS):
        raise ValueError(f"invalid_user_segments:{seg}")
    dp = targeting.get("dayparts") or []
    if dp and not set(dp).issubset(DAYPARTS):
        raise ValueError(f"invalid_dayparts:{dp}")
    if ct == "sponsored_game":
        creative = payload.get("creative") or {}
        if not creative.get("sponsored_game_campaign_id"):
            raise ValueError("sponsored_game_campaign_id_required")


async def create_campaign(db, *, advertiser_id: str, payload: dict,
                                                    user: dict) -> dict:
    adv = await assert_owner(db, advertiser_id=advertiser_id, user=user)
    if adv["status"] != "active" and user.get("role") != "admin":
        raise PermissionError("advertiser_not_active")
    _validate_campaign_payload(payload)
    cid = _gen("adcv2")
    targeting = payload.get("targeting") or {}
    creative = payload.get("creative") or {}
    doc = {
        "campaign_id":                cid,
        "advertiser_id":               advertiser_id,
        "name":                              str(payload["name"]).strip(),
        "campaign_type":            payload["campaign_type"],
        "status":                          "draft",
        "start_at":                      _iso(payload.get("start_at")),
        "end_at":                        _iso(payload.get("end_at")),
        "budget_total_cents":     int(payload.get("budget_total_cents") or 0),
        "budget_spent_cents":     0,
        "daily_cap_cents":           int(payload.get("daily_cap_cents") or 0) or None,
        "pricing_model":             payload.get("pricing_model") or "cpm",
        "cpm_bid_cents":             int(payload.get("cpm_bid_cents") or 0) or None,
        "cpc_bid_cents":             int(payload.get("cpc_bid_cents") or 0) or None,
        "targeting": {
            "cities":                    list(targeting.get("cities") or []),
            "user_segments":     list(targeting.get("user_segments") or ["all"]),
            "dayparts":                list(targeting.get("dayparts") or []),
            "languages":              list(targeting.get("languages") or []),
            "genres":                  list(targeting.get("genres") or []),
        },
        "creative": {
            "headline":              (creative.get("headline") or "").strip() or None,
            "body":                    (creative.get("body") or "").strip() or None,
            "image_url":            creative.get("image_url") or None,
            "click_url":              creative.get("click_url") or None,
            "sponsored_game_campaign_id": creative.get("sponsored_game_campaign_id"),
        },
        "created_at":                   _now(),
        "updated_at":                  _now(),
        "created_by":                  user.get("user_id"),
    }
    await db.ad_campaigns_v2.insert_one(doc)
    return _clean(doc)


async def update_campaign(db, *, advertiser_id: str, campaign_id: str,
                                                    patch: dict, user: dict) -> dict:
    await assert_owner(db, advertiser_id=advertiser_id, user=user)
    camp = await db.ad_campaigns_v2.find_one(
        {"campaign_id": campaign_id, "advertiser_id": advertiser_id})
    if not camp:
        raise LookupError("campaign_not_found")
    if camp["status"] not in ("draft", "rejected") and user.get("role") != "admin":
        raise PermissionError(f"cannot_update_from_{camp['status']}")
    top_allowed = {"name", "start_at", "end_at", "budget_total_cents",
                                "daily_cap_cents", "pricing_model",
                                "cpm_bid_cents", "cpc_bid_cents"}
    upd = {k: v for k, v in (patch or {}).items() if k in top_allowed}
    if "targeting" in (patch or {}) and isinstance(patch["targeting"], dict):
        merged = dict(camp.get("targeting") or {})
        for k in ("cities", "user_segments", "dayparts", "languages", "genres"):
            if k in patch["targeting"]:
                merged[k] = list(patch["targeting"][k] or [])
        upd["targeting"] = merged
    if "creative" in (patch or {}) and isinstance(patch["creative"], dict):
        merged = dict(camp.get("creative") or {})
        for k in ("headline", "body", "image_url", "click_url",
                          "sponsored_game_campaign_id"):
            if k in patch["creative"]:
                merged[k] = patch["creative"][k]
        upd["creative"] = merged
    upd["updated_at"] = _now()
    await db.ad_campaigns_v2.update_one(
        {"campaign_id": campaign_id}, {"$set": upd})
    return _clean(await db.ad_campaigns_v2.find_one(
        {"campaign_id": campaign_id}))


async def submit_campaign_for_approval(db, *, advertiser_id: str,
                                                                                    campaign_id: str,
                                                                                    user: dict) -> dict:
    await assert_owner(db, advertiser_id=advertiser_id, user=user)
    camp = await db.ad_campaigns_v2.find_one(
        {"campaign_id": campaign_id, "advertiser_id": advertiser_id})
    if not camp:
        raise LookupError("campaign_not_found")
    if camp["status"] not in ("draft", "rejected"):
        raise ValueError(f"cannot_submit_from_{camp['status']}")
    # Budget check — need enough available on the advertiser.
    adv = await get_advertiser(db, advertiser_id=advertiser_id)
    if (adv or {}).get("budget_available_cents", 0) < camp["budget_total_cents"]:
        # Not blocking — allow submit; admin can decide.  But surface a warning.
        logger.info("[ad1] campaign %s submitted with underfunded advertiser "
                              "(avail=%s < budget=%s)", campaign_id,
                              adv.get("budget_available_cents", 0),
                              camp["budget_total_cents"])
    await db.ad_campaigns_v2.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status":                "pending_approval",
                          "submitted_at":     _now(),
                          "updated_at":        _now()}})
    # Phase ADMOD.1 — mint a review row in the unified queue.
    try:
        from services import ad_creative_review_service as _ad_review
        # Block blocked advertisers from submitting.
        if await _ad_review.is_advertiser_blocked(db, advertiser_id):
            # Revert the status flip and raise.
            await db.ad_campaigns_v2.update_one(
                {"campaign_id": campaign_id},
                {"$set": {"status": camp.get("status")}})
            raise ValueError("advertiser_blocked")
        await _ad_review.create_review(
            db, ad_type="advertiser_campaign", target_id=campaign_id,
            advertiser_id=advertiser_id,
            submitted_by=(user or {}).get("user_id") or "system")
    except ValueError:
        raise
    except Exception as _e:
        logger.warning("[ad1] review row creation failed: %s", _e)
    return {"campaign_id": campaign_id, "status": "pending_approval"}


async def approve_campaign(db, *, campaign_id: str,
                                                          admin_user_id: str) -> dict:
    camp = await db.ad_campaigns_v2.find_one({"campaign_id": campaign_id})
    if not camp:
        raise LookupError("campaign_not_found")
    await db.ad_campaigns_v2.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status":                 "active",
                          "approved_at":      _now(),
                          "approved_by":      admin_user_id,
                          "rejected_reason": None,
                          "updated_at":         _now()}})
    # AD.1 → PG.1 linkage: if this is a sponsored_game campaign, stamp
    # the linked PG.1 game_campaign with the ad_campaign_id so the game
    # player can render sponsor branding.
    if camp.get("campaign_type") == "sponsored_game":
        gc_id = (camp.get("creative") or {}).get("sponsored_game_campaign_id")
        if gc_id:
            await db.game_campaigns.update_one(
                {"campaign_id": gc_id},
                {"$set": {"sponsored_by_ad_campaign_id": campaign_id,
                                  "updated_at": _now()}})
            # AD.2 — denormalize pricing_model + CPM/CPC + defaults onto
            # the game_campaign so the impression endpoint can bill without
            # a second ad_campaign join.  Non-blocking.
            try:
                from services.ad2_sponsored_game_service import (
                    denormalize_sponsor_to_game_campaign)
                await denormalize_sponsor_to_game_campaign(
                    db, ad_campaign_id=campaign_id)
            except Exception as _e:
                logger.warning("[ad2] denorm on approval failed: %s", _e)
    return {"campaign_id": campaign_id, "status": "active"}


async def reject_campaign(db, *, campaign_id: str,
                                                        admin_user_id: str, reason: str) -> dict:
    r = await db.ad_campaigns_v2.update_one(
        {"campaign_id": campaign_id},
        {"$set": {"status":                "rejected",
                          "rejected_reason":  reason,
                          "approved_by":       admin_user_id,
                          "updated_at":         _now()}})
    if r.matched_count == 0:
        raise LookupError("campaign_not_found")
    return {"campaign_id": campaign_id, "status": "rejected", "reason": reason}


async def pause_campaign(db, *, advertiser_id: str, campaign_id: str,
                                                user: dict) -> dict:
    await assert_owner(db, advertiser_id=advertiser_id, user=user)
    r = await db.ad_campaigns_v2.update_one(
        {"campaign_id": campaign_id, "advertiser_id": advertiser_id,
          "status": "active"},
        {"$set": {"status": "paused", "updated_at": _now()}})
    if r.matched_count == 0:
        raise ValueError("cannot_pause")
    return {"campaign_id": campaign_id, "status": "paused"}


async def end_campaign(db, *, advertiser_id: str, campaign_id: str,
                                              user: dict) -> dict:
    await assert_owner(db, advertiser_id=advertiser_id, user=user)
    now = _now()
    r = await db.ad_campaigns_v2.update_one(
        {"campaign_id": campaign_id, "advertiser_id": advertiser_id,
          "status": {"$in": ["active", "paused"]}},
        {"$set": {"status": "ended", "ended_at": now, "end_at": now.isoformat(),
                          "updated_at": now}})
    if r.matched_count == 0:
        raise ValueError("cannot_end")
    return {"campaign_id": campaign_id, "status": "ended"}


async def list_campaigns_for_advertiser(db, *, advertiser_id: str,
                                                                                          status: Optional[str] = None) -> list[dict]:
    q = {"advertiser_id": advertiser_id}
    if status:
        q["status"] = status
    docs = await db.ad_campaigns_v2.find(q).sort([("created_at", -1)]).to_list(200)
    return [_clean(d) for d in docs]


async def get_campaign(db, *, advertiser_id: str, campaign_id: str) -> Optional[dict]:
    doc = await db.ad_campaigns_v2.find_one(
        {"campaign_id": campaign_id, "advertiser_id": advertiser_id})
    return _clean(doc)


async def list_admin_campaigns(db, *, status: Optional[str] = None,
                                                                        limit: int = 200) -> list[dict]:
    q = {}
    if status:
        q["status"] = status
    docs = await db.ad_campaigns_v2.find(q).sort([("created_at", -1)]).to_list(limit)
    out = []
    for d in docs:
        adv = await db.advertisers_v2.find_one(
            {"advertiser_id": d.get("advertiser_id")},
            {"name": 1, "contact_email": 1, "logo_url": 1, "_id": 0})
        item = _clean(d)
        item["advertiser"] = adv or None
        out.append(item)
    return out


# ─── Top-up (Stripe Checkout) ─────────────────────────────────
async def create_topup_checkout(db, *, advertiser_id: str, amount_cents: int,
                                                                        user: dict,
                                                                        success_url: Optional[str] = None,
                                                                        cancel_url: Optional[str] = None) -> dict:
    adv = await assert_owner(db, advertiser_id=advertiser_id, user=user)
    if amount_cents < 500:            # $5 floor
        raise ValueError("amount_cents_below_floor")
    if amount_cents > 500_00_00:    # $5000 ceiling
        raise ValueError("amount_cents_above_ceiling")
    # Use payments_v2 generic checkout via HTTP-safe pathway (in-process call).
    # We call Stripe directly here since we already have the mode helper.
    from services.stripe_client import is_live, _live_stripe, _mock_id, stripe_mode
    public_base = (os.environ.get("PUBLIC_BACKEND_URL")
                              or os.environ.get("REACT_APP_BACKEND_URL")
                              or "https://mobile-games-v2.preview.emergentagent.com")
    s_url = success_url or f"{public_base}/advertiser/dashboard/budget?topup=success"
    c_url = cancel_url or f"{public_base}/advertiser/dashboard/budget?topup=cancel"
    metadata = {
        "purpose":              "advertiser_topup_v2",
        "entity_id":         advertiser_id,
        "advertiser_id":  advertiser_id,
        "user_id":              user.get("user_id"),
        "amount_cents":  str(int(amount_cents)),
    }
    payment_id = _gen("adpay")
    if is_live():
        sess = _live_stripe().checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency":       "usd",
                    "unit_amount": int(amount_cents),
                    "product_data": {
                        "name": f"BigFM Ad Budget Top-up ${amount_cents/100:.2f}",
                        "description": f"Credit to {adv['name']}"[:300],
                    },
                },
                "quantity": 1,
            }],
            metadata=metadata,
            success_url=s_url, cancel_url=c_url,
            customer_email=adv.get("contact_email"),
        )
        session_id = sess["id"]
        checkout_url = sess["url"]
        mocked = False
    else:
        session_id = _mock_id("cs")
        checkout_url = f"/mock/stripe/checkout?session_id={session_id}&purpose=advertiser_topup_v2"
        mocked = True
    now = _now()
    await db.ad_payments.insert_one({
        "payment_id":                              payment_id,
        "advertiser_id":                           advertiser_id,
        "campaign_id":                             None,
        "amount_cents":                            int(amount_cents),
        "currency":                                    "usd",
        "stripe_checkout_session_id":  session_id,
        "status":                                        "pending",
        "created_at":                                now,
        "paid_at":                                      None,
        "stripe_mode":                             stripe_mode(),
        "mocked":                                     mocked,
    })
    # Also register the payment_intent tracker for the shared webhook.
    await db.payment_intents_v2.update_one(
        {"_id": session_id},
        {"$setOnInsert": {
            "_id":                          session_id,
            "user_id":                  user.get("user_id"),
            "purpose":                  "advertiser_topup_v2",
            "entity_id":              advertiser_id,
            "amount_cents":      int(amount_cents),
            "currency":                "usd",
            "status":                    "pending",
            "stripe_mode":         stripe_mode(),
            "created_at":            now,
        }}, upsert=True)
    return {
        "payment_id":         payment_id,
        "checkout_url":     checkout_url,
        "session_id":         session_id,
        "amount_cents": int(amount_cents),
        "mocked":                mocked,
    }


async def credit_topup_on_webhook(db, *, session_id: str,
                                                                              advertiser_id: str,
                                                                              amount_cents: int) -> dict:
    """Called by the shared /api/webhooks/stripe/events handler when a
    checkout.session.completed event has purpose=`advertiser_topup_v2`.
    Idempotent on the payment row's `status` transition."""
    now = _now()
    pay_before = await db.ad_payments.find_one(
        {"stripe_checkout_session_id": session_id})
    if pay_before and pay_before.get("status") == "paid":
        return {"ok": True, "already_credited": True,
                      "payment_id": pay_before["payment_id"]}
    r = await db.ad_payments.update_one(
        {"stripe_checkout_session_id": session_id, "status": {"$ne": "paid"}},
        {"$set": {"status": "paid", "paid_at": now, "credited_cents": int(amount_cents)}})
    if r.matched_count == 0:
        # Payment row not found — create a reconciliation row so the webhook
        # is idempotent even for out-of-band top-ups.
        pid = _gen("adpay")
        await db.ad_payments.insert_one({
            "payment_id":                             pid,
            "advertiser_id":                          advertiser_id,
            "campaign_id":                            None,
            "amount_cents":                           int(amount_cents),
            "currency":                                   "usd",
            "stripe_checkout_session_id": session_id,
            "status":                                       "paid",
            "created_at":                               now,
            "paid_at":                                     now,
            "reconciliation":                         True,
        })
    # Credit the advertiser wallet atomically.
    r2 = await db.advertisers_v2.update_one(
        {"advertiser_id": advertiser_id},
        {"$inc": {"budget_available_cents": int(amount_cents)},
          "$set": {"updated_at": now}})
    return {"ok": True, "credited_cents": int(amount_cents),
                  "matched_advertiser": r2.matched_count}


# ─── Impression stub + analytics ──────────────────────────────
async def record_impression(db, *, campaign_id: str, user_id: Optional[str],
                                                            placement: str,
                                                            cost_cents: int = 0) -> dict:
    """Stub for future real ad serving.  Writes an ad_impressions_v2 row
    and increments budget_spent_cents.  Not currently called by any live
    surface — kept here so /analytics has data to aggregate."""
    imp = {
        "imp_id":         _gen("imp"),
        "campaign_id": campaign_id,
        "user_id":         user_id,
        "placement":    placement,
        "cost_cents":    int(cost_cents or 0),
        "timestamp":    _now(),
    }
    await db.ad_impressions_v2.insert_one(imp)
    if cost_cents:
        await db.ad_campaigns_v2.update_one(
            {"campaign_id": campaign_id},
            {"$inc": {"budget_spent_cents": int(cost_cents)}})
    return _clean(imp)


async def campaign_analytics(db, *, campaign_id: str) -> dict:
    camp = await db.ad_campaigns_v2.find_one({"campaign_id": campaign_id})
    if not camp:
        raise LookupError("campaign_not_found")
    impressions = await db.ad_impressions_v2.count_documents(
        {"campaign_id": campaign_id})
    # Clicks = subset with placement ending in "_click" (convention for stub);
    # keeps the shape ready without hard-coding a real click collection yet.
    clicks = await db.ad_impressions_v2.count_documents(
        {"campaign_id": campaign_id, "placement": {"$regex": "_click$"}})
    spend = int(camp.get("budget_spent_cents") or 0)
    total = int(camp.get("budget_total_cents") or 0)
    ctr = (clicks / impressions) if impressions else 0.0
    return {
        "campaign_id":                  campaign_id,
        "impressions":                  impressions,
        "clicks":                              clicks,
        "spend_cents":                  spend,
        "ctr":                                  round(ctr, 4),
        "remaining_budget_cents":  max(0, total - spend),
        "budget_total_cents":       total,
        "status":                              camp.get("status"),
    }


# ─── Advertiser dashboard overview ────────────────────────────
async def advertiser_overview(db, *, advertiser_id: str) -> dict:
    adv = await get_advertiser(db, advertiser_id=advertiser_id)
    if not adv:
        raise LookupError("advertiser_not_found")
    active_camps = await db.ad_campaigns_v2.count_documents(
        {"advertiser_id": advertiser_id, "status": "active"})
    now = _now()
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    impressions_month = await db.ad_impressions_v2.count_documents({
        "campaign_id": {"$in": [c["campaign_id"] async for c in
                                                db.ad_campaigns_v2.find(
                                                  {"advertiser_id": advertiser_id},
                                                  {"campaign_id": 1, "_id": 0})]},
        "timestamp": {"$gte": start_of_month},
    })
    # Aggregate spend across all campaigns for this advertiser (all-time).
    spend_pipe = [
        {"$match": {"advertiser_id": advertiser_id}},
        {"$group": {"_id": None,
                              "total": {"$sum": "$budget_spent_cents"}}},
    ]
    total_spend = 0
    async for row in db.ad_campaigns_v2.aggregate(spend_pipe):
        total_spend = int(row.get("total") or 0)
    return {
        "advertiser_id":                  advertiser_id,
        "name":                                    adv.get("name"),
        "status":                                  adv.get("status"),
        "budget_available_cents": int(adv.get("budget_available_cents") or 0),
        "active_campaigns":            active_camps,
        "impressions_this_month": impressions_month,
        "total_spend_cents":            total_spend,
    }
