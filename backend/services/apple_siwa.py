"""BigFM Phase 13e — Sign in with Apple service.

Encapsulates:
  * client_secret JWT generation (ES256 signed with .p8 key).
  * Apple identity_token verification (JWKS fetch + cache + sig check).
  * BigFM user resolution / linking from a verified identity_token.

Env vars required for LIVE mode (any missing → MOCK):
  APPLE_TEAM_ID
  APPLE_KEY_ID
  APPLE_KEY_PATH                ← /app/secrets/apple/AuthKey_<KEY_ID>.p8
  APPLE_SIWA_SERVICE_ID
  APPLE_SIWA_REDIRECT_URI

Everything here is defensive — when creds are missing we raise
SIWANotConfigured so the routes can return a clean 503 / MOCK page.
"""
from __future__ import annotations
import logging
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

import httpx
import jwt

logger = logging.getLogger("bigfm.apple.siwa")

APPLE_ISS = "https://appleid.apple.com"
APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
JWKS_CACHE_TTL_SEC = 86400      # Apple recommends ≤24h
CLIENT_SECRET_MAX_AGE_SEC = 60 * 60 * 24 * 30 * 5  # 5 months (Apple cap 6).


class SIWANotConfigured(RuntimeError):
    """Raised when SIWA env vars aren't fully set — routes catch this and
    return a 503-style MOCK response."""


def _env(name: str) -> Optional[str]:
    v = (os.environ.get(name) or "").strip()
    return v or None


def creds() -> Dict[str, str]:
    team    = _env("APPLE_TEAM_ID")
    kid     = _env("APPLE_KEY_ID")
    kp      = _env("APPLE_KEY_PATH")
    svc     = _env("APPLE_SIWA_SERVICE_ID")
    redir   = _env("APPLE_SIWA_REDIRECT_URI")
    if not (team and kid and kp and svc and redir):
        raise SIWANotConfigured(
            "Missing one of APPLE_TEAM_ID / APPLE_KEY_ID / APPLE_KEY_PATH "
            "/ APPLE_SIWA_SERVICE_ID / APPLE_SIWA_REDIRECT_URI")
    if not os.path.exists(kp):
        raise SIWANotConfigured(f"APPLE_KEY_PATH not on disk: {kp}")
    return {"team_id": team, "key_id": kid, "key_path": kp,
              "service_id": svc, "redirect_uri": redir}


def is_configured() -> bool:
    try:
        creds()
        return True
    except SIWANotConfigured:
        return False


def _load_p8(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


# ─── client_secret JWT ───────────────────────────────────────────────────
def make_client_secret(*, max_age_sec: int = CLIENT_SECRET_MAX_AGE_SEC,
                                  service_id_override: Optional[str] = None) -> str:
    c = creds()
    now = int(time.time())
    payload = {
        "iss": c["team_id"],
        "iat": now,
        "exp": now + min(int(max_age_sec), CLIENT_SECRET_MAX_AGE_SEC),
        "aud": APPLE_ISS,
        "sub": service_id_override or c["service_id"],
    }
    headers = {"kid": c["key_id"], "alg": "ES256"}
    return jwt.encode(payload, _load_p8(c["key_path"]),
                              algorithm="ES256", headers=headers)


# ─── JWKS cache + identity_token verification ───────────────────────────
async def _get_jwks(db) -> list:
    coll = db["apple_jwks_cache"]
    doc  = await coll.find_one({"_id": "apple"})
    if doc and doc.get("fetched_at"):
        fa = doc["fetched_at"]
        if fa.tzinfo is None:
            fa = fa.replace(tzinfo=timezone.utc)
        if (datetime.now(timezone.utc) - fa).total_seconds() \
                  < JWKS_CACHE_TTL_SEC:
            return doc.get("keys", [])
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(APPLE_JWKS_URL)
        r.raise_for_status()
        keys = r.json().get("keys", [])
    await coll.update_one(
        {"_id": "apple"},
        {"$set": {"keys": keys,
                      "fetched_at": datetime.now(timezone.utc)}},
        upsert=True)
    return keys


def _key_from_jwk(jwk: dict):
    return jwt.algorithms.RSAAlgorithm.from_jwk(jwk)


async def verify_identity_token(db, id_token: str,
                                              *, audience: Optional[str] = None
                                              ) -> Dict[str, Any]:
    """Verifies signature + iss + aud + exp. Returns the claims."""
    if not id_token:
        raise ValueError("empty id_token")
    expected_aud = audience or creds()["service_id"]
    unverified_header = jwt.get_unverified_header(id_token)
    kid = unverified_header.get("kid")
    keys = await _get_jwks(db)
    jwk = next((k for k in keys if k.get("kid") == kid), None)
    if not jwk:
        # Force-refresh once and retry — Apple rotates keys.
        await db["apple_jwks_cache"].delete_one({"_id": "apple"})
        keys = await _get_jwks(db)
        jwk = next((k for k in keys if k.get("kid") == kid), None)
    if not jwk:
        raise ValueError(f"unknown_kid:{kid}")
    pub_key = _key_from_jwk(jwk)
    claims = jwt.decode(id_token, pub_key, algorithms=["RS256"],
                                audience=expected_aud, issuer=APPLE_ISS,
                                options={"require": ["exp", "iat", "iss",
                                                                  "aud", "sub"]})
    return claims


# ─── token-exchange (web callback) ───────────────────────────────────────
async def exchange_code(code: str) -> Dict[str, Any]:
    c = creds()
    client_secret = make_client_secret()
    data = {
        "client_id": c["service_id"],
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": c["redirect_uri"],
    }
    async with httpx.AsyncClient(timeout=10) as cl:
        r = await cl.post(APPLE_TOKEN_URL, data=data)
        if r.status_code >= 400:
            raise ValueError(f"apple_token_exchange_failed:{r.status_code}:"
                                  f"{r.text[:200]}")
        return r.json()


# ─── BigFM user resolution / linking ────────────────────────────────────
async def apple_user_from_claims(db, claims: Dict[str, Any],
                                                profile_name: Optional[Dict[str, str]] = None
                                                ) -> Dict[str, Any]:
    """Given verified identity_token claims, return (or create) a BigFM
    user doc. Linking rule: existing user with same email → link by
    setting `apple_sub`. Otherwise create a fresh user.
    """
    apple_sub = claims.get("sub")
    if not apple_sub:
        raise ValueError("missing_sub_in_claims")
    email = (claims.get("email") or "").lower().strip() or None
    email_verified = bool(claims.get("email_verified")
                                      or claims.get("is_private_email") in (
                                          False, "false"))
    # Already linked?
    existing = await db.users.find_one({"apple_sub": apple_sub})
    if existing:
        return existing
    # Link by email if present.
    if email:
        existing = await db.users.find_one({"email": email})
        if existing:
            await db.users.update_one(
                {"_id": existing["_id"]},
                {"$set": {"apple_sub": apple_sub,
                              "email_verified": True}})
            existing["apple_sub"] = apple_sub
            return existing
    # Create.
    uid = f"user_{uuid.uuid4().hex[:16]}"
    full_name = ""
    if profile_name:
        first = (profile_name.get("firstName") or "").strip()
        last  = (profile_name.get("lastName")  or "").strip()
        full_name = (f"{first} {last}").strip()
    doc = {
        "_id": uid, "user_id": uid,
        "email": email or f"{uid}@privaterelay.appleid.com",
        "email_verified": True,
        "apple_sub": apple_sub,
        "display_name": full_name or None,
        "auth_provider": "apple",
        "created_at": datetime.now(timezone.utc),
        "onboarded": False,
    }
    await db.users.insert_one(doc)
    logger.info("apple_siwa: created BigFM user %s for apple_sub=%s",
                       uid, apple_sub[:12])
    return doc


# ─── health probe (for integration_health) ──────────────────────────────
async def probe() -> Dict[str, Any]:
    """Quick smoke test: can we mint a client_secret? Returns a dict
    suitable for record_call."""
    try:
        token = make_client_secret(max_age_sec=120)
        return {"ok": True, "client_secret_len": len(token),
                  "key_id": creds()["key_id"]}
    except SIWANotConfigured as e:
        return {"ok": False, "error": "not_configured", "detail": str(e)}
    except Exception as e:
        logger.warning("apple_siwa probe failed: %s", e)
        return {"ok": False, "error": "probe_failed", "detail": str(e)[:200]}
