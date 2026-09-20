"""RadioLife Social V2 — ADVISOR PAYOUTS (Stripe Connect).

Approved advisors onboard a Stripe Connect account; when a customer pays for a
private reading, the platform keeps an admin-configurable commission and the
advisor's share is transferred to their connected account (separate charges &
transfers, drawing from the original charge). Advisors who haven't finished
onboarding have their share HELD until they do.

Reuses `services.stripe_connect_service`. Preview runs Stripe TEST mode; real
payouts require live keys at deploy time.

Routes: /api/social/payouts/*  ·  admin /api/admin/dreams/payouts/*
"""
from __future__ import annotations
from core.origins import resolve_origin

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from services import stripe_connect_service as scs

logger = logging.getLogger("bigfm.dream_payouts")

router = APIRouter(prefix="/api/social/payouts", tags=["dream_payouts"])
admin_router = APIRouter(prefix="/api/admin/dreams/payouts", tags=["dream_payouts_admin"])

CONFIG_ID = "dream_payout_config"
DEFAULT_COMMISSION_PCT = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else v


async def ensure_payouts_indexes(db) -> None:
    await db.dream_payouts.create_index([("advisor_id", 1), ("created_at", -1)], name="dp_adv")
    await db.dream_payouts.create_index("status", name="dp_status")
    await db.dream_payout_config.update_one(
        {"_id": CONFIG_ID},
        {"$setOnInsert": {"_id": CONFIG_ID, "commission_pct": DEFAULT_COMMISSION_PCT}},
        upsert=True)


async def _commission_pct(db) -> int:
    cfg = await db.dream_payout_config.find_one({"_id": CONFIG_ID})
    return int((cfg or {}).get("commission_pct", DEFAULT_COMMISSION_PCT))


async def _advisor_for(db, uid: str) -> dict:
    a = await db.advisor_profiles.find_one({"user_id": uid, "status": "approved"})
    if not a:
        raise HTTPException(403, {"code": "not_an_advisor"})
    return a


# ─────────────── Payout settlement (called from deliver) ────────────
async def settle_booking_payout(db, booking: dict) -> Optional[dict]:
    """Idempotent. Records a payout-ledger row for a PAID reading and, if the
    advisor is fully onboarded, transfers their share via Stripe Connect.
    Never raises — payout problems must not block reading delivery."""
    try:
        fee = int(booking.get("price_cents", 0))
        if fee <= 0:
            return None
        bid = booking["booking_id"]
        pid = f"payout_{bid}"
        existing = await db.dream_payouts.find_one({"_id": pid})
        if existing and existing.get("status") == "paid":
            return existing

        pct = await _commission_pct(db)
        platform_fee = round(fee * pct / 100)
        advisor_share = fee - platform_fee
        adv = await db.advisor_profiles.find_one({"advisor_id": booking["advisor_id"]})
        acct = (adv or {}).get("stripe_account_id")
        payouts_enabled = bool((adv or {}).get("stripe_payouts_enabled"))

        ledger = {
            "_id": pid, "booking_id": bid, "advisor_id": booking["advisor_id"],
            "advisor_name": booking.get("advisor_name"),
            "user_id": booking.get("user_id"),
            "gross_cents": fee, "commission_pct": pct,
            "platform_fee_cents": platform_fee, "advisor_share_cents": advisor_share,
            "currency": "usd", "status": "pending", "transfer_id": None,
            "error": None, "created_at": _now(), "updated_at": _now()}

        if not acct or not payouts_enabled:
            ledger["status"] = "held_no_account"
            await db.dream_payouts.update_one({"_id": pid}, {"$set": ledger}, upsert=True)
            return ledger

        try:
            import stripe
            stripe.api_key = (os.environ.get("STRIPE_SECRET_KEY")
                              or os.environ.get("STRIPE_API_KEY") or "")
            source_charge = None
            pi_id = booking.get("stripe_payment_intent")
            if pi_id:
                pi = stripe.PaymentIntent.retrieve(pi_id)
                source_charge = pi.get("latest_charge")
            tr = await scs.create_transfer(
                amount_cents=advisor_share, destination_account_id=acct,
                source_transaction=source_charge, transfer_group=bid,
                metadata={"booking_id": bid, "advisor_id": booking["advisor_id"]},
                idempotency_key=pid)
            ledger["status"] = "paid"
            ledger["transfer_id"] = tr.get("transfer_id")
        except Exception as e:  # noqa: BLE001
            ledger["status"] = "failed"
            ledger["error"] = str(e)[:300]
            logger.warning("[payout] transfer failed booking=%s: %s", bid, e)
        ledger["updated_at"] = _now()
        await db.dream_payouts.update_one({"_id": pid}, {"$set": ledger}, upsert=True)
        return ledger
    except Exception as e:  # noqa: BLE001
        logger.warning("[payout] settle error: %s", e)
        return None


async def _earnings(db, advisor_id: str) -> dict:
    paid = pending = held = 0
    async for p in db.dream_payouts.find({"advisor_id": advisor_id}):
        share = int(p.get("advisor_share_cents", 0))
        st = p.get("status")
        if st == "paid":
            paid += share
        elif st == "held_no_account":
            held += share
        else:
            pending += share
    return {"paid_cents": paid, "pending_cents": pending, "held_cents": held}


def _ledger_public(p: dict) -> dict:
    return {"booking_id": p.get("booking_id"), "advisor_id": p.get("advisor_id"),
            "advisor_name": p.get("advisor_name"),
            "gross_cents": int(p.get("gross_cents", 0)),
            "commission_pct": int(p.get("commission_pct", 0)),
            "platform_fee_cents": int(p.get("platform_fee_cents", 0)),
            "advisor_share_cents": int(p.get("advisor_share_cents", 0)),
            "status": p.get("status"), "transfer_id": p.get("transfer_id"),
            "created_at": _iso(p.get("created_at"))}


# ───────────────────────── Advisor endpoints ───────────────────────
@router.get("/status")
async def payout_status(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await _advisor_for(db, user["user_id"])
    return {
        "onboarding_status": a.get("stripe_onboarding_status") or "not_started",
        "payouts_enabled": bool(a.get("stripe_payouts_enabled")),
        "charges_enabled": bool(a.get("stripe_charges_enabled")),
        "has_account": bool(a.get("stripe_account_id")),
        "commission_pct": await _commission_pct(db),
        "earnings": await _earnings(db, a["advisor_id"]),
        "ledger": [_ledger_public(p) async for p in
                   db.dream_payouts.find({"advisor_id": a["advisor_id"]})
                   .sort("created_at", -1).limit(40)],
    }


class OnboardBody(BaseModel):
    origin_url: Optional[str] = None
    country: str = "US"


@router.post("/onboarding/start")
async def onboarding_start(body: OnboardBody, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await _advisor_for(db, user["user_id"])
    acct = a.get("stripe_account_id")
    if not acct:
        created = await scs.create_connected_account(
            merchant_id=a["advisor_id"],
            email=user.get("email") or f"{a['advisor_id']}@advisor.radiolife",
            country=body.country)
        acct = created["stripe_account_id"]
        await db.advisor_profiles.update_one(
            {"advisor_id": a["advisor_id"]},
            {"$set": {"stripe_account_id": acct,
                      "stripe_onboarding_status": "onboarding_in_progress"}})
    origin = resolve_origin(request, body.origin_url)
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    url = await scs.create_onboarding_link(
        stripe_account_id=acct,
        return_url=f"{origin}/social/dreams?payouts=done",
        refresh_url=f"{origin}/social/dreams?payouts=refresh")
    return {"ok": True, "onboarding_url": url}


@router.post("/status/refresh")
async def status_refresh(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await _advisor_for(db, user["user_id"])
    acct = a.get("stripe_account_id")
    if not acct:
        raise HTTPException(400, {"code": "no_account"})
    live = await scs.retrieve_account_status(acct)
    status = scs.derive_onboarding_status(
        charges_enabled=live["charges_enabled"],
        payouts_enabled=live["payouts_enabled"],
        details_submitted=live["details_submitted"],
        requirements_currently_due=live["requirements_currently_due"],
        requirements_past_due=live["requirements_past_due"],
        requirements_disabled_reason=live["requirements_disabled_reason"],
        current_status=a.get("stripe_onboarding_status") or "not_started")
    await db.advisor_profiles.update_one(
        {"advisor_id": a["advisor_id"]},
        {"$set": {"stripe_charges_enabled": live["charges_enabled"],
                  "stripe_payouts_enabled": live["payouts_enabled"],
                  "stripe_details_submitted": live["details_submitted"],
                  "stripe_onboarding_status": status,
                  "stripe_status_synced_at": _now()}})
    return {"ok": True, "onboarding_status": status,
            "payouts_enabled": live["payouts_enabled"]}


@router.post("/dashboard-link")
async def dashboard_link(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    a = await _advisor_for(db, user["user_id"])
    if not a.get("stripe_account_id"):
        raise HTTPException(400, {"code": "no_account"})
    try:
        url = await scs.create_login_link(a["stripe_account_id"])
    except Exception:
        raise HTTPException(400, {"code": "dashboard_unavailable"})
    return {"ok": True, "url": url}


# ───────────────────────────── Admin ───────────────────────────────
@admin_router.get("/config")
async def admin_get_config(request: Request, user: dict = Depends(require_admin)):
    db = request.app.state.db
    return {"commission_pct": await _commission_pct(db)}


class CommissionBody(BaseModel):
    commission_pct: int = Field(..., ge=0, le=90)


@admin_router.patch("/config")
async def admin_set_config(body: CommissionBody, request: Request,
                           user: dict = Depends(require_admin)):
    db = request.app.state.db
    await db.dream_payout_config.update_one(
        {"_id": CONFIG_ID}, {"$set": {"commission_pct": body.commission_pct}},
        upsert=True)
    return {"ok": True, "commission_pct": body.commission_pct}


@admin_router.get("/ledger")
async def admin_ledger(request: Request, status: Optional[str] = None,
                       user: dict = Depends(require_admin)):
    db = request.app.state.db
    q: dict = {}
    if status:
        q["status"] = status
    items = [_ledger_public(p) async for p in
             db.dream_payouts.find(q).sort("created_at", -1).limit(100)]
    return {"items": items, "commission_pct": await _commission_pct(db)}


__all__ = ["router", "admin_router", "ensure_payouts_indexes", "settle_booking_payout"]
