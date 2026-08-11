"""Saved Cards (Phase 2 Checkout) — customer wallet of payment methods.

Consumer endpoints under /api/shop/wallet:
  GET    /cards                          list saved cards + default
  POST   /cards/setup-session            hosted Stripe setup Checkout (add card)
  POST   /cards/setup-session/{sid}/sync attach + set first card as default
  POST   /cards/{pm_id}/default          set default card
  DELETE /cards/{pm_id}                  remove a card

Cards are collected via a hosted Stripe Checkout Session in `setup` mode so
the same flow works on web (redirect) and Expo (WebBrowser) — no Stripe.js /
native modules required.
"""
from __future__ import annotations

import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import current_user
from services.saved_cards_service import (ensure_stripe_customer, list_cards,
                                          owns_payment_method)

stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_API_KEY") or ""

router = APIRouter(prefix="/api/shop/wallet", tags=["saved-cards"])


@router.get("/cards")
async def get_cards(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    cust = await ensure_stripe_customer(db, user)
    try:
        return list_cards(cust)
    except stripe.error.StripeError as e:
        raise HTTPException(502, {"code": "stripe_error", "message": str(e)})


class SetupSessionBody(BaseModel):
    origin_url: str


@router.post("/cards/setup-session")
async def create_setup_session(body: SetupSessionBody, request: Request,
                               user: dict = Depends(current_user)):
    db = request.app.state.db
    if not stripe.api_key:
        raise HTTPException(503, {"code": "stripe_unconfigured"})
    cust = await ensure_stripe_customer(db, user)
    origin = (body.origin_url or "").rstrip("/")
    if not origin:
        raise HTTPException(400, {"code": "origin_required"})
    try:
        session = stripe.checkout.Session.create(
            mode="setup", customer=cust, payment_method_types=["card"],
            success_url=f"{origin}/shop/wallet/cards?setup=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/shop/wallet/cards?setup=cancel",
            metadata={"kind": "save_card", "user_id": user["user_id"]})
    except stripe.error.StripeError as e:
        raise HTTPException(502, {"code": "stripe_error", "message": str(e)})
    return {"checkout_url": session.url, "session_id": session.id}


@router.post("/cards/setup-session/{session_id}/sync")
async def sync_setup_session(session_id: str, request: Request,
                             user: dict = Depends(current_user)):
    """After the hosted setup flow returns, attach the new card (Stripe does
    this automatically) and make it the default if the customer had none."""
    db = request.app.state.db
    cust = await ensure_stripe_customer(db, user)
    try:
        session = stripe.checkout.Session.retrieve(session_id, expand=["setup_intent"])
        si = session.get("setup_intent")
        pm_id = si.get("payment_method") if si else None
        if pm_id:
            cust_obj = stripe.Customer.retrieve(cust)
            cur_default = (cust_obj.get("invoice_settings") or {}).get("default_payment_method")
            if not cur_default:
                stripe.Customer.modify(
                    cust, invoice_settings={"default_payment_method": pm_id})
        return list_cards(cust)
    except stripe.error.StripeError as e:
        raise HTTPException(502, {"code": "stripe_error", "message": str(e)})


@router.post("/cards/{pm_id}/default")
async def set_default_card(pm_id: str, request: Request,
                           user: dict = Depends(current_user)):
    db = request.app.state.db
    cust = await ensure_stripe_customer(db, user)
    if not owns_payment_method(cust, pm_id):
        raise HTTPException(404, {"code": "card_not_found"})
    try:
        stripe.Customer.modify(
            cust, invoice_settings={"default_payment_method": pm_id})
        return list_cards(cust)
    except stripe.error.StripeError as e:
        raise HTTPException(502, {"code": "stripe_error", "message": str(e)})


@router.delete("/cards/{pm_id}")
async def delete_card(pm_id: str, request: Request,
                      user: dict = Depends(current_user)):
    db = request.app.state.db
    cust = await ensure_stripe_customer(db, user)
    if not owns_payment_method(cust, pm_id):
        raise HTTPException(404, {"code": "card_not_found"})
    try:
        stripe.PaymentMethod.detach(pm_id)
        return list_cards(cust)
    except stripe.error.StripeError as e:
        raise HTTPException(502, {"code": "stripe_error", "message": str(e)})


__all__ = ["router"]
