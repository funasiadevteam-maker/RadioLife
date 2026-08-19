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

import hashlib
import hmac
import logging
import os
import secrets
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
    "catalog:read",       # browse the product/inventory catalog
    "advertisers:read", "advertisers:write",
    "campaigns:read", "campaigns:write",
    "reports:read",
    "funding:write",      # top-up campaign budget
]
DEFAULT_SCOPES = list(SCOPES)

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
     "description": "Sponsor a trivia room / question set.",
     "campaign_type": None, "pricing_models": ["flat", "cpm"], "bookable": False,
     "status": "coming_soon"},
    {"key": "sponsorship_rj_read", "name": "AI-RJ Sponsored Read", "category": "audio",
     "description": "A host-read (AI-RJ) audio mention inserted between songs.",
     "campaign_type": None, "pricing_models": ["flat"], "bookable": False,
     "status": "coming_soon"},
    {"key": "programmatic_openrtb", "name": "Programmatic (OpenRTB)", "category": "programmatic",
     "description": "Real-time bidding seat for DSPs. Bid on audio/display impressions "
                    "via the OpenRTB 2.x endpoint; creatives served over VAST for audio.",
     "campaign_type": None, "pricing_models": ["cpm"], "bookable": False,
     "status": "beta", "endpoints": {"bid": "/api/openrtb", "vast": "/api/vast"}},
    {"key": "marketplace_promotion", "name": "Marketplace Promotion", "category": "commerce",
     "description": "Promote a shop on the Marketplace (Promoted rail + Category Spotlight auction).",
     "campaign_type": None, "pricing_models": ["flat", "cpm"], "bookable": False,
     "status": "coming_soon"},
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


async def enforce_rate_limit(db, caller: Caller, limit: int = RATE_LIMIT_PER_MINUTE) -> None:
    now = _now()
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
        missing = set(needed) - caller.scopes
        if missing:
            raise HTTPException(status_code=403,
                                detail={"code": "insufficient_scope",
                                        "missing": sorted(missing)})
        return caller
    return _dep


__all__ = [
    "PRODUCTS", "SCOPES", "DEFAULT_SCOPES", "product_by_key",
    "ensure_partner_api", "get_or_create_partner", "get_partner",
    "issue_api_key", "issue_oauth_client", "list_credentials",
    "revoke_api_key", "revoke_oauth_client",
    "mint_access_token", "verify_client_credentials",
    "Caller", "resolve_caller", "enforce_rate_limit", "require_scopes",
]
