"""Phase Π+2 — Tigris URL resolver.

Maps a `/api/static/...` URL to an inferred Tigris key, HEADs Tigris to
confirm the object exists, and returns an HTTPS URL the browser can
fetch directly.  Result is cached in-process for an hour so we don't
hammer the bucket on every 404.

This is the brain behind the `TigrisFallbackStaticFiles` mount class
in `services/static_fallback.py`.  Both that class AND the track-
playback hotfix in server.py funnel through here so prod stays stateless.

URL strategy (2026-06-20):  the `bigfm-storage` bucket is created
PRIVATE by Tigris and there is no S3-compatible API to flip it to
public-read (`put_bucket_acl`, `put_bucket_policy`, and the
`X-Tigris-Visibility: public` header all return 200 OK but the bucket
remains anonymously inaccessible — the flip requires the Tigris
dashboard).  We therefore mint **presigned URLs** (7-day TTL) for
every fallback redirect.  Browsers / edge caches respect the 6-hour
Cache-Control on the 302 so the cached URL is always well within its
signing window (1 day of headroom).  If the bucket is later flipped
public via the dashboard, swap the resolver back to the unsigned
public URL form without touching any callers.
"""
from __future__ import annotations

import logging
import os
import time
from threading import Lock
from typing import Optional

log = logging.getLogger("bigfm.tigris_resolver")

# URL-prefix → local directory (mirrored from the StaticFiles mounts in
# server.py).  When the local file is missing we strip the URL prefix
# and look up the corresponding object at `tigris_key_prefix/<rest>`.
#
# `tigris_key_prefix` is what we use as the Tigris key root for that
# mount.  Two flavours:
#   • `/api/static/<sub>` → local `/app/backend/static/<sub>` →
#       Tigris key `static/<sub>/<rest>`
#   • `/api/static/persona_samples` → local `/app/backend/storage/persona_samples` →
#       Tigris key `storage/persona_samples/<rest>`
#
# Order matters: the longest matching URL prefix wins.
MOUNT_MAP: dict[str, tuple[str, str]] = {
    # url_prefix                                            (local_dir,                                                          tigris_prefix)
    "/api/static/channel_thumbnails":         ("/app/backend/static/channel_thumbnails",          "static/channel_thumbnails"),
    "/api/static/ad_creatives":                      ("/app/backend/static/ad_creatives",                      "static/ad_creatives"),
    "/api/static/station_artwork":                ("/app/backend/static/station_artwork",                "static/station_artwork"),
    "/api/static/shoppable_cards":                ("/app/backend/static/shoppable_cards",                "static/shoppable_cards"),
    "/api/static/city_stamps":                      ("/app/backend/static/city_stamps",                      "static/city_stamps"),
    "/api/static/landing_images":                ("/app/backend/static/landing_images",                "static/landing_images"),
    "/api/static/game_thumbnails":                ("/app/backend/static/game_thumbnails",                "static/game_thumbnails"),
    "/api/static/station_logos_scraped":  ("/app/backend/static/station_logos_scraped",  "static/station_logos_scraped"),
    "/api/static/persona_samples":                ("/app/backend/storage/persona_samples",              "storage/persona_samples"),
    "/api/static/news_clips":                          ("/app/backend/storage/news_clips",                      "storage/news_clips"),
    "/api/static/rj_segments":                      ("/app/backend/storage/rj_segments",                      "storage/rj_segments"),
}


def _bucket_public_base() -> str:
    """Tigris HTTPS endpoint base: `<endpoint>/<bucket>`.  Used by both
    the (deprecated) anonymous-public URL path AND the presigned-URL
    path — boto3 builds presigned URLs that target this same base.

    e.g. https://fly.storage.tigris.dev/bigfm-storage/static/foo.webp
    """
    endpoint = (os.environ.get("TIGRIS_ENDPOINT_URL")
                            or "https://fly.storage.tigris.dev").rstrip("/")
    bucket = os.environ.get("TIGRIS_BUCKET") or "bigfm-storage"
    return f"{endpoint}/{bucket}"


# Presigned-URL TTL.  Tigris/S3 signature v4 max is 7 days (604_800s).
# We pick 7 days so the embedded URL has plenty of headroom over the
# 6-hour 302 Cache-Control on the fallback redirect.
_PRESIGN_TTL_SECONDS = int(os.environ.get("TIGRIS_PRESIGN_TTL_SECONDS")
                                                        or 604_800)


# ─────────── HEAD-existence cache (TTL 1h) ───────────────────────
_EXISTS_CACHE: dict[str, tuple[float, bool]] = {}
_CACHE_TTL = 3600.0
_CACHE_LOCK = Lock()

# Fallback-hit counter (for /api/admin/system/health asset_migration stats).
_FALLBACK_HITS_TODAY: dict[str, int] = {}  # date string → count


def _today_key() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _record_fallback_hit() -> None:
    k = _today_key()
    _FALLBACK_HITS_TODAY[k] = _FALLBACK_HITS_TODAY.get(k, 0) + 1


def fallback_hits_today() -> int:
    return _FALLBACK_HITS_TODAY.get(_today_key(), 0)


def fallback_hits_summary() -> dict:
    """Snapshot of fallback-hit counters for the health endpoint."""
    today = _today_key()
    return {
        "today":              _FALLBACK_HITS_TODAY.get(today, 0),
        "lifetime":      int(sum(_FALLBACK_HITS_TODAY.values())),
        "tracked_days": len(_FALLBACK_HITS_TODAY),
        "cache_entries": len(_EXISTS_CACHE),
        "cache_ttl_seconds": int(_CACHE_TTL),
    }


def _tigris_head(key: str) -> bool:
    with _CACHE_LOCK:
        hit = _EXISTS_CACHE.get(key)
        if hit and (time.monotonic() - hit[0]) < _CACHE_TTL:
            return hit[1]
    try:
        from services.object_storage import get_storage
        st = get_storage(force_backend="tigris")
        present = st.exists(key=key)
    except Exception as e:
        log.warning("[tigris_resolver] HEAD %s failed: %s", key, e)
        present = False
    with _CACHE_LOCK:
        _EXISTS_CACHE[key] = (time.monotonic(), present)
    return present


def resolve_static_url_to_tigris(static_url_path: str) -> Optional[str]:
    """Input: `/api/static/channel_thumbnails/foo.webp`
    Output: full Tigris HTTPS URL (presigned) if the object exists, else None.

    Used by the StaticFiles fallback subclass when local disk doesn't
    have the file.  Increments the fallback-hit counter on success."""
    # Find the longest matching mount prefix.
    matched_prefix = None
    for prefix in sorted(MOUNT_MAP, key=len, reverse=True):
        if static_url_path.startswith(prefix + "/"):
            matched_prefix = prefix
            break
    if not matched_prefix:
        return None
    rest = static_url_path[len(matched_prefix) + 1:]    # strip "<prefix>/"
    _, tigris_prefix = MOUNT_MAP[matched_prefix]
    key = f"{tigris_prefix}/{rest}".strip("/")
    if not _tigris_head(key):
        return None
    _record_fallback_hit()
    return public_url_for_key(key)


def resolve_local_path_to_tigris_key(local_path: str) -> Optional[str]:
    """Input: `/app/backend/storage/tracks/abc.mp3`
    Output: `storage/tracks/abc.mp3` (no HEAD check, no URL building).

    Pure path transform — caller decides whether to HEAD or just use it.
    """
    p = local_path or ""
    for root, prefix in (
        ("/app/backend/static/",   "static/"),
        ("/app/backend/storage/", "storage/"),
    ):
        if p.startswith(root):
            return prefix + p[len(root):]
    return None


def public_url_for_key(key: str) -> str:
    """Build a fallback-redirect URL for `key`.

    Despite the legacy name, this **returns a presigned URL** (7-day TTL)
    because the `bigfm-storage` bucket is private at the Tigris infra
    layer and cannot be flipped via S3 API.  If the bucket is later made
    public via the Tigris dashboard, swap the body for the unsigned form:
        return f"{_bucket_public_base()}/{key}"
    """
    try:
        from services.object_storage import get_storage
        st = get_storage(force_backend="tigris")
        # boto3 presign — includes signature, expiry, credential scope.
        return st.get_signed_url(key=key, expires_in=_PRESIGN_TTL_SECONDS)
    except Exception as e:
        # If presigning fails for any reason, fall back to the unsigned
        # public URL form — better to return a 403 than crash the request.
        log.warning("[tigris_resolver] presign %s failed: %s — "
                              "falling back to unsigned URL", key, e)
        return f"{_bucket_public_base()}/{key}"


def warm_exists_cache(keys: list[str]) -> None:
    """Pre-warm the HEAD cache (used post-migration to seed the
    in-process cache without doing per-request HEADs)."""
    for k in keys:
        _tigris_head(k)
