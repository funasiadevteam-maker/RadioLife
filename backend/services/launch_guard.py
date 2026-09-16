"""Business Setup Mode — soft-launch launch gate.

Central launch config + a Starlette middleware that, WHEN an admin turns on
"Business Setup Mode", returns HTTP 423 (Locked) for consumer `/api`
endpoints to any caller lacking bypass (admin, an approved business, or a
valid preview token).  Default is OFF → the middleware is a cheap no-op
passthrough, so the running app is unchanged until the toggle is flipped.
"""
from __future__ import annotations

import datetime as _dt
import time
from typing import Optional, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

LAUNCH_KEY = "launch"

DEFAULT_SETTINGS = {
    "key": LAUNCH_KEY,
    "business_setup_mode_enabled": False,
    "waitlist_enabled": True,
    "offer_months": 6,
    "launch_at": None,
}

# When Business Setup Mode is ON, these /api prefixes stay OPEN to everyone
# (auth, business signup/portal, merchant onboarding + soft-launch claim,
# waitlist, launch status, preview redemption, admin tools, partner API,
# payments/webhooks, health, geo).
OPEN_PREFIXES = (
    "/api/launch",
    "/api/waitlist",
    "/api/auth",
    "/api/users",
    "/api/business",
    "/api/merchant",
    "/api/business-categories",
    "/api/admin",
    "/api/v1",
    "/api/stripe",
    "/api/webhooks",
    "/api/health",
    "/api/geo",
    "/api/shell/landing-event",
    "/api/shell/prefs",
    "/api/openapi.json",
    "/api/docs",
    "/api/redoc",
)

_CACHE = {"ts": 0.0, "val": None}
_TTL = 10.0


async def get_launch_settings(db) -> dict:
    """Cached read of the singleton launch config (10s TTL)."""
    now = time.time()
    if _CACHE["val"] is not None and (now - _CACHE["ts"]) < _TTL:
        return _CACHE["val"]
    doc = None
    try:
        doc = await db.platform_settings.find_one({"key": LAUNCH_KEY})
    except Exception:
        doc = None
    out = dict(DEFAULT_SETTINGS)
    if doc:
        out["business_setup_mode_enabled"] = bool(doc.get("business_setup_mode_enabled", False))
        out["waitlist_enabled"] = bool(doc.get("waitlist_enabled", True))
        try:
            out["offer_months"] = int(doc.get("offer_months", 6) or 6)
        except Exception:
            out["offer_months"] = 6
        out["launch_at"] = doc.get("launch_at")
    _CACHE["val"] = out
    _CACHE["ts"] = now
    return out


def bust_launch_cache() -> None:
    _CACHE["val"] = None
    _CACHE["ts"] = 0.0


async def valid_preview_token(db, token: str) -> bool:
    if not token:
        return False
    try:
        doc = await db.preview_tokens.find_one({"token": token})
    except Exception:
        return False
    if not doc or doc.get("revoked"):
        return False
    exp = doc.get("expires_at")
    if exp:
        try:
            if isinstance(exp, str):
                exp = _dt.datetime.fromisoformat(exp.replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=_dt.timezone.utc)
            if exp < _dt.datetime.now(_dt.timezone.utc):
                return False
        except Exception:
            pass
    mu = int(doc.get("max_uses") or 0)
    if mu and int(doc.get("uses", 0)) >= mu:
        return False
    return True


async def is_business_user(db, user: dict) -> bool:
    if not user:
        return False
    if user.get("is_business") or "business" in (user.get("roles") or []):
        return True
    uid = user.get("user_id")
    try:
        if await db.businesses.find_one({"owner_user_id": uid, "active": True}):
            return True
    except Exception:
        pass
    try:
        prof = await db.marketplace_profiles.find_one({"owner_user_id": uid})
        if prof and (prof.get("subscription_active")
                     or prof.get("status") == "approved"
                     or (prof.get("soft_launch_offer") or {}).get("status") == "active"):
            return True
    except Exception:
        pass
    return False


async def resolve_bypass(request, db) -> Tuple[bool, Optional[str]]:
    """Return (has_bypass, reason)."""
    # 1) preview token (cookie or header) — cheapest, anonymous-friendly
    token = (request.cookies.get("rl_preview_token")
             or request.headers.get("x-preview-token") or "")
    if token and await valid_preview_token(db, token):
        return True, "token"
    # 2) authenticated admin / business
    try:
        from auth import _resolve_user_from_request
        user = await _resolve_user_from_request(request)
    except Exception:
        user = None
    if user:
        if user.get("role") == "admin":
            return True, "admin"
        if await is_business_user(db, user):
            return True, "business"
    return False, None


def _is_open_path(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in OPEN_PREFIXES)


class LaunchGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api"):
            return await call_next(request)
        db = getattr(request.app.state, "db", None)
        if db is None:
            return await call_next(request)
        settings = await get_launch_settings(db)
        if not settings.get("business_setup_mode_enabled"):
            return await call_next(request)
        if _is_open_path(path):
            return await call_next(request)
        ok, _reason = await resolve_bypass(request, db)
        if ok:
            return await call_next(request)
        return JSONResponse(
            status_code=423,
            content={"detail": {
                "code": "business_setup_mode",
                "message": ("RadioLife is in Business Setup Mode — the "
                            "listener experience is launching soon."),
            }},
        )
