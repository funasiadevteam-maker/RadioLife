"""Partner API self-serve portal (web dashboard) + admin management.

Lets a logged-in advertiser create their Partner account and mint/revoke
API keys + OAuth2 clients for the public FUUSIC Ads API (`/api/v1`).
Raw secrets are shown exactly once, on creation.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user, require_admin
from core.brand import BRAND_PARTNER_EMAIL
from services import partner_api as pa
from services import partner_marketplace as mkt
from services import trivia_sponsorship_service as tr
from services import rj_sponsored_read_service as rj
from services import ad1_advertiser_service as ad
from services import rj_persona_service as rjp

router = APIRouter(prefix="/api/partner", tags=["partner-portal"])
admin_router = APIRouter(prefix="/api/admin/partner-api", tags=["admin-partner-api"])


class PartnerCreate(BaseModel):
    name: str
    contact_email: str


class KeyCreate(BaseModel):
    environment: str = "live"          # "live" | "sandbox"
    label: Optional[str] = None
    scopes: Optional[list[str]] = None


async def _my_partner(db, user: dict) -> Optional[dict]:
    return await db.partner_accounts.find_one({"owner_user_id": user.get("user_id")})


# ── self-serve ──────────────────────────────────────────────────────
@router.get("/account")
async def get_account(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        return {"exists": False, "scopes": pa.SCOPES}
    creds = await pa.list_credentials(db, partner_id=p["partner_id"])
    return {"exists": True, "partner": pa._clean(p), "scopes": pa.SCOPES, **creds}


@router.post("/account")
async def create_account(body: PartnerCreate, request: Request,
                         user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await pa.get_or_create_partner(
        db, owner_user_id=user.get("user_id"),
        name=body.name, contact_email=body.contact_email)
    return {"partner": p}


@router.post("/keys")
async def create_key(body: KeyCreate, request: Request,
                     user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    return await pa.issue_api_key(db, partner_id=p["partner_id"],
                                  environment=body.environment,
                                  scopes=body.scopes, label=body.label)


@router.post("/keys/{key_id}/revoke")
async def revoke_key(key_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    ok = await pa.revoke_api_key(db, partner_id=p["partner_id"], key_id=key_id)
    if not ok:
        raise HTTPException(404, {"code": "key_not_found"})
    return {"ok": True, "key_id": key_id, "revoked": True}


@router.post("/oauth-clients")
async def create_oauth_client(body: KeyCreate, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    return await pa.issue_oauth_client(db, partner_id=p["partner_id"],
                                       environment=body.environment,
                                       scopes=body.scopes, label=body.label)


@router.post("/oauth-clients/{client_id}/revoke")
async def revoke_oauth_client(client_id: str, request: Request,
                              user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    ok = await pa.revoke_oauth_client(db, partner_id=p["partner_id"], client_id=client_id)
    if not ok:
        raise HTTPException(404, {"code": "client_not_found"})
    return {"ok": True, "client_id": client_id, "revoked": True}


class WebhookBody(BaseModel):
    url: str
    events: Optional[list[str]] = None
    environment: str = "live"


@router.get("/usage")
async def my_usage(request: Request, days: int = 30, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        return {"exists": False}
    return await pa.compute_usage(db, partner_id=p["partner_id"], days=days)


@router.get("/webhooks")
async def my_webhooks(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        return {"items": [], "events": pa.WEBHOOK_EVENTS}
    return {"items": await pa.list_webhooks(db, partner_id=p["partner_id"]), "events": pa.WEBHOOK_EVENTS}


@router.post("/webhooks")
async def my_create_webhook(body: WebhookBody, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    return await pa.create_webhook(db, partner_id=p["partner_id"], environment=body.environment,
                                   url=body.url, events=body.events)


@router.post("/webhooks/{webhook_id}/ping")
async def my_ping_webhook(webhook_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    r = await pa.ping_webhook(db, partner_id=p["partner_id"], webhook_id=webhook_id)
    if r is None:
        raise HTTPException(404, {"code": "webhook_not_found"})
    return r


@router.delete("/webhooks/{webhook_id}")
async def my_delete_webhook(webhook_id: str, request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    if not await pa.delete_webhook(db, partner_id=p["partner_id"], webhook_id=webhook_id):
        raise HTTPException(404, {"code": "webhook_not_found"})
    return {"deleted": True}


# ── Phase F: portal webhook hardening + key IP allowlist ────────────
class IpAllowlistBody(BaseModel):
    ip_allowlist: list[str] = Field(default_factory=list)


@router.post("/keys/{key_id}/ip-allowlist")
async def my_set_key_ip_allowlist(key_id: str, body: IpAllowlistBody, request: Request,
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    ok = await pa.set_key_ip_allowlist(db, partner_id=p["partner_id"], key_id=key_id,
                                       ip_allowlist=body.ip_allowlist)
    if not ok:
        raise HTTPException(404, {"code": "key_not_found"})
    return {"ok": True, "key_id": key_id, "ip_allowlist": body.ip_allowlist}


@router.post("/webhooks/{webhook_id}/rotate-secret")
async def my_rotate_webhook_secret(webhook_id: str, request: Request,
                                   user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    r = await pa.rotate_webhook_secret(db, partner_id=p["partner_id"], webhook_id=webhook_id)
    if r is None:
        raise HTTPException(404, {"code": "webhook_not_found"})
    return r


@router.get("/webhooks/{webhook_id}/deliveries")
async def my_webhook_deliveries(webhook_id: str, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    return {"items": await pa.list_deliveries(db, partner_id=p["partner_id"], webhook_id=webhook_id)}


@router.post("/webhooks/{webhook_id}/deliveries/{delivery_id}/retry")
async def my_retry_delivery(webhook_id: str, delivery_id: str, request: Request,
                            user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    r = await pa.retry_delivery(db, partner_id=p["partner_id"], webhook_id=webhook_id,
                                delivery_id=delivery_id)
    if r is None:
        raise HTTPException(404, {"code": "delivery_not_found"})
    return r


# ── console "buy & promote" (cookie-auth wrappers over /api/v1) ──────
# The Advertiser Dashboard "API Checkout" page drives the SAME Partner-API
# services as /api/v1, but authenticated by the logged-in user's cookie so
# the browser never handles a raw API key. Environment ("live"|"sandbox")
# is chosen per request; sandbox activates instantly with no Stripe.
from routes import partner_api_v1 as v1  # noqa: E402  (no cycle: v1 never imports this module)


class PortalPromoCheckout(BaseModel):
    business_id: str
    tier: str
    environment: str = "sandbox"
    origin_url: Optional[str] = None


class PortalSpotlightCheckout(BaseModel):
    business_id: str
    category: str
    bid_cents: int = Field(..., ge=1, le=1000)
    amount_cents: int = Field(..., ge=500, le=1000000)
    daily_cap_cents: int = 0
    environment: str = "sandbox"
    origin_url: Optional[str] = None


class PortalSponsorship(BaseModel):
    type: str                         # trivia | rj_read
    environment: str = "sandbox"
    display_name: Optional[str] = None
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    sponsor_target_type: Optional[str] = "any"
    target_id: Optional[str] = None
    prize_pool: Optional[list] = None
    winner_selection: Optional[str] = "top_n"
    score_threshold: Optional[int] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    persona_id: Optional[str] = None
    station_ids: Optional[list] = None
    any_station: Optional[bool] = True
    disclosure_prefix: Optional[str] = None
    plays_target: Optional[int] = None
    cost_per_play_cents: Optional[int] = None
    script_body: Optional[str] = None
    product_name: Optional[str] = None
    key_message: Optional[str] = None
    cta: Optional[str] = None


class PortalSpAction(BaseModel):      # submit / checkout
    type: str
    advertiser_id: str
    environment: str = "sandbox"
    final_script: Optional[str] = None
    origin_url: Optional[str] = None


async def _require_partner(db, user):
    p = await _my_partner(db, user)
    if not p:
        raise HTTPException(400, {"code": "no_partner_account"})
    return p


async def _ensure_partner_adv(db, p, env):
    """One reusable advertiser per (partner, env), force-activated so console
    sponsorships aren't blocked on approval."""
    owner = f"partner:{p['partner_id']}:{env.lower()}"
    adv = await db.advertisers_v2.find_one({"owner_user_id": owner})
    if adv:
        return adv["advertiser_id"]
    created = await ad.create_advertiser(
        db, owner_user_id=owner, name=p.get("name") or "Partner Console",
        contact_email=p.get("contact_email") or BRAND_PARTNER_EMAIL)
    aid = created["advertiser_id"]
    await db.advertisers_v2.update_one(
        {"advertiser_id": aid},
        {"$set": {"status": "active", "approved_at": pa._now(),
                  "approved_by": "portal", "updated_at": pa._now()}})
    return aid


def _return_urls(origin_url):
    if origin_url:
        base = origin_url.rstrip("/")
        return (f"{base}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
                f"{base}/payment/cancel")
    return None, None                 # services fall back to BIGFM_PUBLIC_BASE_URL


def _mkt_err(e: Exception) -> HTTPException:
    if isinstance(e, LookupError):
        return HTTPException(404, {"code": str(e) or "not_found"})
    return HTTPException(400, {"code": str(e) or "bad_request"})


@router.get("/commerce/catalog")
async def portal_commerce_catalog(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _require_partner(db, user)
    return {"tiers": mkt.promo_tiers(),
            "categories": await mkt.list_categories(db),
            "businesses": await mkt.list_promotable_businesses(db, limit=60),
            "personas": await rjp.list_personas(db, status="active"),
            "favourite_persona_id": p.get("favourite_persona_id")}


class VoiceFavourite(BaseModel):
    persona_id: Optional[str] = None


@router.post("/commerce/voice-favourite")
async def portal_set_voice_favourite(body: VoiceFavourite, request: Request,
                                     user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _require_partner(db, user)
    await db.partner_accounts.update_one(
        {"partner_id": p["partner_id"]}, {"$set": {"favourite_persona_id": body.persona_id}})
    return {"favourite_persona_id": body.persona_id}


@router.get("/commerce/history")
async def portal_commerce_history(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _require_partner(db, user)
    live_ids = await pa._partner_advertiser_ids(db, p["partner_id"], "live")
    sand_ids = await pa._partner_advertiser_ids(db, p["partner_id"], "sandbox")
    adv_env = {**{a: "LIVE" for a in live_ids}, **{a: "SANDBOX" for a in sand_ids}}
    items = await mkt.list_partner_history(
        db, partner_id=p["partner_id"], adv_ids=live_ids + sand_ids, adv_env=adv_env)
    return {"items": items, "count": len(items)}


@router.get("/commerce/analytics/summary")
async def portal_commerce_summary(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _require_partner(db, user)
    return await mkt.partner_analytics_summary(db, partner_id=p["partner_id"])


@router.post("/commerce/promotion/checkout")
async def portal_promotion_checkout(body: PortalPromoCheckout, request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _require_partner(db, user)
    env = pa._norm_env(body.environment)
    s_url, c_url = _return_urls(body.origin_url)
    try:
        return await mkt.promotion_checkout(
            db, business_id=body.business_id, tier_key=body.tier,
            partner_id=p["partner_id"], sandbox=(env == "SANDBOX"), environment=env,
            success_url=s_url, cancel_url=c_url)
    except Exception as e:
        raise _mkt_err(e)


@router.get("/commerce/promotion/{promotion_id}/status")
async def portal_promotion_status(promotion_id: str, request: Request,
                                  environment: str = "sandbox",
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _require_partner(db, user)
    try:
        return await mkt.promotion_status(db, promotion_id=promotion_id,
                                          partner_id=p["partner_id"],
                                          environment=pa._norm_env(environment))
    except Exception as e:
        raise _mkt_err(e)


@router.get("/commerce/promotion/{promotion_id}/report")
async def portal_promotion_report(promotion_id: str, request: Request,
                                  environment: str = "sandbox",
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _require_partner(db, user)
    try:
        return await mkt.promotion_report(db, promotion_id=promotion_id,
                                          partner_id=p["partner_id"],
                                          environment=pa._norm_env(environment))
    except Exception as e:
        raise _mkt_err(e)


@router.post("/commerce/spotlight/checkout")
async def portal_spotlight_checkout(body: PortalSpotlightCheckout, request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _require_partner(db, user)
    env = pa._norm_env(body.environment)
    s_url, c_url = _return_urls(body.origin_url)
    try:
        return await mkt.spotlight_checkout(
            db, business_id=body.business_id, category=body.category,
            bid_cents=body.bid_cents, amount_cents=body.amount_cents,
            daily_cap_cents=body.daily_cap_cents, partner_id=p["partner_id"],
            sandbox=(env == "SANDBOX"), environment=env,
            success_url=s_url, cancel_url=c_url)
    except Exception as e:
        raise _mkt_err(e)


@router.get("/commerce/spotlight/{session_id}/status")
async def portal_spotlight_status(session_id: str, request: Request,
                                  environment: str = "sandbox",
                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _require_partner(db, user)
    try:
        return await mkt.spotlight_status(db, session_id=session_id,
                                          partner_id=p["partner_id"],
                                          environment=pa._norm_env(environment))
    except Exception as e:
        raise _mkt_err(e)


@router.get("/commerce/spotlight")
async def portal_spotlight_get(request: Request, business_id: str,
                               user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_partner(db, user)
    return await mkt.spotlight_get(db, business_id=business_id)


@router.get("/commerce/personas")
async def portal_personas(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_partner(db, user)
    return {"items": await rjp.list_personas(db, status="active")}


@router.post("/commerce/personas/{persona_id}/preview")
async def portal_persona_preview(persona_id: str, request: Request,
                                 user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_partner(db, user)
    per = await db.rj_personas.find_one({"id": persona_id})
    if not per:
        raise HTTPException(404, {"code": "persona_not_found"})
    if per.get("sample_audio_url"):
        return {"audio_url": per["sample_audio_url"], "cached": True,
                "persona_id": persona_id}
    try:
        r = await rjp.generate_preview(
            db, persona_id=persona_id, actor_user_id=user.get("user_id"),
            context={"product_name": "Acme Cola", "key_message": "crisp and refreshing",
                     "cta": "Try one today", "disclosure_prefix": "Sponsored by"})
    except RuntimeError as e:
        raise HTTPException(503, {"code": str(e)})
    except ValueError as e:
        raise HTTPException(404, {"code": str(e)})
    except Exception as e:
        raise HTTPException(503, {"code": "voice_preview_failed", "detail": str(e)[:200]})
    return {"audio_url": r.get("audio_url"), "script": r.get("script_text"),
            "cached": False, "persona_id": persona_id}


@router.post("/commerce/sponsorships")
async def portal_create_sponsorship(body: PortalSponsorship, request: Request,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    p = await _require_partner(db, user)
    env = pa._norm_env(body.environment)
    aid = await _ensure_partner_adv(db, p, env)
    owner = f"partner:{p['partner_id']}:{env.lower()}"
    t = body.type
    try:
        if t == "trivia":
            tbody = {"sponsor_target_type": body.sponsor_target_type or "any",
                     "target_id": body.target_id, "prize_pool": body.prize_pool or [],
                     "winner_selection": body.winner_selection or "top_n",
                     "score_threshold": body.score_threshold, "display_name": body.display_name,
                     "tagline": body.tagline, "logo_url": body.logo_url,
                     "start_at": body.start_at, "end_at": body.end_at}
            res = await tr.create_sponsorship(db, advertiser_business_id=aid, body=tbody, user_id=owner)
            sid = res.get("id") or res.get("sponsorship_id")
        elif t == "rj_read":
            rbody = {"persona_id": body.persona_id, "station_ids": body.station_ids or [],
                     "any_station": bool(body.any_station), "disclosure_prefix": body.disclosure_prefix,
                     "plays_target": body.plays_target, "cost_per_play_cents": body.cost_per_play_cents,
                     "script_body": body.script_body or "", "product_name": body.product_name,
                     "key_message": body.key_message, "cta": body.cta,
                     "start_at": body.start_at, "end_at": body.end_at}
            res = await rj.create_sponsored_read(db, advertiser_business_id=aid, body=rbody, user_id=owner)
            sid = res.get("id") or res.get("sponsored_read_id")
        else:
            raise HTTPException(400, {"code": "unknown_sponsorship_type"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, {"code": str(e)})
    if env == "SANDBOX" and sid:
        await v1._sandbox_activate(db, t, sid)
        res = await v1._sp_fetch(db, t, sid)
    return {"sponsorship": res, "sponsorship_id": sid, "type": t,
            "advertiser_id": aid, "environment": env}


@router.post("/commerce/sponsorships/{sponsorship_id}/submit")
async def portal_submit_sponsorship(sponsorship_id: str, body: PortalSpAction,
                                    request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_partner(db, user)
    if body.type == "trivia":
        raise HTTPException(409, {"code": "use_checkout_endpoint"})
    if body.type == "rj_read":
        final = (body.final_script or "").strip()
        if not final:
            doc = await db.rj_sponsored_reads.find_one({"id": sponsorship_id})
            final = (doc or {}).get("script_body") or ""
        try:
            return await rj.submit_sponsored_read(
                db, sponsored_read_id=sponsorship_id,
                advertiser_business_id=body.advertiser_id, final_script=final)
        except Exception as e:
            raise HTTPException(400, {"code": str(e)})
    raise HTTPException(400, {"code": "unknown_sponsorship_type"})


@router.post("/commerce/sponsorships/{sponsorship_id}/checkout")
async def portal_sponsorship_checkout(sponsorship_id: str, body: PortalSpAction,
                                      request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_partner(db, user)
    env = pa._norm_env(body.environment)
    if env == "SANDBOX":
        return {"sandbox": True, "checkout_required": False, "status": "active",
                "type": body.type, "sponsorship_id": sponsorship_id}
    s_url, c_url = _return_urls(body.origin_url)
    try:
        if body.type == "trivia":
            r = await tr.create_checkout(db, sponsorship_id=sponsorship_id,
                                         advertiser_business_id=body.advertiser_id,
                                         success_url=s_url, cancel_url=c_url)
        elif body.type == "rj_read":
            r = await rj.create_checkout(db, sponsored_read_id=sponsorship_id,
                                         advertiser_business_id=body.advertiser_id,
                                         success_url=s_url, cancel_url=c_url)
        else:
            raise HTTPException(400, {"code": "unknown_sponsorship_type"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, {"code": str(e)})
    return {**r, "type": body.type, "sponsorship_id": sponsorship_id}


@router.get("/commerce/sponsorships/{sponsorship_id}/checkout/status")
async def portal_sponsorship_status(sponsorship_id: str, request: Request,
                                    type: str, advertiser_id: str,
                                    environment: str = "sandbox",
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    await _require_partner(db, user)
    env = pa._norm_env(environment)
    if env == "SANDBOX":
        d = await v1._sp_fetch(db, type, sponsorship_id)
        return {"paid": True, "sandbox": True, "status": (d or {}).get("status"),
                "type": type, "sponsorship": d}
    try:
        if type == "trivia":
            r = await tr.sync_checkout(db, sponsorship_id=sponsorship_id,
                                       advertiser_business_id=advertiser_id)
        elif type == "rj_read":
            r = await rj.sync_checkout(db, sponsored_read_id=sponsorship_id,
                                       advertiser_business_id=advertiser_id)
        else:
            raise HTTPException(400, {"code": "unknown_sponsorship_type"})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, {"code": str(e)})
    return {**r, "type": type}



# ── admin ───────────────────────────────────────────────────────────
@admin_router.get("/partners")
async def admin_list_partners(request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    out = [pa._clean(p) async for p in db.partner_accounts.find({}).sort("created_at", -1).limit(200)]
    return {"items": out, "count": len(out)}


class AdminPartnerCreate(BaseModel):
    name: str
    contact_email: str
    owner_user_id: Optional[str] = None


@admin_router.post("/partners")
async def admin_create_partner(body: AdminPartnerCreate, request: Request,
                               _a=Depends(require_admin)):
    db = request.app.state.db
    p = await pa.get_or_create_partner(
        db, owner_user_id=body.owner_user_id or f"admin:{pa._gen('mgd')}",
        name=body.name, contact_email=body.contact_email)
    return {"partner": p}


@admin_router.post("/partners/{partner_id}/keys")
async def admin_issue_key(partner_id: str, body: KeyCreate, request: Request,
                          _a=Depends(require_admin)):
    db = request.app.state.db
    if not await pa.get_partner(db, partner_id):
        raise HTTPException(404, {"code": "partner_not_found"})
    return await pa.issue_api_key(db, partner_id=partner_id, environment=body.environment,
                                  scopes=body.scopes, label=body.label)


# ── Phase F: admin partner management ───────────────────────────────
class AdminStatusBody(BaseModel):
    status: str = Field(..., description="active | suspended")


class AdminRateLimitBody(BaseModel):
    per_minute: int = Field(..., ge=1, le=100000)


class AdminFlagsBody(BaseModel):
    flags: dict


async def _admin_assert_partner(db, partner_id: str) -> dict:
    p = await pa.get_partner(db, partner_id)
    if not p:
        raise HTTPException(404, {"code": "partner_not_found"})
    return p


@admin_router.get("/partners/{partner_id}/credentials")
async def admin_partner_credentials(partner_id: str, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    await _admin_assert_partner(db, partner_id)
    return await pa.list_credentials(db, partner_id=partner_id)


@admin_router.get("/partners/{partner_id}/usage")
async def admin_partner_usage(partner_id: str, request: Request, days: int = 30,
                              _a=Depends(require_admin)):
    db = request.app.state.db
    await _admin_assert_partner(db, partner_id)
    return await pa.compute_usage(db, partner_id=partner_id, days=days)


@admin_router.post("/partners/{partner_id}/status")
async def admin_partner_status(partner_id: str, body: AdminStatusBody, request: Request,
                               _a=Depends(require_admin)):
    db = request.app.state.db
    await _admin_assert_partner(db, partner_id)
    try:
        await pa.set_partner_status(db, partner_id=partner_id, status=body.status)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    return {"ok": True, "partner_id": partner_id, "status": body.status}


@admin_router.post("/partners/{partner_id}/rate-limit")
async def admin_partner_rate_limit(partner_id: str, body: AdminRateLimitBody, request: Request,
                                   _a=Depends(require_admin)):
    db = request.app.state.db
    await _admin_assert_partner(db, partner_id)
    await pa.set_partner_rate_limit(db, partner_id=partner_id, per_minute=body.per_minute)
    return {"ok": True, "partner_id": partner_id, "rate_limit_per_minute": body.per_minute}


@admin_router.get("/partners/{partner_id}/flags")
async def admin_get_partner_flags(partner_id: str, request: Request, _a=Depends(require_admin)):
    db = request.app.state.db
    await _admin_assert_partner(db, partner_id)
    return {"flags": await pa.get_partner_flags(db, partner_id)}


@admin_router.post("/partners/{partner_id}/flags")
async def admin_set_partner_flags(partner_id: str, body: AdminFlagsBody, request: Request,
                                  _a=Depends(require_admin)):
    db = request.app.state.db
    await _admin_assert_partner(db, partner_id)
    flags = await pa.set_partner_flags(db, partner_id=partner_id, flags=body.flags)
    return {"ok": True, "partner_id": partner_id, "flags": flags}


@admin_router.post("/partners/{partner_id}/keys/{key_id}/revoke")
async def admin_revoke_key(partner_id: str, key_id: str, request: Request,
                           _a=Depends(require_admin)):
    db = request.app.state.db
    await _admin_assert_partner(db, partner_id)
    if not await pa.revoke_api_key(db, partner_id=partner_id, key_id=key_id):
        raise HTTPException(404, {"code": "key_not_found"})
    return {"ok": True, "key_id": key_id, "revoked": True}


__all__ = ["router", "admin_router"]
