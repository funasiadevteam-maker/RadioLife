"""RadioLife Ads Public API — v1 (mounted at /api/v1).

A versioned, partner-authenticated facade over the internal ad platform
(`services.ad1_advertiser_service`). External systems use it to discover
marketing inventory and buy campaigns programmatically. Interactive docs are
served at `/api/v1/docs` (OpenAPI at `/api/v1/openapi.json`).

Auth: `Authorization: Bearer <api_key | oauth_access_token>` — see
`services.partner_api`. LIVE vs SANDBOX credentials are isolated; sandbox
campaigns are auto-approved and never serve/bill real inventory.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from services import ad1_advertiser_service as ad
from services import partner_api as pa
from services.partner_api import Caller, require_scopes

log = logging.getLogger("bigfm.partner_api.v1")

partner_app = FastAPI(
    title="RadioLife Ads API",
    version="1.0.0",
    description=(
        "Programmatic access to RadioLife marketing inventory — audio ads, "
        "display banners, sponsorships, programmatic (OpenRTB) and marketplace "
        "promotion. Authenticate with a partner API key or an OAuth2 "
        "client-credentials token. Use a `SANDBOX` key to test end-to-end "
        "without spending real budget."
    ),
    docs_url="/docs", redoc_url="/redoc", openapi_url="/openapi.json",
)


# ── error mapping ───────────────────────────────────────────────────
def _map_error(e: Exception) -> HTTPException:
    if isinstance(e, HTTPException):
        return e
    if isinstance(e, LookupError):
        return HTTPException(404, {"code": str(e) or "not_found"})
    if isinstance(e, PermissionError):
        return HTTPException(403, {"code": str(e) or "forbidden"})
    if isinstance(e, ValueError):
        return HTTPException(400, {"code": str(e) or "bad_request"})
    log.warning("[v1] unhandled error: %s", e)
    return HTTPException(500, {"code": "internal_error"})


def _svc_user(caller: Caller) -> dict:
    return {"user_id": caller.owner_id, "role": "partner"}


async def _assert_adv(db, caller: Caller, advertiser_id: str) -> dict:
    adv = await ad.get_advertiser(db, advertiser_id=advertiser_id)
    if not adv or adv.get("owner_user_id") != caller.owner_id:
        raise HTTPException(404, {"code": "advertiser_not_found"})
    return adv


# ══════════════════════════ meta ════════════════════════════════════
@partner_app.get("/", tags=["meta"])
async def root():
    return {"api": "RadioLife Ads API", "version": "1.0.0",
            "docs": "/api/v1/docs", "openapi": "/api/v1/openapi.json",
            "auth": "Bearer partner API key or OAuth2 client-credentials token",
            "token_url": "/api/v1/oauth/token"}


@partner_app.get("/me", tags=["meta"])
async def whoami(request: Request, caller: Caller = Depends(require_scopes())):
    p = await pa.get_partner(request.app.state.db, caller.partner_id)
    return {"partner_id": caller.partner_id, "partner": p,
            "environment": caller.environment, "scopes": sorted(caller.scopes),
            "credential_type": caller.credential_type}


@partner_app.get("/products", tags=["catalog"])
async def products(caller: Caller = Depends(require_scopes("catalog:read"))):
    return {"pricing_models": {"cpm": "cost per 1,000 impressions",
                               "cpc": "cost per click", "flat": "flat fee for the flight"},
            "scopes": pa.SCOPES, "items": pa.PRODUCTS}


# ══════════════════════════ OAuth2 ══════════════════════════════════
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    scope: str


@partner_app.post("/oauth/token", response_model=TokenResponse, tags=["auth"])
async def oauth_token(request: Request):
    """OAuth2 client-credentials grant. Send `client_id`/`client_secret` as form
    fields or HTTP Basic, `grant_type=client_credentials`, optional `scope`."""
    db = request.app.state.db
    form = await request.form()
    if form.get("grant_type") != "client_credentials":
        raise HTTPException(400, {"code": "unsupported_grant_type"})
    client_id = form.get("client_id")
    client_secret = form.get("client_secret")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("basic "):
        import base64
        try:
            client_id, client_secret = base64.b64decode(auth[6:]).decode().split(":", 1)
        except Exception:
            pass
    if not client_id or not client_secret:
        raise HTTPException(401, {"code": "client_authentication_required"})
    doc = await pa.verify_client_credentials(db, client_id, client_secret)
    if not doc:
        raise HTTPException(401, {"code": "invalid_client"})
    allowed = set(doc.get("scopes", []))
    requested = set((form.get("scope") or "").split())
    if requested - allowed:
        raise HTTPException(400, {"code": "invalid_scope"})
    scopes = list(requested & allowed) if requested else list(allowed)
    tok = await pa.mint_access_token(db, client_id=client_id,
                                     partner_id=doc["partner_id"],
                                     environment=doc["environment"], scopes=scopes)
    return TokenResponse(**tok)


# ══════════════════════════ advertisers ═════════════════════════════
class AdvertiserCreate(BaseModel):
    name: str
    contact_email: str
    contact_name: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    logo_url: Optional[str] = None


@partner_app.post("/advertisers", tags=["advertisers"], status_code=201)
async def create_advertiser(body: AdvertiserCreate, request: Request,
                            caller: Caller = Depends(require_scopes("advertisers:write"))):
    db = request.app.state.db
    try:
        adv = await ad.create_advertiser(
            db, owner_user_id=caller.owner_id, name=body.name,
            contact_email=body.contact_email, contact_name=body.contact_name,
            website=body.website, industry=body.industry, logo_url=body.logo_url)
    except Exception as e:
        raise _map_error(e)
    aid = adv["advertiser_id"]
    if caller.is_sandbox:
        await db.advertisers_v2.update_one(
            {"advertiser_id": aid},
            {"$set": {"status": "active", "approved_at": pa._now(),
                      "approved_by": "sandbox", "updated_at": pa._now()}})
        adv["status"] = "active"
    else:
        await ad.submit_advertiser_for_approval(db, advertiser_id=aid, user=_svc_user(caller))
        adv["status"] = "pending_approval"
    return {"advertiser": adv, "environment": caller.environment}


@partner_app.get("/advertisers/{advertiser_id}", tags=["advertisers"])
async def get_advertiser(advertiser_id: str, request: Request,
                         caller: Caller = Depends(require_scopes("advertisers:read"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    return {"advertiser": ad._clean(await ad.get_advertiser(db, advertiser_id=advertiser_id))}


@partner_app.get("/advertisers/{advertiser_id}/balance", tags=["funding"])
async def advertiser_balance(advertiser_id: str, request: Request,
                             caller: Caller = Depends(require_scopes("funding:write"))):
    db = request.app.state.db
    adv = await _assert_adv(db, caller, advertiser_id)
    return {"advertiser_id": advertiser_id,
            "budget_available_cents": int(adv.get("budget_available_cents", 0)),
            "currency": "usd"}


class TopUpBody(BaseModel):
    amount_cents: int = Field(..., ge=500, le=50000000)
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@partner_app.post("/advertisers/{advertiser_id}/funding/topup", tags=["funding"])
async def topup(advertiser_id: str, body: TopUpBody, request: Request,
                caller: Caller = Depends(require_scopes("funding:write"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    if caller.is_sandbox:
        # Sandbox: credit budget instantly, no Stripe.
        await db.advertisers_v2.update_one(
            {"advertiser_id": advertiser_id},
            {"$inc": {"budget_available_cents": int(body.amount_cents)},
             "$set": {"updated_at": pa._now()}})
        adv = await ad.get_advertiser(db, advertiser_id=advertiser_id)
        return {"credited": True, "sandbox": True,
                "budget_available_cents": int((adv or {}).get("budget_available_cents", 0))}
    try:
        r = await ad.create_topup_checkout(
            db, advertiser_id=advertiser_id, amount_cents=int(body.amount_cents),
            user=_svc_user(caller), success_url=body.success_url, cancel_url=body.cancel_url)
    except Exception as e:
        raise _map_error(e)
    return {"checkout_url": r.get("checkout_url"), "payment_id": r.get("payment_id"),
            "session_id": r.get("stripe_checkout_session_id") or r.get("session_id"),
            "sandbox": False}


# ══════════════════════════ campaigns ═══════════════════════════════
class Targeting(BaseModel):
    cities: list[str] = []
    user_segments: list[str] = ["all"]
    dayparts: list[str] = []
    languages: list[str] = []
    genres: list[str] = []


class Creative(BaseModel):
    headline: Optional[str] = None
    body: Optional[str] = None
    image_url: Optional[str] = None
    click_url: Optional[str] = None
    audio_url: Optional[str] = None
    sponsored_game_campaign_id: Optional[str] = None


class CampaignCreate(BaseModel):
    advertiser_id: str
    product: str = Field(..., description="Product key from GET /products (e.g. audio_preroll, display_banner)")
    name: str
    budget_total_cents: int = Field(..., ge=1)
    pricing_model: str = "cpm"
    cpm_bid_cents: Optional[int] = None
    cpc_bid_cents: Optional[int] = None
    daily_cap_cents: Optional[int] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    targeting: Targeting = Field(default_factory=Targeting)
    creative: Creative = Field(default_factory=Creative)


@partner_app.post("/campaigns", tags=["campaigns"], status_code=201)
async def create_campaign(body: CampaignCreate, request: Request,
                          caller: Caller = Depends(require_scopes("campaigns:write"))):
    db = request.app.state.db
    adv = await _assert_adv(db, caller, body.advertiser_id)
    prod = pa.product_by_key(body.product)
    if not prod:
        raise HTTPException(400, {"code": "unknown_product", "product": body.product})
    if not prod.get("bookable") or not prod.get("campaign_type"):
        raise HTTPException(409, {"code": "product_not_bookable_via_api",
                                  "product": body.product, "status": prod.get("status"),
                                  "hint": "Contact RadioLife to onboard this product."})
    if adv.get("status") != "active":
        raise HTTPException(409, {"code": "advertiser_not_active",
                                  "status": adv.get("status")})
    creative = body.creative.model_dump(exclude_none=True)
    if prod["campaign_type"] == "audio_preroll_stub" and body.creative.audio_url:
        creative["image_url"] = creative.get("image_url") or body.creative.audio_url
    payload = {
        "campaign_type": prod["campaign_type"], "name": body.name,
        "budget_total_cents": body.budget_total_cents, "pricing_model": body.pricing_model,
        "cpm_bid_cents": body.cpm_bid_cents, "cpc_bid_cents": body.cpc_bid_cents,
        "daily_cap_cents": body.daily_cap_cents,
        "start_at": body.start_at, "end_at": body.end_at,
        "targeting": body.targeting.model_dump(), "creative": creative,
    }
    try:
        camp = await ad.create_campaign(db, advertiser_id=body.advertiser_id,
                                        payload=payload, user=_svc_user(caller))
    except Exception as e:
        raise _map_error(e)
    cid = camp["campaign_id"]
    if caller.is_sandbox:
        await db.ad_campaigns_v2.update_one(
            {"campaign_id": cid},
            {"$set": {"status": "active", "approved_at": pa._now(),
                      "approved_by": "sandbox", "updated_at": pa._now()}})
        camp["status"] = "active"
    return {"campaign": camp, "product": body.product, "environment": caller.environment}


@partner_app.get("/campaigns", tags=["campaigns"])
async def list_campaigns(request: Request, advertiser_id: str,
                         status: Optional[str] = None,
                         caller: Caller = Depends(require_scopes("campaigns:read"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    items = await ad.list_campaigns_for_advertiser(db, advertiser_id=advertiser_id, status=status)
    return {"items": items, "count": len(items)}


@partner_app.get("/campaigns/{campaign_id}", tags=["campaigns"])
async def get_campaign(campaign_id: str, request: Request, advertiser_id: str,
                       caller: Caller = Depends(require_scopes("campaigns:read"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    camp = await ad.get_campaign(db, advertiser_id=advertiser_id, campaign_id=campaign_id)
    if not camp:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return {"campaign": camp}


class CreativePatch(Creative):
    pass


@partner_app.post("/campaigns/{campaign_id}/creatives", tags=["campaigns"])
async def upload_creative(campaign_id: str, body: CreativePatch, request: Request,
                          advertiser_id: str,
                          caller: Caller = Depends(require_scopes("campaigns:write"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    try:
        camp = await ad.update_campaign(db, advertiser_id=advertiser_id, campaign_id=campaign_id,
                                        patch={"creative": body.model_dump(exclude_none=True)},
                                        user=_svc_user(caller))
    except Exception as e:
        raise _map_error(e)
    return {"campaign": camp}


@partner_app.post("/campaigns/{campaign_id}/submit", tags=["campaigns"])
async def submit_campaign(campaign_id: str, request: Request, advertiser_id: str,
                          caller: Caller = Depends(require_scopes("campaigns:write"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    if caller.is_sandbox:
        return {"campaign_id": campaign_id, "status": "active", "sandbox": True}
    try:
        r = await ad.submit_campaign_for_approval(db, advertiser_id=advertiser_id,
                                                  campaign_id=campaign_id, user=_svc_user(caller))
    except Exception as e:
        raise _map_error(e)
    return r


@partner_app.post("/campaigns/{campaign_id}/pause", tags=["campaigns"])
async def pause_campaign(campaign_id: str, request: Request, advertiser_id: str,
                         caller: Caller = Depends(require_scopes("campaigns:write"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    try:
        return await ad.pause_campaign(db, advertiser_id=advertiser_id,
                                       campaign_id=campaign_id, user=_svc_user(caller))
    except Exception as e:
        raise _map_error(e)


@partner_app.post("/campaigns/{campaign_id}/stop", tags=["campaigns"])
async def stop_campaign(campaign_id: str, request: Request, advertiser_id: str,
                        caller: Caller = Depends(require_scopes("campaigns:write"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    try:
        return await ad.end_campaign(db, advertiser_id=advertiser_id,
                                     campaign_id=campaign_id, user=_svc_user(caller))
    except Exception as e:
        raise _map_error(e)


@partner_app.get("/campaigns/{campaign_id}/report", tags=["reporting"])
async def campaign_report(campaign_id: str, request: Request, advertiser_id: str,
                          caller: Caller = Depends(require_scopes("reports:read"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    camp = await ad.get_campaign(db, advertiser_id=advertiser_id, campaign_id=campaign_id)
    if not camp:
        raise HTTPException(404, {"code": "campaign_not_found"})
    return await ad.campaign_analytics(db, campaign_id=campaign_id)


__all__ = ["partner_app"]
