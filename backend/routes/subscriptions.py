"""Phase 36e Turn 1 — Subscription routes (creator + listener + webhook)."""
from __future__ import annotations
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from auth import current_user, require_admin
from services import subscriptions as subs
from services import podcasts as podc_svc
from services import stripe_client

logger = logging.getLogger("bigfm.routes.subscriptions")

subscriptions_router = APIRouter(prefix="/api", tags=["subscriptions"])


# ─── Helper ──────────────────────────────────────────────────────
async def _own_creator(db, user: dict, creator_id: str) -> dict:
    """Ensures `user` owns the creator profile `creator_id`."""
    creator = await podc_svc.require_approved_creator(db, user)
    if creator["id"] != creator_id:
        raise HTTPException(403, "not_your_creator_profile")
    return creator


async def _own_channel(db, user: dict, channel_id: str) -> dict:
    creator = await podc_svc.require_approved_creator(db, user)
    ch = await db.podcast_channels.find_one(
        {"id": channel_id}, {"_id": 0, "creator_id": 1, "id": 1, "title": 1})
    if not ch: raise HTTPException(404, "channel_not_found")
    if ch["creator_id"] != creator["id"]:
        raise HTTPException(403, "not_your_channel")
    return creator


# ─── Creator: Stripe Connect Express ─────────────────────────────
@subscriptions_router.post("/creators/{creator_id}/stripe-account")
async def post_create_stripe_account(creator_id: str, request: Request,
                                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    creator = await _own_creator(db, user, creator_id)
    row = await subs.get_or_create_stripe_account(
        db, creator=creator, creator_email=user.get("email") or "creator@bigfm.local")
    return row


@subscriptions_router.get("/creators/{creator_id}/stripe-account")
async def get_stripe_account(creator_id: str, request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_creator(db, user, creator_id)
    row = await db.creator_stripe_accounts.find_one(
        {"creator_id": creator_id}, {"_id": 0})
    if not row: raise HTTPException(404, "stripe_account_not_found")
    # Normalize datetime fields.
    for k in ("created_at", "updated_at", "onboarding_completed_at"):
        if row.get(k) and not isinstance(row[k], str):
            row[k] = row[k].isoformat()
    return row


@subscriptions_router.post("/creators/{creator_id}/stripe-account/onboarding-link")
async def post_onboarding_link(creator_id: str, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_creator(db, user, creator_id)
    row = await db.creator_stripe_accounts.find_one(
        {"creator_id": creator_id})
    if not row: raise HTTPException(404, "stripe_account_not_found")
    base = str(request.base_url).rstrip("/")
    link = stripe_client.create_account_link(
        account_id=row["stripe_account_id"],
        refresh_url=f"{base}/creator/settings?stripe=refresh",
        return_url=f"{base}/creator/settings?stripe=onboarded")
    return {"url": link["url"], "expires_at": link.get("expires_at")}


@subscriptions_router.post("/creators/{creator_id}/stripe-account/refresh")
async def post_refresh_account(creator_id: str, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_creator(db, user, creator_id)
    return await subs.refresh_stripe_account(db, creator_id=creator_id)


# Mock-only helper used by the mock Express-onboard page to flip booleans
# without going through Stripe. Live mode no-ops.
@subscriptions_router.post("/creators/{creator_id}/stripe-account/mock/complete")
async def post_mock_complete(creator_id: str, request: Request,
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _own_creator(db, user, creator_id)
    if stripe_client.is_live():
        raise HTTPException(400, "mock_complete_disabled_in_live_mode")
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    await db.creator_stripe_accounts.update_one(
        {"creator_id": creator_id},
        {"$set": {"charges_enabled": True, "payouts_enabled": True,
                          "details_submitted": True,
                          "onboarding_completed_at": now,
                          "updated_at": now}})
    return await subs.refresh_stripe_account(db, creator_id=creator_id)


# ─── Creator: Plans ──────────────────────────────────────────────
@subscriptions_router.post("/podcasts/channels/{channel_id}/subscription-plan")
async def post_create_plan(channel_id: str, request: Request,
                                                      body: dict = Body(...),
                                                      user: dict = Depends(current_user)):
    db = request.app.state.db
    creator = await _own_channel(db, user, channel_id)
    return await subs.create_plan(
        db, creator=creator, channel_id=channel_id,
        name=body.get("name") or "Premium",
        price_cents=int(body.get("price_cents") or 0),
        trial_days=int(body.get("trial_days") or subs.DEFAULT_TRIAL_DAYS),
        features=body.get("features"))


@subscriptions_router.get("/podcasts/channels/{channel_id}/subscription-plan")
async def get_plan(channel_id: str, request: Request):
    """Public — listeners see pricing without auth."""
    db = request.app.state.db
    plan = await subs.get_active_plan(db, channel_id=channel_id)
    if not plan: raise HTTPException(404, "no_active_plan")
    return plan


@subscriptions_router.patch("/podcasts/channels/{channel_id}/subscription-plan")
async def patch_active_plan(channel_id: str, request: Request,
                                                            body: dict = Body(...),
                                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    creator = await _own_channel(db, user, channel_id)
    return await subs.patch_plan(db, creator=creator,
                                                              channel_id=channel_id, patch=body)


@subscriptions_router.delete("/podcasts/channels/{channel_id}/subscription-plan")
async def delete_active_plan(channel_id: str, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    creator = await _own_channel(db, user, channel_id)
    return await subs.patch_plan(db, creator=creator,
                                                              channel_id=channel_id,
                                                              patch={"active": False})


# ─── Listener: Subscribe / Cancel / Resume ───────────────────────
@subscriptions_router.post("/podcasts/channels/{channel_id}/subscribe")
async def post_subscribe(channel_id: str, request: Request,
                                                user: dict = Depends(current_user)):
    db = request.app.state.db
    base = str(request.base_url).rstrip("/")
    return await subs.create_checkout(
        db, user=user, channel_id=channel_id, base_url=base)


@subscriptions_router.get("/podcasts/channels/{channel_id}/subscription-status")
async def get_my_sub_status(channel_id: str, request: Request,
                                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    sub = await db.listener_subscriptions.find_one({
        "listener_user_id": user["user_id"],
        "channel_id":              channel_id,
        "status":                      {"$in": ["trialing", "active", "past_due"]},
    }, {"_id": 0})
    if not sub:
        return {"is_subscribed": False, "status": "none", "trial_end": None}
    return {
        "is_subscribed": True,
        "status":              sub["status"],
        "trial_end":      sub.get("trial_end").isoformat() if sub.get("trial_end") and not isinstance(sub.get("trial_end"), str) else sub.get("trial_end"),
        "cancel_at_period_end": bool(sub.get("cancel_at_period_end")),
    }


@subscriptions_router.get("/listener/subscriptions")
async def list_my_subs(request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    return await subs.list_user_subscriptions(db, user_id=user["user_id"])


@subscriptions_router.post("/listener/subscriptions/{lsub_id}/cancel")
async def cancel_my_sub(lsub_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    return await subs.cancel_subscription(db, user=user, lsub_id=lsub_id)


@subscriptions_router.post("/listener/subscriptions/{lsub_id}/resume")
async def resume_my_sub(lsub_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    return await subs.resume_subscription(db, user=user, lsub_id=lsub_id)


# ─── Webhook ─────────────────────────────────────────────────────
@subscriptions_router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    db = request.app.state.db
    body = await request.body()
    sig    = request.headers.get("stripe-signature", "")
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    try:
        event = stripe_client.verify_webhook_signature(
            payload=body, sig_header=sig, secret=secret)
    except stripe_client.WebhookSignatureError as e:
        raise HTTPException(400, f"signature_invalid: {e}")
    return await subs.handle_stripe_event(db, event=event)


# Admin-only mock-fire endpoint for development. Live-mode disabled.
@subscriptions_router.post("/admin/stripe/mock/fire-webhook")
async def mock_fire_webhook(request: Request,
                                                      body: dict = Body(...),
                                                      user: dict = Depends(require_admin)):
    if stripe_client.is_live():
        raise HTTPException(400, "mock_fire_disabled_in_live_mode")
    db = request.app.state.db
    event_type = body.get("event_type")
    data_object = body.get("data_object") or {}
    if not event_type:
        raise HTTPException(400, "event_type required")
    event = stripe_client.build_mock_event(
        event_type=event_type, data_object=data_object)
    return await subs.handle_stripe_event(db, event=event)


# Mock-only listener flow helper — simulates Stripe Checkout completion
# from the in-app mock checkout page. Authed listener.
@subscriptions_router.post("/mock/stripe/checkout/{session_id}/complete")
async def mock_checkout_complete(session_id: str, request: Request,
                                                                      body: dict = Body(default={}),
                                                                      user: dict = Depends(current_user)):
    if stripe_client.is_live():
        raise HTTPException(400, "mock_complete_disabled_in_live_mode")
    db = request.app.state.db
    sub_row = await db.listener_subscriptions.find_one(
        {"stripe_checkout_session_id": session_id})
    if not sub_row: raise HTTPException(404, "session_not_found")
    if sub_row["listener_user_id"] != user["user_id"]:
        raise HTTPException(403, "not_your_checkout_session")
    success = bool(body.get("success", True))
    if not success:
        # Simulate cancel — leave incomplete.
        return {"ok": False, "status": "incomplete"}
    # Simulate Stripe webhook for created subscription in trialing state.
    from datetime import datetime, timezone, timedelta
    plan = await db.creator_subscription_plans.find_one(
        {"id": sub_row["plan_id"]})
    trial_days = (plan or {}).get("trial_days", subs.DEFAULT_TRIAL_DAYS)
    now = datetime.now(timezone.utc)
    trial_end = now + timedelta(days=trial_days)
    fake_sub_id = stripe_client._mock_id("sub")
    fake_cus_id = stripe_client._mock_id("cus")
    event = stripe_client.build_mock_event(
        event_type="customer.subscription.created",
        data_object={
            "id":                          fake_sub_id,
            "object":                  "subscription",
            "status":                  "trialing",
            "customer":            fake_cus_id,
            "client_reference_id": sub_row["id"],
            "trial_end":              int(trial_end.timestamp()),
            "current_period_end": int(trial_end.timestamp()),
            "cancel_at_period_end": False,
            "metadata": {"listener_sub_id": sub_row["id"]},
        })
    out = await subs.handle_stripe_event(db, event=event)
    return {"ok": True, "result": out, "subscription_id": sub_row["id"]}



# ─── Phase 36f — Creator SaaS tier checkout (mobile + web parity) ─
@subscriptions_router.post("/podcasts/creators/{creator_id}/subscription/checkout")
async def post_creator_saas_checkout(creator_id: str, request: Request,
                                                                              body: dict = Body(...),
                                                                              user: dict = Depends(current_user)):
    """Mobile and web call this when a creator upgrades their platform tier.

    Body: `{plan_id, success_url, cancel_url}`.
    Returns:  `{checkout_url, session_id, plan_id, subscription_id, expires_at}`.
    Ownership: the auth'd user must own `creator_id` (admin bypass).
    Idempotent: 409 `already_subscribed` if an active SaaS sub exists.
    """
    db = request.app.state.db
    plan_id          = (body or {}).get("plan_id")
    success_url = (body or {}).get("success_url") or ""
    cancel_url   = (body or {}).get("cancel_url") or ""
    if not plan_id:
        raise HTTPException(400, {"code": "missing_plan_id"})
    if not success_url or not cancel_url:
        raise HTTPException(400, {"code": "missing_redirect_urls"})

    # Admin bypass — look up the target creator row directly.
    if user.get("role") == "admin":
        creator = await db.podcast_creators.find_one(
            {"id": creator_id}, {"_id": 0})
        if not creator: raise HTTPException(404, "creator_not_found")
    else:
        creator = await _own_creator(db, user, creator_id)

    return await subs.create_creator_saas_checkout(
        db, user=user, creator=creator, plan_id=plan_id,
        success_url=success_url, cancel_url=cancel_url)
