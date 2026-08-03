"""Phase FUN.1-v2 — Geo helpers + priority sort.

`get_user_region(user, request) -> "AE" | "US" | "OTHER"`
    Priority: user.country → geoip → default "AE".

`sort_with_flagship_priority(stations, user_region)`
    Rank 0: flagship AND matches user_region
    Rank 1: flagship other region
    Rank 2: priority Dubai (is_priority=True)
    Rank 3: everything else
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("bigfm.geo")

# Map ISO2 country code → normalized region key.
_COUNTRY_TO_REGION = {
    "AE": "AE", "US": "US",
}


def _region_from_country(cc: Optional[str]) -> str:
    if not cc:
        return "OTHER"
    return _COUNTRY_TO_REGION.get(cc.upper(), "OTHER")


def _region_from_ip(request) -> Optional[str]:
    """Try geoip via lightweight httpx call to ipapi.co (no key needed for
    minimal usage — best effort).  Returns None on any failure."""
    if not request:
        return None
    try:
        ip = None
        # Prefer X-Forwarded-For (behind ingress).
        xff = request.headers.get("x-forwarded-for")
        if xff:
            ip = xff.split(",")[0].strip()
        else:
            client = getattr(request, "client", None)
            ip = getattr(client, "host", None) if client else None
        if not ip or ip.startswith(("10.", "172.", "192.168.", "127.")):
            return None
        # Blocking-safe: use httpx sync in a thread if needed.  We keep it
        # simple + short-timeout; caller can await this via to_thread.
        import httpx
        r = httpx.get(f"https://ipapi.co/{ip}/country/", timeout=1.5)
        if r.status_code != 200:
            return None
        cc = r.text.strip().upper()
        return _region_from_country(cc)
    except Exception as e:
        logger.debug("[geo] ip lookup failed: %s", e)
        return None


async def get_user_region(user: Optional[dict], request=None) -> str:
    """Resolve user's region to AE / US / OTHER.

    1. Explicit `user.country` (or `user.country_code`).
    2. GeoIP from request.  (Best-effort, short timeout.)
    3. Default "AE" (primary market)."""
    if user:
        cc = user.get("country_code") or user.get("country") or ""
        # Full names → ISO2 heuristic.
        _NAME_MAP = {"united arab emirates": "AE", "uae": "AE",
                                  "united states": "US", "usa": "US", "us": "US"}
        if len(cc) == 2:
            r = _region_from_country(cc)
            if r != "OTHER":
                return r
        elif cc.lower() in _NAME_MAP:
            return _NAME_MAP[cc.lower()]

    # GeoIP fallback (best effort, non-fatal).
    try:
        import asyncio
        r = await asyncio.to_thread(_region_from_ip, request)
        if r and r != "OTHER":
            return r
    except Exception:
        pass

    # Default to AE (primary market).
    return "AE"


def _rank(station: dict, user_region: str) -> int:
    if station.get("is_flagship"):
        if station.get("flagship_region") == user_region:
            return 0
        return 1
    if station.get("is_priority"):
        return 2
    return 3


def sort_with_flagship_priority(stations: list, user_region: str = "AE") -> list:
    """Stable sort — flagships first (region-matched → other), then priority
    Dubai stations, then everything else.  Within each rank, preserve
    upstream ordering (or flagship_priority ↓ for flagship-rank ties)."""
    def _key(s):
        r = _rank(s, user_region)
        # Higher priority number = earlier within same rank.
        prio = -(int(s.get("flagship_priority") or 0)) if r in (0, 1) else 0
        return (r, prio)
    return sorted(stations, key=_key)
