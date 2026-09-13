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
import time
import uuid
from datetime import timedelta
from typing import Any, Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services import ad1_advertiser_service as ad
from services import ad3_sponsorship_service as pw
from services import trivia_sponsorship_service as tr
from services import rj_sponsored_read_service as rj
from services import partner_api as pa
from services import partner_marketplace as mkt
from services import ad_product_registry as reg
from services import partner_api_ext as ext
from services import partner_creatives as cr
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


@partner_app.middleware("http")
async def _usage_mw(request: Request, call_next):
    """Log each authenticated call for usage analytics + fire webhook events.
    Also stamps every response with the API version + a request id."""
    t0 = time.time()
    request_id = request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:20]}"
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-RadioLife-API-Version"] = reg.API_VERSION
    response.headers["X-Request-ID"] = request_id
    try:
        caller = getattr(request.state, "caller", None)
        if caller is not None:
            db = request.app.state.db
            await pa.log_api_call(db, partner_id=caller.partner_id, environment=caller.environment,
                                  credential_id=caller.credential_id, method=request.method,
                                  path=request.url.path, status=response.status_code,
                                  duration_ms=int((time.time() - t0) * 1000))
            await pa.sweep_webhook_events(db, caller.partner_id, caller.environment)
    except Exception:
        pass
    return response


# ── normalized error envelope (Phase A) ─────────────────────────────
# Every error carries {error:{code,message,field?,request_id}} while ALSO
# keeping the legacy `detail` field for backward compatibility.
def _error_body(request: Request, status_code: int, detail: Any) -> dict:
    code, message, field = None, None, None
    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message")
        field = detail.get("field")
        if not message:
            message = detail.get("error") or detail.get("detail")
    elif isinstance(detail, str):
        message = detail
    code = code or {400: "bad_request", 401: "unauthorized", 403: "forbidden",
                    404: "not_found", 409: "conflict", 422: "unprocessable",
                    429: "rate_limited"}.get(status_code, "error")
    return {
        "detail": detail,
        "error": {"code": code, "message": message or code,
                  "field": field,
                  "request_id": getattr(request.state, "request_id", None)},
    }


@partner_app.exception_handler(HTTPException)
async def _http_exc_handler(request: Request, exc: HTTPException):
    body = _error_body(request, exc.status_code, exc.detail)
    headers = dict(exc.headers or {})
    headers["X-RadioLife-API-Version"] = reg.API_VERSION
    headers["X-Request-ID"] = getattr(request.state, "request_id", "") or ""
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


@partner_app.exception_handler(Exception)
async def _unhandled_exc_handler(request: Request, exc: Exception):
    log.warning("[v1] unhandled error: %s", exc)
    body = _error_body(request, 500, {"code": "internal_error"})
    return JSONResponse(status_code=500, content=body,
                        headers={"X-RadioLife-API-Version": reg.API_VERSION,
                                 "X-Request-ID": getattr(request.state, "request_id", "") or ""})


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


# ══════════════════════════ discovery (Phase A) ═════════════════════
@partner_app.get("/status", tags=["meta"])
async def status_ep():
    """Public, unauthenticated operational status."""
    return {"status": "operational", "api_version": reg.API_VERSION,
            "docs": "/api/v1/docs", "services": {
                "campaigns": "operational", "sponsorships": "operational",
                "marketplace": "operational", "webhooks": "operational"}}


@partner_app.get("/capabilities", tags=["catalog"])
async def capabilities_ep(request: Request,
                          caller: Caller = Depends(require_scopes("catalog:read"))):
    """Dynamic capability discovery — external clients should read this instead
    of hardcoding which products/markets/targeting are available."""
    caps = await reg.capabilities(request.app.state.db, environment=caller.environment)
    caps["scopes"] = pa.SCOPES
    return caps


@partner_app.get("/inventory", tags=["catalog"])
async def inventory_ep(caller: Caller = Depends(require_scopes("catalog:read"))):
    return {"categories": reg.inventory()}


@partner_app.get("/markets", tags=["catalog"])
async def markets_ep(caller: Caller = Depends(require_scopes("catalog:read"))):
    return {"data": reg.markets()}


@partner_app.get("/targeting/options", tags=["catalog"])
async def targeting_options_ep(caller: Caller = Depends(require_scopes("catalog:read"))):
    return {"data": reg.TARGETING_OPTIONS}


@partner_app.get("/rate-card", tags=["catalog"])
async def rate_card_ep(caller: Caller = Depends(require_scopes("catalog:read"))):
    return reg.RATE_CARD


@partner_app.get("/stations", tags=["catalog"])
async def stations_ep(request: Request,
                      market: Optional[str] = None,
                      country: Optional[str] = None,
                      genre: Optional[str] = None,
                      language: Optional[str] = None,
                      station_type: Optional[str] = None,
                      flagship: Optional[bool] = None,
                      q: Optional[str] = None,
                      cursor: Optional[str] = None,
                      limit: int = 50,
                      caller: Caller = Depends(require_scopes("catalog:read"))):
    """Cursor-paginated station directory. `station_type=radiolife` returns the
    RadioLife AI stations; otherwise the imported live-radio directory."""
    db = request.app.state.db
    limit = max(1, min(int(limit), 100))

    if station_type == "radiolife":
        query: dict = {"active": True}
        if market:
            query["market"] = market
        rows = await db.channels.find(query).sort("_id", 1).to_list(200)
        data = [{"station_id": c["_id"], "name": c.get("name"),
                 "station_type": "radiolife", "market": c.get("market"),
                 "genre": c.get("music_genre"), "language": c.get("language_mix"),
                 "premium": bool(c.get("premium_only")),
                 "artwork": c.get("cover_image_url")} for c in rows]
        return {"data": data, "next_cursor": None, "has_more": False}

    query = {"active": True}
    if country:
        query["country_code"] = country.upper()
    if language:
        query["language"] = {"$regex": language, "$options": "i"}
    if genre:
        query["music_genre"] = {"$regex": genre, "$options": "i"}
    if flagship is not None:
        query["is_flagship"] = bool(flagship)
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    if cursor:
        try:
            from bson import ObjectId
            query["_id"] = {"$gt": ObjectId(cursor)}
        except Exception:
            raise HTTPException(400, {"code": "invalid_cursor"})

    rows = await db.imported_radio_stations.find(query).sort("_id", 1).to_list(limit + 1)
    has_more = len(rows) > limit
    rows = rows[:limit]
    data = [{"station_id": r.get("id") or str(r.get("_id")),
             "name": r.get("name"), "station_type": "live_radio",
             "country": r.get("country"), "country_code": r.get("country_code"),
             "city": r.get("city"), "genre": r.get("music_genre"),
             "language": r.get("language"), "flagship": bool(r.get("is_flagship")),
             "artwork": r.get("favicon"), "frequency": r.get("frequency")}
            for r in rows]
    next_cursor = str(rows[-1]["_id"]) if (has_more and rows) else None
    return {"data": data, "next_cursor": next_cursor, "has_more": has_more}


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
    external_id: Optional[str] = Field(None, description="Your own id for this advertiser (de-dupes retries)")


@partner_app.post("/advertisers", tags=["advertisers"], status_code=201)
async def create_advertiser(body: AdvertiserCreate, request: Request,
                            caller: Caller = Depends(require_scopes("advertisers:write"))):
    db = request.app.state.db
    idem = request.headers.get("Idempotency-Key")
    cached = await ext.idem_get(db, caller, "create_advertiser", idem)
    if cached is not None:
        return cached
    dup = await ext.external_get(db, caller, "advertiser", body.external_id)
    if dup is not None:
        await ext.idem_save(db, caller, "create_advertiser", idem, dup)
        return dup
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
    result = {"advertiser": adv, "external_id": body.external_id,
              "environment": caller.environment}
    await ext.external_save(db, caller, "advertiser", body.external_id, aid, result)
    await ext.idem_save(db, caller, "create_advertiser", idem, result)
    return result


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


class LineItem(BaseModel):
    type: str = Field(..., description="Product key (e.g. audio_preroll, display_banner, sponsored_game)")
    creative_ids: list[str] = []
    name: Optional[str] = None
    budget_total_cents: Optional[int] = None
    pricing_model: Optional[str] = None
    cpm_bid_cents: Optional[int] = None
    cpc_bid_cents: Optional[int] = None
    targeting: Optional[Targeting] = None
    sponsored_game_campaign_id: Optional[str] = None


class CampaignCreate(BaseModel):
    advertiser_id: str
    product: Optional[str] = Field(None, description="Product key from GET /products (single-format). Omit when using line_items.")
    name: str
    budget_total_cents: int = Field(..., ge=1)
    pricing_model: str = "cpm"
    cpm_bid_cents: Optional[int] = None
    cpc_bid_cents: Optional[int] = None
    daily_cap_cents: Optional[int] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    objective: Optional[str] = None
    targeting: Targeting = Field(default_factory=Targeting)
    creative: Creative = Field(default_factory=Creative)
    line_items: Optional[list[LineItem]] = Field(None, description="Multi-format: one parent campaign holding several media line items.")
    external_id: Optional[str] = Field(None, description="Your own id for this campaign (de-dupes retries)")


class QuoteRequest(BaseModel):
    product: str
    pricing_model: str = "cpm"
    market: Optional[str] = None
    budget_cents: int = Field(0, ge=0)
    targeting_dimensions: int = Field(0, ge=0)
    daypart: Optional[str] = None
    premium: bool = False


@partner_app.post("/quotes", tags=["catalog"])
async def create_quote(body: QuoteRequest, request: Request,
                       caller: Caller = Depends(require_scopes("catalog:read"))):
    """Server-authoritative pricing estimate. External systems cannot submit
    arbitrary low prices — the rate card remains the source of truth."""
    db = request.app.state.db
    idem = request.headers.get("Idempotency-Key")
    cached = await ext.idem_get(db, caller, "create_quote", idem)
    if cached is not None:
        return cached
    try:
        q = reg.compute_quote(
            product=body.product, pricing_model=body.pricing_model, market=body.market,
            budget_cents=body.budget_cents, targeting_dimensions=body.targeting_dimensions,
            daypart=body.daypart, premium=body.premium)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    now = pa._now()
    quote_id = "qte_" + uuid.uuid4().hex[:16]
    expires_at = now + timedelta(hours=24)
    q.update({"quote_id": quote_id, "environment": caller.environment,
              "created_at": now.isoformat()})
    await db.api_quotes.insert_one({"_id": quote_id, "partner_id": caller.partner_id,
                                    "environment": caller.environment,
                                    "expires_at": expires_at, **q})
    q["expires_at"] = expires_at.isoformat()
    await ext.idem_save(db, caller, "create_quote", idem, q)
    return q


async def _create_multiformat(db, caller: Caller, body: "CampaignCreate", adv: dict) -> dict:
    """Create a parent campaign container plus one underlying campaign per line
    item, reusing the existing ad engine for each bookable media type."""
    parent_id = "pcmp_" + uuid.uuid4().hex[:18]
    now = pa._now()
    n = len(body.line_items)
    default_budget = max(1, int(body.budget_total_cents // n)) if body.budget_total_cents else None
    line_docs = []
    for li in body.line_items:
        li_id = "cli_" + uuid.uuid4().hex[:16]
        prod = pa.product_by_key(li.type)
        rec = {"_id": li_id, "line_item_id": li_id, "parent_id": parent_id,
               "partner_id": caller.partner_id, "environment": caller.environment,
               "type": li.type, "creative_ids": li.creative_ids,
               "name": li.name or f"{body.name} · {li.type}",
               "budget_total_cents": li.budget_total_cents or default_budget,
               "underlying_campaign_id": None, "status": "pending",
               "error": None, "created_at": now, "updated_at": now}
        if not prod or not prod.get("bookable") or not prod.get("campaign_type"):
            rec["status"] = "unsupported"
            rec["error"] = {"code": "product_not_bookable_via_api", "status": (prod or {}).get("status")}
            await db.campaign_line_items.insert_one(rec)
            line_docs.append(rec)
            continue
        # resolve first library creative → engine creative payload
        creative: dict = {}
        if li.creative_ids:
            crv = await db.creative_assets.find_one(
                {"creative_id": li.creative_ids[0], "partner_id": caller.partner_id,
                 "environment": caller.environment})
            if crv:
                creative = _creative_to_payload(crv)
        if li.sponsored_game_campaign_id:
            creative["sponsored_game_campaign_id"] = li.sponsored_game_campaign_id
        payload = {
            "campaign_type": prod["campaign_type"], "name": rec["name"],
            "budget_total_cents": rec["budget_total_cents"] or 1,
            "pricing_model": li.pricing_model or body.pricing_model or "cpm",
            "cpm_bid_cents": li.cpm_bid_cents if li.cpm_bid_cents is not None else body.cpm_bid_cents,
            "cpc_bid_cents": li.cpc_bid_cents if li.cpc_bid_cents is not None else body.cpc_bid_cents,
            "start_at": body.start_at, "end_at": body.end_at,
            "targeting": (li.targeting or body.targeting).model_dump(),
            "creative": creative, "parent_campaign_id": parent_id,
        }
        try:
            camp = await ad.create_campaign(db, advertiser_id=body.advertiser_id,
                                            payload=payload, user=_svc_user(caller))
            cid = camp["campaign_id"]
            if caller.is_sandbox:
                await db.ad_campaigns_v2.update_one(
                    {"campaign_id": cid},
                    {"$set": {"status": "active", "approved_at": now,
                              "approved_by": "sandbox", "parent_campaign_id": parent_id,
                              "updated_at": now}})
            else:
                await db.ad_campaigns_v2.update_one(
                    {"campaign_id": cid}, {"$set": {"parent_campaign_id": parent_id}})
            rec["underlying_campaign_id"] = cid
            rec["status"] = "active" if caller.is_sandbox else "draft"
        except Exception as e:  # partial success — one bad line item shouldn't sink the campaign
            rec["status"] = "error"
            rec["error"] = {"code": "line_item_create_failed", "message": str(e)}
        await db.campaign_line_items.insert_one(rec)
        line_docs.append(rec)

    created = sum(1 for r in line_docs if r["underlying_campaign_id"])
    parent = {"_id": parent_id, "parent_id": parent_id, "partner_id": caller.partner_id,
              "environment": caller.environment, "advertiser_id": body.advertiser_id,
              "name": body.name, "objective": body.objective,
              "budget_total_cents": body.budget_total_cents,
              "start_at": body.start_at, "end_at": body.end_at,
              "line_item_ids": [r["line_item_id"] for r in line_docs],
              "status": "active" if (caller.is_sandbox and created) else "draft",
              "created_at": now, "updated_at": now}
    await db.api_parent_campaigns.insert_one(parent)
    return {"parent_campaign_id": parent_id, "multi_format": True,
            "status": parent["status"], "objective": body.objective,
            "external_id": body.external_id, "environment": caller.environment,
            "line_items": [cr._clean(r) for r in line_docs]}


@partner_app.post("/campaigns", tags=["campaigns"], status_code=201)
async def create_campaign(body: CampaignCreate, request: Request,
                          caller: Caller = Depends(require_scopes("campaigns:write"))):
    db = request.app.state.db
    idem = request.headers.get("Idempotency-Key")
    cached = await ext.idem_get(db, caller, "create_campaign", idem)
    if cached is not None:
        return cached
    dup = await ext.external_get(db, caller, "campaign", body.external_id)
    if dup is not None:
        await ext.idem_save(db, caller, "create_campaign", idem, dup)
        return dup
    adv = await _assert_adv(db, caller, body.advertiser_id)
    if adv.get("status") != "active":
        raise HTTPException(409, {"code": "advertiser_not_active", "status": adv.get("status")})

    # ── Multi-format: one parent campaign holding several media line items ──
    if body.line_items:
        result = await _create_multiformat(db, caller, body, adv)
        if body.external_id:
            await ext.external_save(db, caller, "campaign", body.external_id,
                                    result["parent_campaign_id"], result)
        await ext.idem_save(db, caller, "create_campaign", idem, result)
        return result

    if not body.product:
        raise HTTPException(400, {"code": "product_required",
                                  "message": "provide `product` (single-format) or `line_items` (multi-format)"})
    prod = pa.product_by_key(body.product)
    if not prod:
        raise HTTPException(400, {"code": "unknown_product", "product": body.product})
    if not prod.get("bookable") or not prod.get("campaign_type"):
        raise HTTPException(409, {"code": "product_not_bookable_via_api",
                                  "product": body.product, "status": prod.get("status"),
                                  "hint": "Contact RadioLife to onboard this product."})
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
    result = {"campaign": camp, "product": body.product,
              "external_id": body.external_id, "environment": caller.environment}
    await ext.external_save(db, caller, "campaign", body.external_id, cid, result)
    await ext.idem_save(db, caller, "create_campaign", idem, result)
    return result


@partner_app.get("/campaigns", tags=["campaigns"])
async def list_campaigns(request: Request, advertiser_id: str,
                         status: Optional[str] = None,
                         external_id: Optional[str] = None,
                         cursor: Optional[str] = None, limit: int = 50,
                         caller: Caller = Depends(require_scopes("campaigns:read"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    items = await ad.list_campaigns_for_advertiser(db, advertiser_id=advertiser_id, status=status)
    if external_id:
        internal_id = await ext.external_lookup_id(db, caller, "campaign", external_id)
        items = [c for c in items if c.get("campaign_id") == internal_id]
    try:
        page = ext.paginate(items, cursor, limit)
    except ValueError:
        raise HTTPException(400, {"code": "invalid_cursor"})
    return {"items": page["data"], "count": page["count"],
            "data": page["data"], "next_cursor": page["next_cursor"],
            "has_more": page["has_more"]}


@partner_app.get("/campaigns/{parent_id}/line-items", tags=["campaigns"])
async def list_line_items(parent_id: str, request: Request,
                          caller: Caller = Depends(require_scopes("campaigns:read"))):
    db = request.app.state.db
    parent = await db.api_parent_campaigns.find_one(
        {"parent_id": parent_id, "partner_id": caller.partner_id,
         "environment": caller.environment})
    if not parent:
        raise HTTPException(404, {"code": "parent_campaign_not_found"})
    items = [cr._clean(x) async for x in
             db.campaign_line_items.find({"parent_id": parent_id}).sort("created_at", 1)]
    return {"parent_campaign_id": parent_id, "parent": cr._clean(parent),
            "line_items": items, "count": len(items)}



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


# ══════════════════════════ creative library (Phase C) ═════════════
def _creative_to_payload(crv: dict) -> dict:
    """Map a library creative to the underlying engine's creative dict."""
    t = crv.get("type")
    p: dict = {"headline": crv.get("name"), "click_url": crv.get("click_url")}
    if t == "image":
        p["image_url"] = crv.get("asset_url")
    elif t == "audio":
        p["audio_url"] = crv.get("asset_url")
    else:  # video / html — best-effort thumbnail slot
        p["image_url"] = crv.get("asset_url")
    return {k: v for k, v in p.items() if v is not None}


class CreativeCreate(BaseModel):
    type: str = Field(..., description="audio | image | video | html")
    name: Optional[str] = None
    asset_url: Optional[str] = None
    mime: Optional[str] = None
    size_bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    click_url: Optional[str] = None
    advertiser_id: Optional[str] = None
    external_id: Optional[str] = None


class UploadUrlBody(BaseModel):
    type: str
    filename: str
    content_type: str
    advertiser_id: Optional[str] = None


class ImportBody(BaseModel):
    type: str
    url: str
    name: Optional[str] = None
    click_url: Optional[str] = None
    advertiser_id: Optional[str] = None
    external_id: Optional[str] = None


class CreativePatchBody(BaseModel):
    name: Optional[str] = None
    click_url: Optional[str] = None
    status: Optional[str] = None


def _asset_key(caller: Caller, creative_id: str, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"creatives/{caller.partner_id}/{caller.environment.lower()}/{creative_id}.{ext}"


@partner_app.post("/creatives", tags=["creatives"], status_code=201)
async def create_creative(body: CreativeCreate, request: Request,
                          caller: Caller = Depends(require_scopes("creatives:write"))):
    db = request.app.state.db
    idem = request.headers.get("Idempotency-Key")
    cached = await ext.idem_get(db, caller, "create_creative", idem)
    if cached is not None:
        return cached
    dup = await ext.external_get(db, caller, "creative", body.external_id)
    if dup is not None:
        await ext.idem_save(db, caller, "create_creative", idem, dup)
        return dup
    err = cr.validate_metadata(body.type, size_bytes=body.size_bytes, mime=body.mime,
                               duration_seconds=body.duration_seconds)
    if err:
        raise HTTPException(400, err)
    cid = cr._cid()
    now = cr._now()
    status = "ready" if body.asset_url else "processing"
    doc = {"_id": cid, "creative_id": cid, "partner_id": caller.partner_id,
           "environment": caller.environment, "advertiser_id": body.advertiser_id,
           "type": body.type, "name": body.name, "status": status,
           "asset_url": body.asset_url, "asset_key": None, "mime": body.mime,
           "size_bytes": body.size_bytes, "width": body.width, "height": body.height,
           "duration_seconds": body.duration_seconds, "click_url": body.click_url,
           "external_id": body.external_id, "created_at": now, "updated_at": now}
    await db.creative_assets.insert_one(doc)
    result = {"creative": cr._clean(doc)}
    await ext.external_save(db, caller, "creative", body.external_id, cid, result)
    await ext.idem_save(db, caller, "create_creative", idem, result)
    return result


@partner_app.post("/creatives/upload-url", tags=["creatives"], status_code=201)
async def creative_upload_url(body: UploadUrlBody, request: Request,
                              caller: Caller = Depends(require_scopes("creatives:write"))):
    db = request.app.state.db
    err = cr.validate_metadata(body.type, mime=body.content_type, filename=body.filename)
    if err:
        raise HTTPException(400, err)
    cid = cr._cid()
    now = cr._now()
    key = _asset_key(caller, cid, body.filename)
    try:
        signed = cr.signed_upload(key, body.content_type)
    except Exception as e:
        raise HTTPException(502, {"code": "upload_url_unavailable", "message": str(e)})
    doc = {"_id": cid, "creative_id": cid, "partner_id": caller.partner_id,
           "environment": caller.environment, "advertiser_id": body.advertiser_id,
           "type": body.type, "name": body.filename, "status": "uploading",
           "asset_url": None, "asset_key": key, "mime": body.content_type,
           "size_bytes": None, "click_url": None, "external_id": None,
           "created_at": now, "updated_at": now}
    await db.creative_assets.insert_one(doc)
    return {"creative_id": cid, "asset_key": key, "expires_in": cr.UPLOAD_URL_TTL,
            "finalize_url": f"/api/v1/creatives/{cid}/finalize", **signed}


@partner_app.post("/creatives/{creative_id}/finalize", tags=["creatives"])
async def finalize_creative(creative_id: str, request: Request,
                            caller: Caller = Depends(require_scopes("creatives:write"))):
    db = request.app.state.db
    crv = await db.creative_assets.find_one({"creative_id": creative_id,
                                             "partner_id": caller.partner_id,
                                             "environment": caller.environment})
    if not crv:
        raise HTTPException(404, {"code": "creative_not_found"})
    key = crv.get("asset_key")
    if not key:
        raise HTTPException(409, {"code": "no_asset_key", "message": "creative was not created via upload-url"})
    from services.object_storage import get_storage
    try:
        head = get_storage().head(key=key)
    except Exception:
        head = None
    if not head:
        # Object not uploaded yet — leave status 'uploading' so the client can retry.
        raise HTTPException(409, {"code": "asset_not_found", "message": "no object uploaded to the signed URL yet"})
    err = cr.validate_metadata(crv["type"], size_bytes=head.get("size"),
                               mime=head.get("content_type"))
    if err:
        await db.creative_assets.update_one({"creative_id": creative_id},
            {"$set": {"status": "rejected", "reject_reason": err, "updated_at": cr._now()}})
        raise HTTPException(400, err)
    try:
        asset_url = get_storage().get_signed_url(key=key, expires_in=7 * 24 * 3600)
    except Exception:
        asset_url = f"/api/storage/local/{key}"
    await db.creative_assets.update_one({"creative_id": creative_id},
        {"$set": {"status": "ready", "asset_url": asset_url,
                  "size_bytes": head.get("size"), "mime": head.get("content_type"),
                  "updated_at": cr._now()}})
    return {"creative": cr._clean(await db.creative_assets.find_one({"creative_id": creative_id}))}


@partner_app.post("/creatives/import", tags=["creatives"], status_code=201)
async def import_creative(body: ImportBody, request: Request,
                          caller: Caller = Depends(require_scopes("creatives:write"))):
    db = request.app.state.db
    idem = request.headers.get("Idempotency-Key")
    cached = await ext.idem_get(db, caller, "import_creative", idem)
    if cached is not None:
        return cached
    if body.type not in cr.CREATIVE_TYPES:
        raise HTTPException(400, {"code": "invalid_creative_type"})
    try:
        cr.assert_safe_url(body.url)
    except ValueError as e:
        raise HTTPException(400, {"code": str(e)})
    import httpx
    rule = cr.RULES[body.type]
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            resp = await client.get(body.url)
    except Exception as e:
        raise HTTPException(400, {"code": "import_fetch_failed", "message": str(e)})
    if resp.status_code != 200:
        raise HTTPException(400, {"code": "import_fetch_failed", "message": f"status {resp.status_code}"})
    data = resp.content
    if len(data) > rule["max_bytes"]:
        raise HTTPException(400, {"code": "file_too_large"})
    mime = resp.headers.get("content-type", "").split(";")[0].strip()
    err = cr.validate_metadata(body.type, size_bytes=len(data), mime=mime or None)
    if err:
        raise HTTPException(400, err)
    cid = cr._cid()
    ext_map = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp",
               "audio/mpeg": "mp3", "audio/mp3": "mp3", "video/mp4": "mp4", "text/html": "html"}
    key = f"creatives/{caller.partner_id}/{caller.environment.lower()}/{cid}.{ext_map.get(mime, 'bin')}"
    from services.object_storage import get_storage
    try:
        get_storage().upload_bytes(key=key, data=data, content_type=mime or "application/octet-stream")
        asset_url = get_storage().get_signed_url(key=key, expires_in=7 * 24 * 3600)
    except Exception as e:
        raise HTTPException(502, {"code": "storage_write_failed", "message": str(e)})
    now = cr._now()
    doc = {"_id": cid, "creative_id": cid, "partner_id": caller.partner_id,
           "environment": caller.environment, "advertiser_id": body.advertiser_id,
           "type": body.type, "name": body.name, "status": "ready",
           "asset_url": asset_url, "asset_key": key, "mime": mime,
           "size_bytes": len(data), "click_url": body.click_url,
           "external_id": body.external_id, "created_at": now, "updated_at": now}
    await db.creative_assets.insert_one(doc)
    result = {"creative": cr._clean(doc)}
    await ext.external_save(db, caller, "creative", body.external_id, cid, result)
    await ext.idem_save(db, caller, "import_creative", idem, result)
    return result


@partner_app.get("/creatives", tags=["creatives"])
async def list_creatives(request: Request, type: Optional[str] = None,
                         status: Optional[str] = None, advertiser_id: Optional[str] = None,
                         external_id: Optional[str] = None,
                         cursor: Optional[str] = None, limit: int = 50,
                         caller: Caller = Depends(require_scopes("creatives:read"))):
    db = request.app.state.db
    q = {"partner_id": caller.partner_id, "environment": caller.environment}
    if type:
        q["type"] = type
    if status:
        q["status"] = status
    if advertiser_id:
        q["advertiser_id"] = advertiser_id
    if external_id:
        q["external_id"] = external_id
    items = [cr._clean(x) async for x in
             db.creative_assets.find(q).sort("created_at", -1).limit(500)]
    try:
        page = ext.paginate(items, cursor, limit)
    except ValueError:
        raise HTTPException(400, {"code": "invalid_cursor"})
    return {"data": page["data"], "count": page["count"],
            "next_cursor": page["next_cursor"], "has_more": page["has_more"]}


@partner_app.get("/creatives/{creative_id}", tags=["creatives"])
async def get_creative(creative_id: str, request: Request,
                       caller: Caller = Depends(require_scopes("creatives:read"))):
    db = request.app.state.db
    crv = await db.creative_assets.find_one({"creative_id": creative_id,
                                             "partner_id": caller.partner_id,
                                             "environment": caller.environment})
    if not crv:
        raise HTTPException(404, {"code": "creative_not_found"})
    return {"creative": cr._clean(crv)}


@partner_app.patch("/creatives/{creative_id}", tags=["creatives"])
async def patch_creative(creative_id: str, body: CreativePatchBody, request: Request,
                         caller: Caller = Depends(require_scopes("creatives:write"))):
    db = request.app.state.db
    patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    if "status" in patch and patch["status"] not in cr.CREATIVE_STATUSES:
        raise HTTPException(400, {"code": "invalid_status"})
    if not patch:
        raise HTTPException(400, {"code": "empty_patch"})
    patch["updated_at"] = cr._now()
    r = await db.creative_assets.update_one(
        {"creative_id": creative_id, "partner_id": caller.partner_id,
         "environment": caller.environment}, {"$set": patch})
    if r.matched_count == 0:
        raise HTTPException(404, {"code": "creative_not_found"})
    return {"creative": cr._clean(await db.creative_assets.find_one({"creative_id": creative_id}))}


@partner_app.delete("/creatives/{creative_id}", tags=["creatives"])
async def delete_creative(creative_id: str, request: Request,
                          caller: Caller = Depends(require_scopes("creatives:write"))):
    db = request.app.state.db
    r = await db.creative_assets.update_one(
        {"creative_id": creative_id, "partner_id": caller.partner_id,
         "environment": caller.environment},
        {"$set": {"status": "deleted", "updated_at": cr._now()}})
    if r.matched_count == 0:
        raise HTTPException(404, {"code": "creative_not_found"})
    return {"deleted": True, "creative_id": creative_id}



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


# ══════════════════════════ sponsorships ════════════════════════════
# type -> (collection, id field, owner field, active status)
_SP = {
    "predict_win": ("predict_win_sponsorships", "sponsorship_id", "advertiser_id", "live"),
    "trivia": ("trivia_sponsorships", "id", "advertiser_business_id", "active"),
    "rj_read": ("rj_sponsored_reads", "id", "advertiser_business_id", "active"),
}


def _sp_clean(d: Optional[dict]) -> Optional[dict]:
    if not d:
        return d
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in d.items() if k != "_id"}


async def _sandbox_activate(db, t: str, sid: str) -> None:
    coll, idf, _owner, active = _SP[t]
    sets = {"status": active, "updated_at": pa._now()}
    if t == "predict_win":
        sets["approval_status"] = "approved"
    else:
        sets["activated_at"] = pa._now()
    await db[coll].update_one({idf: sid}, {"$set": sets})


async def _sp_fetch(db, t: str, sid: str) -> Optional[dict]:
    coll, idf, _o, _a = _SP[t]
    return _sp_clean(await db[coll].find_one({idf: sid}))


async def _assert_sp(db, caller: Caller, t: str, sid: str) -> dict:
    if t not in _SP:
        raise HTTPException(400, {"code": "unknown_sponsorship_type"})
    coll, idf, owner, _a = _SP[t]
    d = await db[coll].find_one({idf: sid})
    if not d:
        raise HTTPException(404, {"code": "sponsorship_not_found"})
    await _assert_adv(db, caller, d.get(owner))  # 404 unless owned by caller
    return d


class SponsorshipCreate(BaseModel):
    type: str = Field(..., description="predict_win | trivia | rj_read")
    advertiser_id: str
    display_name: Optional[str] = None
    tagline: Optional[str] = None
    logo_url: Optional[str] = None
    budget_cents: Optional[int] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    # predict_win
    parent_campaign_id: Optional[str] = None
    brand_name: Optional[str] = None
    brand_asset_url: Optional[str] = None
    pricing_model: Optional[str] = None
    cpe_cents: Optional[int] = None
    cpi_cents: Optional[int] = None
    daily_cap_cents: Optional[int] = None
    # trivia
    sponsor_target_type: Optional[str] = None
    target_id: Optional[str] = None
    prize_pool: Optional[list] = None
    winner_selection: Optional[str] = None
    score_threshold: Optional[int] = None
    # rj_read
    persona_id: Optional[str] = None
    station_ids: Optional[list] = None
    any_station: Optional[bool] = None
    disclosure_prefix: Optional[str] = None
    plays_target: Optional[int] = None
    cost_per_play_cents: Optional[int] = None
    script_body: Optional[str] = None
    product_name: Optional[str] = None
    key_message: Optional[str] = None
    cta: Optional[str] = None
    external_id: Optional[str] = Field(None, description="Your own id for this sponsorship (de-dupes retries)")


@partner_app.get("/sponsorships/inventory", tags=["sponsorships"])
async def sponsorship_inventory(request: Request, type: str,
                                caller: Caller = Depends(require_scopes("catalog:read"))):
    db = request.app.state.db
    if type == "predict_win":
        return await pw.available_parent_campaigns(db, limit=50)
    if type == "trivia":
        cats = [{"id": c.get("id"), "name": c.get("name")}
                async for c in db.trivia_categories.find({}, {"id": 1, "name": 1}).limit(100)]
        return {"target_types": list(tr.TARGET_TYPES), "selection_modes": list(tr.SELECTION_MODES),
                "categories": cats, "platform_fee_pct": tr.PLATFORM_FEE_PCT}
    if type == "rj_read":
        personas = [{"id": p.get("id"), "name": p.get("name")}
                    async for p in db.rj_personas.find({"status": "active"}, {"id": 1, "name": 1}).limit(50)]
        return {"personas": personas, "disclosure_prefixes": list(rj.DISCLOSURE_PREFIXES),
                "any_station_supported": True}
    raise HTTPException(400, {"code": "unknown_sponsorship_type"})


@partner_app.post("/sponsorships", tags=["sponsorships"], status_code=201)
async def create_sponsorship(body: SponsorshipCreate, request: Request,
                             caller: Caller = Depends(require_scopes("campaigns:write"))):
    db = request.app.state.db
    idem = request.headers.get("Idempotency-Key")
    cached = await ext.idem_get(db, caller, "create_sponsorship", idem)
    if cached is not None:
        return cached
    dup = await ext.external_get(db, caller, "sponsorship", body.external_id)
    if dup is not None:
        await ext.idem_save(db, caller, "create_sponsorship", idem, dup)
        return dup
    await _assert_adv(db, caller, body.advertiser_id)
    t, owner = body.type, caller.owner_id
    try:
        if t == "predict_win":
            payload = {"parent_campaign_id": body.parent_campaign_id, "brand_name": body.brand_name,
                       "brand_asset_url": body.brand_asset_url, "tagline": body.tagline,
                       "pricing_model": body.pricing_model, "cpe_cents": body.cpe_cents,
                       "cpi_cents": body.cpi_cents, "budget_cents": body.budget_cents,
                       "daily_cap_cents": body.daily_cap_cents,
                       "start_time": body.start_at, "end_time": body.end_at}
            res = await pw.create_sponsorship(db, advertiser_id=body.advertiser_id, submitted_by=owner, payload=payload)
            sid = res.get("sponsorship_id")
        elif t == "trivia":
            tbody = {"sponsor_target_type": body.sponsor_target_type or "any", "target_id": body.target_id,
                     "prize_pool": body.prize_pool or [], "winner_selection": body.winner_selection or "top_n",
                     "score_threshold": body.score_threshold, "display_name": body.display_name,
                     "tagline": body.tagline, "logo_url": body.logo_url,
                     "start_at": body.start_at, "end_at": body.end_at}
            res = await tr.create_sponsorship(db, advertiser_business_id=body.advertiser_id, body=tbody, user_id=owner)
            sid = res.get("id") or res.get("sponsorship_id")
        elif t == "rj_read":
            rbody = {"persona_id": body.persona_id, "station_ids": body.station_ids or [],
                     "any_station": bool(body.any_station), "disclosure_prefix": body.disclosure_prefix,
                     "plays_target": body.plays_target, "cost_per_play_cents": body.cost_per_play_cents,
                     "script_body": body.script_body or "", "product_name": body.product_name,
                     "key_message": body.key_message, "cta": body.cta,
                     "start_at": body.start_at, "end_at": body.end_at}
            res = await rj.create_sponsored_read(db, advertiser_business_id=body.advertiser_id, body=rbody, user_id=owner)
            sid = res.get("id") or res.get("sponsored_read_id")
        else:
            raise HTTPException(400, {"code": "unknown_sponsorship_type"})
    except HTTPException:
        raise
    except Exception as e:
        raise _map_error(e)
    if caller.is_sandbox and sid:
        await _sandbox_activate(db, t, sid)
        res = await _sp_fetch(db, t, sid)
    result = {"sponsorship": res, "type": t, "external_id": body.external_id,
              "environment": caller.environment}
    if sid:
        await ext.external_save(db, caller, "sponsorship", body.external_id, sid, result)
    await ext.idem_save(db, caller, "create_sponsorship", idem, result)
    return result


@partner_app.get("/sponsorships", tags=["sponsorships"])
async def list_sponsorships(request: Request, type: str, advertiser_id: str,
                            external_id: Optional[str] = None,
                            cursor: Optional[str] = None, limit: int = 50,
                            caller: Caller = Depends(require_scopes("campaigns:read"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    if type not in _SP:
        raise HTTPException(400, {"code": "unknown_sponsorship_type"})
    coll, _idf, owner, _a = _SP[type]
    items = [_sp_clean(x) async for x in db[coll].find({owner: advertiser_id}).sort("created_at", -1).limit(500)]
    if external_id:
        internal_id = await ext.external_lookup_id(db, caller, "sponsorship", external_id)
        items = [s for s in items if (s.get("id") or s.get("sponsorship_id")) == internal_id]
    try:
        page = ext.paginate(items, cursor, limit)
    except ValueError:
        raise HTTPException(400, {"code": "invalid_cursor"})
    return {"items": page["data"], "count": page["count"],
            "data": page["data"], "next_cursor": page["next_cursor"],
            "has_more": page["has_more"]}


@partner_app.get("/sponsorships/{sponsorship_id}", tags=["sponsorships"])
async def get_sponsorship_ep(sponsorship_id: str, request: Request, type: str, advertiser_id: str,
                             caller: Caller = Depends(require_scopes("campaigns:read"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    d = await _assert_sp(db, caller, type, sponsorship_id)
    return {"sponsorship": _sp_clean(d)}


class SponsorshipSubmitBody(BaseModel):
    final_script: Optional[str] = None


class SponsorshipCheckoutBody(BaseModel):
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@partner_app.post("/sponsorships/{sponsorship_id}/submit", tags=["sponsorships"])
async def submit_sponsorship(sponsorship_id: str, request: Request, type: str, advertiser_id: str,
                             body: SponsorshipSubmitBody = SponsorshipSubmitBody(),
                             caller: Caller = Depends(require_scopes("campaigns:write"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    d = await _assert_sp(db, caller, type, sponsorship_id)
    if caller.is_sandbox:
        return {"sponsorship_id": sponsorship_id, "status": "active", "sandbox": True}
    try:
        if type == "predict_win":
            return await pw.publish_sponsorship(db, sponsorship_id=sponsorship_id)
        if type == "trivia":
            # Trivia goes live via hosted Checkout (prize-pool payment).
            raise HTTPException(409, {"code": "use_checkout_endpoint",
                                      "hint": f"POST /api/v1/sponsorships/{sponsorship_id}/checkout?type=trivia&advertiser_id={advertiser_id}"})
        if type == "rj_read":
            # Finalize the copy (disclosure + moderation). Payment happens
            # next via POST /sponsorships/{id}/checkout.
            final_script = (body.final_script or d.get("script_body") or "").strip()
            return await rj.submit_sponsored_read(
                db, sponsored_read_id=sponsorship_id,
                advertiser_business_id=advertiser_id, final_script=final_script)
    except HTTPException:
        raise
    except Exception as e:
        raise _map_error(e)
    raise HTTPException(400, {"code": "unknown_sponsorship_type"})


@partner_app.post("/sponsorships/{sponsorship_id}/checkout", tags=["sponsorships"])
async def sponsorship_checkout(sponsorship_id: str, request: Request, type: str, advertiser_id: str,
                               body: SponsorshipCheckoutBody = SponsorshipCheckoutBody(),
                               caller: Caller = Depends(require_scopes("campaigns:write"))):
    """Create a Stripe HOSTED Checkout session to fund a LIVE sponsorship
    (trivia prize pool / AI-RJ read booking). Returns `checkout_url` for the
    partner to open. Poll `/checkout/status` to confirm payment + activation.
    Sandbox sponsorships activate on create — no payment needed."""
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    await _assert_sp(db, caller, type, sponsorship_id)
    if type not in ("trivia", "rj_read"):
        raise HTTPException(400, {"code": "checkout_not_supported_for_type",
                                  "hint": "Hosted Checkout is available for trivia and rj_read."})
    if caller.is_sandbox:
        return {"sandbox": True, "checkout_required": False, "status": "active",
                "type": type, "sponsorship_id": sponsorship_id,
                "message": "Sandbox sponsorships activate on create — no payment needed."}
    try:
        if type == "trivia":
            r = await tr.create_checkout(db, sponsorship_id=sponsorship_id,
                                         advertiser_business_id=advertiser_id,
                                         success_url=body.success_url, cancel_url=body.cancel_url)
        else:
            r = await rj.create_checkout(db, sponsored_read_id=sponsorship_id,
                                         advertiser_business_id=advertiser_id,
                                         success_url=body.success_url, cancel_url=body.cancel_url)
    except Exception as e:
        raise _map_error(e)
    return {**r, "type": type, "sponsorship_id": sponsorship_id}


@partner_app.get("/sponsorships/{sponsorship_id}/checkout/status", tags=["sponsorships"])
async def sponsorship_checkout_status(sponsorship_id: str, request: Request, type: str, advertiser_id: str,
                                      caller: Caller = Depends(require_scopes("campaigns:read"))):
    """Sync the Stripe Checkout payment and activate the sponsorship when
    paid. Idempotent — safe to poll. For rj_read this also TTS-renders the
    read after payment clears (may briefly return `processing: true`)."""
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    await _assert_sp(db, caller, type, sponsorship_id)
    if type not in ("trivia", "rj_read"):
        raise HTTPException(400, {"code": "checkout_not_supported_for_type"})
    if caller.is_sandbox:
        d = await _sp_fetch(db, type, sponsorship_id)
        return {"paid": True, "sandbox": True, "status": (d or {}).get("status"),
                "type": type, "sponsorship": d}
    try:
        if type == "trivia":
            r = await tr.sync_checkout(db, sponsorship_id=sponsorship_id, advertiser_business_id=advertiser_id)
        else:
            r = await rj.sync_checkout(db, sponsored_read_id=sponsorship_id, advertiser_business_id=advertiser_id)
    except Exception as e:
        raise _map_error(e)
    return {**r, "type": type}


@partner_app.get("/sponsorships/{sponsorship_id}/report", tags=["reporting"])
async def sponsorship_report(sponsorship_id: str, request: Request, type: str, advertiser_id: str,
                             caller: Caller = Depends(require_scopes("reports:read"))):
    db = request.app.state.db
    await _assert_adv(db, caller, advertiser_id)
    d = await _assert_sp(db, caller, type, sponsorship_id)
    return {"sponsorship_id": sponsorship_id, "type": type, "status": d.get("status"),
            "spent_cents": int(d.get("spent_cents") or 0),
            "impressions": int(d.get("impressions_count") or 0),
            "entries": int(d.get("entries_count") or 0),
            "plays_delivered": int(d.get("plays_delivered") or 0),
            "awarded_count": int(d.get("awarded_count") or 0)}


# ══════════════════════════ marketplace promotion ═══════════════════
class PromotionCheckoutBody(BaseModel):
    business_id: str
    tier: str = Field(..., description="Promo tier key from GET /marketplace/promotion/tiers")
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


class SpotlightCheckoutBody(BaseModel):
    business_id: str
    category: str = Field(..., description="Category key from GET /marketplace/categories")
    bid_cents: int = Field(..., ge=1, le=1000, description="Per-impression bid")
    amount_cents: int = Field(..., ge=500, le=1000000, description="Prepaid budget to fund")
    daily_cap_cents: int = Field(0, ge=0, le=10000000)
    success_url: Optional[str] = None
    cancel_url: Optional[str] = None


@partner_app.get("/marketplace/promotion/tiers", tags=["marketplace"])
async def mkt_tiers(caller: Caller = Depends(require_scopes("catalog:read"))):
    return {"tiers": mkt.promo_tiers()}


@partner_app.get("/marketplace/categories", tags=["marketplace"])
async def mkt_categories(request: Request, caller: Caller = Depends(require_scopes("catalog:read"))):
    return {"items": await mkt.list_categories(request.app.state.db)}


@partner_app.get("/marketplace/businesses", tags=["marketplace"])
async def mkt_businesses(request: Request, q: Optional[str] = None, limit: int = 50,
                         caller: Caller = Depends(require_scopes("catalog:read"))):
    items = await mkt.list_promotable_businesses(request.app.state.db, q=q, limit=limit)
    return {"items": items, "count": len(items)}


@partner_app.post("/marketplace/promotion/checkout", tags=["marketplace"])
async def mkt_promotion_checkout(body: PromotionCheckoutBody, request: Request,
                                 caller: Caller = Depends(require_scopes("campaigns:write"))):
    """Buy a Promoted-rail placement for a listed business. LIVE returns a
    hosted Checkout `checkout_url`; after payment it enters admin review.
    Sandbox activates instantly (comp, no payment)."""
    try:
        return await mkt.promotion_checkout(
            request.app.state.db, business_id=body.business_id, tier_key=body.tier,
            partner_id=caller.partner_id, sandbox=caller.is_sandbox, environment=caller.environment,
            success_url=body.success_url, cancel_url=body.cancel_url)
    except Exception as e:
        raise _map_error(e)


@partner_app.get("/marketplace/promotion/{promotion_id}/status", tags=["marketplace"])
async def mkt_promotion_status(promotion_id: str, request: Request,
                               caller: Caller = Depends(require_scopes("campaigns:read"))):
    try:
        return await mkt.promotion_status(request.app.state.db,
                                          promotion_id=promotion_id, partner_id=caller.partner_id,
                                          environment=caller.environment)
    except Exception as e:
        raise _map_error(e)


@partner_app.get("/marketplace/promotion/{promotion_id}/report", tags=["marketplace", "reporting"])
async def mkt_promotion_report(promotion_id: str, request: Request,
                               caller: Caller = Depends(require_scopes("reports:read"))):
    """Impressions, views, orders, revenue and total spend for a promotion the
    partner purchased (over its active window)."""
    try:
        return await mkt.promotion_report(request.app.state.db,
                                          promotion_id=promotion_id, partner_id=caller.partner_id,
                                          environment=caller.environment)
    except Exception as e:
        raise _map_error(e)


@partner_app.post("/marketplace/spotlight/checkout", tags=["marketplace"])
async def mkt_spotlight_checkout(body: SpotlightCheckoutBody, request: Request,
                                 caller: Caller = Depends(require_scopes("campaigns:write"))):
    """Set a Category Spotlight bid for a listed business and fund its prepaid
    budget. LIVE returns a hosted Checkout `checkout_url`; the budget is
    credited (and the bid activates) once payment clears. Sandbox funds
    instantly."""
    try:
        return await mkt.spotlight_checkout(
            request.app.state.db, business_id=body.business_id, category=body.category,
            bid_cents=body.bid_cents, amount_cents=body.amount_cents,
            daily_cap_cents=body.daily_cap_cents, partner_id=caller.partner_id,
            sandbox=caller.is_sandbox, environment=caller.environment,
            success_url=body.success_url, cancel_url=body.cancel_url)
    except Exception as e:
        raise _map_error(e)


@partner_app.get("/marketplace/spotlight/{session_id}/status", tags=["marketplace"])
async def mkt_spotlight_status(session_id: str, request: Request,
                               caller: Caller = Depends(require_scopes("campaigns:read"))):
    try:
        return await mkt.spotlight_status(request.app.state.db,
                                          session_id=session_id, partner_id=caller.partner_id,
                                          environment=caller.environment)
    except Exception as e:
        raise _map_error(e)


@partner_app.get("/marketplace/spotlight", tags=["marketplace"])
async def mkt_spotlight_get(request: Request, business_id: str,
                            caller: Caller = Depends(require_scopes("campaigns:read"))):
    try:
        return await mkt.spotlight_get(request.app.state.db, business_id=business_id)
    except Exception as e:
        raise _map_error(e)


# ══════════════════════════ usage analytics ═════════════════════════
@partner_app.get("/usage", tags=["reporting"])
async def usage_ep(request: Request, days: int = 30,
                   caller: Caller = Depends(require_scopes("reports:read"))):
    return await pa.compute_usage(request.app.state.db, partner_id=caller.partner_id, days=days)


# ══════════════════════════ webhooks ════════════════════════════════
class WebhookCreate(BaseModel):
    url: str
    events: Optional[list[str]] = None


@partner_app.get("/webhooks/events", tags=["webhooks"])
async def webhook_event_types(caller: Caller = Depends(require_scopes("catalog:read"))):
    return {"events": pa.WEBHOOK_EVENTS}


@partner_app.post("/webhooks", tags=["webhooks"], status_code=201)
async def create_webhook_ep(body: WebhookCreate, request: Request,
                            caller: Caller = Depends(require_scopes("campaigns:write"))):
    return await pa.create_webhook(request.app.state.db, partner_id=caller.partner_id,
                                   environment=caller.environment, url=body.url, events=body.events)


@partner_app.get("/webhooks", tags=["webhooks"])
async def list_webhooks_ep(request: Request, caller: Caller = Depends(require_scopes("campaigns:read"))):
    return {"items": await pa.list_webhooks(request.app.state.db, partner_id=caller.partner_id)}


@partner_app.delete("/webhooks/{webhook_id}", tags=["webhooks"])
async def delete_webhook_ep(webhook_id: str, request: Request,
                            caller: Caller = Depends(require_scopes("campaigns:write"))):
    if not await pa.delete_webhook(request.app.state.db, partner_id=caller.partner_id, webhook_id=webhook_id):
        raise HTTPException(404, {"code": "webhook_not_found"})
    return {"deleted": True, "webhook_id": webhook_id}


@partner_app.post("/webhooks/{webhook_id}/ping", tags=["webhooks"])
async def ping_webhook_ep(webhook_id: str, request: Request,
                          caller: Caller = Depends(require_scopes("campaigns:write"))):
    r = await pa.ping_webhook(request.app.state.db, partner_id=caller.partner_id, webhook_id=webhook_id)
    if r is None:
        raise HTTPException(404, {"code": "webhook_not_found"})
    return r


@partner_app.get("/webhooks/{webhook_id}/deliveries", tags=["webhooks"])
async def deliveries_ep(webhook_id: str, request: Request,
                        caller: Caller = Depends(require_scopes("campaigns:read"))):
    return {"items": await pa.list_deliveries(request.app.state.db, partner_id=caller.partner_id, webhook_id=webhook_id)}


__all__ = ["partner_app"]
