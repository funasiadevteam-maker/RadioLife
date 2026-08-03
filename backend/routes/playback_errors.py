"""POST /api/playback-errors — client-reported live-stream failures.

Purpose:
- Give the frontend a single dead-letter for `<audio onError>` events
  so we can drive the auto-advance / offline-modal UX.
- Feed those signals into the imported_station_probe failure
  counter so a station observed dead by real users gets flipped to
  `dead` (and drops out of the browse feed) inside a handful of
  clicks — even before the scheduled probe pass would catch it.

Rate limit:
- 60 requests / 60 seconds / client IP (declared via
  services.security_middleware _LIMITS on `/api/playback-errors`).

Privacy:
- We NEVER log the full upstream stream URL.  hostname is enough.
- user_id is optional; anonymous errors are accepted and counted.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from services.imported_station_probe import (
    FAILURE_THRESHOLD, bump_failure_from_client,
)

log = logging.getLogger("bigfm.playback_errors")

router = APIRouter(prefix="/api", tags=["playback-errors"])


class PlaybackErrorIn(BaseModel):
    station_id:      str
    error_code:      Optional[str] = Field(default=None,
                                            description=("Browser MediaError "
                                                          "code / http status "
                                                          "/ synthetic label"))
    upstream_status: Optional[int] = None
    hostname:        Optional[str] = None
    source:          Optional[str] = Field(
        default=None,
        description="\"imported\" | \"bigfm_ai\" | \"community\"")


def _client_ip(request: Request) -> str:
    return (request.client.host if request.client else None) or "unknown"


def _sanitize_hostname(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip().lower()
    # If the client passed a full URL, extract hostname; if it
    # passed a bare hostname, keep as-is.  Never store the full URL.
    if "://" in raw:
        try:
            return (urlparse(raw).hostname or "").lower() or None
        except Exception:
            return None
    # Basic hostname sanity — reject anything with a slash or space.
    if "/" in raw or " " in raw:
        return None
    return raw or None


@router.post("/playback-errors")
async def report_playback_error(payload: PlaybackErrorIn,
                                 request: Request):
    """Record a client-side playback failure and, for imp_* stations,
    bump the shared probe failure counter so we can promote to dead.

    Fire-and-forget from the frontend's point of view — response is
    a compact ack, never blocks the audio element.
    """
    db = request.app.state.db
    now = datetime.now(timezone.utc)
    host_clean = _sanitize_hostname(payload.hostname)

    doc = {
        "station_id":      payload.station_id,
        "error_code":      (payload.error_code or "")[:64] or None,
        "upstream_status": payload.upstream_status,
        "hostname":        host_clean,
        "source":          (payload.source or "")[:32] or None,
        "client_ip":       _client_ip(request),
        "user_agent":      (request.headers.get("user-agent")
                            or "")[:200],
        "ts":              now,
    }

    try:
        await db.playback_errors.insert_one(doc)
    except Exception as e:                    # noqa: BLE001 — never fatal
        log.warning("[playback-error] mongo insert failed: %s", e)

    # Only imported stations feed the probe counter; AI / community
    # channels have their own playback paths and error surfaces.
    new_status = None
    if payload.station_id and payload.station_id.startswith("imp_"):
        try:
            new_status = await bump_failure_from_client(
                db, payload.station_id)
        except Exception as e:                # noqa: BLE001
            log.warning("[playback-error] probe bump failed: %s", e)

    log.info("[playback-error] sid=%s host=%s code=%s status=%s → %s",
             payload.station_id, host_clean or "?",
             doc["error_code"] or "?",
             payload.upstream_status if payload.upstream_status is not None
             else "?",
             new_status or "unchanged")

    return {"ok":                 True,
            "new_health_status":  new_status,
            "failure_threshold":  FAILURE_THRESHOLD}


__all__ = ["router"]
