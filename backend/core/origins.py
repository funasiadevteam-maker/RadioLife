"""Shared resolver for the public site origin used in Stripe redirect URLs.

Prevents the `origin_url_required` class of error: even when a client forgets
to send `origin_url`, we fall back to the browser's Origin/Referer header, then
the configured public base URL, then the request base URL. Always returns a
clean `scheme://host` (no trailing slash) or "" if nothing usable is found.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse


def resolve_origin(request=None, body_origin: str | None = None) -> str:
    candidates = [body_origin]
    if request is not None:
        try:
            candidates.append(request.headers.get("origin"))
            candidates.append(request.headers.get("referer"))
        except Exception:
            pass
    candidates.append(os.environ.get("BIGFM_PUBLIC_BASE_URL"))
    if request is not None:
        try:
            candidates.append(str(request.base_url))
        except Exception:
            pass
    for c in candidates:
        if c and str(c).startswith("http"):
            p = urlparse(str(c))
            if p.scheme and p.netloc:
                return f"{p.scheme}://{p.netloc}"
    return ""
