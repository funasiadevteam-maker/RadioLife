"""Phase 42-F.6 — Community track usage endpoint + imported-station source.

Add-on endpoints layered on top of `routes/station_tracks.py`:

  • GET  /api/stations/{slug}/usage
        Returns `{current, limit, tier, remaining}` for the owner's
        station pool.  Hard-caps:
            free      → 10 tracks
            premium → 100 tracks

  • POST /api/stations/{slug}/tracks/from-imported
        Wires an imported live-radio station (`imp_*`) as a track-source
        for the community station.  Inserts a synthetic
        `tracks` row when the live stream isn't already cataloged, then
        a `station_tracks` join row pointing at it.  Does NOT go
        through the moderation pipeline (live streams aren't UGC).

Limits are also enforced from `add_tracks` and `upload_track` via a
shared `_assert_under_pool_cap` helper that this module exposes.  The
import in `station_tracks.py` is best-effort — if this file is missing
the legacy endpoints continue to work without quotas (we just lose F.6
enforcement until a redeploy).
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user

log = logging.getLogger("bigfm.community_library")

router = APIRouter(prefix="/api/stations",
                                          tags=["community-library"])

POOL_LIMIT_FREE = 10
POOL_LIMIT_PREMIUM = 100


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tier_for_user(user: dict) -> str:
    return "premium" if user.get("is_premium") else "free"


def _limit_for_tier(tier: str) -> int:
    return POOL_LIMIT_PREMIUM if tier == "premium" else POOL_LIMIT_FREE


async def _pool_size(db, station_id: str) -> int:
    return await db.station_tracks.count_documents({"station_id": station_id})


async def assert_under_pool_cap(db, *, station_id: str, user: dict,
                                                                          incoming: int = 1) -> dict:
    """Raises HTTP 400 `pool_cap_reached` when adding `incoming` more
    tracks would exceed the user's tier cap.  Returns the current usage
    snapshot otherwise (so callers can include it in success payloads).
    """
    tier = _tier_for_user(user)
    limit = _limit_for_tier(tier)
    current = await _pool_size(db, station_id)
    if current + incoming > limit:
        raise HTTPException(
            400,
            {"code": "pool_cap_reached",
              "message": (f"{tier.capitalize()} stations can hold up to "
                                  f"{limit} tracks. You have {current}; this "
                                  f"add would bring you to "
                                  f"{current + incoming}."),
              "current": current, "limit": limit, "tier": tier,
              "incoming": incoming})
    return {"current": current, "limit": limit, "tier": tier,
                  "remaining": max(0, limit - current)}


async def _get_owned_station(db, slug: str, user: dict) -> dict:
    s = await db.community_radio_stations.find_one({"slug": slug})
    if not s:
        raise HTTPException(404, {"code": "station_not_found"})
    if s.get("owner_user_id") != user.get("user_id"):
        if not user.get("is_admin"):
            raise HTTPException(403, {"code": "not_station_owner"})
    return s


@router.get("/{slug}/usage")
async def station_usage(slug: str, request: Request,
                                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    s = await _get_owned_station(db, slug, user)
    tier = _tier_for_user(user)
    limit = _limit_for_tier(tier)
    current = await _pool_size(db, s["station_id"])
    return {"slug": slug, "station_id": s["station_id"],
                  "tier": tier, "limit": limit,
                  "current": current,
                  "remaining": max(0, limit - current),
                  "by_source": await _by_source(db, s["station_id"])}


async def _by_source(db, station_id: str) -> dict:
    """Breakdown by `source` field on station_tracks so the UI can show
    how many came from upload vs catalog vs imported."""
    out: dict = {"catalog_add": 0, "upload": 0, "upload_dedupe": 0,
                          "imported_station": 0, "other": 0}
    async for r in db.station_tracks.aggregate([
            {"$match": {"station_id": station_id}},
            {"$group": {"_id": "$source", "n": {"$sum": 1}}}]):
        bucket = r["_id"] or "other"
        if bucket in out:
            out[bucket] = r["n"]
        else:
            out["other"] += r["n"]
    return out


class FromImportedIn(BaseModel):
    imported_station_id: str = Field(..., min_length=1, max_length=64)


@router.post("/{slug}/tracks/from-imported")
async def add_from_imported(slug: str, body: FromImportedIn,
                                                          request: Request,
                                                          user: dict = Depends(current_user)):
    """Pin an imported live-radio stream as a 'track' on this community
    station. The synthetic `tracks` row has duration_sec=0 and a
    `source_kind=live_stream` marker so the radio engine can branch on
    it (queue builder ignores live_stream rows; they're useful only
    for cross-promo cards and the upcoming 'Live source' tab)."""
    db = request.app.state.db
    s = await _get_owned_station(db, slug, user)
    snapshot = await assert_under_pool_cap(
        db, station_id=s["station_id"], user=user, incoming=1)
    # `snapshot` discarded — we re-snapshot at the end of the function via
    # _post_action_snapshot so the response reflects the post-insert state.
    del snapshot

    imp = await db.imported_radio_stations.find_one(
        {"id": body.imported_station_id})
    if not imp:
        raise HTTPException(404, {"code": "imported_station_not_found"})
    if not imp.get("active"):
        raise HTTPException(400, {"code": "imported_station_inactive"})

    # Synthesize a tracks row keyed off the imported_station_id so we
    # don't pollute the catalog with duplicates on repeat adds.
    track_id = f"liv_{body.imported_station_id}"
    await db.tracks.update_one(
        {"_id": track_id},
        {"$setOnInsert": {
            "_id": track_id,
            "title":  imp.get("name") or "Live Stream",
            "artist": imp.get("country") or "Live Radio",
            "album":  "Live Source",
            "duration_sec": 0,
            "language": (imp.get("language") or "english"),
            "genre":  "live_stream",
            "mood":  "live",
            "energy_level": "medium",
            "year":  None,
            "status": "active",
            "explicit_flag": False,
            "source_kind": "live_stream",
            "live_stream_url": imp.get("stream_url"),
            "live_country":     imp.get("country"),
            "created_at": _now_iso(),
        }},
        upsert=True)

    # Compute next sort_index.
    last = await db.station_tracks.find_one(
        {"station_id": s["station_id"]}, sort=[("sort_index", -1)])
    next_sort = ((last or {}).get("sort_index") or 0) + 1
    join_id = f"stt_{s['station_id']}_{track_id}"
    try:
        await db.station_tracks.insert_one({
            "_id": join_id,
            "station_id": s["station_id"],
            "station_slug": s["slug"],
            "track_id": track_id,
            "added_at": _now_iso(),
            "added_by": user["user_id"],
            "sort_index": next_sort,
            "source": "imported_station",
            "imported_station_id": body.imported_station_id,
        })
    except Exception as e:
        if "duplicate key" in str(e).lower():
            return {"ok": True, "track_id": track_id,
                          "already_on_station": True,
                          **(await _post_action_snapshot(db, s, user))}
        raise

    return {"ok": True, "track_id": track_id,
                  "already_on_station": False,
                  **(await _post_action_snapshot(db, s, user))}


async def _post_action_snapshot(db, station: dict, user: dict) -> dict:
    tier = _tier_for_user(user)
    limit = _limit_for_tier(tier)
    current = await _pool_size(db, station["station_id"])
    return {"current": current, "limit": limit, "tier": tier,
                  "remaining": max(0, limit - current)}
