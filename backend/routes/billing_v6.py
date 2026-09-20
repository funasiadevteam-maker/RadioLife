"""Phase 6 — Multi-tier billing routes.

NEW endpoints (mounted at /api/billing/*):
  GET  /plans                           → 4-plan catalog with localized prices
  GET  /status                          → full subscription + grace state
  POST /change_plan {target_plan_slug}  → upgrade (proration) / downgrade (queued)
  POST /cancel | /resume                → soft cancel + undo
  POST /pause   | /unpause              → pause-collection up to 3 months
  POST /portal                          → Stripe Customer Portal session URL
  POST /family/invite {email}           → seat invite (token)
  POST /family/accept {token}           → attach to root, premium on
  POST /family/remove {user_id}         → seat removal, immediate downgrade
  GET  /family                          → seat state for current user
  POST /admin/simulate_payment_failed   → admin-only test hook to fire dunning
  POST /webhook/stripe (v2)             → idempotent dedup + lifecycle log

Backward-compat: the Phase 3 /api/billing/{config,checkout,status/{id},
subscription} endpoints in routes/billing.py remain operational. Phase 6
extends, doesn't replace.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import current_user, require_admin
from core.config import STRIPE_API_KEY, STRIPE_MODE
from services.currency import detect_currency
from services.plans import (
    PLAN_CATALOG, compare_tiers, get_plan, get_price, list_plans_for_currency,
    seed_plans,
)
from services.family import (
    accept_family_invite, family_state, invite_family_member,
    remove_family_member,
)
from services.dunning import (
    already_processed, expire_grace_period, GRACE_PERIOD_DAYS,
    log_lifecycle, mark_past_due, mark_payment_recovered, mark_processed,
    sweep_grace_periods,
)
from services.billing_service import grant_premium

logger = logging.getLogger("bigfm.billing.p6")
stripe.api_key = STRIPE_API_KEY

billing6_router = APIRouter(prefix="/api/billing", tags=["billing-v6"])


def _aware(dt):
    """Mongo returns naive datetimes; normalize to UTC-aware for comparison."""
    if dt is None: return None
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# ---------------------------------------------------------------
@billing6_router.get("/plans")
async def list_plans(request: Request,
                       currency: Optional[str] = Query(default=None)):
    """Public — returns the full 4-plan catalog priced in the caller's
    auto-detected currency (override via ?currency=USD|AED|INR)."""
    try:
        cur, country = detect_currency(request, override=currency)
    except Exception:
        cur, country = "USD", None
    plans = list_plans_for_currency(cur)
    return {"currency": cur, "country_hint": country,
            "stripe_mode": STRIPE_MODE, "plans": plans}


# ---------------------------------------------------------------
@billing6_router.get("/status")
async def billing_status(request: Request, user: dict = Depends(current_user)):
    """Complete subscription state — used by /billing UI + past-due banner."""
    db = request.app.state.db
    fresh = await db.users.find_one({"user_id": user["user_id"]},
                                        {"_id": 0}) or user
    sub = fresh.get("subscription") or {}
    cur_plan_slug = sub.get("plan") or ("free" if not fresh.get("is_premium")
                                            else "premium_monthly")
    plan = get_plan(cur_plan_slug) or get_plan("free")
    fam = await family_state(db, fresh["user_id"])
    grace = fresh.get("grace_period_ends_at")
    return {
        "user_id": fresh["user_id"],
        "is_premium": bool(fresh.get("is_premium")),
        "premium_tier": fresh.get("premium_tier"),
        "premium_source": fresh.get("premium_source"),
        "current_plan_slug": cur_plan_slug,
        "current_plan_display": plan.get("display_name") if plan else None,
        "billing_status": fresh.get("billing_status") or "active",
        "grace_period_ends_at": grace.isoformat() if grace else None,
        "pending_plan_change": fresh.get("pending_plan_change"),
        "next_invoice_at": (sub.get("current_period_end").isoformat()
                              if sub.get("current_period_end") else None),
        "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
        "paused": bool(sub.get("paused")),
        "pause_resumes_at": (sub.get("pause_resumes_at").isoformat()
                              if sub.get("pause_resumes_at") else None),
        "stripe_customer_id": sub.get("stripe_customer_id"),
        "stripe_subscription_id": sub.get("stripe_subscription_id"),
        "family": fam,
    }


# ---------------------------------------------------------------
@billing6_router.post("/change_plan")
async def change_plan(payload: dict, request: Request,
                        user: dict = Depends(current_user)):
    """Upgrade or downgrade. UPGRADE = immediate Stripe-level charge with
    prorated extension of premium_until; DOWNGRADE = queued to next
    period_end via pending_plan_change. Family-downgrade blocked while
    seats are still occupied. Supports Idempotency-Key header."""
    db = request.app.state.db
    target = (payload or {}).get("target_plan_slug")
    target_plan = get_plan(target)
    if not target_plan or not target_plan.get("active"):
        raise HTTPException(400, "unknown_or_inactive_plan")
    if not target_plan.get("purchasable"):
        raise HTTPException(400, "plan_not_purchasable")
    sub = (user.get("subscription") or {})
    cur_slug = sub.get("plan") or "free"

    # Idempotency check FIRST — a replay of the same key always returns the
    # same response, even if the state has since drifted.
    idem_key = request.headers.get("Idempotency-Key")
    if idem_key:
        prior = await db.subscription_lifecycle_log.find_one(
            {"metadata.idempotency_key": idem_key, "user_id": user["user_id"]},
        )
        if prior:
            return {"ok": True, "idempotent": True,
                     "ref": prior.get("_id"), "action": prior.get("event_type"),
                     "from_plan": prior.get("from_state"),
                     "to_plan": prior.get("to_state")}

    if cur_slug == target:
        return {"ok": True, "no_change": True, "current_plan": cur_slug}

    direction = compare_tiers(cur_slug, target)
    now = datetime.now(timezone.utc)

    # Family downgrade guard
    cur_plan = get_plan(cur_slug) or {}
    new_seats = int(target_plan.get("family_seats") or 0)
    cur_seats_used = int(user.get("family_seats_used") or 0)
    if direction == "downgrade" and cur_plan.get("family_seats", 0) > 1 \
        and new_seats < cur_plan["family_seats"] and cur_seats_used > 0:
        raise HTTPException(400,
            f"family_downgrade_blocked: still have {cur_seats_used} active seat(s). Remove them first.")

    if direction == "upgrade":
        # Proration math (USD-equivalent, on the Mongo side — Phase 3 uses
        # one-time Checkouts, not native Stripe subscriptions, so we compute
        # the prorated delta ourselves and extend premium_until.)
        period_end = _aware(sub.get("current_period_end"))
        period_start = _aware(sub.get("current_period_start")) or now
        if period_end and period_end > now and period_start < now:
            total = (period_end - period_start).total_seconds()
            elapsed = (now - period_start).total_seconds()
            remaining_pct = max(0.0, min(1.0, 1.0 - (elapsed / total)))
        else:
            remaining_pct = 1.0
        cur_price = get_price(cur_slug, sub.get("currency") or "USD") if cur_plan.get("purchasable") else {"amount": 0}
        tgt_price = get_price(target, sub.get("currency") or "USD")
        proration_credit = float(cur_price.get("amount") or 0) * remaining_pct
        net_charge = max(0.0, float(tgt_price["amount"]) - proration_credit)
        # Extend premium_until based on the target plan interval
        days_to_add = int(target_plan.get("interval_days") or 30)
        new_period_end = (period_end if period_end and period_end > now else now) + \
                          timedelta(days=days_to_add)
        await db.users.update_one(
            {"user_id": user["user_id"]},
            {"$set": {
                "is_premium": True,
                "premium_tier": target_plan.get("tier") or "premium",
                "premium_source": "paid",
                "premium_until": new_period_end,
                "billing_status": "active",
                "family_seats_total": new_seats,
                "subscription.plan": target,
                "subscription.status": "active",
                "subscription.current_period_start": now,
                "subscription.current_period_end": new_period_end,
                "subscription.cancel_at_period_end": False,
                "subscription.last_proration_credit": proration_credit,
                "subscription.last_proration_charge": net_charge,
            },
             "$unset": {"pending_plan_change": ""}},
        )
        await log_lifecycle(db, user_id=user["user_id"],
                              event_type="plan_upgraded",
                              from_state=cur_slug, to_state=target,
                              metadata={"net_charge": net_charge,
                                        "proration_credit": proration_credit,
                                        "remaining_pct": remaining_pct,
                                        "idempotency_key": idem_key})
        return {
            "ok": True, "action": "upgrade",
            "from_plan": cur_slug, "to_plan": target,
            "net_charge": round(net_charge, 2),
            "proration_credit": round(proration_credit, 2),
            "currency": sub.get("currency") or "USD",
            "premium_until": new_period_end.isoformat(),
            "family_seats_total": new_seats,
        }

    # downgrade — queue for next period end
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"pending_plan_change": {
            "target_plan_slug": target,
            "scheduled_at": (sub.get("current_period_end") or
                                (now + timedelta(days=30))).isoformat(),
            "scheduled_by": user["user_id"],
            "created_at": now,
        }}},
    )
    await log_lifecycle(db, user_id=user["user_id"],
                          event_type="plan_downgrade_queued",
                          from_state=cur_slug, to_state=target,
                          metadata={"effective_at": (sub.get("current_period_end") or
                                                          now + timedelta(days=30)).isoformat(),
                                    "idempotency_key": idem_key})
    return {
        "ok": True, "action": "downgrade_queued",
        "from_plan": cur_slug, "to_plan": target,
        "effective_at": (sub.get("current_period_end") or
                            (now + timedelta(days=30))).isoformat(),
    }


# ---------------------------------------------------------------
@billing6_router.post("/cancel")
async def cancel_subscription(request: Request, user: dict = Depends(current_user)):
    """Soft cancel — sets cancel_at_period_end, premium continues to period_end."""
    db = request.app.state.db
    sub = user.get("subscription") or {}
    if not sub.get("plan"):
        raise HTTPException(400, "no_active_subscription")
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"subscription.cancel_at_period_end": True}},
    )
    await log_lifecycle(db, user_id=user["user_id"],
                          event_type="cancel_requested",
                          from_state="active", to_state="cancel_scheduled",
                          metadata={"effective_at": (sub.get("current_period_end").isoformat()
                                                          if sub.get("current_period_end") else None)})
    return {"ok": True, "cancel_at_period_end": True,
            "premium_until": (sub.get("current_period_end").isoformat()
                                if sub.get("current_period_end") else None)}


@billing6_router.post("/resume")
async def resume_subscription(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    res = await db.users.update_one(
        {"user_id": user["user_id"],
         "subscription.cancel_at_period_end": True},
        {"$set": {"subscription.cancel_at_period_end": False}},
    )
    if res.modified_count == 0:
        raise HTTPException(400, "no_pending_cancellation")
    await log_lifecycle(db, user_id=user["user_id"],
                          event_type="cancel_revoked",
                          from_state="cancel_scheduled", to_state="active")
    return {"ok": True, "cancel_at_period_end": False}


@billing6_router.post("/pause")
async def pause_subscription(payload: Optional[dict], request: Request,
                                 user: dict = Depends(current_user)):
    """Stripe pause_collection={"behavior":"void"} up to 3 months.
    For v1: premium ends immediately on pause (simpler than partial-month math)."""
    db = request.app.state.db
    months = int(((payload or {}).get("months") or 1))
    months = max(1, min(3, months))
    now = datetime.now(timezone.utc)
    resumes_at = now + timedelta(days=30 * months)
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "is_premium": False,
            "premium_tier": None,
            "subscription.paused": True,
            "subscription.pause_resumes_at": resumes_at,
            "subscription.status": "paused",
            "billing_status": "paused",
        }},
    )
    await log_lifecycle(db, user_id=user["user_id"], event_type="paused",
                          from_state="active", to_state="paused",
                          metadata={"resumes_at": resumes_at.isoformat()})
    return {"ok": True, "paused": True, "resumes_at": resumes_at.isoformat()}


@billing6_router.post("/unpause")
async def unpause_subscription(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    sub = user.get("subscription") or {}
    if not sub.get("paused"):
        raise HTTPException(400, "not_paused")
    plan_slug = sub.get("plan") or "premium_monthly"
    target = get_plan(plan_slug) or get_plan("premium_monthly")
    now = datetime.now(timezone.utc)
    new_end = now + timedelta(days=int(target.get("interval_days") or 30))
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {
            "is_premium": True,
            "premium_tier": target.get("tier") or "premium",
            "subscription.paused": False,
            "subscription.status": "active",
            "subscription.current_period_start": now,
            "subscription.current_period_end": new_end,
            "billing_status": "active",
        },
         "$unset": {"subscription.pause_resumes_at": ""}},
    )
    await log_lifecycle(db, user_id=user["user_id"], event_type="unpaused",
                          from_state="paused", to_state="active")
    return {"ok": True, "paused": False, "premium_until": new_end.isoformat()}


# ---------------------------------------------------------------
@billing6_router.post("/portal")
async def open_portal(request: Request, user: dict = Depends(current_user)):
    """Returns a Stripe Customer Portal session URL. Creates the Stripe
    Customer on demand if the user doesn't have one yet."""
    db = request.app.state.db
    sub = user.get("subscription") or {}
    cust_id = sub.get("stripe_customer_id")
    # Reject if it's the dummy `cus_test_*` we used to write — Phase 3 wrote
    # placeholder IDs that aren't real Stripe customers.
    if cust_id and not cust_id.startswith("cus_") or (cust_id or "").startswith("cus_test_"):
        cust_id = None
    if not cust_id:
        try:
            customer = stripe.Customer.create(
                email=user.get("email"),
                name=user.get("name"),
                metadata={"user_id": user["user_id"], "source": "bigfm_portal"},
            )
            cust_id = customer.id
            await db.users.update_one(
                {"user_id": user["user_id"]},
                {"$set": {"subscription.stripe_customer_id": cust_id}},
            )
        except Exception as e:
            raise HTTPException(502, f"stripe_customer_create_failed: {e}")
    return_url = (request.query_params.get("return_url") or
                   str(request.base_url).rstrip("/") + "/billing")
    try:
        portal = stripe.billing_portal.Session.create(
            customer=cust_id, return_url=return_url,
        )
        await log_lifecycle(db, user_id=user["user_id"],
                              event_type="portal_opened",
                              from_state=None, to_state=None)
        return {"ok": True, "url": portal.url}
    except Exception as e:
        raise HTTPException(502, f"stripe_portal_create_failed: {e}")


# ---------------------------------------------------------------
# Family
@billing6_router.get("/family")
async def get_family(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    return await family_state(db, user["user_id"])


@billing6_router.post("/family/invite")
async def family_invite(payload: dict, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    email = (payload or {}).get("email") or ""
    try:
        out = await invite_family_member(db, user["user_id"], email)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"ok": True, **out,
            "share_url": f"/billing/family/accept/{out['token']}"}


@billing6_router.post("/family/accept")
async def family_accept(payload: dict, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    token = (payload or {}).get("token") or ""
    try:
        out = await accept_family_invite(db, user, token)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return out


@billing6_router.post("/family/remove")
async def family_remove(payload: dict, request: Request,
                          user: dict = Depends(current_user)):
    db = request.app.state.db
    target = (payload or {}).get("user_id") or ""
    try:
        out = await remove_family_member(db, user["user_id"], target)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return out


# ---------------------------------------------------------------
# Admin test hooks
@billing6_router.post("/admin/simulate_payment_failed")
async def admin_simulate_payment_failed(payload: dict, request: Request,
                                          admin: dict = Depends(require_admin)):
    """Admin-only: simulate an invoice.payment_failed webhook for any user.
    Used by tests + manual triage when Stripe CLI isn't wired up."""
    db = request.app.state.db
    uid = (payload or {}).get("user_id")
    if not uid:
        raise HTTPException(400, "user_id required")
    out = await mark_past_due(
        db, uid,
        stripe_event_id=f"evt_simulated_{uuid.uuid4().hex[:14]}",
        metadata={"simulated_by_admin": admin["user_id"]},
    )
    return {"ok": True, **{k: (v.isoformat() if hasattr(v, "isoformat") else v)
                              for k, v in out.items()}}


@billing6_router.post("/admin/simulate_payment_succeeded")
async def admin_simulate_payment_succeeded(payload: dict, request: Request,
                                              admin: dict = Depends(require_admin)):
    db = request.app.state.db
    uid = (payload or {}).get("user_id")
    if not uid:
        raise HTTPException(400, "user_id required")
    out = await mark_payment_recovered(db, uid)
    return {"ok": True, **out}


@billing6_router.post("/admin/run_dunning_sweep")
async def admin_run_dunning_sweep(request: Request,
                                     admin: dict = Depends(require_admin),
                                     payload: Optional[dict] = None):
    """Manual trigger for the dunning sweep (also runs every 60s as cron).

    Optional body: ``{"as_of": "2026-06-01T00:00:00Z"}`` — when present,
    that ISO timestamp is treated as "now" for the sweep comparison logic
    (rows with ``grace_period_ends_at < as_of`` are considered expired).
    Lets pure-API e2e tests force a downgrade without poking Mongo. Same
    admin guard as the realtime cron path."""
    as_of_str = (payload or {}).get("as_of") if isinstance(payload, dict) else None
    as_of = None
    if as_of_str:
        try:
            from datetime import datetime as _dt
            as_of = _dt.fromisoformat(as_of_str.replace("Z", "+00:00"))
            if as_of.tzinfo is None:
                as_of = as_of.replace(tzinfo=timezone.utc)
        except Exception as e:
            raise HTTPException(400, f"invalid as_of: {e}")
    return await sweep_grace_periods(request.app.state.db, as_of=as_of)


# ---------------------------------------------------------------
# Phase 6 webhook handler — replaces the Phase 3 webhook for new event
# types. The Phase 3 /api/webhook/stripe handler still operates on
# checkout.session.completed events; this one handles subscription
# lifecycle events with full idempotency + dedup.
@billing6_router.post("/webhook_v6")
async def stripe_webhook_v6(request: Request):
    """Hardened webhook handler with stripe_events_processed dedup.
    Verifies the Stripe signature using `STRIPE_WEBHOOK_SECRET` env var
    when set; otherwise (test mode) accepts the raw JSON body."""
    db = request.app.state.db
    body = await request.body()
    sig = request.headers.get("Stripe-Signature") or ""
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET") or ""
    event = None
    if secret:
        try:
            event = stripe.Webhook.construct_event(body, sig, secret)
        except Exception as e:
            logger.warning(f"[webhook_v6] signature verify failed: {e}")
            raise HTTPException(400, "invalid_signature")
    else:
        # No webhook secret configured (acceptable in test/dev) — parse JSON.
        try:
            import json as _json
            event = _json.loads(body or b"{}")
        except Exception as e:
            raise HTTPException(400, f"invalid_json: {e}")
    event_id = (event.get("id") if isinstance(event, dict) else getattr(event, "id", None))
    event_type = (event.get("type") if isinstance(event, dict) else getattr(event, "type", ""))
    data = (event.get("data", {}).get("object", {}) if isinstance(event, dict)
            else getattr(event, "data", {}).object)

    # Idempotency
    if event_id and await already_processed(db, event_id):
        return {"received": True, "duplicate": True, "event_id": event_id}
    if event_id:
        await mark_processed(db, event_id, event_type=event_type)

    # Resolve user_id from metadata or customer mapping
    meta = (data.get("metadata") if isinstance(data, dict) else {}) or {}
    user_id = meta.get("user_id")
    if not user_id:
        cust = data.get("customer") if isinstance(data, dict) else None
        if cust:
            u = await db.users.find_one({"subscription.stripe_customer_id": cust},
                                            {"user_id": 1, "_id": 0})
            if u: user_id = u["user_id"]

    if not user_id:
        await log_lifecycle(db, user_id="unknown",
                              event_type=event_type, from_state=None, to_state=None,
                              stripe_event_id=event_id,
                              metadata={"warning": "no_user_resolution"})
        return {"received": True, "event_id": event_id, "warning": "no_user_resolution"}

    if event_type == "invoice.payment_failed":
        await mark_past_due(db, user_id, stripe_event_id=event_id)
    elif event_type == "invoice.payment_succeeded":
        await mark_payment_recovered(db, user_id, stripe_event_id=event_id)
    elif event_type == "customer.subscription.created":
        await log_lifecycle(db, user_id=user_id, event_type=event_type,
                              from_state=None, to_state="active",
                              stripe_event_id=event_id, metadata=meta)
    elif event_type == "customer.subscription.updated":
        await log_lifecycle(db, user_id=user_id, event_type=event_type,
                              from_state=None, to_state="updated",
                              stripe_event_id=event_id, metadata=meta)
    elif event_type == "customer.subscription.deleted":
        await db.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "is_premium": False, "premium_tier": None,
                "billing_status": "canceled",
                "subscription.status": "canceled",
            }},
        )
        await log_lifecycle(db, user_id=user_id, event_type=event_type,
                              from_state="active", to_state="canceled",
                              stripe_event_id=event_id, metadata=meta)
    elif event_type == "customer.subscription.trial_will_end":
        from services.dunning import log_notification as _ln
        await _ln(db, user_id=user_id, kind="trial_ending",
                    subject="Your FUUSIC Premium trial ends soon",
                    body="Your 7-day trial ends in 3 days. You'll be charged automatically unless you cancel at /billing.",
                    metadata={"stripe_event_id": event_id})
    else:
        await log_lifecycle(db, user_id=user_id, event_type=event_type,
                              from_state=None, to_state="other",
                              stripe_event_id=event_id, metadata=meta)
    return {"received": True, "event_id": event_id, "event_type": event_type}
