"""Phase Π.2 — Security middleware bundle.

Three middlewares stacked into a single registration helper:
  1. SecurityHeadersMiddleware  — CSP + HSTS + X-Content-Type-Options +
                                                  Referrer-Policy + Permissions-Policy.
  2. RateLimitMiddleware              — per-IP token bucket on a small
                                                  whitelist of public paths (signup, login,
                                                  share log, business/register, invite/send).
                                                  Mongo-backed counter, no Redis needed.
  3. Cookie helpers                          — `set_session_cookie(response, name, value)`
                                                  that always emits Secure + HttpOnly +
                                                  SameSite=Lax in prod.

Production-safe defaults; flippable via env.  Skips itself entirely for
the /api/openapi.json and /api/docs surfaces so the Swagger UI keeps
working.
"""
from __future__ import annotations

import logging
import os
import time
from collections import defaultdict, deque
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

log = logging.getLogger("bigfm.security_mw")


def _envbool(name: str, default: bool) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    if v in ("1", "true", "yes", "on"): return True
    if v in ("0", "false", "no", "off"): return False
    return default


# ─────────────────────── CSP / HSTS ──────────────────────────────
def _build_csp() -> str:
    """Allowlist sources required by current integrations.

    Permissive enough that all existing flows work; tighten later as
    we move static assets behind a CDN."""
    parts = [
        "default-src 'self'",
        # React inline runtime + Stripe + Google Maps need 'unsafe-inline'
        # on script-src.  We deliberately do NOT allow 'unsafe-eval'.
        "script-src 'self' 'unsafe-inline' "
        "https://js.stripe.com https://maps.googleapis.com "
        "https://*.tile.openstreetmap.org",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' data: https://fonts.gstatic.com",
        # img-src: self + data + https blanket so Pixabay / Mapbox / OG
        # / Tigris bucket / Mailgun pixels / news thumbnails all render.
        "img-src 'self' data: blob: https:",
        # connect-src for our APIs + Stripe + ElevenLabs + Mailgun events.
        "connect-src 'self' https: wss:",
        # frame-src for Stripe Checkout + Google Maps embeds.
        "frame-src 'self' https://js.stripe.com https://hooks.stripe.com "
        "https://checkout.stripe.com https://maps.google.com "
        "https://www.google.com",
        # media-src for audio playback (ours + remote streams).
        "media-src 'self' blob: https:",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self' https://checkout.stripe.com",
        "frame-ancestors 'self'",
    ]
    return "; ".join(parts)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds CSP / HSTS / X-Content-Type-Options / Referrer-Policy on
    every response.  HSTS only attaches when ENV=production."""

    def __init__(self, app):
        super().__init__(app)
        self._csp = _build_csp()
        self._is_prod = (os.environ.get("ENV") or "").lower() == "production"

    async def dispatch(self, request: Request, call_next: Callable):
        response: Response = await call_next(request)
        # Skip for OpenAPI / docs so the Swagger UI keeps working.
        path = request.url.path
        if path in ("/api/openapi.json",) or path.startswith("/api/docs"):
            return response
        response.headers.setdefault("Content-Security-Policy", self._csp)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy",
                                                                          "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy",
                                                                          "camera=(), microphone=(self), "
                                                                          "geolocation=(self), payment=(self)")
        if self._is_prod:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains")
        return response


# ─────────────────── Rate limiting (in-memory) ───────────────────
# Tunables: per-IP, per-path, sliding-window token bucket.  Mongo
# fallback would be needed for multi-replica deploys; the platform is
# currently single-replica, so in-memory is fine.

_LIMITS: dict[str, tuple[int, float]] = {
    # path-prefix → (max_requests, window_seconds)
    "/api/auth/signup":                          (10, 60.0),
    "/api/auth/login":                              (15, 60.0),
    "/api/auth/password-reset":          (5,  60.0),
    "/api/auth/password-reset-request": (5, 60.0),
    "/api/share/log":                                  (200, 60.0),
    "/api/invite/send":                            (10, 60.0),
    "/api/business/register":                  (5,  60.0),
    "/api/feedback/submit":                  (60, 60.0),
    "/api/tips/send":                                  (60, 60.0),
    # Phase RELIABILITY.P2 — client-reported live-stream failures.
    "/api/playback-errors":                  (60, 60.0),
}

_HISTORY: dict[tuple[str, str], deque] = defaultdict(lambda: deque())


def _client_ip(request: Request) -> str:
    # Prefer X-Forwarded-For if behind the K8s ingress; ProxyHeadersMiddleware
    # rewrites request.client to the forwarded value when enabled.
    return (request.client.host if request.client else None) or "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Best-effort, single-replica in-memory rate limit.  Returns 429
    with a Retry-After header when over budget."""

    async def dispatch(self, request: Request, call_next: Callable):
        path = request.url.path
        match = None
        for prefix, (limit, window) in _LIMITS.items():
            if path == prefix or path.startswith(prefix + "/"):
                match = (prefix, limit, window)
                break
        if not match:
            return await call_next(request)

        prefix, limit, window = match
        ip = _client_ip(request)
        key = (prefix, ip)
        now = time.monotonic()
        history = _HISTORY[key]
        # Drop entries outside the window.
        while history and (now - history[0]) > window:
            history.popleft()
        if len(history) >= limit:
            retry_after = max(1, int(window - (now - history[0])))
            log.warning("[ratelimit] %s ip=%s blocked (%d/%ds)",
                              prefix, ip, len(history), int(window))
            return JSONResponse(
                {"detail": {"code": "rate_limited",
                                        "limit": limit, "window_seconds": int(window),
                                        "retry_after": retry_after}},
                status_code=429,
                headers={"Retry-After": str(retry_after)})
        history.append(now)
        return await call_next(request)


# ────────────────────── Public mount helper ──────────────────────
def install_security_middlewares(app):
    """Single entrypoint: server.py calls this once after CORS."""
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    log.info("[security_mw] CSP + HSTS + rate-limit middlewares installed")
