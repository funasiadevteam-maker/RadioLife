"""FUUSIC Phase 13e — APNs direct push delivery.

Apple Push Notification service over HTTP/2 using a token-auth JWT signed
with the same .p8 ES256 key as Sign in with Apple.

Env vars required for LIVE mode (any missing → MOCK):
  APPLE_TEAM_ID
  APPLE_KEY_ID
  APPLE_KEY_PATH
  APPLE_BUNDLE_ID
  APNS_ENV                      ← "sandbox" (default) or "production"
"""
from __future__ import annotations
import logging
import os
import time
from typing import Optional, Dict, Any

import httpx
import jwt

logger = logging.getLogger("bigfm.apple.apns")

APNS_HOSTS = {
    "sandbox":    "https://api.sandbox.push.apple.com",
    "production": "https://api.push.apple.com",
}
APNS_JWT_TTL_SEC = 50 * 60   # 50min (Apple cap 60min)

# Module-level JWT cache.
_jwt_cache: Dict[str, Any] = {"token": None, "minted_at": 0.0}


class APNsNotConfigured(RuntimeError):
    """Raised when APNs env vars aren't set."""


def _env(name: str) -> Optional[str]:
    v = (os.environ.get(name) or "").strip()
    return v or None


def creds() -> Dict[str, str]:
    team   = _env("APPLE_TEAM_ID")
    kid    = _env("APPLE_KEY_ID")
    kp     = _env("APPLE_KEY_PATH")
    bundle = _env("APPLE_BUNDLE_ID")
    if not (team and kid and kp and bundle):
        raise APNsNotConfigured(
            "Missing APPLE_TEAM_ID / APPLE_KEY_ID / APPLE_KEY_PATH / "
            "APPLE_BUNDLE_ID")
    if not os.path.exists(kp):
        raise APNsNotConfigured(f"APPLE_KEY_PATH not on disk: {kp}")
    return {"team_id": team, "key_id": kid, "key_path": kp,
              "bundle_id": bundle}


def is_configured() -> bool:
    try:
        creds()
        return True
    except APNsNotConfigured:
        return False


def apns_env() -> str:
    env = (os.environ.get("APNS_ENV") or "sandbox").lower()
    return env if env in APNS_HOSTS else "sandbox"


def apns_host() -> str:
    return APNS_HOSTS[apns_env()]


def _load_p8(path: str) -> str:
    with open(path, "r") as f:
        return f.read()


def make_apns_jwt(*, force_refresh: bool = False) -> str:
    """Mint (or reuse cached) JWT signed with our .p8 ES256 key."""
    now = time.time()
    cached = _jwt_cache.get("token")
    minted_at = _jwt_cache.get("minted_at") or 0.0
    if cached and not force_refresh and (now - minted_at) < APNS_JWT_TTL_SEC:
        return cached
    c = creds()
    payload = {"iss": c["team_id"], "iat": int(now)}
    headers = {"kid": c["key_id"], "alg": "ES256"}
    tok = jwt.encode(payload, _load_p8(c["key_path"]),
                              algorithm="ES256", headers=headers)
    _jwt_cache.update({"token": tok, "minted_at": now})
    return tok


async def send_push(*, device_token: str, title: str, body: str,
                              deep_link: Optional[str] = None,
                              campaign_id: Optional[str] = None,
                              variant_slug: Optional[str] = None,
                              badge: Optional[int] = None,
                              priority: int = 10) -> Dict[str, Any]:
    """Send one APNs alert to a single device token. Returns
    `{ok, status_code, apns_id?, reason?}`."""
    c = creds()
    payload = {
        "aps": {
            "alert": {"title": title, "body": body},
            "sound": "default",
        },
        "campaign_id": campaign_id,
        "deep_link": deep_link or "/",
        "variant_slug": variant_slug,
    }
    if badge is not None:
        payload["aps"]["badge"] = int(badge)
    url = f"{apns_host()}/3/device/{device_token}"
    headers = {
        "authorization": f"bearer {make_apns_jwt()}",
        "apns-topic":       c["bundle_id"],
        "apns-push-type":   "alert",
        "apns-priority":    str(priority),
    }
    try:
        async with httpx.AsyncClient(http2=True, timeout=10) as cli:
            r = await cli.post(url, json=payload, headers=headers)
        ok = r.status_code == 200
        result: Dict[str, Any] = {
            "ok": ok,
            "status_code": r.status_code,
            "apns_id": r.headers.get("apns-id"),
            "env": apns_env(),
        }
        if not ok:
            try:
                result["reason"] = (r.json() or {}).get("reason")
            except Exception:
                result["reason"] = r.text[:200]
            logger.warning("APNs send failed token=%s… code=%d reason=%s",
                                device_token[:12], r.status_code,
                                result.get("reason"))
        return result
    except Exception as e:
        logger.warning("APNs HTTP/2 send raised: %s", e)
        return {"ok": False, "error": str(e)[:200], "env": apns_env()}


async def probe() -> Dict[str, Any]:
    """Mint a fresh JWT to confirm key + env are wired up."""
    try:
        tok = make_apns_jwt(force_refresh=True)
        return {"ok": True, "jwt_len": len(tok),
                  "env": apns_env(),
                  "bundle_id": creds()["bundle_id"]}
    except APNsNotConfigured as e:
        return {"ok": False, "error": "not_configured", "detail": str(e)}
    except Exception as e:
        return {"ok": False, "error": "probe_failed",
                  "detail": str(e)[:200]}
