"""Phase SC.4 — Merchant Payment Links + QR endpoints.

Merchant-side (owner-auth, requires merchant_status ∈ {approved, active}):
    POST      /api/merchant/{merchant_id}/payment-links
    GET        /api/merchant/{merchant_id}/payment-links
    PUT        /api/merchant/{merchant_id}/payment-links/{link_id}
    POST      /api/merchant/{merchant_id}/payment-links/{link_id}/deactivate
    GET        /api/merchant/{merchant_id}/payment-links/{link_id}/analytics

Public (no auth):
    GET        /api/pay/link/{token}                          — resolves to full pay-page payload
    GET        /api/pay/qr/{token}.png                    — QR PNG (image/png)
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import (APIRouter, BackgroundTasks, Depends, HTTPException, Query,
                                Request, Response)
from pydantic import BaseModel, Field

from auth import current_user
from services.payment_link_service import (VALID_LINK_TYPES, create_payment_link,
                                                                                    default_txn_type,
                                                                                    deactivate_link,
                                                                                    ensure_payment_link_indexes,
                                                                                    generate_qr_png,
                                                                                    get_link_by_token,
                                                                                    hosted_url_for,
                                                                                    is_link_serving,
                                                                                    link_analytics, qr_url_for,
                                                                                    record_link_impression,
                                                                                    update_payment_link)
from services.commission_service import calculate_platform_fee

logger = logging.getLogger("bigfm.payment_links.routes")

router = APIRouter(prefix="/api", tags=["payment_links"])


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


# ─── Owner auth resolver ─────────────────────────────────────────
# Phase MER.2 — extended to accept staff-role users with the right
# permission alongside owners + admins.
async def _resolve_owner(db, merchant_id: str, user: dict,
                                                *, permission: Optional[str] = None) -> dict:
    from services.merchant_rbac_service import resolve_merchant_with_role
    biz, _role = await resolve_merchant_with_role(
        db, merchant_id=merchant_id, user=user, permission=permission)
    return biz


# ─── Serialiser ──────────────────────────────────────────────────
def _link_view(link: dict) -> dict:
    return {
        "link_id":                          link.get("link_id"),
        "token":                              link.get("token"),
        "merchant_id":                  link.get("merchant_id"),
        "location_id":                  link.get("location_id"),
        "link_type":                      link.get("link_type"),
        "title":                              link.get("title"),
        "description":                  link.get("description"),
        "amount_cents":              link.get("amount_cents"),
        "currency":                        link.get("currency"),
        "transaction_type":      link.get("transaction_type"),
        "min_amount_cents":      link.get("min_amount_cents"),
        "max_amount_cents":      link.get("max_amount_cents"),
        "table_number":              link.get("table_number"),
        "offer_id":                        link.get("offer_id"),
        "product_id":                  link.get("product_id"),
        "event_id":                        link.get("event_id"),
        "service_id":                  link.get("service_id"),
        "campaign_id":                  link.get("campaign_id"),
        "gift_card_id":              link.get("gift_card_id"),
        "prepaid_meal_id":        link.get("prepaid_meal_id"),
        "expires_at":                  _iso(link.get("expires_at")),
        "max_uses":                        link.get("max_uses"),
        "usage_count":                  link.get("usage_count") or 0,
        "impressions":                  link.get("impressions") or 0,
        "last_impression_at":  _iso(link.get("last_impression_at")),
        "active":                            bool(link.get("active", True)),
        "qr_style":                        link.get("qr_style") or "default",
        "hosted_url":                    hosted_url_for(link["token"]),
        "qr_url":                            qr_url_for(link["token"]),
        "created_at":                    _iso(link.get("created_at")),
        "updated_at":                    _iso(link.get("updated_at")),
    }


# ─── Bodies ──────────────────────────────────────────────────────
class LinkCreateBody(BaseModel):
    link_type:                str = Field(min_length=2, max_length=40)
    title:                        Optional[str] = Field(default=None, max_length=140)
    description:            Optional[str] = Field(default=None, max_length=600)
    amount_cents:          Optional[int] = Field(default=None, ge=0)
    currency:                  Optional[str] = Field(default="AED", max_length=8)
    transaction_type:  Optional[str] = Field(default=None, max_length=40)
    min_amount_cents:  Optional[int] = Field(default=None, ge=0)
    max_amount_cents:  Optional[int] = Field(default=None, ge=0)
    table_number:          Optional[str] = Field(default=None, max_length=32)
    location_id:            Optional[str] = None
    offer_id:                    Optional[str] = None
    product_id:                Optional[str] = None
    event_id:                    Optional[str] = None
    service_id:                Optional[str] = None
    campaign_id:            Optional[str] = None
    gift_card_id:          Optional[str] = None
    prepaid_meal_id:      Optional[str] = None
    expires_at:                Optional[datetime] = None
    max_uses:                    Optional[int] = Field(default=None, ge=1)
    qr_style:                    Optional[str] = Field(default="default")


class LinkPatchBody(BaseModel):
    title:                        Optional[str] = Field(default=None, max_length=140)
    description:            Optional[str] = Field(default=None, max_length=600)
    amount_cents:          Optional[int] = Field(default=None, ge=0)
    currency:                  Optional[str] = None
    transaction_type:  Optional[str] = None
    min_amount_cents:  Optional[int] = Field(default=None, ge=0)
    max_amount_cents:  Optional[int] = Field(default=None, ge=0)
    table_number:          Optional[str] = None
    location_id:            Optional[str] = None
    expires_at:                Optional[datetime] = None
    max_uses:                    Optional[int] = Field(default=None, ge=1)
    active:                      Optional[bool] = None


# ─── Merchant-side endpoints ─────────────────────────────────────
@router.post("/merchant/{merchant_id}/payment-links")
async def create_link(merchant_id: str, body: LinkCreateBody, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_owner(db, merchant_id, user,
                                                      permission="can_create_links")

    if body.link_type not in VALID_LINK_TYPES:
        raise HTTPException(400, {"code": "invalid_link_type",
                                                    "allowed": sorted(VALID_LINK_TYPES)})

    # Cross-field validation
    if body.amount_cents is not None \
              and body.min_amount_cents is not None \
              and body.amount_cents < body.min_amount_cents:
        raise HTTPException(400, "amount_below_min")
    if body.max_amount_cents is not None \
              and body.min_amount_cents is not None \
              and body.max_amount_cents < body.min_amount_cents:
        raise HTTPException(400, "max_below_min")

    try:
        doc = await create_payment_link(
            db,
            merchant_id=biz.get("business_id") or biz.get("_id"),
            link_type=body.link_type,
            actor=user,
            title=body.title,
            description=body.description,
            amount_cents=body.amount_cents,
            currency=body.currency,
            transaction_type=body.transaction_type,
            min_amount_cents=body.min_amount_cents,
            max_amount_cents=body.max_amount_cents,
            table_number=body.table_number,
            location_id=body.location_id,
            offer_id=body.offer_id,
            product_id=body.product_id,
            event_id=body.event_id,
            service_id=body.service_id,
            campaign_id=body.campaign_id,
            gift_card_id=body.gift_card_id,
            prepaid_meal_id=body.prepaid_meal_id,
            expires_at=body.expires_at,
            max_uses=body.max_uses,
            qr_style=body.qr_style,
        )
    except ValueError as ve:
        # merchant_not_approved / merchant_not_found / invalid_link_type
        code = str(ve)
        status = 403 if code.startswith("merchant_not_approved") else 400
        if code == "merchant_not_found":
            status = 404
        raise HTTPException(status, code)

    return _link_view(doc)


@router.get("/merchant/{merchant_id}/payment-links")
async def list_links(merchant_id: str, request: Request,
                                      user: dict = Depends(current_user),
                                      active: Optional[bool] = Query(None),
                                      link_type: Optional[str] = Query(None),
                                      limit: int = Query(100, ge=1, le=500),
                                      offset: int = Query(0, ge=0)):
    db = request.app.state.db
    biz = await _resolve_owner(db, merchant_id, user,
                                                      permission="can_view_analytics")
    mid = biz.get("business_id") or biz.get("_id")

    q: dict = {"merchant_id": mid}
    if active is not None:
        q["active"] = active
    if link_type:
        if link_type not in VALID_LINK_TYPES:
            raise HTTPException(400, f"invalid_link_type:{link_type}")
        q["link_type"] = link_type

    total = await db.merchant_payment_links.count_documents(q)
    cursor = db.merchant_payment_links.find(q).sort("created_at", -1) \
                                              .skip(offset).limit(limit)
    items = []
    async for l in cursor:
        items.append(_link_view(l))
    return {"total": total, "count": len(items),
              "limit": limit, "offset": offset, "items": items}


@router.put("/merchant/{merchant_id}/payment-links/{link_id}")
async def update_link(merchant_id: str, link_id: str, body: LinkPatchBody,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_owner(db, merchant_id, user,
                                                      permission="can_create_links")
    mid = biz.get("business_id") or biz.get("_id")

    patch = {k: v for k, v in body.model_dump(exclude_unset=True).items()
                  if v is not None or k in ("expires_at", "max_uses",
                                                                  "max_amount_cents", "min_amount_cents",
                                                                  "amount_cents", "table_number", "location_id")}
    try:
        fresh = await update_payment_link(
            db, link_id=link_id, merchant_id=mid, patch=patch, actor=user)
    except ValueError as ve:
        code = str(ve)
        status = 404 if code == "link_not_found" else 403
        raise HTTPException(status, code)
    return _link_view(fresh)


@router.post("/merchant/{merchant_id}/payment-links/{link_id}/deactivate")
async def deactivate_link_endpoint(merchant_id: str, link_id: str,
                                                                    request: Request,
                                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_owner(db, merchant_id, user,
                                                      permission="can_create_links")
    mid = biz.get("business_id") or biz.get("_id")
    try:
        fresh = await deactivate_link(db, link_id=link_id, merchant_id=mid,
                                                                actor=user)
    except ValueError as ve:
        code = str(ve)
        status = 404 if code == "link_not_found" else 403
        raise HTTPException(status, code)
    return _link_view(fresh)


@router.get("/merchant/{merchant_id}/payment-links/{link_id}/analytics")
async def link_analytics_endpoint(merchant_id: str, link_id: str,
                                                                    request: Request,
                                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    biz = await _resolve_owner(db, merchant_id, user,
                                                      permission="can_view_analytics")
    mid = biz.get("business_id") or biz.get("_id")
    link = await db.merchant_payment_links.find_one({"link_id": link_id})
    if not link or link.get("merchant_id") != mid:
        raise HTTPException(404, "link_not_found")
    base = await link_analytics(db, link=link)

    # Phase MER.1 — enrich with real transaction aggregations from
    # `payment_transactions_v2` (SC.5+) + refund totals (SC.6).  Do NOT
    # change the shape — just replace the SC.4 placeholder zeros.
    tx_pipe = [
        {"$match": {"link_id": link_id, "status": "succeeded"}},
        {"$group": {"_id": None,
                              "count":  {"$sum": 1},
                              "sum":      {"$sum": "$amount_cents"}}},
    ]
    tx_r = await db.payment_transactions_v2.aggregate(tx_pipe).to_list(1)
    tx_count = int(tx_r[0]["count"]) if tx_r else 0
    tx_sum    = int(tx_r[0]["sum"])    if tx_r else 0

    # Refunded amount (from SC.6 refunds joined by tx_id → link_id)
    refunded_pipe = [
        {"$match": {"link_id": link_id, "refunded_cents": {"$gt": 0}}},
        {"$group": {"_id": None, "sum": {"$sum": "$refunded_cents"}}},
    ]
    rf_r = await db.payment_transactions_v2.aggregate(refunded_pipe).to_list(1)
    refunded_sum = int(rf_r[0]["sum"]) if rf_r else 0

    base["transactions"]        = tx_count
    base["revenue_cents"]        = tx_sum
    base["avg_amount_cents"] = int(tx_sum / tx_count) if tx_count else 0
    base["refunded_cents"]    = refunded_sum
    base["net_revenue_cents"] = tx_sum - refunded_sum
    return base


# ─── Public — pay-page payload + QR ──────────────────────────────
@router.get("/pay/link/{token}")
async def public_link_view(token: str, request: Request,
                                                background_tasks: BackgroundTasks):
    db = request.app.state.db
    link, biz = await get_link_by_token(db, token)
    if not link:
        raise HTTPException(404, "link_not_found")

    serving, reason = is_link_serving(link)

    # Merchant metadata for the pay page
    primary_loc = None
    if biz:
        loc = await db.merchant_locations.find_one(
            {"merchant_id": biz.get("business_id") or biz.get("_id"),
              "primary": True, "active": True})
        if loc:
            primary_loc = {
                "location_id": loc.get("location_id"),
                "name":              loc.get("name"),
                "address":        loc.get("address"),
                "city":              loc.get("city"),
                "country":        loc.get("country"),
                "latitude":      loc.get("latitude"),
                "longitude":    loc.get("longitude"),
            }

    merchant_view = None
    if biz:
        merchant_view = {
            "merchant_id":              biz.get("business_id") or biz.get("_id"),
            "name":                          biz.get("name"),
            "category":                  biz.get("category_id") or biz.get("category"),
            "logo_url":                  biz.get("logo_url"),
            "primary_location":  primary_loc,
            "description":              biz.get("description"),
        }

    # If amount is fixed, compute a commission preview (merchant-side —
    # not exposed on the consumer pay page — the merchant portal fetches
    # this endpoint too during the "New Link" preview step).
    commission_preview = None
    if link.get("amount_cents") is not None and merchant_view:
        try:
            commission_preview = await calculate_platform_fee(
                db,
                merchant_id=merchant_view["merchant_id"],
                category=merchant_view.get("category") or "other",
                transaction_type=link.get("transaction_type") or "payment",
                amount_cents=int(link["amount_cents"]),
                write_audit=False,
            )
        except Exception:
            logger.exception("[payment_links] preview calc failed (non-blocking)")

    # Fire-and-forget impression (only when actually serving)
    if serving:
        client_ip = request.client.host if request.client else None
        headers = dict(request.headers)
        background_tasks.add_task(
            record_link_impression, db, link=link,
            viewer_ip=client_ip, headers=headers)

    return {
        "merchant":                    merchant_view,
        "link":                            _link_view(link),
        "commission_preview": commission_preview,
        "active":                        serving,
        "inactive_reason":      reason,
        "hosted_url":                hosted_url_for(token),
        "qr_url":                        qr_url_for(token),
    }


@router.get("/pay/qr/{token_with_ext}")
async def public_qr(token_with_ext: str, request: Request,
                                    size: int = Query(512, ge=128, le=2048)):
    db = request.app.state.db
    token = token_with_ext.rsplit(".", 1)[0]      # strip .png suffix
    link = await db.merchant_payment_links.find_one({"token": token})
    if not link:
        raise HTTPException(404, "link_not_found")
    png_bytes = generate_qr_png(token, size=size)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Cache-Control":            "public, max-age=3600",
            "Content-Disposition": f'inline; filename="bigfm-pay-{token}.png"',
        },
    )


# ─── Phase SC.5 — Payment Intent creation + polling + receipt ───
from services.payment_service import (create_payment_intent_for_link,
                                                                              PaymentError,
                                                                              poll_intent_and_sync)
from auth import current_user_optional


class IntentBody(BaseModel):
    amount_cents:      Optional[int] = Field(default=None, ge=0)
    customer_email: Optional[str] = Field(default=None, max_length=200)
    # Phase MER.3 — optional modifiers list
    modifiers:          Optional[list[dict]] = Field(default=None)


class PollBody(BaseModel):
    intent_id: str = Field(min_length=6, max_length=120)


@router.post("/pay/{token}/intent")
async def sc5_create_intent(token: str, body: IntentBody, request: Request,
                                                    user: Optional[dict] = Depends(current_user_optional)):
    db = request.app.state.db
    try:
        result = await create_payment_intent_for_link(
            db,
            token=token,
            amount_cents=body.amount_cents or 0,
            customer_user_id=(user or {}).get("user_id"),
            customer_email=(body.customer_email or (user or {}).get("email")),
            modifiers=body.modifiers or None,
        )
    except PaymentError as pe:
        raise HTTPException(pe.http_status, {"code": pe.code,
                                                                              "detail": pe.detail})
    return result


@router.post("/pay/{token}/confirm-poll")
async def sc5_confirm_poll(token: str, body: PollBody, request: Request):
    db = request.app.state.db
    # Validate that the intent belongs to this link (avoid cross-token abuse)
    tx = await db.payment_transactions_v2.find_one(
        {"stripe_payment_intent_id": body.intent_id})
    if not tx:
        raise HTTPException(404, "intent_not_found")
    if tx.get("link_token") != token:
        raise HTTPException(403, "intent_token_mismatch")
    try:
        return await poll_intent_and_sync(db, intent_id=body.intent_id)
    except PaymentError as pe:
        raise HTTPException(pe.http_status, {"code": pe.code,
                                                                              "detail": pe.detail})


@router.get("/pay/{token}/receipt")
async def sc5_receipt(token: str, request: Request,
                                            intent_id: str = Query(...)):
    db = request.app.state.db
    tx = await db.payment_transactions_v2.find_one(
        {"stripe_payment_intent_id": intent_id})
    if not tx or tx.get("link_token") != token:
        raise HTTPException(404, "transaction_not_found")
    if tx.get("status") != "succeeded":
        # Return 404 per SC.5 spec so the frontend keeps polling
        raise HTTPException(404, {"code": "not_succeeded_yet",
                                                            "current_status": tx.get("status")})

    biz = await db.businesses.find_one({"$or": [
        {"business_id": tx["merchant_id"]}, {"_id": tx["merchant_id"]}]})
    link = await db.merchant_payment_links.find_one({"link_id": tx["link_id"]})
    primary_loc = None
    if biz:
        loc = await db.merchant_locations.find_one({
            "merchant_id": biz.get("business_id") or biz.get("_id"),
            "primary": True, "active": True})
        if loc:
            primary_loc = {"address": loc.get("address"),
                                        "city": loc.get("city"),
                                        "country": loc.get("country")}

    return {
        "transaction_id":            tx["transaction_id"],
        "amount_cents":                  tx["amount_cents"],
        "currency":                          tx["currency"],
        "succeeded_at":                  _iso(tx.get("succeeded_at")),
        "payment_method_type":  tx.get("payment_method_type"),
        "points_earned":                tx.get("points_earned") or 0,
        "table_number":                  tx.get("table_number"),
        "merchant": {
            "merchant_id":              tx["merchant_id"],
            "name":                          (biz or {}).get("name"),
            "logo_url":                  (biz or {}).get("logo_url"),
            "category":                  (biz or {}).get("category_id")
                                                    or (biz or {}).get("category"),
            "primary_location":  primary_loc,
        },
        "link": {
            "title":                        (link or {}).get("title"),
            "link_type":              (link or {}).get("link_type"),
        },
    }


__all__ = ["router", "ensure_payment_link_indexes"]
