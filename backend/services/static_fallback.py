"""Phase Π+2 — Tigris-aware StaticFiles drop-in replacement.

`TigrisFallbackStaticFiles(directory=…, tigris_prefix=…)` behaves
exactly like Starlette's `StaticFiles` for files that exist on local
disk.  When the local file is missing it issues a 302 redirect to the
corresponding Tigris HTTPS URL (presigned — see `tigris_url_resolver`
for why) if the object exists — otherwise it returns the usual 404.

This is the keystone of the "stateless deploy" property: fresh
containers with empty local-disk volumes will transparently serve
every asset from Tigris.
"""
from __future__ import annotations

import logging
from pathlib import PurePosixPath
from typing import Optional

# Use Starlette's HTTPException — that's the one StaticFiles raises.
# fastapi.HTTPException is a subclass, but if we import only the
# FastAPI one our `except` clause silently fails to catch the
# Starlette one and the 404 escapes to the global exception handler
# without ever consulting Tigris.
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles
from starlette.responses import RedirectResponse, Response

from services.tigris_url_resolver import (
    public_url_for_key, _tigris_head, _record_fallback_hit,
)

log = logging.getLogger("bigfm.static_fallback")


class TigrisFallbackStaticFiles(StaticFiles):
    """Drop-in replacement for `StaticFiles` with Tigris fallback.

    Args:
        directory:      local mount root (same as StaticFiles).
        tigris_prefix: Tigris key prefix to look under when the local
                                  file is missing.  e.g. "static/channel_thumbnails".
        cache_max_age: seconds for the 302 Cache-Control header
                                  (default 86400 = 1 day; clients re-check daily so
                                  a cache miss after migration self-heals).
    """

    def __init__(self, *, directory: str, tigris_prefix: Optional[str] = None,
                              cache_max_age: int = 86400, **kwargs) -> None:
        super().__init__(directory=directory, **kwargs)
        # Auto-derive tigris_prefix from directory if not given.  Maps:
        #     /app/backend/static/<sub>   → "static/<sub>"
        #     /app/backend/storage/<sub> → "storage/<sub>"
        # Anything else uses the trailing path as-is.
        if tigris_prefix is None:
            d = directory.rstrip("/")
            if "/app/backend/" in d:
                tigris_prefix = d.split("/app/backend/", 1)[1]
            else:
                tigris_prefix = d.lstrip("/")
        self.tigris_prefix = tigris_prefix.strip("/")
        self.cache_max_age = int(cache_max_age)

    async def get_response(self, path: str, scope) -> Response:
        # Try the local-file path first.  Starlette's StaticFiles may
        # either RAISE HTTPException(404) (older versions, and the
        # 'check_dir' branch) or RETURN a Response with status_code==404
        # (the lookup_path branch).  We handle both.  Importantly we
        # catch the **Starlette** HTTPException base class — `fastapi.
        # HTTPException` is a subclass and wouldn't catch the raw form.
        try:
            resp = await super().get_response(path, scope)
            if resp.status_code != 404:
                return resp
        except StarletteHTTPException as e:
            if e.status_code != 404:
                raise
            # fall through to Tigris fallback

        # `path` arrives without a leading slash, e.g.
        # "channel_thumbnails/foo.webp" but the URL prefix is already
        # stripped by Starlette.  The relative-to-mount part IS `path`.
        rel = PurePosixPath(path).as_posix().lstrip("/")
        if not rel:
            return Response("Not Found", status_code=404)

        key = f"{self.tigris_prefix}/{rel}"
        if not _tigris_head(key):
            log.info("[fallback_static] miss prefix=%s rel=%s key=%s",
                          self.tigris_prefix, rel, key)
            return Response("Not Found", status_code=404)

        # Hit — 302 to the Tigris URL.  `public_url_for_key` returns a
        # 7-day presigned URL (bucket is private at the infra layer).
        _record_fallback_hit()
        tigris_url = public_url_for_key(key)
        log.info("[fallback_static] hit prefix=%s rel=%s → tigris",
                      self.tigris_prefix, rel)
        return RedirectResponse(
            tigris_url, status_code=302,
            headers={"Cache-Control": f"public, max-age={self.cache_max_age}"})
