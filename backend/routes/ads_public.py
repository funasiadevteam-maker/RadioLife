"""Phase 4 — Ad public surface:
- GET  /api/ads/creative/{creative_id}/audio  → stream ad audio (Range support)
- POST /api/ads/impression/{ad_pod_id}/progress  → playback progress
- POST /api/ads/impression/{ad_pod_id}/complete  → 100% complete
- GET  /api/ads/current?session_id=X  → details for the most recent active ad pod (Action Card)
- POST /api/ads/action/{action_type}  → 11 action types (6 fully wired, 5 stubs)
- GET  /api/wallet/items  → user's saved coupons + wallet items
- POST /api/openrtb/bid|win|billed  → OpenRTB 2.5 endpoints (no-bid scaffold)
- GET  /api/vast/{creative_id}  → VAST 4.2 XML
- GET  /ads.txt  (mounted at app root, NOT /api)
- GET  /app-ads.txt  (mounted at app root)
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import StreamingResponse, Response, PlainTextResponse

ads_router = APIRouter(prefix="/api/ads", tags=["ads"])
wallet_router = APIRouter(prefix="/api/wallet", tags=["wallet"])
openrtb_router = APIRouter(prefix="/api/openrtb", tags=["openrtb"])
vast_router = APIRouter(prefix="/api/vast", tags=["vast"])
public_files_router = APIRouter(tags=["public-files"])  # no /api prefix

_RANGE_RE = re.compile(r"bytes=(\d+)-(\d*)")


# Phase 36c.5 (post-repack ads migration) — prefer Tigris key, fall back to
# the local audio_path. Mirrors the HEAD/Range pattern used by the public
# `podcasts/{ep}/audio.mp3` route. Returns a fastapi Response/StreamingResponse.
async def _serve_ad_creative_audio(cr: dict, request: Request):
    storage_key = cr.get("storage_key_creative_audio")
    if storage_key:
        from services import object_storage as obs
        st = obs.get_storage()
        head = st.head(key=storage_key)
        if head:
            size = int(head.get("size") or 0)
            headers = {"Accept-Ranges":   "bytes",
                              "Content-Length": str(size),
                              "Content-Type":     "audio/mpeg",
                              "Cache-Control":   "public, max-age=3600"}
            rng = request.headers.get("range") or request.headers.get("Range")
            if not rng:
                buf = st.open_range(key=storage_key, start=0, end=size - 1)
                return Response(content=buf, status_code=200, headers=headers,
                                              media_type="audio/mpeg")
            m = _RANGE_RE.match(rng)
            if not m: raise HTTPException(416, "bad Range")
            start = int(m.group(1))
            end = int(m.group(2)) if m.group(2) else size - 1
            end = min(end, size - 1)
            if start < 0 or start > end:
                return Response(status_code=416,
                                              headers={"Content-Range": f"bytes */{size}"})
            buf = st.open_range(key=storage_key, start=start, end=end)
            hdrs = dict(headers)
            hdrs["Content-Length"] = str(len(buf))
            hdrs["Content-Range"]  = f"bytes {start}-{end}/{size}"
            return Response(content=buf, status_code=206, headers=hdrs,
                                          media_type="audio/mpeg")
        # Tigris key set but HEAD failed → fall through to local fallback.
    p = Path(cr.get("audio_path") or "")
    if not p.is_file() or p.stat().st_size < 200:
        raise HTTPException(404, "audio not generated yet")
    return await _stream_audio_with_range(p, request)


async def _maybe_user(request: Request):
    """Returns user dict or None — does NOT raise."""
    try:
        from auth import current_user
        return await current_user(request)
    except Exception:
        return None


async def _require_user(request: Request):
    from auth import current_user
    return await current_user(request)


def _ser(d):
    if not d: return d
    d = dict(d)
    if "_id" in d: d["id"] = str(d["_id"]); d.pop("_id", None)
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"): d[k] = v.isoformat()
    return d


# ---------- Ad creative streaming ----------
@ads_router.get("/creative/{creative_id}/preview")
async def stream_creative_preview(creative_id: str, request: Request,
                                    u: dict = Depends(_require_user)):
    """Preview an ad creative regardless of `active` status. Used by advertisers
    to audit AI-generated sponsor reads before they're approved + flipped active.
    Requires auth — any logged-in user can preview their own creatives or admin
    can preview anything. Phase 4.5."""
    db = request.app.state.db
    cr = await db.ad_creatives.find_one(
        {"$or": [{"id": creative_id}, {"creative_id": creative_id}]},
        {"audio_path": 1, "advertiser_id": 1,
          "storage_key_creative_audio": 1, "_id": 0})
    if not cr or (not cr.get("audio_path") and not cr.get("storage_key_creative_audio")):
        raise HTTPException(404, "creative not found")
    # Ownership: admin or owning advertiser
    if u.get("role") != "admin":
        adv = await db.advertisers.find_one({"user_id": u["user_id"]}, {"advertiser_id": 1})
        if not adv or adv.get("advertiser_id") != cr.get("advertiser_id"):
            raise HTTPException(403, "not your creative")
    return await _serve_ad_creative_audio(cr, request)


async def _stream_audio_with_range(p: Path, request: Request) -> StreamingResponse:
    file_size = p.stat().st_size
    range_header = request.headers.get("range") or request.headers.get("Range")
    if not range_header:
        def _full():
            with open(p, "rb") as f:
                while chunk := f.read(65536): yield chunk
        return StreamingResponse(_full(), media_type="audio/mpeg",
                                  headers={"Content-Length": str(file_size),
                                            "Accept-Ranges": "bytes",
                                            "Cache-Control": "public, max-age=3600"})
    m = _RANGE_RE.match(range_header)
    if not m: raise HTTPException(416, "bad Range")
    start = int(m.group(1)); end = int(m.group(2)) if m.group(2) else file_size - 1
    end = min(end, file_size - 1); length = end - start + 1
    def _r():
        with open(p, "rb") as f:
            f.seek(start); remaining = length
            while remaining > 0:
                c = f.read(min(65536, remaining))
                if not c: break
                remaining -= len(c); yield c
    return StreamingResponse(_r(), status_code=206, media_type="audio/mpeg",
                              headers={"Content-Range": f"bytes {start}-{end}/{file_size}",
                                        "Accept-Ranges": "bytes",
                                        "Content-Length": str(length),
                                        "Cache-Control": "public, max-age=3600"})


@ads_router.get("/creative/{creative_id}/audio")
async def stream_creative(creative_id: str, request: Request):
    db = request.app.state.db
    # Phase 36c.5 (post-repack hotfix): match by either `id` (newer writers)
    # or legacy `creative_id`, and gate on either `status="approved"` OR
    # legacy `active=True` (legacy seed creatives use the active flag with
    # `approval_status="approved"`; newer writers use the `status` field).
    cr = await db.ad_creatives.find_one(
        {"$and": [
            {"$or": [{"id": creative_id}, {"creative_id": creative_id}]},
            {"$or": [{"status": {"$in": ["approved", "active"]}},
                          {"active": True}]},
        ]},
        {"audio_path": 1,
          "storage_key_creative_audio": 1, "_id": 0})
    if not cr or (not cr.get("audio_path") and not cr.get("storage_key_creative_audio")):
        raise HTTPException(404, "creative not found")
    return await _serve_ad_creative_audio(cr, request)


# ---------- Impression tracking ----------
@ads_router.post("/impression/{ad_pod_id}/progress")
async def impression_progress(ad_pod_id: str, request: Request,
                                completion_pct: float = Query(0.0, ge=0.0, le=1.0),
                                played_for_sec: float = Query(0.0, ge=0.0)):
    db = request.app.state.db
    imp = await db.ad_impressions.find_one({"ad_pod_id": ad_pod_id}, {"_id": 1})
    if not imp:
        raise HTTPException(404, "impression not found")
    update = {"completion_pct": completion_pct, "played_for_sec": played_for_sec}
    if completion_pct >= 0.99:
        update["completed_at"] = datetime.now(timezone.utc)
    await db.ad_impressions.update_one({"_id": imp["_id"]}, {"$set": update})
    return {"ok": True}


@ads_router.get("/current")
async def current_ad(request: Request, session_id: str = Query(...)):
    """Frontend polls this when a new segment starts. Returns the most recent
    ad_pod for the session (if the current segment has one) with Action Card data."""
    db = request.app.state.db
    pod = await db.ad_pods.find_one({"session_id": session_id}, sort=[("served_at", -1)])
    if not pod:
        return {"has_ad": False}
    # Get creative + campaign + action cards + business
    cr = await db.ad_creatives.find_one(
        {"$or": [{"id": pod["ad_creative_id"]},
                      {"creative_id": pod["ad_creative_id"]}]})
    cmp = await db.campaigns.find_one({"campaign_id": pod["campaign_id"]})
    biz = await db.businesses.find_one({"business_id": cmp.get("business_id") if cmp else None})
    actions = await db.ad_action_cards.find({"campaign_id": pod["campaign_id"], "enabled": True}).sort([("display_order", 1)]).to_list(length=20)
    # P1.2 — contextual "Shop this sponsor" store link (if the sponsor runs a storefront)
    store = None
    try:
        from routes.storefront import resolve_sponsor_store
        adv_id = (cmp or {}).get("advertiser_id") or (cr or {}).get("advertiser_id")
        store = await resolve_sponsor_store(db, adv_id)
    except Exception:
        store = None
    return {"has_ad": True,
            "ad_pod": _ser(pod), "creative": _ser(cr),
            "campaign": _ser(cmp), "business": _ser(biz),
            "store": store,
            "action_cards": [_ser(a) for a in actions]}


# ---------- Action endpoints (6 wired + 5 stubs) ----------
async def _impression_for_pod(db, ad_pod_id: str) -> Optional[dict]:
    return await db.ad_impressions.find_one({"ad_pod_id": ad_pod_id})


async def _log_click(db, *, user_id: str, ad_pod_id: str, action_type: str,
                      payload: dict, conversion_value_cents: int = 0):
    imp = await _impression_for_pod(db, ad_pod_id)
    click_id = str(uuid.uuid4())
    await db.ad_clicks.insert_one({
        "_id": click_id,
        "ad_impression_id": imp["_id"] if imp else None,
        "ad_pod_id": ad_pod_id, "user_id": user_id,
        "action_type": action_type, "payload_json": payload,
        "clicked_at": datetime.now(timezone.utc),
        "conversion_value_cents": conversion_value_cents,
    })
    return click_id


@ads_router.post("/action/save_coupon")
async def action_save_coupon(request: Request, payload: dict, u: dict = Depends(_require_user)):
    db = request.app.state.db
    ad_pod_id = payload.get("ad_pod_id")
    offer_id = payload.get("offer_id")
    if not ad_pod_id or not offer_id: raise HTTPException(400, "ad_pod_id + offer_id required")
    offer = await db.offers.find_one({"offer_id": offer_id})
    if not offer: raise HTTPException(404, "offer not found")
    coupon_id = f"cp_{uuid.uuid4().hex[:14]}"
    code = f"BIGFM-{coupon_id[-6:].upper()}"
    now = datetime.now(timezone.utc)
    # Phase 18c — attribution chain: resolve serve_id → campaign_id + advertiser_id.
    # Accepted via body field `attribution_serve_id` OR header `X-Attribution-Serve-Id`.
    # If missing or unknown, write coupon without attribution fields (do NOT 4xx).
    serve_id = (payload.get("attribution_serve_id")
                or request.headers.get("X-Attribution-Serve-Id")
                or request.headers.get("x-attribution-serve-id"))
    attribution = {}
    if serve_id:
        evt = await db.ad_serve_events.find_one(
            {"$or": [{"id": serve_id}, {"serve_id": serve_id}]},
            {"campaign_id": 1, "advertiser_id": 1, "_id": 0})
        if evt:
            attribution = {
                "attribution_serve_id": serve_id,
                "attribution_campaign_id": evt.get("campaign_id"),
                "attribution_advertiser_id": evt.get("advertiser_id"),
            }
    await db.coupons.insert_one({
        "_id": coupon_id, "coupon_id": coupon_id,
        "user_id": u["user_id"], "offer_id": offer_id,
        "code": code, "status": "saved",
        "saved_at": now, "expires_at": now + timedelta(days=30),
        **attribution,
    })
    await db.user_wallet_items.insert_one({
        "_id": f"wi_{coupon_id}", "user_id": u["user_id"], "item_type": "coupon",
        "source_ad_pod_id": ad_pod_id, "source_campaign_id": payload.get("campaign_id"),
        "offer_id": offer_id, "coupon_id": coupon_id,
        "title": offer.get("title"), "description": offer.get("description"),
        "value_cents": offer.get("discount_value_cents") or 0,
        "status": "active", "expiration": (now + timedelta(days=30)).isoformat(),
        "created_at": now,
    })
    await _log_click(db, user_id=u["user_id"], ad_pod_id=ad_pod_id,
                      action_type="save_coupon", payload={"offer_id": offer_id, "code": code})
    # Phase 5 — award 5 BC for saving a coupon
    try:
        from services.bigcoin import award as _bc_award
        _bc = await _bc_award(db, u["user_id"], 5, "ad_save",
                                 metadata={"ad_pod_id": ad_pod_id, "offer_id": offer_id,
                                           "coupon_id": coupon_id})
    except Exception:
        _bc = None
    # Phase 8b — milestone unlock for first ad save of the day
    try:
        from services.game_unlock_engine import on_ad_save
        await on_ad_save(db, u["user_id"], ad_id=ad_pod_id)
    except Exception:
        pass
    # Phase AD.12 bundle — fire the `coupon_saved` trigger for any LIVE
    # notification campaign using that recipe.  Silent on failure.
    try:
        from services.notification_trigger_dispatcher import dispatch_event
        await dispatch_event(db, event_name="coupon_saved",
                                                    user_id=u["user_id"],
                                                    payload={"offer_id": offer_id,
                                                                      "coupon_id": coupon_id})
    except Exception:
        pass
    return {"ok": True, "coupon_id": coupon_id, "code": code,
            "bigcoin_earned": (_bc or {}).get("balance_after") and 5 or 0,
            "bigcoin_balance_after": (_bc or {}).get("balance_after")}


@ads_router.post("/action/get_directions")
async def action_get_directions(request: Request, payload: dict, u: dict = Depends(_require_user)):
    db = request.app.state.db
    ad_pod_id = payload.get("ad_pod_id")
    business_id = payload.get("business_id")
    biz = await db.businesses.find_one({"business_id": business_id})
    if not biz: raise HTTPException(404, "business not found")
    # Build Google Maps deeplink
    addr = quote(biz.get("address") or biz.get("name") or "")
    maps_url = f"https://www.google.com/maps/search/?api=1&query={addr}"
    if biz.get("latitude") and biz.get("longitude"):
        maps_url += f"&query_place_id=&center={biz['latitude']},{biz['longitude']}"
    await _log_click(db, user_id=u["user_id"], ad_pod_id=ad_pod_id,
                      action_type="get_directions", payload={"business_id": business_id, "url": maps_url})
    return {"ok": True, "maps_url": maps_url, "address": biz.get("address"),
            "phone": biz.get("phone"), "name": biz.get("name")}


@ads_router.post("/action/buy_now")
async def action_buy_now(request: Request, payload: dict, u: dict = Depends(_require_user)):
    db = request.app.state.db
    ad_pod_id = payload.get("ad_pod_id")
    product_id = payload.get("product_id")
    if not product_id: raise HTTPException(400, "product_id required")
    product = await db.products.find_one({"product_id": product_id})
    if not product: raise HTTPException(404, "product not found")
    business = await db.businesses.find_one({"business_id": product.get("business_id")}) or {}
    order_id = f"ord_{uuid.uuid4().hex[:14]}"
    now = datetime.now(timezone.utc)

    # Phase 4.5 — if the business has Stripe Connect onboarded, create a real
    # Stripe Checkout Session with destination charges (10% platform fee).
    checkout_url = f"/checkout/order/{order_id}"
    checkout_session_id = None
    note = "Phase 4 stub — business not yet on Stripe Connect"
    connect_acct = business.get("stripe_connect_account_id")
    charges_enabled = bool(business.get("stripe_charges_enabled"))
    if connect_acct and charges_enabled:
        try:
            import os, stripe as _stripe
            _stripe.api_key = os.environ.get("STRIPE_API_KEY") or os.environ.get("STRIPE_SECRET_KEY")
            platform_fee_pct = float(os.environ.get("PLATFORM_FEE_PCT", "0.10"))
            amount_cents = int(product.get("price_cents") or 0)
            currency = (product.get("currency") or "USD").lower()
            fee_cents = int(amount_cents * platform_fee_pct)
            base = str(request.base_url).rstrip("/")
            cs = _stripe.checkout.Session.create(
                mode="payment",
                payment_method_types=["card"],
                line_items=[{
                    "price_data": {
                        "currency": currency,
                        "unit_amount": amount_cents,
                        "product_data": {
                            "name": product.get("title") or "RadioLife Action Card Purchase",
                            "description": (product.get("description") or "")[:300],
                        },
                    },
                    "quantity": 1,
                }],
                payment_intent_data={
                    "application_fee_amount": fee_cents,
                    "transfer_data": {"destination": connect_acct},
                    "metadata": {
                        "order_id": order_id, "product_id": product_id,
                        "ad_pod_id": ad_pod_id or "",
                        "business_id": business.get("business_id") or "",
                        "campaign_id": product.get("campaign_id") or "",
                        "user_id": u.get("user_id") or "",
                    },
                },
                metadata={"order_id": order_id, "user_id": u.get("user_id") or ""},
                customer_email=u.get("email"),
                success_url=f"{base}/checkout/success?order_id={order_id}",
                cancel_url=f"{base}/checkout/cancel?order_id={order_id}",
            )
            checkout_url = cs.url
            checkout_session_id = cs.id
            note = "Stripe Connect Checkout (destination charge)"
        except Exception as e:
            note = f"Stripe Checkout failed, fell back to intent: {e}"
            checkout_url = f"/checkout/order/{order_id}"

    await db.orders.insert_one({
        "_id": order_id, "user_id": u["user_id"], "product_id": product_id,
        "business_id": product.get("business_id"), "campaign_id": product.get("campaign_id"),
        "amount_cents": product.get("price_cents"), "currency": product.get("currency"),
        "status": "checkout_open" if checkout_session_id else "intent_created",
        "stripe_checkout_session_id": checkout_session_id,
        "stripe_destination_account": connect_acct,
        "platform_fee_cents": int(int(product.get("price_cents") or 0) * float(os.environ.get("PLATFORM_FEE_PCT", "0.10"))) if checkout_session_id else 0,
        "created_at": now, "ad_pod_id": ad_pod_id,
    })
    await _log_click(db, user_id=u["user_id"], ad_pod_id=ad_pod_id,
                      action_type="buy_now", payload={"product_id": product_id, "order_id": order_id},
                      conversion_value_cents=int(product.get("price_cents") or 0))
    # Update wallet
    await db.user_wallet_items.insert_one({
        "_id": f"wi_{order_id}", "user_id": u["user_id"], "item_type": "order_intent",
        "source_ad_pod_id": ad_pod_id, "product_id": product_id, "order_id": order_id,
        "title": product.get("title"), "value_cents": product.get("price_cents"),
        "status": "pending_payment", "created_at": now,
    })
    return {"ok": True, "order_id": order_id, "checkout_url": checkout_url,
            "stripe_session_id": checkout_session_id, "note": note}


@ads_router.post("/action/reserve_table")
async def action_reserve_table(request: Request, payload: dict, u: dict = Depends(_require_user)):
    db = request.app.state.db
    ad_pod_id = payload.get("ad_pod_id")
    business_id = payload.get("business_id")
    biz = await db.businesses.find_one({"business_id": business_id})
    if not biz: raise HTTPException(404, "business not found")
    res_id = f"res_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    requested = payload.get("requested_time") or (now + timedelta(hours=24)).isoformat()
    party = int(payload.get("party_size") or 2)
    await db.reservations.insert_one({
        "_id": res_id, "user_id": u["user_id"], "business_id": business_id,
        "requested_time": requested, "party_size": party,
        "phone": payload.get("phone") or u.get("phone"),
        "name": u.get("name"), "email": u.get("email"),
        "status": "requested",
        "created_at": now, "ad_pod_id": ad_pod_id,
        "business_phone": biz.get("phone"), "business_name": biz.get("name"),
    })
    await _log_click(db, user_id=u["user_id"], ad_pod_id=ad_pod_id,
                      action_type="reserve_table",
                      payload={"reservation_id": res_id, "business_id": business_id, "party_size": party})
    return {"ok": True, "reservation_id": res_id, "status": "requested",
            "business_name": biz.get("name"), "business_phone": biz.get("phone"),
            "note": f"Reservation sent to {biz.get('name')}. They'll confirm via phone/SMS."}


@ads_router.post("/action/share")
async def action_share(request: Request, payload: dict, u: dict = Depends(_require_user)):
    db = request.app.state.db
    ad_pod_id = payload.get("ad_pod_id")
    campaign_id = payload.get("campaign_id")
    share_url = f"{request.base_url}share/ad/{ad_pod_id}" if ad_pod_id else f"{request.base_url}"
    await _log_click(db, user_id=u["user_id"], ad_pod_id=ad_pod_id,
                      action_type="share", payload={"campaign_id": campaign_id, "url": share_url})
    return {"ok": True, "share_url": share_url}


@ads_router.post("/action/join_giveaway")
async def action_join_giveaway(request: Request, payload: dict, u: dict = Depends(_require_user)):
    db = request.app.state.db
    ad_pod_id = payload.get("ad_pod_id")
    giveaway_id = payload.get("giveaway_id")
    if not giveaway_id: raise HTTPException(400, "giveaway_id required")
    gw = await db.giveaways.find_one({"giveaway_id": giveaway_id})
    if not gw: raise HTTPException(404, "giveaway not found")
    # idempotent — one entry per user per giveaway
    existing = await db.giveaway_entries.find_one({"giveaway_id": giveaway_id, "user_id": u["user_id"]})
    if existing:
        return {"ok": True, "entry_id": str(existing.get("_id")), "already_entered": True}
    entry_id = f"gwe_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    await db.giveaway_entries.insert_one({
        "_id": entry_id, "giveaway_id": giveaway_id, "user_id": u["user_id"],
        "entered_at": now, "status": "entered",
    })
    await db.user_wallet_items.insert_one({
        "_id": f"wi_{entry_id}", "user_id": u["user_id"], "item_type": "giveaway_entry",
        "giveaway_id": giveaway_id, "title": gw.get("title"),
        "value_cents": gw.get("prize_value_cents"), "status": "active",
        "expiration": gw.get("draw_at"), "created_at": now,
        "source_ad_pod_id": ad_pod_id,
    })
    await _log_click(db, user_id=u["user_id"], ad_pod_id=ad_pod_id,
                      action_type="join_giveaway", payload={"giveaway_id": giveaway_id, "entry_id": entry_id})
    return {"ok": True, "entry_id": entry_id, "draw_at": gw.get("draw_at")}


# ---------- Stub actions (write intent, return ack) ----------
_STUB_ACTIONS = ["clip_ad", "add_to_wallet", "book_appointment", "order_now",
                  "buy_gift_card", "buy_product", "buy_prepaid_lunch", "buy_prepaid_dinner",
                  "buy_tickets", "request_callback", "remind_me_later"]

for _act in _STUB_ACTIONS:
    async def _stub(request: Request, payload: dict, _act=_act, u: dict = Depends(_require_user)):
        db = request.app.state.db
        ad_pod_id = payload.get("ad_pod_id")
        intent_id = f"int_{uuid.uuid4().hex[:12]}"
        # Persist intent + log
        await db.action_intents.insert_one({
            "_id": intent_id, "user_id": u["user_id"], "action_type": _act,
            "payload": payload, "ad_pod_id": ad_pod_id,
            "status": "captured", "created_at": datetime.now(timezone.utc),
        })
        await _log_click(db, user_id=u["user_id"], ad_pod_id=ad_pod_id,
                          action_type=_act, payload=payload)
        # Add a wallet entry for the stub
        if _act in ("book_appointment", "buy_tickets", "buy_prepaid_lunch", "buy_prepaid_dinner",
                     "buy_gift_card", "add_to_wallet", "remind_me_later"):
            await db.user_wallet_items.insert_one({
                "_id": f"wi_{intent_id}", "user_id": u["user_id"], "item_type": _act,
                "source_ad_pod_id": ad_pod_id, "title": payload.get("title") or _act.replace("_", " ").title(),
                "status": "intent_captured",
                "created_at": datetime.now(timezone.utc),
            })
        return {"ok": True, "intent_id": intent_id, "action_type": _act,
                "note": f"Phase 4 stub for {_act}. Full flow ships Phase 4.5+."}

    ads_router.post(f"/action/{_act}")(_stub)


# ---------- Wallet ----------
@wallet_router.get("/items")
async def wallet_items(request: Request, u: dict = Depends(_require_user),
                        status: Optional[str] = Query(None)):
    db = request.app.state.db
    q = {"user_id": u["user_id"]}
    if status: q["status"] = status
    docs = await db.user_wallet_items.find(q).sort([("created_at", -1)]).to_list(length=200)
    coupons = await db.coupons.find({"user_id": u["user_id"]}).sort([("saved_at", -1)]).to_list(length=200)
    return {"items": [_ser(d) for d in docs],
            "coupons": [_ser(d) for d in coupons],
            "total": len(docs)}


# ---------- OpenRTB 2.5 ----------
@openrtb_router.post("/bid")
async def openrtb_bid(request: Request):
    """Phase 4: scaffold. Validates BidRequest shape, logs to openrtb_bid_logs,
    returns 204 No Content (no bid). Phase 4.5 implements real auction."""
    db = request.app.state.db
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "invalid JSON")
    # Minimal OpenRTB 2.5 validation
    if not isinstance(body, dict): raise HTTPException(400, "bid request must be object")
    if not body.get("id"): raise HTTPException(400, "missing BidRequest.id")
    imps = body.get("imp") or []
    if not isinstance(imps, list) or len(imps) == 0:
        raise HTTPException(400, "missing BidRequest.imp")
    # Log it
    await db.openrtb_bid_logs.insert_one({
        "_id": str(uuid.uuid4()),
        "bidrequest_id": body.get("id"),
        "imp_count": len(imps),
        "imp_types": [_imp_type(i) for i in imps],
        "site": body.get("site"), "app": body.get("app"),
        "user_geo_country": (body.get("user") or {}).get("geo", {}).get("country"),
        "decision": "no_bid",
        "received_at": datetime.now(timezone.utc),
        "raw_keys": list(body.keys()),
    })
    return Response(status_code=204)


def _imp_type(imp: dict) -> str:
    if "audio" in imp: return "audio"
    if "video" in imp: return "video"
    if "banner" in imp: return "banner"
    if "native" in imp: return "native"
    return "unknown"


@openrtb_router.post("/win")
async def openrtb_win(request: Request, body: dict):
    db = request.app.state.db
    await db.openrtb_bid_logs.update_one(
        {"bidrequest_id": body.get("bidrequest_id")},
        {"$set": {"win_notified_at": datetime.now(timezone.utc),
                   "win_price_cents": int(body.get("price_cents") or 0)}},
    )
    return {"ok": True}


@openrtb_router.post("/billed")
async def openrtb_billed(request: Request, body: dict):
    db = request.app.state.db
    await db.openrtb_bid_logs.update_one(
        {"bidrequest_id": body.get("bidrequest_id")},
        {"$set": {"billed_at": datetime.now(timezone.utc)}},
    )
    return {"ok": True}


# ---------- VAST 4.2 XML ----------
@vast_router.get("/{creative_id}")
async def vast_xml(creative_id: str, request: Request):
    db = request.app.state.db
    cr = await db.ad_creatives.find_one(
        {"$and": [
            {"$or": [{"id": creative_id}, {"creative_id": creative_id}]},
            {"$or": [{"status": {"$in": ["approved", "active"]}},
                          {"active": True}]},
        ]})
    if not cr:
        # Return an empty VAST so callers don't choke
        empty = '<?xml version="1.0" encoding="UTF-8"?>\n<VAST version="4.2"/>'
        return Response(empty, media_type="application/xml")
    cmp = await db.campaigns.find_one({"campaign_id": cr.get("campaign_id")})
    biz = await db.businesses.find_one({"business_id": cmp.get("business_id") if cmp else None})
    base = str(request.base_url).rstrip("/")
    audio_url = f"{base}{cr['audio_url']}"
    impression_url = f"{base}/api/ads/impression/{creative_id}/served"
    click_url = (biz or {}).get("website") or f"{base}/"
    duration = float(cr.get("duration_sec") or 20)
    mm = int(duration // 60); ss = int(duration % 60)
    duration_str = f"00:{mm:02d}:{ss:02d}"
    title = (cmp.get("name") if cmp else cr.get("creative_id", ""))
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<VAST version="4.2">
  <Ad id="{creative_id}">
    <InLine>
      <AdSystem version="1.0">BigFM</AdSystem>
      <AdTitle><![CDATA[{title}]]></AdTitle>
      <Description><![CDATA[{(cr.get('transcript') or '')[:300]}]]></Description>
      <Advertiser><![CDATA[{(biz or {}).get('name') or 'BigFM Advertiser'}]]></Advertiser>
      <Impression id="bigfm-imp"><![CDATA[{impression_url}]]></Impression>
      <Creatives>
        <Creative id="{creative_id}-c1" sequence="1">
          <Linear>
            <Duration>{duration_str}</Duration>
            <TrackingEvents>
              <Tracking event="start"><![CDATA[{base}/api/ads/track/{creative_id}/start]]></Tracking>
              <Tracking event="firstQuartile"><![CDATA[{base}/api/ads/track/{creative_id}/q1]]></Tracking>
              <Tracking event="midpoint"><![CDATA[{base}/api/ads/track/{creative_id}/midpoint]]></Tracking>
              <Tracking event="thirdQuartile"><![CDATA[{base}/api/ads/track/{creative_id}/q3]]></Tracking>
              <Tracking event="complete"><![CDATA[{base}/api/ads/track/{creative_id}/complete]]></Tracking>
              <Tracking event="mute"><![CDATA[{base}/api/ads/track/{creative_id}/mute]]></Tracking>
            </TrackingEvents>
            <VideoClicks>
              <ClickThrough id="bigfm-click"><![CDATA[{click_url}]]></ClickThrough>
            </VideoClicks>
            <MediaFiles>
              <MediaFile delivery="progressive" type="audio/mpeg" bitrate="192" width="0" height="0">
                <![CDATA[{audio_url}]]>
              </MediaFile>
            </MediaFiles>
          </Linear>
        </Creative>
      </Creatives>
    </InLine>
  </Ad>
</VAST>"""
    return Response(xml, media_type="application/xml",
                     headers={"Cache-Control": "public, max-age=3600"})


@ads_router.get("/track/{creative_id}/{event}")
async def vast_track(creative_id: str, event: str, request: Request):
    """Trackback endpoint for VAST tracking events."""
    db = request.app.state.db
    await db.vast_tracking_events.insert_one({
        "creative_id": creative_id, "event": event,
        "received_at": datetime.now(timezone.utc),
        "ua": request.headers.get("user-agent"),
    })
    # Standard 1x1 transparent gif response (no payload needed)
    return Response(status_code=204)


# ---------- /ads.txt & /app-ads.txt (PUBLIC, no /api prefix) ----------
_ADS_TXT = """# BigFM / FunAsia AI Radio — ads.txt
# Authorized sellers / direct-sold inventory.
# Spec: IAB Tech Lab ads.txt v1.1
# Updated: 2026

google.com, 21958684679, DIRECT, f08c47fec0942fa0

# Direct-sold inventory served by BigFM Networks. SSP/exchange entries will be
# added as we onboard programmatic partners (Magnite, PubMatic, Index, etc.).
"""


@public_files_router.get("/ads.txt", response_class=PlainTextResponse)
async def ads_txt():
    # Phase 18d — single source of truth: /app/backend/static/ads.txt
    # (override with ADS_TXT_PATH env).  No fallback to baked-in seed —
    # the file is guaranteed to exist after the lifespan boot seed runs.
    from services.ads_txt_manager import read_content
    return PlainTextResponse(read_content(),
                                            headers={"Cache-Control": "public, max-age=300"})


@public_files_router.get("/app-ads.txt", response_class=PlainTextResponse)
async def app_ads_txt():
    from services.ads_txt_manager import read_content
    return PlainTextResponse(read_content(),
                                            headers={"Cache-Control": "public, max-age=300"})
