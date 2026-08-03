"""Phase 9c — Local Commerce routes.

Mounts under three umbrella routers:
  - public_commerce_router  →  /api/public/businesses/*  (no auth)
  - listener_commerce_router → /api/commerce/*           (current_user)
  - partner_router          → /api/partner/*             (business_partner)
  - admin_commerce_router   → /api/admin/*               (admin)
"""
from __future__ import annotations

import io
import csv
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from auth import current_user, require_admin
from services.local_commerce import (
    business_view, claim_business, assign_slug_if_missing,
    create_offer, update_offer, submit_offer_for_approval,
    approve_offer, reject_offer, revise_offer,
    transition_offer_status,
    offer_view, offers_feed, claim_offer, coupon_view,
    list_user_coupons, redeem_coupon_by_qr, offer_analytics,
    backfill_missing_coupon_ids,
    OFFER_STATUS, POS_PROVIDERS, PARTNER_STATUSES,
    _new_id as _new_commerce_id,
)
from services.google_wallet import (
    get_wallet_client, mint_apple_wallet_stub,
)


# ─── Helpers ───────────────────────────────────────────────────────────
def _require_partner(user: dict) -> None:
    if user.get("role") not in ("business_partner", "admin", "moderator"):
        raise HTTPException(403, "business_partner_role_required")


async def _own_business(db, *, business_id: str, user_id: str) -> dict:
    biz = await db.businesses.find_one({"business_id": business_id})
    if not biz:
        raise HTTPException(404, "business_not_found")
    if user_id not in (biz.get("owner_user_ids") or []):
        raise HTTPException(403, "not_business_owner")
    return biz


def _now():
    return datetime.now(timezone.utc)


# ═══════════════════════════════════════════════════════════════════════
# PUBLIC — no auth
# ═══════════════════════════════════════════════════════════════════════
public_commerce_router = APIRouter(prefix="/api/public/businesses",
                                              tags=["public_commerce"])


@public_commerce_router.get("/nearby")
async def public_nearby_businesses(request: Request,
                                              lat: float, lng: float,
                                              radius_m: int = 5000,
                                              category: Optional[str] = None,
                                              q: Optional[str] = None,
                                              limit: int = 30):
    db = request.app.state.db
    query: dict = {
        "loc": {"$nearSphere": {
            "$geometry": {"type": "Point",
                              "coordinates": [float(lng), float(lat)]},
            "$maxDistance": int(radius_m)}}}
    if category:
        query["category"] = category
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    cur = db.businesses.find(query).limit(int(min(max(limit, 1), 100)))
    items: list[dict] = []
    async for b in cur:
        if not b.get("slug"):
            try:
                await assign_slug_if_missing(db, b["business_id"])
                b = await db.businesses.find_one({"business_id": b["business_id"]})
            except Exception:
                pass
        items.append(business_view(b, public=True))
    return {"items": items, "count": len(items)}


@public_commerce_router.get("/{slug}")
async def public_business_profile(slug: str, request: Request):
    db = request.app.state.db
    b = await db.businesses.find_one({"slug": slug})
    if not b:
        raise HTTPException(404, "business_not_found")
    # Embed active offers count for quick UI
    offers_count = await db.offers.count_documents(
        {"business_id": b["business_id"], "status": "active",
          "end_at": {"$gte": _now()}})
    return {**business_view(b, public=True), "active_offers_count": offers_count}


@public_commerce_router.get("/{slug}/offers")
async def public_business_offers(slug: str, request: Request,
                                            limit: int = 30):
    db = request.app.state.db
    b = await db.businesses.find_one({"slug": slug}, {"business_id": 1})
    if not b:
        raise HTTPException(404, "business_not_found")
    cur = db.offers.find(
        {"business_id": b["business_id"], "status": "active",
          "end_at": {"$gte": _now()}}
    ).sort("created_at", -1).limit(int(min(max(limit, 1), 100)))
    items = [offer_view(o, public=True) async for o in cur]
    return {"items": items, "count": len(items)}


@public_commerce_router.get("/{slug}/qr.png")
async def public_business_qr(slug: str, request: Request):
    """QR code linking to the public business page.  Returns PNG."""
    db = request.app.state.db
    b = await db.businesses.find_one({"slug": slug}, {"slug": 1})
    if not b:
        raise HTTPException(404, "business_not_found")
    # Lazy import qrcode (already in deps via the gamification phase)
    import qrcode
    from io import BytesIO
    public_url = (request.headers.get("x-forwarded-host")
                       or request.url.netloc)
    proto = "https" if request.url.scheme != "http" or request.headers.get(
        "x-forwarded-proto") == "https" else "http"
    target = f"{proto}://{public_url}/business/{slug}"
    img = qrcode.make(target)
    buf = BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


# ═══════════════════════════════════════════════════════════════════════
# LISTENER — auth required
# ═══════════════════════════════════════════════════════════════════════
listener_commerce_router = APIRouter(prefix="/api/commerce",
                                                tags=["commerce_listener"])


@listener_commerce_router.get("/offers/feed")
async def commerce_feed(request: Request,
                              lat: Optional[float] = None,
                              lng: Optional[float] = None,
                              radius_m: int = 5000,
                              include_route: bool = True,
                              limit: int = 30,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    items = await offers_feed(
        db, user_id=user["user_id"], lat=lat, lng=lng,
        radius_m=int(radius_m), include_route=bool(include_route),
        limit=int(min(max(limit, 1), 100)))
    return {"items": items, "count": len(items)}


@listener_commerce_router.post("/offers/{offer_id}/claim")
async def commerce_claim_offer(offer_id: str, request: Request, body: dict,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    src = (body or {}).get("claim_source", "public_page")
    ctx = (body or {}).get("claim_context") or {}
    try:
        coupon = await claim_offer(
            db, offer_id=offer_id, user_id=user["user_id"],
            claim_source=src, claim_context=ctx)
    except ValueError as e:
        msg = str(e)
        code = 409 if msg in ("max_per_user_reached",
                                       "out_of_inventory") else 400
        raise HTTPException(code, msg)
    # Phase 18c — attribution chain: stamp campaign + advertiser onto the
    # freshly minted coupon if the client passed a known serve_id.  Accepted
    # via body field `attribution_serve_id` OR header `X-Attribution-Serve-Id`.
    # Unknown / missing serve_ids are a silent no-op (do NOT 4xx).
    serve_id = ((body or {}).get("attribution_serve_id")
                or request.headers.get("X-Attribution-Serve-Id")
                or request.headers.get("x-attribution-serve-id"))
    if serve_id:
        evt = await db.ad_serve_events.find_one(
            {"$or": [{"id": serve_id}, {"serve_id": serve_id}]},
            {"campaign_id": 1, "advertiser_id": 1, "_id": 0})
        if evt:
            attr = {"attribution_serve_id": serve_id,
                    "attribution_campaign_id": evt.get("campaign_id"),
                    "attribution_advertiser_id": evt.get("advertiser_id")}
            await db.coupons.update_one(
                {"coupon_id": coupon["coupon_id"]}, {"$set": attr})
            coupon.update(attr)
    # Mint a wallet pass URL eagerly.  Even in stub mode the listener
    # gets a save_url they can show to test the flow.
    biz = await db.businesses.find_one({"business_id": coupon["business_id"]})
    offer = await db.offers.find_one({"offer_id": offer_id})
    cli = get_wallet_client()
    pass_res = cli.mint_coupon_pass(coupon=coupon, business=biz or {},
                                                offer=offer or {})
    # Persist save_url so future GETs don't re-mint
    await db.coupons.update_one(
        {"coupon_id": coupon["coupon_id"]},
        {"$set": {"wallet_pass_url": pass_res["save_url"]}})
    coupon["wallet_pass_url"] = pass_res["save_url"]
    coupon["wallet_pass_status"] = pass_res["pass_status"]
    return coupon


@listener_commerce_router.get("/coupons/me")
async def commerce_my_coupons(request: Request,
                                        status: Optional[str] = None,
                                        limit: int = 50,
                                        user: dict = Depends(current_user)):
    db = request.app.state.db
    try:
        items = await list_user_coupons(
            db, user_id=user["user_id"], status=status,
            limit=int(min(max(limit, 1), 200)))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"items": items, "count": len(items)}


@listener_commerce_router.get("/coupons/{coupon_id}")
async def commerce_my_coupon_detail(coupon_id: str, request: Request,
                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await db.coupons.find_one(
        {"coupon_id": coupon_id, "user_id": user["user_id"]})
    if not c:
        raise HTTPException(404, "coupon_not_found")
    # Phase R.1.1 — hydrate offer + business snapshot fields so the
    # Redeem screen renders a real title and the QR code content is the
    # user-facing redemption code (BIGFM-XXXXXX) rather than the internal
    # coupon_id.  Fall back to offer.business_id when the coupon row's
    # own business_id is missing (as with Phase H save-coupon rows).
    offer = (await db.offers.find_one({"offer_id": c.get("offer_id")})
                    if c.get("offer_id") else None)
    biz_id = c.get("business_id") or (offer.get("business_id") if offer else None)
    business = (await db.businesses.find_one({"business_id": biz_id})
                        if biz_id else None)
    return coupon_view(c, offer=offer, business=business)


@listener_commerce_router.post("/coupons/{coupon_id}/wallet_pass/google")
async def commerce_google_wallet(coupon_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    c = await db.coupons.find_one(
        {"coupon_id": coupon_id, "user_id": user["user_id"]})
    if not c:
        raise HTTPException(404, "coupon_not_found")
    biz = await db.businesses.find_one({"business_id": c["business_id"]})
    offer = await db.offers.find_one({"offer_id": c["offer_id"]})
    cli = get_wallet_client()
    res = cli.mint_coupon_pass(coupon=c, business=biz or {},
                                          offer=offer or {})
    await db.coupons.update_one(
        {"coupon_id": coupon_id},
        {"$set": {"wallet_pass_url": res["save_url"]}})
    return res


@listener_commerce_router.post("/coupons/{coupon_id}/wallet_pass/apple")
async def commerce_apple_wallet(coupon_id: str, request: Request,
                                            user: dict = Depends(current_user)):
    """Apple Wallet is stub-only in 9c."""
    db = request.app.state.db
    c = await db.coupons.find_one(
        {"coupon_id": coupon_id, "user_id": user["user_id"]})
    if not c:
        raise HTTPException(404, "coupon_not_found")
    return mint_apple_wallet_stub(c)


@listener_commerce_router.post("/coupons/{coupon_id}/share")
async def commerce_share_preview(coupon_id: str, request: Request,
                                              user: dict = Depends(current_user)):
    """Returns a shareable PREVIEW URL.  Sharing doesn't transfer the
    coupon — receiver still has to claim their own."""
    db = request.app.state.db
    c = await db.coupons.find_one(
        {"coupon_id": coupon_id, "user_id": user["user_id"]})
    if not c:
        raise HTTPException(404, "coupon_not_found")
    biz = await db.businesses.find_one({"business_id": c["business_id"]},
                                                  {"slug": 1})
    slug = (biz or {}).get("slug") or ""
    # Just point to the business page; the offer card on that page
    # invites the recipient to claim their own.
    public_url = (request.headers.get("x-forwarded-host")
                       or request.url.netloc)
    proto = "https" if request.url.scheme != "http" or request.headers.get(
        "x-forwarded-proto") == "https" else "http"
    return {"share_url": f"{proto}://{public_url}/business/{slug}",
              "preview_only": True}


# ═══════════════════════════════════════════════════════════════════════
# AUTH — partner upgrade
# ═══════════════════════════════════════════════════════════════════════
partner_upgrade_router = APIRouter(prefix="/api/auth/partner",
                                              tags=["auth_partner"])


@partner_upgrade_router.post("/upgrade")
async def auth_partner_upgrade(request: Request, body: dict,
                                          user: dict = Depends(current_user)):
    """Idempotent role bump to business_partner.  Requires accepting
    the partner terms (body must include `accept_terms: true`)."""
    db = request.app.state.db
    if not (body or {}).get("accept_terms"):
        raise HTTPException(400, "accept_terms_required")
    role = user.get("role")
    # admins / moderators stay as-is — they already have partner perms
    new_role = role if role in ("admin", "moderator",
                                          "business_partner") else "business_partner"
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"role": new_role,
                   "partner_terms_accepted_at": _now()}})
    fresh = await db.users.find_one({"user_id": user["user_id"]},
                                                {"user_id": 1, "role": 1,
                                                  "partner_terms_accepted_at": 1})
    return {"ok": True, "role": fresh.get("role"),
              "partner_terms_accepted_at": fresh.get("partner_terms_accepted_at").isoformat()
              if fresh.get("partner_terms_accepted_at") else None}


# ═══════════════════════════════════════════════════════════════════════
# PARTNER — business + offer management
# ═══════════════════════════════════════════════════════════════════════
partner_router = APIRouter(prefix="/api/partner", tags=["partner"])


@partner_router.post("/businesses/claim")
async def partner_claim_business(request: Request, body: dict,
                                            user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    try:
        out = await claim_business(
            db, user_id=user["user_id"],
            slug=(body or {}).get("slug"),
            business_id=(body or {}).get("business_id"),
            external_place_id=(body or {}).get("external_place_id"),
            manual_business=(body or {}).get("manual_business"))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return out


@partner_router.get("/businesses/me")
async def partner_my_businesses(request: Request,
                                          user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    cur = db.businesses.find({"owner_user_ids": user["user_id"]})
    items = []
    async for b in cur:
        if not b.get("slug"):
            try:
                await assign_slug_if_missing(db, b["business_id"])
                b = await db.businesses.find_one({"business_id": b["business_id"]})
            except Exception:
                pass
        items.append(business_view(b))
    return {"items": items, "count": len(items)}


@partner_router.patch("/businesses/{biz_id}")
async def partner_edit_business(biz_id: str, request: Request, body: dict,
                                            user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    EDITABLE = {"name", "tagline", "description", "logo_url",
                  "cover_image_url", "hours_json", "social_links_json",
                  "phone", "address", "tags", "cuisines"}
    upd = {k: v for k, v in (body or {}).items() if k in EDITABLE}
    if not upd:
        raise HTTPException(400, "no_editable_fields")
    upd["updated_at"] = _now()
    await db.businesses.update_one(
        {"business_id": biz_id}, {"$set": upd})
    biz = await db.businesses.find_one({"business_id": biz_id})
    return business_view(biz)


@partner_router.post("/businesses/{biz_id}/pos/connect")
async def partner_pos_connect(biz_id: str, request: Request, body: dict,
                                        user: dict = Depends(current_user)):
    """POS scaffold — stores config, no live API call.  Phase 9c is
    deliberately scaffold-only here."""
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    provider = (body or {}).get("provider")
    if provider not in POS_PROVIDERS:
        raise HTTPException(400, f"provider_invalid:{provider}")
    if provider == "none":
        await db.businesses.update_one(
            {"business_id": biz_id},
            {"$unset": {"pos_integration": ""}})
        return {"ok": True, "provider": "none"}
    from services.local_commerce import _new_id  # type: ignore
    iid = _new_id("posint")
    cfg = {
        "integration_id": iid,
        "business_id": biz_id,
        "provider": provider,
        "external_merchant_id": (body or {}).get("external_merchant_id", ""),
        "external_location_id": (body or {}).get("external_location_id"),
        "api_credentials_ref": (body or {}).get("api_credentials_ref")
                                      or f"vault:partner_pos:{iid}",
        "webhook_secret": (body or {}).get("webhook_secret"),
        "connected_at": _now(),
        "status": "connected",  # scaffold: no real handshake
        "error_message": None,
    }
    await db.partner_pos_integrations.insert_one(cfg)
    # Mirror summary on the business doc
    summary = {"provider": provider,
                  "merchant_id": cfg["external_merchant_id"],
                  "integration_id": iid,
                  "status": "connected"}
    await db.businesses.update_one(
        {"business_id": biz_id},
        {"$set": {"pos_integration": summary}})
    return {"ok": True, **summary,
              "note": "scaffold_only_no_live_api_calls_in_9c"}


@partner_router.post("/businesses/{biz_id}/offers")
async def partner_create_offer(biz_id: str, request: Request, body: dict,
                                          user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    try:
        out = await create_offer(db, business_id=biz_id, payload=body or {})
    except ValueError as e:
        raise HTTPException(400, str(e))
    return out


@partner_router.patch("/businesses/{biz_id}/offers/{offer_id}")
async def partner_edit_offer(biz_id: str, offer_id: str, request: Request,
                                        body: dict,
                                        user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    try:
        out = await update_offer(db, offer_id=offer_id, business_id=biz_id,
                                          patch=body or {})
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not out:
        raise HTTPException(404, "offer_not_found")
    return out


@partner_router.post(
    "/businesses/{biz_id}/offers/{offer_id}/submit_for_approval")
async def partner_submit_offer(biz_id: str, offer_id: str,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    try:
        return await submit_offer_for_approval(
            db, offer_id=offer_id, business_id=biz_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@partner_router.post(
    "/businesses/{biz_id}/offers/{offer_id}/revise")
async def partner_revise_offer(biz_id: str, offer_id: str,
                                          request: Request, body: dict,
                                          user: dict = Depends(current_user)):
    """Phase 9c.1 — Partner acknowledges the admin rejection reason and
    re-opens the offer for editing.  Body must include
    `acknowledge_rejection_reason: true`.  Returns the offer in `draft`
    state with a `previous_rejections` audit trail.
    """
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    try:
        return await revise_offer(
            db, offer_id=offer_id, business_id=biz_id,
            acknowledge_rejection_reason=bool(
                (body or {}).get("acknowledge_rejection_reason")))
    except ValueError as e:
        raise HTTPException(400, str(e))


@partner_router.post("/businesses/{biz_id}/offers/{offer_id}/pause")
async def partner_pause_offer(biz_id: str, offer_id: str,
                                          request: Request,
                                          user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    try:
        return await transition_offer_status(
            db, offer_id=offer_id, business_id=biz_id, new_status="paused")
    except ValueError as e:
        raise HTTPException(400, str(e))


@partner_router.post("/businesses/{biz_id}/offers/{offer_id}/resume")
async def partner_resume_offer(biz_id: str, offer_id: str,
                                            request: Request,
                                            user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    try:
        return await transition_offer_status(
            db, offer_id=offer_id, business_id=biz_id, new_status="active")
    except ValueError as e:
        raise HTTPException(400, str(e))


@partner_router.post("/businesses/{biz_id}/offers/{offer_id}/end")
async def partner_end_offer(biz_id: str, offer_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    try:
        return await transition_offer_status(
            db, offer_id=offer_id, business_id=biz_id, new_status="ended")
    except ValueError as e:
        raise HTTPException(400, str(e))


@partner_router.get("/businesses/{biz_id}/offers")
async def partner_list_offers(biz_id: str, request: Request,
                                        user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    cur = db.offers.find({"business_id": biz_id}).sort("created_at", -1)
    items = [offer_view(o) async for o in cur]
    return {"items": items, "count": len(items)}


@partner_router.get("/businesses/{biz_id}/offers/{offer_id}/analytics")
async def partner_offer_analytics(biz_id: str, offer_id: str,
                                              request: Request,
                                              user: dict = Depends(current_user)):
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    out = await offer_analytics(db, offer_id=offer_id, business_id=biz_id)
    if not out:
        raise HTTPException(404, "offer_not_found")
    return out


@partner_router.get("/businesses/{biz_id}/offers/{offer_id}/redemptions")
async def partner_offer_redemptions(biz_id: str, offer_id: str,
                                                  request: Request,
                                                  user: dict = Depends(current_user),
                                                  limit: int = 50,
                                                  status: Optional[str] = None):
    _require_partner(user)
    db = request.app.state.db
    await _own_business(db, business_id=biz_id, user_id=user["user_id"])
    q: dict = {"offer_id": offer_id, "business_id": biz_id}
    if status:
        q["status"] = status
    cur = db.coupons.find(q).sort("redeemed_at", -1).limit(
        int(min(max(limit, 1), 200)))
    items = [coupon_view(c) async for c in cur]
    return {"items": items, "count": len(items)}


@partner_router.post("/redeem/{qr_token}")
async def partner_redeem(qr_token: str, request: Request,
                                user: dict = Depends(current_user)):
    """Partner redeems a coupon by QR.

    The raw partner-token secret must be passed in either:
      - `X-Partner-Token` header (preferred), OR
      - `Authorization: Partner <secret>` header (Phase 9c.1 shim).

    Scope `redeem_offers` is required.  Every failed-auth attempt
    writes a row to `offer_redemptions_audit` BEFORE returning 401 so
    suspicious activity is recoverable from the audit log.
    """
    _require_partner(user)
    db = request.app.state.db
    # Phase 9c.1 — accept Authorization: Partner <secret> as a shim
    raw = request.headers.get("x-partner-token") \
              or request.headers.get("X-Partner-Token")
    if not raw:
        auth_hdr = (request.headers.get("authorization")
                          or request.headers.get("Authorization") or "")
        if auth_hdr.lower().startswith("partner "):
            raw = auth_hdr.split(None, 1)[1].strip() or None

    async def _audit_failed(outcome: str, partner_token_id: Optional[str],
                                  reason: str):
        # Phase 9c.1 — never silently drop a failed redemption.  Write
        # to offer_redemptions_audit BEFORE raising 401 so the partner
        # operator can debug + admins have visibility.
        aud_id = _new_commerce_id("rda")
        await db.offer_redemptions_audit.insert_one({
            "_id": aud_id, "audit_id": aud_id,
            "qr_token_prefix": (qr_token or "")[:12],
            "partner_token_id": partner_token_id,
            "coupon_id": None, "offer_id": None, "business_id": None,
            "outcome": outcome, "reason": reason,
            "ip": request.client.host if request.client else "",
            "user_agent": request.headers.get("user-agent", "")[:200],
            "ts": _now(),
        })

    if not raw:
        await _audit_failed("missing_auth", None, "no_partner_token_header")
        raise HTTPException(401, "partner_token_required")
    from services.games_v2 import check_partner_token_status
    # Two-pass: scope-less check first, then scope assertion.  This
    # lets us distinguish `insufficient_scope` from `invalid`/`revoked`
    # in the audit trail.
    row_any, status_any = await check_partner_token_status(
        db, raw, required_scope="")
    if status_any == "revoked":
        await _audit_failed("token_revoked",
                                  (row_any or {}).get("partner_token_id"),
                                  "partner_token_revoked")
        raise HTTPException(401, "partner_token_revoked")
    if status_any != "valid":
        await _audit_failed("missing_auth", None, "partner_token_invalid")
        raise HTTPException(401, "partner_token_invalid")
    # Now check the scope
    scopes = (row_any or {}).get("scopes") or []
    if "redeem_offers" not in scopes:
        await _audit_failed("insufficient_scope",
                                  row_any.get("partner_token_id"),
                                  "missing_scope:redeem_offers")
        raise HTTPException(401, "partner_token_insufficient_scope")

    row = row_any
    pid = row["partner_token_id"]
    bid_check = row.get("partner_business_id") or ""
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    try:
        out = await redeem_coupon_by_qr(
            db, qr_token=qr_token, partner_token_id=pid,
            business_id_check=bid_check, ip=ip, user_agent=ua)
    except ValueError as e:
        msg = str(e)
        if msg in ("not_found",):
            raise HTTPException(404, msg)
        # Phase 9c.1 — alias `inventory_exhausted` to `out_of_inventory`
        if msg == "inventory_exhausted":
            msg = "out_of_inventory"
        # Phase 12c Hotfix #3 — structured fraud detail body so partner
        # POS UIs can render "fraud_blocked" distinctly from a normal
        # idempotent "already_redeemed" replay.
        if msg.startswith("fraud_block:"):
            parts = msg.split(":")
            rule = parts[1] if len(parts) > 1 else "unknown"
            fraud_id = parts[2] if len(parts) > 2 else None
            raise HTTPException(409, {
                "code": "fraud_blocked",
                "rule": rule,
                "fraud_id": fraud_id,
                "human_message": "Already redeemed."})
        raise HTTPException(409, msg)
    # Touch last_used_at on partner_token
    await db.partner_tokens.update_one(
        {"partner_token_id": pid}, {"$set": {"last_used_at": _now()}})
    return out


# ═══════════════════════════════════════════════════════════════════════
# ADMIN
# ═══════════════════════════════════════════════════════════════════════
admin_commerce_router = APIRouter(prefix="/api/admin",
                                              tags=["admin_commerce"])


@admin_commerce_router.get("/businesses/verify_queue")
async def admin_verify_queue(request: Request,
                                        _u: dict = Depends(require_admin),
                                        limit: int = 50):
    db = request.app.state.db
    cur = db.businesses.find(
        {"partner_status": "claimed"}
    ).sort("claimed_at", -1).limit(int(min(max(limit, 1), 200)))
    items = [business_view(b) async for b in cur]
    return {"items": items, "count": len(items)}


@admin_commerce_router.post("/coupons/backfill_missing_ids")
async def admin_backfill_coupon_ids(request: Request,
                                                      _u: dict = Depends(require_admin)):
    """Phase 11.4 — one-shot backfill for legacy coupon rows missing the
    `coupon_id` field.  Sets `coupon_id = str(_id)`.  Idempotent."""
    db = request.app.state.db
    return await backfill_missing_coupon_ids(db)




@admin_commerce_router.post("/businesses/{biz_id}/verify")
async def admin_verify_business(biz_id: str, request: Request,
                                            _u: dict = Depends(require_admin)):
    db = request.app.state.db
    res = await db.businesses.update_one(
        {"business_id": biz_id, "partner_status": {"$in": ["claimed", "suspended"]}},
        {"$set": {"partner_status": "verified", "verified_at": _now()}})
    if res.matched_count == 0:
        raise HTTPException(404, "business_not_found_or_already_verified")
    return business_view(await db.businesses.find_one({"business_id": biz_id}))


@admin_commerce_router.post("/businesses/{biz_id}/reject")
async def admin_reject_business(biz_id: str, request: Request, body: dict,
                                            _u: dict = Depends(require_admin)):
    reason = (body or {}).get("reason", "").strip()
    if not reason:
        raise HTTPException(400, "reason_required")
    db = request.app.state.db
    res = await db.businesses.update_one(
        {"business_id": biz_id, "partner_status": {"$in": ["claimed"]}},
        {"$set": {"partner_status": "suspended",
                   "rejected_at": _now(),
                   "rejection_reason": reason[:500]}})
    if res.matched_count == 0:
        raise HTTPException(404, "business_not_found")
    return business_view(await db.businesses.find_one({"business_id": biz_id}))


@admin_commerce_router.get("/offers/approve_queue")
async def admin_approve_queue(request: Request,
                                          _u: dict = Depends(require_admin),
                                          limit: int = 50):
    db = request.app.state.db
    cur = db.offers.find(
        {"status": "pending_approval"}
    ).sort("updated_at", -1).limit(int(min(max(limit, 1), 200)))
    items = [offer_view(o) async for o in cur]
    return {"items": items, "count": len(items)}


@admin_commerce_router.post("/offers/{offer_id}/approve")
async def admin_approve_offer(offer_id: str, request: Request,
                                          u: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        return await approve_offer(db, offer_id=offer_id,
                                              admin_user_id=u["user_id"])
    except ValueError as e:
        raise HTTPException(400, str(e))


@admin_commerce_router.post("/offers/{offer_id}/reject")
async def admin_reject_offer(offer_id: str, request: Request, body: dict,
                                        u: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        return await reject_offer(
            db, offer_id=offer_id, admin_user_id=u["user_id"],
            reason=(body or {}).get("reason", ""))
    except ValueError as e:
        raise HTTPException(400, str(e))


@admin_commerce_router.post("/offers/{offer_id}/force_pause")
async def admin_force_pause(offer_id: str, request: Request,
                                       _u: dict = Depends(require_admin)):
    db = request.app.state.db
    try:
        return await transition_offer_status(
            db, offer_id=offer_id, business_id=None,
            new_status="paused", allow_admin=True)
    except ValueError as e:
        raise HTTPException(400, str(e))


@admin_commerce_router.get("/offer_redemptions_audit")
async def admin_offer_redemptions_audit(request: Request,
                                                       _u: dict = Depends(require_admin),
                                                       business_id: Optional[str] = None,
                                                       coupon_id: Optional[str] = None,
                                                       outcome: Optional[str] = None,
                                                       limit: int = 100):
    db = request.app.state.db
    q: dict = {}
    if business_id: q["business_id"] = business_id
    if coupon_id:   q["coupon_id"] = coupon_id
    if outcome:     q["outcome"] = outcome
    cur = db.offer_redemptions_audit.find(q).sort("ts", -1).limit(
        int(min(max(limit, 1), 500)))
    items = []
    async for r in cur:
        items.append({
            "audit_id": r.get("audit_id"),
            "coupon_id": r.get("coupon_id"),
            "offer_id": r.get("offer_id"),
            "business_id": r.get("business_id"),
            "partner_token_id": r.get("partner_token_id"),
            "outcome": r.get("outcome"),
            "reason": r.get("reason"),
            "qr_token_prefix": r.get("qr_token_prefix"),
            "ip": r.get("ip"),
            "user_agent": r.get("user_agent"),
            "ts": (r["ts"].isoformat()
                      if hasattr(r.get("ts"), "isoformat") else r.get("ts")),
        })
    return {"items": items, "count": len(items)}


@admin_commerce_router.get("/offer_redemptions_audit.csv")
async def admin_offer_redemptions_audit_csv(request: Request,
                                                              _u: dict = Depends(require_admin),
                                                              business_id: Optional[str] = None,
                                                              limit: int = 1000):
    db = request.app.state.db
    q: dict = {}
    if business_id: q["business_id"] = business_id
    cur = db.offer_redemptions_audit.find(q).sort("ts", -1).limit(
        int(min(max(limit, 1), 5000)))
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["audit_id", "coupon_id", "offer_id", "business_id",
                          "partner_token_id", "outcome", "reason",
                          "qr_token_prefix",
                          "ip", "user_agent", "ts"])
    async for r in cur:
        ts = r.get("ts")
        if hasattr(ts, "isoformat"):
            ts = ts.isoformat()
        writer.writerow([r.get("audit_id"), r.get("coupon_id"),
                              r.get("offer_id"), r.get("business_id"),
                              r.get("partner_token_id"), r.get("outcome"),
                              r.get("reason") or "",
                              r.get("qr_token_prefix") or "",
                              r.get("ip"), (r.get("user_agent") or "")[:120],
                              ts])
    return Response(content=buf.getvalue(),
                        media_type="text/csv",
                        headers={"Content-Disposition":
                                  "attachment; filename=offer_redemptions_audit.csv"})


__all__ = [
    "public_commerce_router",
    "listener_commerce_router",
    "partner_upgrade_router",
    "partner_router",
    "admin_commerce_router",
]
