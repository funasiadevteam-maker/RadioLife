"""RadioLife Phase 13d — region awareness layer.

Reads two env vars:
  BIGFM_REGION         — geographic tag (default 'ae-uae'; e.g. 'us-east',
                                  'eu-west', 'sg-asia'). Surfaces in the
                                  ``X-RadioLife-Region`` response header and
                                  in every structured log line.
  BIGFM_REGION_ROLE    — 'primary' (default) or 'replica'. A replica region
                                  runs identical code but is downstream of a primary
                                  for writes; we still serve reads locally and
                                  forward writes when ``role=replica``.

The module never talks to Mongo directly — it is pure config + middleware.
"""
from __future__ import annotations
import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

log = logging.getLogger("bigfm.region")

_DEFAULT_REGION = "ae-uae"
_DEFAULT_ROLE   = "primary"


def current_region() -> str:
    return (os.environ.get("BIGFM_REGION") or _DEFAULT_REGION).lower()


def current_role() -> str:
    role = (os.environ.get("BIGFM_REGION_ROLE") or _DEFAULT_ROLE).lower()
    return role if role in ("primary", "replica") else _DEFAULT_ROLE


def is_primary() -> bool:
    return current_role() == "primary"


def is_replica_region() -> bool:
    return current_role() == "replica"


def audio_bucket_region() -> str:
    """Returns the bucket region tag for audio assets.

    Defaults to the runtime region. Documented but not yet wired into the
    storage layer — the storage layer still writes to local disk in preview.
    """
    return (os.environ.get("BIGFM_AUDIO_BUCKET_REGION")
                or current_region())


# ─── Middleware ──────────────────────────────────────────────────────────
class RegionHeaderMiddleware(BaseHTTPMiddleware):
    """Adds X-RadioLife-Region to every response and X-RadioLife-Region-Role.

    Also attaches the region to `request.state.region` so downstream
    logging / route code can read it without re-reading the env.
    """

    async def dispatch(self, request: Request, call_next):
        region = current_region()
        role   = current_role()
        request.state.region      = region
        request.state.region_role = role
        try:
            response: Response = await call_next(request)
        except Exception:
            # Region tags must propagate even on error paths so the client
            # can observe which region rejected the request.
            log.exception("region middleware caught upstream error "
                                "region=%s role=%s path=%s",
                                region, role, request.url.path)
            raise
        response.headers["X-RadioLife-Region"]      = region
        response.headers["X-RadioLife-Region-Role"] = role
        return response


__all__ = [
    "current_region", "current_role", "is_primary", "is_replica_region",
    "audio_bucket_region", "RegionHeaderMiddleware",
]
