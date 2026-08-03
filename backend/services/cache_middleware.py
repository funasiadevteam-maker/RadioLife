"""BigFM Phase 13d — Cache-Control + ETag middleware.

Splits public read-only routes from auth-gated routes:
  * Public routes (channel list, public passport profiles, public
    leaderboards, public business pages, channel discovery) get:
        Cache-Control: public, max-age=60, s-maxage=300, stale-while-revalidate=120
        ETag: "<sha1(body)>"
        + honors If-None-Match (returns 304)
  * Auth-gated routes (any request that arrives with an Authorization
    header or Cookie, OR is in the explicit private prefixes) get:
        Cache-Control: private, no-store
The middleware only acts on GET requests with JSON bodies — websockets,
streaming endpoints (audio, range) are left alone.
"""
from __future__ import annotations
import hashlib
import re
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Path-prefix allow-list for SWR caching. Regexes are anchored.
# Note: we use prefix match — anything starting with these paths benefits
# from the public SWR header. Keep this list TIGHT (no PII surfaces).
PUBLIC_SWR_PATTERNS: Iterable[str] = (
    r"^/api/channels(/|$|\?)",
    r"^/api/channels/list(/|$|\?)",
    r"^/api/public/passport/[^/]+/profile(/|$|\?)",
    r"^/api/public/leaderboards(/|$|\?)",
    r"^/api/public/businesses(/|$|\?)",
    r"^/api/commerce/public(/|$|\?)",
)
_PUBLIC_RE = [re.compile(p) for p in PUBLIC_SWR_PATTERNS]

# Routes that MUST never be cached (admin, auth, write surfaces). These are
# private no matter what — we set `private, no-store`.
PRIVATE_PATTERNS: Iterable[str] = (
    r"^/api/admin/",
    r"^/api/auth/",
    r"^/api/me/",
    r"^/api/billing/",
    r"^/api/billing6/",
)
_PRIVATE_RE = [re.compile(p) for p in PRIVATE_PATTERNS]

# Paths to skip entirely (binary streaming, audio, websockets).
SKIP_PATTERNS: Iterable[str] = (
    r"^/api/stream/",
    r"^/api/audio/",
    r"^/api/segments/",
    r"^/api/files/",
    r"^/api/openapi\.json$",
    r"^/api/docs",
)
_SKIP_RE = [re.compile(p) for p in SKIP_PATTERNS]

PUBLIC_CACHE_HEADER = ("public, max-age=60, s-maxage=300, "
                                  "stale-while-revalidate=120")
PRIVATE_CACHE_HEADER = "private, no-store"


def _is_public(path: str) -> bool:
    return any(rx.search(path) for rx in _PUBLIC_RE)


def _is_private(path: str) -> bool:
    return any(rx.search(path) for rx in _PRIVATE_RE)


def _is_skipped(path: str) -> bool:
    return any(rx.search(path) for rx in _SKIP_RE)


def _etag(body: bytes) -> str:
    return f'W/"{hashlib.sha1(body).hexdigest()}"'


class CacheControlMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if _is_skipped(path):
            return await call_next(request)
        response: Response = await call_next(request)
        if request.method != "GET":
            # Non-GET writes never get caching headers from us.
            return response
        if _is_private(path):
            response.headers["Cache-Control"] = PRIVATE_CACHE_HEADER
            return response
        if not _is_public(path):
            # Default: treat unknown auth-gated surfaces as private.
            if "authorization" in {k.lower() for k in request.headers.keys()} \
                or "cookie" in {k.lower() for k in request.headers.keys()}:
                response.headers["Cache-Control"] = PRIVATE_CACHE_HEADER
            return response
        # ---- public SWR route -----------------------------------------
        # Buffer the body so we can compute an ETag and short-circuit 304.
        body_chunks = []
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
        body = b"".join(body_chunks)
        etag = _etag(body)
        inm = request.headers.get("if-none-match")
        if inm and inm.strip() == etag:
            return Response(
                status_code=304,
                headers={
                    "ETag": etag,
                    "Cache-Control": PUBLIC_CACHE_HEADER,
                    "X-BigFM-Region": response.headers.get("X-BigFM-Region", ""),
                })
        # Rebuild the response with the buffered body so downstream
        # clients see exactly what the route produced — only headers
        # change.
        new_headers = dict(response.headers)
        new_headers["Cache-Control"] = PUBLIC_CACHE_HEADER
        new_headers["ETag"] = etag
        new_headers.pop("content-length", None)
        return Response(content=body,
                              status_code=response.status_code,
                              headers=new_headers,
                              media_type=response.media_type)
