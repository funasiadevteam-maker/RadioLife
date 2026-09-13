"""RadioLife Ads Public API — partner authentication + SDK.

External systems (ad agencies, brands, DSPs) authenticate to the versioned
public API (`/api/v1/*`) with either:

  1. A partner API key  ->  `Authorization: Bearer rlk_<env>_<id>.<secret>`
  2. An OAuth2 client-credentials access token (HS256 JWT) obtained from
     `POST /api/v1/oauth/token`.

Security model (per the auth playbook):
  * Secrets are high-entropy random; only an HMAC-SHA256 digest (salted with a
    server pepper) is stored — never the raw secret.
  * The signing secret + pepper live in a single Mongo config doc
    (`partner_api_secrets`, _id="global"), generated once, so the API works in
    any environment without manual env setup. `PARTNER_API_JWT_SECRET` /
    `PARTNER_API_PEPPER` env vars override when present.
  * JWTs are HS256 (single service signs & verifies), short-lived, and carry
    `partner_id`, `environment`, and space-delimited `scope`.
  * LIVE and SANDBOX credentials are isolated: sandbox advertisers/campaigns
    live under a different owner id and never serve/bill real inventory.

This module is a thin AUTH + catalog layer; all ad business logic is reused
from `services.ad1_advertiser_service` (the existing ad platform).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import secrets
import time
import httpx
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import HTTPException, Request
from pymongo import ReturnDocument

log = logging.getLogger("bigfm.partner_api")

JWT_ALG = "HS256"
JWT_ISSUER = "radiolife-ads"
JWT_AUDIENCE = "partner-api"
ACCESS_TOKEN_MINUTES = int(os.environ.get("PARTNER_API_ACCESS_TOKEN_MINUTES", "30"))
RATE_LIMIT_PER_MINUTE = int(os.environ.get("PARTNER_API_RATE_LIMIT_PER_MINUTE", "120"))

# ── Scopes ──────────────────────────────────────────────────────────
SCOPES = [
    "account:read",       # read partner/account profile
    "catalog:read",       # browse the product/inventory catalog
    "inventory:read", "markets:read", "stations:read",
    "targeting:read", "ratecard:read",
    "advertisers:read", "advertisers:write",
    "campaigns:read", "campaigns:write",
    "creatives:read", "creatives:write",
    "games:read", "games:write",
    "offers:read", "offers:write",
    "merchant:read", "merchant:write",
    "reports:read", "analytics:read", "billing:read",
    "funding:write",      # top-up campaign budget
    "webhooks:read", "webhooks:write",
    "rewards:read", "rewards:write",          # Phase E — reward events
    "conversions:read", "conversions:write",  # Phase E — conversions
    "jobs:read", "jobs:write",                # Phase E — bulk/async jobs
]
# Keys/clients minted without an explicit scope list get this least-privilege
# read+basic set (write scopes for advertisers/campaigns/creatives kept for
# backward compatibility with the pre-Phase-A default).
DEFAULT_SCOPES = [
    "account:read", "catalog:read", "inventory:read", "markets:read",
    "stations:read", "targeting:read", "ratecard:read",
    "advertisers:read", "advertisers:write",
    "campaigns:read", "campaigns:write",
    "creatives:read", "creatives:write",
    "reports:read", "analytics:read", "funding:write",
]

# Webhook event types partners can subscribe to.
WEBHOOK_EVENTS = [
    "campaign.approved", "campaign.live", "campaign.budget_exhausted",
    "campaign.completed", "sponsorship.approved",
    # Phase D / E
    "sponsored_game.created", "conversion.recorded", "reward_event.recorded",
    "job.completed", "merchant.created", "offer.created",
    "ping",
]

# ── Marketing product catalog (facade over the internal ad engine) ──
# `campaign_type` maps to services.ad1_advertiser_service.CAMPAIGN_TYPES for
# bookable products.  Non-bookable products are surfaced for discovery and
# come online in later phases / via dedicated endpoints (OpenRTB).
PRODUCTS: list[dict] = [
    {"key": "audio_preroll", "name": "Audio Pre-roll", "category": "audio",
     "description": "A :15–:30 audio spot played before a live-radio stream starts.",
     "campaign_type": "audio_preroll_stub", "pricing_models": ["cpm", "flat"],
     "formats": ["audio/mp3", "audio/aac"], "bookable": True, "status": "available"},
    {"key": "display_banner", "name": "Display Banner", "category": "display",
     "description": "In-app display banner across web + mobile placements.",
     "campaign_type": "display_banner", "pricing_models": ["cpm", "cpc", "flat"],
     "formats": ["image/png", "image/jpeg"], "bookable": True, "status": "available"},
    {"key": "sponsored_game", "name": "Sponsored Game", "category": "sponsorship",
     "description": "Brand a Play & Win game; requires a linked game campaign id.",
     "campaign_type": "sponsored_game", "pricing_models": ["cpm", "flat"],
     "formats": ["image/png"], "bookable": True, "status": "available",
     "requires": ["creative.sponsored_game_campaign_id"]},
    {"key": "audio_midroll", "name": "Audio Mid-stream", "category": "audio",
     "description": "Dynamic mid-stream audio insertion during live radio.",
     "campaign_type": None, "pricing_models": ["cpm"], "bookable": False,
     "status": "coming_soon"},
    {"key": "sponsorship_predict_win", "name": "Predict & Win Sponsorship",
     "category": "sponsorship", "description": "Sponsor a Predict & Win event (per-entry / per-impression).",
     "campaign_type": None, "pricing_models": ["per_entry", "per_impression"],
     "bookable": False, "status": "coming_soon"},
    {"key": "sponsorship_trivia", "name": "Trivia Sponsorship", "category": "sponsorship",
     "description": "Sponsor a trivia room / category and fund a winner prize pool. "
                    "Create via POST /sponsorships (type=trivia), then pay the prize pool "
                    "with a hosted Checkout link via POST /sponsorships/{id}/checkout.",
     "campaign_type": None, "pricing_models": ["prize_pool"], "bookable": False,
     "status": "available", "endpoints": {"create": "/api/v1/sponsorships",
                                           "checkout": "/api/v1/sponsorships/{id}/checkout"}},
    {"key": "sponsorship_rj_read", "name": "AI-RJ Sponsored Read", "category": "audio",
     "description": "A host-read (AI-RJ) audio mention inserted between songs. Create via "
                    "POST /sponsorships (type=rj_read), finalize the script via "
                    "POST /sponsorships/{id}/submit, then pay the booking with a hosted "
                    "Checkout link via POST /sponsorships/{id}/checkout.",
     "campaign_type": None, "pricing_models": ["cost_per_play"], "bookable": False,
     "status": "available", "endpoints": {"create": "/api/v1/sponsorships",
                                           "submit": "/api/v1/sponsorships/{id}/submit",
                                           "checkout": "/api/v1/sponsorships/{id}/checkout"}},
    {"key": "programmatic_openrtb", "name": "Programmatic (OpenRTB)", "category": "programmatic",
     "description": "Real-time bidding seat for DSPs. Bid on audio/display impressions "
                    "via the OpenRTB 2.x endpoint; creatives served over VAST for audio.",
     "campaign_type": None, "pricing_models": ["cpm"], "bookable": False,
     "status": "beta", "endpoints": {"bid": "/api/openrtb", "vast": "/api/vast"}},
    {"key": "marketplace_promotion", "name": "Marketplace Promotion", "category": "commerce",
     "description": "Promote a listed shop on the Marketplace: a Promoted-rail placement "
                    "(tiered flat fee, admin-reviewed) or a Category Spotlight bid (prepaid, "
                    "billed per impression). Discover businesses via GET /marketplace/businesses, "
                    "then buy via POST /marketplace/promotion/checkout or "
                    "POST /marketplace/spotlight/checkout.",
     "campaign_type": None, "pricing_models": ["flat", "cpm"], "bookable": False,
     "status": "available", "endpoints": {"tiers": "/api/v1/marketplace/promotion/tiers",
                                           "categories": "/api/v1/marketplace/categories",
                                           "businesses": "/api/v1/marketplace/businesses",
                                           "promotion_checkout": "/api/v1/marketplace/promotion/checkout",
                                           "spotlight_checkout": "/api/v1/marketplace/spotlight/checkout"}},
]


def product_by_key(key: str) -> Optional[dict]:
    return next((p for p in PRODUCTS if p["key"] == key), None)


# ── time / id helpers ───────────────────────────────────────────────
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(10)}"


# ── secret material (cached) ────────────────────────────────────────
_secret_cache: dict[str, bytes | str] = {}


async def _load_secrets(db) -> dict:
    if _secret_cache:
        return _secret_cache  # type: ignore[return-value]
    env_jwt = os.environ.get("PARTNER_API_JWT_SECRET")
    env_pepper = os.environ.get("PARTNER_API_PEPPER")
    doc = await db.partner_api_secrets.find_one({"_id": "global"})
    if not doc:
        doc = {"_id": "global",
               "jwt_secret": env_jwt or secrets.token_hex(32),
               "pepper": env_pepper or secrets.token_hex(32),
               "created_at": _now()}
        try:
            await db.partner_api_secrets.insert_one(doc)
        except Exception:
            doc = await db.partner_api_secrets.find_one({"_id": "global"}) or doc
    _secret_cache["jwt"] = env_jwt or doc["jwt_secret"]
    _secret_cache["pepper"] = bytes.fromhex(env_pepper or doc["pepper"])
    return _secret_cache  # type: ignore[return-value]


def _digest(pepper: bytes, value: str) -> str:
    return hmac.new(pepper, value.encode("utf-8"), hashlib.sha256).hexdigest()


# ── bootstrap ───────────────────────────────────────────────────────
async def ensure_partner_api(db) -> dict:
    await db.partner_accounts.create_index("partner_id", unique=True)
    await db.partner_accounts.create_index("owner_user_id", sparse=True)
    await db.partner_keys.create_index("key_id", unique=True)
    await db.partner_keys.create_index([("partner_id", 1), ("environment", 1)])
    await db.partner_oauth_clients.create_index("client_id", unique=True)
    await db.partner_oauth_clients.create_index([("partner_id", 1), ("environment", 1)])
    await db.partner_rate_windows.create_index("expires_at", expireAfterSeconds=0)
    await db.partner_api_calls.create_index([("partner_id", 1), ("ts", -1)])
    await db.partner_api_calls.create_index("ts", expireAfterSeconds=90 * 86400)
    await db.partner_webhooks.create_index([("partner_id", 1), ("environment", 1)])
    await db.partner_webhook_deliveries.create_index([("webhook_id", 1), ("ts", -1)])
    await _load_secrets(db)
    log.info("[partner_api] ready — indexes + secrets ensured")
    return {"ok": True}


# ── partner accounts ────────────────────────────────────────────────
def _clean(doc: Optional[dict]) -> Optional[dict]:
    if not doc:
        return doc
    out = {k: v for k, v in doc.items() if k != "_id" and not k.endswith("_hash")}
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


async def get_or_create_partner(db, *, owner_user_id: str, name: str,
                                contact_email: str) -> dict:
    existing = await db.partner_accounts.find_one({"owner_user_id": owner_user_id})
    if existing:
        return _clean(existing)
    doc = {"partner_id": _gen("prt"), "owner_user_id": owner_user_id,
           "name": (name or "Partner").strip(),
           "contact_email": (contact_email or "").strip().lower(),
           "status": "active", "created_at": _now(), "updated_at": _now()}
    await db.partner_accounts.insert_one(doc)
    return _clean(doc)


async def get_partner(db, partner_id: str) -> Optional[dict]:
    return _clean(await db.partner_accounts.find_one({"partner_id": partner_id}))


# ── credential issuance ─────────────────────────────────────────────
def _norm_env(environment: str) -> str:
    e = (environment or "live").strip().lower()
    return "SANDBOX" if e in ("sandbox", "test") else "LIVE"


def _env_tag(environment: str) -> str:
    return "test" if _norm_env(environment) == "SANDBOX" else "live"


async def issue_api_key(db, *, partner_id: str, environment: str,
                        scopes: Optional[list[str]] = None,
                        label: Optional[str] = None) -> dict:
    s = await _load_secrets(db)
    env = _norm_env(environment)
    key_id = f"rlk_{_env_tag(env)}_{secrets.token_urlsafe(9)}"
    raw_secret = secrets.token_urlsafe(32)
    scopes = sorted(set(scopes or DEFAULT_SCOPES) & set(SCOPES)) or list(DEFAULT_SCOPES)
    doc = {"key_id": key_id, "secret_hash": _digest(s["pepper"], raw_secret),
           "partner_id": partner_id, "environment": env, "scopes": scopes,
           "label": (label or "").strip() or None, "revoked_at": None,
           "last_used_at": None, "created_at": _now()}
    await db.partner_keys.insert_one(doc)
    return {"key_id": key_id, "api_key": f"{key_id}.{raw_secret}",
            "environment": env, "scopes": scopes, "label": doc["label"],
            "created_at": doc["created_at"].isoformat()}


async def issue_oauth_client(db, *, partner_id: str, environment: str,
                             scopes: Optional[list[str]] = None,
                             label: Optional[str] = None) -> dict:
    s = await _load_secrets(db)
    env = _norm_env(environment)
    client_id = f"rlc_{_env_tag(env)}_{secrets.token_urlsafe(9)}"
    raw_secret = secrets.token_urlsafe(32)
    scopes = sorted(set(scopes or DEFAULT_SCOPES) & set(SCOPES)) or list(DEFAULT_SCOPES)
    doc = {"client_id": client_id, "client_secret_hash": _digest(s["pepper"], raw_secret),
           "partner_id": partner_id, "environment": env, "scopes": scopes,
           "label": (label or "").strip() or None, "revoked_at": None,
           "created_at": _now()}
    await db.partner_oauth_clients.insert_one(doc)
    return {"client_id": client_id, "client_secret": raw_secret,
            "environment": env, "scopes": scopes, "label": doc["label"],
            "token_url": "/api/v1/oauth/token",
            "created_at": doc["created_at"].isoformat()}


async def list_credentials(db, *, partner_id: str) -> dict:
    keys = [_clean(k) async for k in db.partner_keys.find({"partner_id": partner_id}).sort("created_at", -1)]
    clients = [_clean(c) async for c in db.partner_oauth_clients.find({"partner_id": partner_id}).sort("created_at", -1)]
    return {"api_keys": keys, "oauth_clients": clients}


async def revoke_api_key(db, *, partner_id: str, key_id: str) -> bool:
    r = await db.partner_keys.update_one(
        {"key_id": key_id, "partner_id": partner_id, "revoked_at": None},
        {"$set": {"revoked_at": _now()}})
    return r.modified_count > 0


async def revoke_oauth_client(db, *, partner_id: str, client_id: str) -> bool:
    r = await db.partner_oauth_clients.update_one(
        {"client_id": client_id, "partner_id": partner_id, "revoked_at": None},
        {"$set": {"revoked_at": _now()}})
    return r.modified_count > 0


# ── token minting / verification ────────────────────────────────────
async def mint_access_token(db, *, client_id: str, partner_id: str,
                            environment: str, scopes: list[str]) -> dict:
    s = await _load_secrets(db)
    now = _now()
    claims = {"iss": JWT_ISSUER, "aud": JWT_AUDIENCE, "sub": client_id,
              "partner_id": partner_id, "environment": environment,
              "scope": " ".join(sorted(set(scopes))),
              "iat": now, "nbf": now,
              "exp": now + timedelta(minutes=ACCESS_TOKEN_MINUTES),
              "jti": secrets.token_urlsafe(12)}
    token = jwt.encode(claims, s["jwt"], algorithm=JWT_ALG)
    return {"access_token": token, "token_type": "Bearer",
            "expires_in": ACCESS_TOKEN_MINUTES * 60,
            "scope": claims["scope"]}


async def verify_client_credentials(db, client_id: str, client_secret: str) -> Optional[dict]:
    s = await _load_secrets(db)
    doc = await db.partner_oauth_clients.find_one({"client_id": client_id})
    if not doc or doc.get("revoked_at"):
        return None
    if not hmac.compare_digest(_digest(s["pepper"], client_secret), doc["client_secret_hash"]):
        return None
    return doc


# ── caller resolution + scope enforcement ───────────────────────────
@dataclass
class Caller:
    partner_id: str
    environment: str
    scopes: set = field(default_factory=set)
    credential_type: str = "api_key"
    credential_id: str = ""

    @property
    def owner_id(self) -> str:
        """Owner id used on advertiser docs — isolates SANDBOX from LIVE."""
        return f"partner:{self.partner_id}:{self.environment.lower()}"

    @property
    def is_sandbox(self) -> bool:
        return self.environment == "SANDBOX"


def _unauthorized(detail: str = "invalid_credentials") -> HTTPException:
    return HTTPException(status_code=401, detail={"code": detail},
                         headers={"WWW-Authenticate": "Bearer"})


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return (request.client.host if request.client else "") or ""


def _ip_allowed(ip: str, allowlist: list[str]) -> bool:
    """True if `ip` matches any allowlist entry (exact IP or CIDR)."""
    if not allowlist:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in allowlist:
        entry = (entry or "").strip()
        if not entry:
            continue
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


async def resolve_caller(request: Request) -> Caller:
    db = request.app.state.db
    s = await _load_secrets(db)
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise _unauthorized("missing_bearer_token")
    raw = header[7:].strip()

    if raw.startswith("rlk_") and "." in raw:
        key_id, _, provided = raw.partition(".")
        doc = await db.partner_keys.find_one({"key_id": key_id})
        if (not doc or doc.get("revoked_at")
                or not hmac.compare_digest(_digest(s["pepper"], provided), doc["secret_hash"])):
            raise _unauthorized()
        # Optional per-key IP allowlist (Phase F security hardening).
        allowlist = doc.get("ip_allowlist") or []
        if allowlist and not _ip_allowed(_client_ip(request), allowlist):
            raise HTTPException(status_code=403, detail={"code": "ip_not_allowed"})
        # best-effort last-used tracking (never blocks the request)
        try:
            await db.partner_keys.update_one({"key_id": key_id},
                                             {"$set": {"last_used_at": _now()}})
        except Exception:
            pass
        return Caller(partner_id=doc["partner_id"], environment=doc["environment"],
                      scopes=set(doc.get("scopes", [])), credential_type="api_key",
                      credential_id=key_id)

    # else: OAuth access token
    try:
        p = jwt.decode(raw, s["jwt"], algorithms=[JWT_ALG],
                       issuer=JWT_ISSUER, audience=JWT_AUDIENCE,
                       options={"require": ["exp", "iat", "iss", "aud", "sub"]})
    except jwt.InvalidTokenError:
        raise _unauthorized("invalid_token")
    return Caller(partner_id=p["partner_id"], environment=p.get("environment", "LIVE"),
                  scopes=set((p.get("scope") or "").split()), credential_type="oauth",
                  credential_id=p["sub"])


_partner_limit_cache: dict[str, tuple[float, int, bool]] = {}


async def _partner_meta(db, partner_id: str, default: int) -> tuple[int, bool]:
    """(rate_limit, active) for a partner — admin-set override, cached 60s."""
    cached = _partner_limit_cache.get(partner_id)
    if cached and (time.time() - cached[0]) < 60:
        return cached[1], cached[2]
    limit, active = default, True
    try:
        p = await db.partner_accounts.find_one(
            {"partner_id": partner_id},
            {"rate_limit_per_minute": 1, "status": 1})
        if p:
            if int(p.get("rate_limit_per_minute") or 0) > 0:
                limit = int(p["rate_limit_per_minute"])
            active = (p.get("status") or "active") != "suspended"
    except Exception:
        pass
    _partner_limit_cache[partner_id] = (time.time(), limit, active)
    return limit, active


async def enforce_rate_limit(db, caller: Caller, limit: int = RATE_LIMIT_PER_MINUTE) -> None:
    now = _now()
    limit, active = await _partner_meta(db, caller.partner_id, limit)
    if not active:
        raise HTTPException(status_code=403, detail={"code": "partner_suspended"})
    window = now.replace(second=0, microsecond=0)
    key = f"{caller.environment}:{caller.credential_id}:{window.isoformat()}"
    doc = await db.partner_rate_windows.find_one_and_update(
        {"_id": key},
        {"$inc": {"count": 1},
         "$setOnInsert": {"expires_at": window + timedelta(minutes=2)}},
        upsert=True, return_document=ReturnDocument.AFTER)
    if int(doc.get("count", 0)) > limit:
        raise HTTPException(status_code=429, detail={"code": "rate_limit_exceeded"},
                            headers={"Retry-After": "60"})


def require_scopes(*needed: str):
    """FastAPI dependency factory — auth + rate-limit + scope check."""
    async def _dep(request: Request) -> Caller:
        caller = await resolve_caller(request)
        await enforce_rate_limit(request.app.state.db, caller)
        request.state.caller = caller
        missing = set(needed) - caller.scopes
        if missing:
            raise HTTPException(status_code=403,
                                detail={"code": "insufficient_scope",
                                        "missing": sorted(missing)})
        return caller
    return _dep


# ══════════════════════════ usage analytics ═════════════════════════
async def log_api_call(db, *, partner_id, environment, credential_id,
                       method, path, status, duration_ms) -> None:
    try:
        await db.partner_api_calls.insert_one({
            "partner_id": partner_id, "environment": environment,
            "credential_id": credential_id, "method": method, "path": path,
            "status": int(status), "duration_ms": int(duration_ms),
            "day": _now().date().isoformat(), "ts": _now()})
    except Exception:
        pass


async def _partner_advertiser_ids(db, partner_id, environment=None) -> list[str]:
    if environment:
        owners = [f"partner:{partner_id}:{_norm_env(environment).lower()}"]
    else:
        owners = [f"partner:{partner_id}:live", f"partner:{partner_id}:sandbox"]
    return [a["advertiser_id"] async for a in
            db.advertisers_v2.find({"owner_user_id": {"$in": owners}}, {"advertiser_id": 1})]


async def compute_usage(db, *, partner_id: str, days: int = 30) -> dict:
    since = _now() - timedelta(days=max(1, min(days, 365)))
    total = await db.partner_api_calls.count_documents({"partner_id": partner_id, "ts": {"$gte": since}})
    by_day, by_endpoint, by_status = {}, {}, {}
    async for c in db.partner_api_calls.find(
            {"partner_id": partner_id, "ts": {"$gte": since}},
            {"day": 1, "path": 1, "status": 1}):
        by_day[c.get("day")] = by_day.get(c.get("day"), 0) + 1
        by_endpoint[c.get("path")] = by_endpoint.get(c.get("path"), 0) + 1
        st = str(c.get("status"))
        by_status[st] = by_status.get(st, 0) + 1
    adv_ids = await _partner_advertiser_ids(db, partner_id)
    camps = []
    if adv_ids:
        camps = [c async for c in db.ad_campaigns_v2.find(
            {"advertiser_id": {"$in": adv_ids}},
            {"campaign_id": 1, "budget_spent_cents": 1, "status": 1})]
    camp_ids = [c["campaign_id"] for c in camps]
    spend = sum(int(c.get("budget_spent_cents") or 0) for c in camps)
    impressions = await db.ad_impressions_v2.count_documents({"campaign_id": {"$in": camp_ids}}) if camp_ids else 0
    clicks = await db.ad_impressions_v2.count_documents(
        {"campaign_id": {"$in": camp_ids}, "placement": {"$regex": "_click$"}}) if camp_ids else 0
    return {"days": days, "total_calls": total, "calls_by_day": by_day,
            "calls_by_endpoint": by_endpoint, "calls_by_status": by_status,
            "campaigns": len(camps),
            "active_campaigns": sum(1 for c in camps if c.get("status") == "active"),
            "spend_cents": spend, "impressions": impressions, "clicks": clicks,
            "ctr": round(clicks / impressions, 4) if impressions else 0.0}


# ══════════════════════════ webhooks ════════════════════════════════
def _wh_public(doc: Optional[dict]) -> Optional[dict]:
    d = _clean(doc)
    if d:
        d.pop("secret", None)
    return d


async def create_webhook(db, *, partner_id: str, environment: str,
                         url: str, events: Optional[list[str]] = None) -> dict:
    env = _norm_env(environment)
    subscribable = [e for e in WEBHOOK_EVENTS if e != "ping"]
    evs = [e for e in (events or []) if e in WEBHOOK_EVENTS] or list(subscribable)
    secret = "whsec_" + secrets.token_urlsafe(24)
    wid = _gen("whk")
    await db.partner_webhooks.insert_one({
        "webhook_id": wid, "partner_id": partner_id, "environment": env,
        "url": url, "events": evs, "secret": secret, "status": "active",
        "created_at": _now(), "last_delivery_at": None})
    return {"webhook_id": wid, "url": url, "events": evs, "environment": env,
            "secret": secret, "created_at": _now().isoformat()}


async def list_webhooks(db, *, partner_id: str) -> list[dict]:
    return [_wh_public(w) async for w in
            db.partner_webhooks.find({"partner_id": partner_id}).sort("created_at", -1)]


async def delete_webhook(db, *, partner_id: str, webhook_id: str) -> bool:
    r = await db.partner_webhooks.delete_one({"webhook_id": webhook_id, "partner_id": partner_id})
    return r.deleted_count > 0


async def list_deliveries(db, *, partner_id: str, webhook_id: str, limit: int = 20) -> list[dict]:
    out = []
    async for d in db.partner_webhook_deliveries.find(
            {"partner_id": partner_id, "webhook_id": webhook_id}).sort("ts", -1).limit(limit):
        out.append({k: (v.isoformat() if isinstance(v, datetime) else v)
                    for k, v in d.items() if k != "_id"})
    return out


async def _deliver(db, wh: dict, event: dict) -> bool:
    body = json.dumps(event, separators=(",", ":"), default=str)
    ts = str(int(time.time()))
    sig = hmac.new(wh["secret"].encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-RadioLife-Event": event["type"],
               "X-RadioLife-Delivery": event["id"],
               "X-RadioLife-Signature": f"t={ts},v1={sig}"}
    status, ok, err = None, False, None
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=6) as c:
                r = await c.post(wh["url"], content=body, headers=headers)
            status, ok = r.status_code, 200 <= r.status_code < 300
            if ok:
                break
        except Exception as e:
            err = str(e)[:200]
        await asyncio.sleep(0.5 * (attempt + 1))
    try:
        await db.partner_webhook_deliveries.insert_one({
            "delivery_id": _gen("whd"),
            "webhook_id": wh["webhook_id"], "partner_id": wh["partner_id"],
            "event_type": event["type"], "event_id": event["id"], "url": wh["url"],
            "status_code": status, "ok": ok, "error": err,
            "event": event, "ts": _now()})
        await db.partner_webhooks.update_one({"webhook_id": wh["webhook_id"]},
                                             {"$set": {"last_delivery_at": _now()}})
    except Exception:
        pass
    return ok


async def emit_event(db, *, partner_id: str, environment: str,
                     event_type: str, data: dict) -> int:
    env = _norm_env(environment)
    whs = [w async for w in db.partner_webhooks.find(
        {"partner_id": partner_id, "environment": env, "status": "active", "events": event_type})]
    if not whs:
        return 0
    ev = {"id": _gen("evt"), "type": event_type, "created": _now().isoformat(),
          "environment": env, "data": data}
    for w in whs:
        asyncio.create_task(_deliver(db, w, ev))
    return len(whs)


async def ping_webhook(db, *, partner_id: str, webhook_id: str) -> Optional[dict]:
    w = await db.partner_webhooks.find_one({"webhook_id": webhook_id, "partner_id": partner_id})
    if not w:
        return None
    ev = {"id": _gen("evt"), "type": "ping", "created": _now().isoformat(),
          "environment": w["environment"], "data": {"message": "pong"}}
    return {"delivered": await _deliver(db, w, ev)}


async def rotate_webhook_secret(db, *, partner_id: str, webhook_id: str) -> Optional[dict]:
    """Issue a fresh signing secret (shown once). Old signatures stop verifying."""
    w = await db.partner_webhooks.find_one({"webhook_id": webhook_id, "partner_id": partner_id})
    if not w:
        return None
    secret = "whsec_" + secrets.token_urlsafe(24)
    await db.partner_webhooks.update_one(
        {"webhook_id": webhook_id}, {"$set": {"secret": secret, "rotated_at": _now()}})
    return {"webhook_id": webhook_id, "secret": secret, "rotated_at": _now().isoformat()}


async def retry_delivery(db, *, partner_id: str, webhook_id: str,
                         delivery_id: str) -> Optional[dict]:
    """Re-POST a previously-recorded event to its webhook (manual replay)."""
    d = await db.partner_webhook_deliveries.find_one(
        {"delivery_id": delivery_id, "webhook_id": webhook_id, "partner_id": partner_id})
    if not d or not d.get("event"):
        return None
    w = await db.partner_webhooks.find_one({"webhook_id": webhook_id, "partner_id": partner_id})
    if not w:
        return None
    return {"delivered": await _deliver(db, w, d["event"]), "event_id": d.get("event_id")}


# ══════════════════════ management (Phase F) ════════════════════════
async def set_key_ip_allowlist(db, *, partner_id: str, key_id: str,
                               ip_allowlist: list[str]) -> bool:
    r = await db.partner_keys.update_one(
        {"key_id": key_id, "partner_id": partner_id},
        {"$set": {"ip_allowlist": [x.strip() for x in (ip_allowlist or []) if x.strip()]}})
    return r.matched_count > 0


DEFAULT_PARTNER_FLAGS = {"api_bookings", "sandbox", "webhooks", "reward_events",
                         "conversions", "merchant_api", "bulk_jobs"}


async def get_partner_flags(db, partner_id: str) -> dict:
    """Per-partner feature-flag overrides (only the keys the admin has set)."""
    p = await db.partner_accounts.find_one({"partner_id": partner_id},
                                           {"feature_flags": 1})
    return dict((p or {}).get("feature_flags") or {})


async def set_partner_flags(db, *, partner_id: str, flags: dict) -> dict:
    clean = {k: bool(v) for k, v in (flags or {}).items()}
    await db.partner_accounts.update_one(
        {"partner_id": partner_id},
        {"$set": {"feature_flags": clean, "updated_at": _now()}})
    _partner_limit_cache.pop(partner_id, None)
    return clean


async def set_partner_status(db, *, partner_id: str, status: str) -> bool:
    if status not in ("active", "suspended"):
        raise ValueError("invalid_status")
    r = await db.partner_accounts.update_one(
        {"partner_id": partner_id},
        {"$set": {"status": status, "updated_at": _now()}})
    return r.matched_count > 0


async def set_partner_rate_limit(db, *, partner_id: str, per_minute: int) -> bool:
    r = await db.partner_accounts.update_one(
        {"partner_id": partner_id},
        {"$set": {"rate_limit_per_minute": max(1, int(per_minute)), "updated_at": _now()}})
    _partner_limit_cache.pop(partner_id, None)
    return r.matched_count > 0


_last_wh_sweep: dict = {}


async def sweep_webhook_events(db, partner_id: str, environment: str,
                               throttle_seconds: int = 10) -> None:
    """Detect state changes on a partner's campaigns/sponsorships and fire
    webhooks. Idempotent via per-doc `partner_evt_*_sent` flags. Throttled
    per (partner, env)."""
    env = _norm_env(environment)
    key = f"{partner_id}:{env}"
    now = _now()
    last = _last_wh_sweep.get(key)
    if last and (now - last).total_seconds() < throttle_seconds:
        return
    _last_wh_sweep[key] = now
    if not await db.partner_webhooks.count_documents(
            {"partner_id": partner_id, "environment": env, "status": "active"}):
        return
    adv_ids = await _partner_advertiser_ids(db, partner_id, env)
    if not adv_ids:
        return
    async for c in db.ad_campaigns_v2.find({"advertiser_id": {"$in": adv_ids}}):
        cid, st = c["campaign_id"], c.get("status")
        total = int(c.get("budget_total_cents") or 0)
        spent = int(c.get("budget_spent_cents") or 0)
        base = {"campaign_id": cid, "name": c.get("name"), "status": st,
                "budget_total_cents": total, "budget_spent_cents": spent}
        if st == "active" and not c.get("partner_evt_live_sent"):
            await emit_event(db, partner_id=partner_id, environment=env, event_type="campaign.approved", data=base)
            await emit_event(db, partner_id=partner_id, environment=env, event_type="campaign.live", data=base)
            await db.ad_campaigns_v2.update_one({"campaign_id": cid}, {"$set": {"partner_evt_live_sent": True}})
        if total > 0 and spent >= total and not c.get("partner_evt_exhausted_sent"):
            await emit_event(db, partner_id=partner_id, environment=env, event_type="campaign.budget_exhausted", data=base)
            await db.ad_campaigns_v2.update_one({"campaign_id": cid}, {"$set": {"partner_evt_exhausted_sent": True}})
        if st in ("ended", "completed", "stopped") and not c.get("partner_evt_completed_sent"):
            await emit_event(db, partner_id=partner_id, environment=env, event_type="campaign.completed", data=base)
            await db.ad_campaigns_v2.update_one({"campaign_id": cid}, {"$set": {"partner_evt_completed_sent": True}})
    for coll, idf, ownerf, active_states in [
        ("predict_win_sponsorships", "sponsorship_id", "advertiser_id", ("live", "active")),
        ("trivia_sponsorships", "id", "advertiser_business_id", ("active",)),
        ("rj_sponsored_reads", "id", "advertiser_business_id", ("active", "posted")),
    ]:
        async for s in db[coll].find({ownerf: {"$in": adv_ids}}):
            if s.get("status") in active_states and not s.get("partner_evt_appr_sent"):
                await emit_event(db, partner_id=partner_id, environment=env,
                                 event_type="sponsorship.approved",
                                 data={"sponsorship_id": s.get(idf), "type": coll, "status": s.get("status")})
                await db[coll].update_one({idf: s.get(idf)}, {"$set": {"partner_evt_appr_sent": True}})


__all__ = [
    "PRODUCTS", "SCOPES", "DEFAULT_SCOPES", "WEBHOOK_EVENTS", "product_by_key",
    "ensure_partner_api", "get_or_create_partner", "get_partner",
    "issue_api_key", "issue_oauth_client", "list_credentials",
    "revoke_api_key", "revoke_oauth_client",
    "mint_access_token", "verify_client_credentials",
    "Caller", "resolve_caller", "enforce_rate_limit", "require_scopes",
    "log_api_call", "compute_usage",
    "create_webhook", "list_webhooks", "delete_webhook", "list_deliveries",
    "emit_event", "ping_webhook", "sweep_webhook_events",
    "rotate_webhook_secret", "retry_delivery",
    "set_key_ip_allowlist", "get_partner_flags", "set_partner_flags",
    "set_partner_status", "set_partner_rate_limit",
]
