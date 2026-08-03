"""Phase 36e Turn 1 — Subscription core service.

Collections:
    creator_stripe_accounts            (UNIQUE creator_id)
    creator_subscription_plans      (UNIQUE active plan per channel)
    listener_subscriptions               (UNIQUE active sub per (user, channel))
    subscription_events                  (audit log, indexed by sub_id)

All Stripe touches route through services.stripe_client.

Paywall gate: `is_episode_accessible(episode, user)`.
Active-sub helper: `user_has_active_sub_for_channel(db, user_id, channel_id)`.

NO money is moved here. NO real Stripe calls happen in mock mode.
"""
from __future__ import annotations
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from pymongo import ASCENDING, DESCENDING

from services import stripe_client

logger = logging.getLogger("bigfm.subscriptions")

MIN_PRICE_CENTS = 300                  # $3
DEFAULT_TRIAL_DAYS = 7
DEFAULT_PLATFORM_CUT_PCT = 15


# ─── Indexes (lazy) ──────────────────────────────────────────────
_indexes_built = False
async def ensure_indexes(db) -> None:
    global _indexes_built
    if _indexes_built: return
    try:
        await db.creator_stripe_accounts.create_index(
            "creator_id", unique=True, name="creator_uniq")
        await db.creator_stripe_accounts.create_index(
            "stripe_account_id", name="acct_lookup", sparse=True)
        await db.creator_subscription_plans.create_index(
            [("channel_id", ASCENDING), ("active", ASCENDING)],
            partialFilterExpression={"active": True},
            unique=True, name="active_plan_uniq")
        await db.creator_subscription_plans.create_index("creator_id")
        await db.listener_subscriptions.create_index(
            "stripe_subscription_id", name="stripe_sub_lookup", sparse=True)
        await db.listener_subscriptions.create_index(
            [("channel_id", ASCENDING), ("status", ASCENDING)])
        await db.listener_subscriptions.create_index(
            [("listener_user_id", ASCENDING), ("status", ASCENDING)])
        await db.subscription_events.create_index("subscription_id")
        await db.subscription_events.create_index([("created_at", DESCENDING)])
    except Exception as e:
        logger.warning(f"subscriptions index build skipped: {e}")
    _indexes_built = True


def _now():
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    if not doc: return None
    doc.pop("_id", None)
    for k in ("created_at", "updated_at", "onboarding_completed_at",
                      "trial_end", "current_period_end", "canceled_at"):
        v = doc.get(k)
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


# ─── Creator Stripe accounts ─────────────────────────────────────
async def get_or_create_stripe_account(db, *, creator: dict,
                                                                                creator_email: str) -> dict:
    """Idempotent: returns existing row or creates a new Stripe Express
    account + row."""
    await ensure_indexes(db)
    existing = await db.creator_stripe_accounts.find_one(
        {"creator_id": creator["id"]})
    if existing:
        return _serialize(existing)
    acct = stripe_client.create_express_account(email=creator_email)
    now = _now()
    doc = {
        "id":                                          _new_id("csa"),
        "creator_id":                          creator["id"],
        "stripe_account_id":          acct["id"],
        "charges_enabled":              bool(acct.get("charges_enabled")),
        "payouts_enabled":              bool(acct.get("payouts_enabled")),
        "details_submitted":          bool(acct.get("details_submitted")),
        "onboarding_completed_at": None,
        "default_currency":            acct.get("default_currency", "usd"),
        "created_at":                          now,
        "updated_at":                          now,
    }
    await db.creator_stripe_accounts.insert_one(doc)
    return _serialize(doc)


async def refresh_stripe_account(db, *, creator_id: str) -> dict:
    await ensure_indexes(db)
    row = await db.creator_stripe_accounts.find_one(
        {"creator_id": creator_id})
    if not row: raise HTTPException(404, "stripe_account_not_found")
    acct = stripe_client.retrieve_account(row["stripe_account_id"])
    now = _now()
    update = {
        "charges_enabled":              bool(acct.get("charges_enabled")),
        "payouts_enabled":              bool(acct.get("payouts_enabled")),
        "details_submitted":          bool(acct.get("details_submitted")),
        "updated_at":                          now,
    }
    # First time all three booleans flip true → stamp onboarding completion.
    if (update["charges_enabled"] and update["payouts_enabled"]
            and update["details_submitted"]
            and not row.get("onboarding_completed_at")):
        update["onboarding_completed_at"] = now
    await db.creator_stripe_accounts.update_one(
        {"id": row["id"]}, {"$set": update})
    return _serialize(await db.creator_stripe_accounts.find_one({"id": row["id"]}))


# ─── Plans ───────────────────────────────────────────────────────
DEFAULT_FEATURES = {"ad_free": True, "early_access_hours": 24,
                                      "bonus_episodes": True}


async def create_plan(db, *, creator: dict, channel_id: str,
                                          name: str, price_cents: int,
                                          trial_days: int = DEFAULT_TRIAL_DAYS,
                                          features: Optional[dict] = None) -> dict:
    await ensure_indexes(db)
    if price_cents < MIN_PRICE_CENTS:
        raise HTTPException(400,
            f"price_cents must be >= {MIN_PRICE_CENTS} (${MIN_PRICE_CENTS/100:.2f})")
    if not (1 <= trial_days <= 30):
        raise HTTPException(400, "trial_days must be in [1, 30]")
    acct = await db.creator_stripe_accounts.find_one(
        {"creator_id": creator["id"]})
    if not acct or not acct.get("charges_enabled"):
        raise HTTPException(412, "stripe_charges_not_enabled")
    # Reject 2nd active plan on the channel.
    dup = await db.creator_subscription_plans.find_one(
        {"channel_id": channel_id, "active": True})
    if dup: raise HTTPException(409, "active_plan_exists")
    product = stripe_client.create_product(
        name=name, metadata={"channel_id": channel_id,
                                              "creator_id": creator["id"]})
    price = stripe_client.create_recurring_price(
        product_id=product["id"], unit_amount_cents=price_cents)
    now = _now()
    f = dict(DEFAULT_FEATURES)
    if features: f.update({k: v for k, v in features.items() if k in DEFAULT_FEATURES})
    doc = {
        "id":                                  _new_id("csp"),
        "creator_id":                  creator["id"],
        "channel_id":                  channel_id,
        "name":                              name,
        "price_cents":              int(price_cents),
        "currency":                      "usd",
        "trial_days":                  trial_days,
        "features":                      f,
        "stripe_product_id":  product["id"],
        "stripe_price_id":      price["id"],
        "active":                          True,
        "created_at":                  now,
        "updated_at":                  now,
    }
    await db.creator_subscription_plans.insert_one(doc)
    # Denormalize on channel for fast checks.
    await db.podcast_channels.update_one(
        {"id": channel_id}, {"$set": {"has_active_plan": True,
                                                                "platform_cut_pct": DEFAULT_PLATFORM_CUT_PCT}})
    return _serialize(doc)


async def get_active_plan(db, *, channel_id: str) -> Optional[dict]:
    await ensure_indexes(db)
    return _serialize(await db.creator_subscription_plans.find_one(
        {"channel_id": channel_id, "active": True}))


async def patch_plan(db, *, creator: dict, channel_id: str,
                                        patch: dict) -> dict:
    plan = await db.creator_subscription_plans.find_one(
        {"channel_id": channel_id, "active": True})
    if not plan or plan["creator_id"] != creator["id"]:
        raise HTTPException(404, "plan_not_found")
    allowed = {"name", "features", "active"}
    update = {k: v for k, v in patch.items() if k in allowed}
    if "price_cents" in patch:
        # TODO Phase 36e+: real Stripe price migration. For now, refuse.
        raise HTTPException(400, "price_change_requires_stripe_migration_TODO")
    if not update:
        raise HTTPException(400, "no_editable_fields")
    update["updated_at"] = _now()
    await db.creator_subscription_plans.update_one(
        {"id": plan["id"]}, {"$set": update})
    if update.get("active") is False:
        # Plan paused/soft-deleted — drop the channel flag.
        await db.podcast_channels.update_one(
            {"id": channel_id}, {"$set": {"has_active_plan": False}})
    return _serialize(await db.creator_subscription_plans.find_one(
        {"id": plan["id"]}))


# ─── Listener subscriptions ──────────────────────────────────────
async def user_has_active_sub_for_channel(db, *, user_id: str,
                                                                                          channel_id: str) -> bool:
    if not user_id or not channel_id: return False
    return await db.listener_subscriptions.count_documents({
        "listener_user_id": user_id,
        "channel_id":              channel_id,
        "status":                      {"$in": ["trialing", "active"]},
    }) > 0


async def list_user_subscriptions(db, *, user_id: str) -> list:
    await ensure_indexes(db)
    out = []
    async for d in db.listener_subscriptions.find(
            {"listener_user_id": user_id,
              "status": {"$in": ["trialing", "active", "past_due"]}},
            {"_id": 0}):
        out.append(_serialize(d))
    return out


# ─── Phase 36f — Creator SaaS tier checkout ──────────────────────
# Distinct from `create_checkout` below (listener → channel). This is the
# CREATOR upgrading their own platform tier (e.g. lite → pro). Plans are
# global, not per-channel; subscription rows live in
# `creator_saas_subscriptions`. Mobile flagged the missing endpoint during
# Phase 36f Turn 2.
CREATOR_SAAS_PLANS = {
    "creator_lite":      {"price_id_env": "STRIPE_PRICE_CREATOR_LITE",
                                      "fallback":          "price_mock_creator_lite"},
    "creator_pro":        {"price_id_env": "STRIPE_PRICE_CREATOR_PRO",
                                      "fallback":          "price_mock_creator_pro"},
    "creator_studio": {"price_id_env": "STRIPE_PRICE_CREATOR_STUDIO",
                                      "fallback":          "price_mock_creator_studio"},
}


def _resolve_creator_plan_price_id(plan_id: str) -> str:
    import os
    cfg = CREATOR_SAAS_PLANS.get(plan_id)
    if not cfg:
        raise HTTPException(400, {"code": "invalid_plan_id",
                                                          "allowed": list(CREATOR_SAAS_PLANS.keys())})
    return os.environ.get(cfg["price_id_env"]) or cfg["fallback"]


async def get_active_creator_saas_sub(db, *, creator_id: str) -> Optional[dict]:
    return await db.creator_saas_subscriptions.find_one({
        "creator_id": creator_id,
        "status":          {"$in": ["trialing", "active", "past_due"]},
    }, {"_id": 0})


async def create_creator_saas_checkout(db, *, user: dict, creator: dict,
                                                                            plan_id: str, success_url: str,
                                                                            cancel_url: str) -> dict:
    """Wraps `stripe_client.create_checkout_session` for the creator-tier
    upgrade flow. Idempotent — returns 409 `already_subscribed` if the
    creator already has an active SaaS sub. Persists a
    `creator_saas_subscriptions` row keyed by the Stripe checkout session
    id."""
    await ensure_indexes(db)
    price_id = _resolve_creator_plan_price_id(plan_id)
    existing = await get_active_creator_saas_sub(db, creator_id=creator["id"])
    if existing:
        raise HTTPException(409, {"code":                "already_subscribed",
                                                          "subscription_id": existing["id"],
                                                          "plan_id":              existing.get("plan_id")})
    sub_row_id = _new_id("csub")
    cs = stripe_client.create_checkout_session(
        customer_email=user.get("email") or "creator@bigfm.local",
        price_id=price_id,
        success_url=success_url,
        cancel_url=cancel_url,
        trial_period_days=DEFAULT_TRIAL_DAYS,
        client_reference_id=sub_row_id,
        metadata={"flow":              "creator_saas",
                            "creator_id": creator["id"],
                            "plan_id":      plan_id,
                            "user_id":      user["user_id"]})
    now = _now()
    expires_at = now + timedelta(hours=24)
    doc = {
        "id":                                              sub_row_id,
        "creator_id":                              creator["id"],
        "owner_user_id":                      user["user_id"],
        "plan_id":                                      plan_id,
        "stripe_price_id":                    price_id,
        "stripe_checkout_session_id": cs["id"],
        "stripe_subscription_id":      None,    # set by webhook
        "status":                                      "incomplete",
        "trial_end":                                None,
        "current_period_end":              now + timedelta(days=DEFAULT_TRIAL_DAYS),
        "cancel_at_period_end":          False,
        "created_at":                              now,
        "updated_at":                              now,
        "expires_at":                              expires_at,
    }
    await db.creator_saas_subscriptions.insert_one(doc)
    return {"checkout_url":      cs["url"],
                  "session_id":          cs["id"],
                  "plan_id":                plan_id,
                  "subscription_id": sub_row_id,
                  "expires_at":        expires_at.isoformat()}



async def create_checkout(db, *, user: dict, channel_id: str,
                                                base_url: str) -> dict:
    """Creates an `incomplete` sub row + Stripe Checkout Session.
    Listener clicks the URL → completes (mock or live) → webhook flips
    status to `trialing`."""
    await ensure_indexes(db)
    plan = await db.creator_subscription_plans.find_one(
        {"channel_id": channel_id, "active": True})
    if not plan: raise HTTPException(404, "no_active_plan")
    # Reject duplicate active sub.
    active = await db.listener_subscriptions.find_one({
        "listener_user_id": user["user_id"],
        "channel_id":              channel_id,
        "status":                      {"$in": ["trialing", "active", "past_due"]},
    })
    if active: raise HTTPException(409, "already_subscribed")
    acct = await db.creator_stripe_accounts.find_one(
        {"creator_id": plan["creator_id"]})
    sub_row_id = _new_id("lsub")
    cs = stripe_client.create_checkout_session(
        customer_email=user.get("email") or "anon@bigfm.local",
        price_id=plan["stripe_price_id"],
        success_url=f"{base_url}/listener/subscriptions?welcome=1",
        cancel_url=f"{base_url}/podcasts/{channel_id}?canceled=1",
        trial_period_days=plan["trial_days"],
        connected_account_id=(acct or {}).get("stripe_account_id"),
        application_fee_percent=float(DEFAULT_PLATFORM_CUT_PCT),
        client_reference_id=sub_row_id,
        metadata={"channel_id": channel_id, "plan_id": plan["id"],
                            "listener_user_id": user["user_id"]})
    now = _now()
    doc = {
        "id":                                              sub_row_id,
        "listener_user_id":                  user["user_id"],
        "channel_id":                              channel_id,
        "plan_id":                                      plan["id"],
        "stripe_subscription_id":      None,    # set by webhook
        "stripe_customer_id":              None,
        "stripe_checkout_session_id": cs["id"],
        "status":                                      "incomplete",
        "trial_end":                                None,
        "current_period_end":              now + timedelta(days=plan["trial_days"]),
        "cancel_at_period_end":          False,
        "created_at":                              now,
        "updated_at":                              now,
        "canceled_at":                          None,
    }
    await db.listener_subscriptions.insert_one(doc)
    return {"checkout_url": cs["url"], "session_id": cs["id"],
                  "subscription_id": sub_row_id}


async def cancel_subscription(db, *, user: dict,
                                                              lsub_id: str) -> dict:
    sub = await db.listener_subscriptions.find_one({"id": lsub_id})
    if not sub or sub["listener_user_id"] != user["user_id"]:
        raise HTTPException(404, "subscription_not_found")
    if sub["status"] in ("canceled", "incomplete"):
        raise HTTPException(400, "cannot_cancel_in_current_state")
    if sub.get("stripe_subscription_id"):
        stripe_client.cancel_subscription_at_period_end(
            subscription_id=sub["stripe_subscription_id"], cancel=True)
    await db.listener_subscriptions.update_one(
        {"id": lsub_id},
        {"$set": {"cancel_at_period_end": True, "updated_at": _now()}})
    return _serialize(await db.listener_subscriptions.find_one({"id": lsub_id}))


async def resume_subscription(db, *, user: dict,
                                                              lsub_id: str) -> dict:
    sub = await db.listener_subscriptions.find_one({"id": lsub_id})
    if not sub or sub["listener_user_id"] != user["user_id"]:
        raise HTTPException(404, "subscription_not_found")
    if not sub.get("cancel_at_period_end"):
        raise HTTPException(400, "not_in_cancellation")
    if sub.get("stripe_subscription_id"):
        stripe_client.cancel_subscription_at_period_end(
            subscription_id=sub["stripe_subscription_id"], cancel=False)
    await db.listener_subscriptions.update_one(
        {"id": lsub_id},
        {"$set": {"cancel_at_period_end": False, "updated_at": _now()}})
    return _serialize(await db.listener_subscriptions.find_one({"id": lsub_id}))


# ─── Webhook handler ─────────────────────────────────────────────
async def handle_stripe_event(db, *, event: dict) -> dict:
    """Process a Stripe-shaped event dict (already signature-verified
    upstream). Idempotent on `stripe_event_id`."""
    await ensure_indexes(db)
    etype = event.get("type")
    obj      = (event.get("data") or {}).get("object") or {}
    stripe_event_id = event.get("id")
    sub_id_local = None
    new_status      = None
    extra_set      = {}

    if etype in ("customer.subscription.created",
                          "customer.subscription.updated",
                          "customer.subscription.deleted"):
        # Find listener_subscriptions row via client_reference_id
        # (set during checkout) OR via stripe_subscription_id.
        ref      = obj.get("client_reference_id") or (obj.get("metadata") or {}).get("listener_sub_id")
        stripe_sub_id = obj.get("id")
        row      = None
        if ref:
            row = await db.listener_subscriptions.find_one({"id": ref})
        if not row and stripe_sub_id:
            row = await db.listener_subscriptions.find_one(
                {"stripe_subscription_id": stripe_sub_id})
        if row:
            sub_id_local = row["id"]
            new_status = obj.get("status") or "active"
            extra_set = {
                "stripe_subscription_id": stripe_sub_id or row.get("stripe_subscription_id"),
                "stripe_customer_id":          obj.get("customer") or row.get("stripe_customer_id"),
                "status":                                  new_status,
                "cancel_at_period_end":      bool(obj.get("cancel_at_period_end") or False),
                "updated_at":                          _now(),
            }
            # Convert epoch seconds → datetime if present.
            if obj.get("trial_end"):
                extra_set["trial_end"] = datetime.fromtimestamp(
                    obj["trial_end"], tz=timezone.utc)
            if obj.get("current_period_end"):
                extra_set["current_period_end"] = datetime.fromtimestamp(
                    obj["current_period_end"], tz=timezone.utc)
            if etype == "customer.subscription.deleted":
                extra_set["status"]            = "canceled"
                extra_set["canceled_at"] = _now()
            await db.listener_subscriptions.update_one(
                {"id": row["id"]}, {"$set": extra_set})

    elif etype == "invoice.payment_succeeded":
        sub_stripe_id = obj.get("subscription")
        if sub_stripe_id:
            row = await db.listener_subscriptions.find_one(
                {"stripe_subscription_id": sub_stripe_id})
            if row:
                sub_id_local = row["id"]
                await db.listener_subscriptions.update_one(
                    {"id": row["id"]},
                    {"$set": {"status": "active", "updated_at": _now()}})

    elif etype == "invoice.payment_failed":
        sub_stripe_id = obj.get("subscription")
        if sub_stripe_id:
            row = await db.listener_subscriptions.find_one(
                {"stripe_subscription_id": sub_stripe_id})
            if row:
                sub_id_local = row["id"]
                await db.listener_subscriptions.update_one(
                    {"id": row["id"]},
                    {"$set": {"status": "past_due", "updated_at": _now()}})

    # Always emit an event row — even unmatched events are audited.
    event_map = {
        "customer.subscription.created":  "trial_started",
        "customer.subscription.updated":  "renewed",
        "customer.subscription.deleted":  "canceled",
        "invoice.payment_succeeded":          "trial_converted",
        "invoice.payment_failed":                "payment_failed",
    }
    await db.subscription_events.insert_one({
        "id":                          _new_id("se"),
        "subscription_id":  sub_id_local,
        "event_type":              event_map.get(etype, etype),
        "stripe_event_id":  stripe_event_id,
        "payload_json":      obj,
        "created_at":              _now(),
    })
    return {"ok": True, "matched_sub_id": sub_id_local,
                  "status_set": new_status, "type": etype}


# ─── Paywall gate ────────────────────────────────────────────────
def _to_dt(v):
    if isinstance(v, datetime): return v
    if isinstance(v, str):
        try: return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception: return None
    return None


async def is_episode_accessible(db, *, episode: dict,
                                                              user: Optional[dict]) -> bool:
    """Returns True if `user` (may be None) can access `episode`."""
    is_bonus     = bool(episode.get("is_bonus"))
    embargo_ts = _to_dt(episode.get("release_for_subscribers_at"))
    now              = _now()
    embargo_active = bool(embargo_ts and now < embargo_ts)
    if not is_bonus and not embargo_active:
        return True
    if not user: return False
    return await user_has_active_sub_for_channel(
        db, user_id=user.get("user_id"), channel_id=episode.get("channel_id"))


def paywall_payload(*, channel_id: str, plan: Optional[dict]) -> dict:
    """Shape the 402 response so the FE knows where to drive the user."""
    if not plan:
        return {"paywall": {"channel_id": channel_id,
                                            "plan_id": None, "price_cents": None,
                                            "trial_days": None,
                                            "reason": "no_active_plan"}}
    return {"paywall": {
        "channel_id":  channel_id,
        "plan_id":          plan["id"],
        "plan_name":  plan["name"],
        "price_cents": plan["price_cents"],
        "currency":      plan.get("currency", "usd"),
        "trial_days":  plan["trial_days"],
        "features":      plan["features"],
    }}
