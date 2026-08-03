"""Phase 39 Session 5 — Frequent place detection (DBSCAN-on-grid) +
places routes. All endpoints require location_consent_level >= 3."""
from __future__ import annotations
import hashlib, logging, uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from auth import current_user

router = APIRouter(prefix="/api/places", tags=["places"])
log = logging.getLogger("bigfm.places")

GRID_DECIMALS = 4   # ~11m at equator; we collapse to ~50m via neighbor merge
MIN_SAMPLES   = 5
DBSCAN_EPS    = 2   # in grid cells (Chebyshev distance)
LOOKBACK_DAYS = 30


def _now(): return datetime.now(timezone.utc)


async def _check_consent(db, user, required=3):
    fresh = await db.users.find_one({"user_id": user["user_id"]}) or {}
    cl = int(fresh.get("location_consent_level", 0))
    if cl < required:
        raise HTTPException(403, {"code": "consent_required",
                                                      "required_level": required,
                                                      "current_level": cl})
    return fresh


def _grid_key(lat: float, lng: float):
    return (round(lat, GRID_DECIMALS), round(lng, GRID_DECIMALS))


def _cluster_grid(events: list[dict]) -> list[dict]:
    """DBSCAN-on-grid. Returns list of clusters with centroid, visit_count,
    first_seen, last_seen."""
    # Count visits per grid cell
    cell_counts: dict[tuple, list[dict]] = defaultdict(list)
    for e in events:
        cell_counts[_grid_key(e["lat"], e["lng"])].append(e)
    high = {k: v for k, v in cell_counts.items() if len(v) >= MIN_SAMPLES}
    if not high:
        return []
    # Cluster adjacent high cells (Chebyshev distance ≤ DBSCAN_EPS).
    visited = set()
    clusters: list[list[tuple]] = []
    for cell in high:
        if cell in visited: continue
        stack = [cell]
        cluster = []
        while stack:
            c = stack.pop()
            if c in visited: continue
            visited.add(c)
            cluster.append(c)
            for dx in range(-DBSCAN_EPS, DBSCAN_EPS + 1):
                for dy in range(-DBSCAN_EPS, DBSCAN_EPS + 1):
                    if dx == 0 and dy == 0: continue
                    n = (round(c[0] + dx * 10 ** (-GRID_DECIMALS), GRID_DECIMALS),
                              round(c[1] + dy * 10 ** (-GRID_DECIMALS), GRID_DECIMALS))
                    if n in high and n not in visited:
                        stack.append(n)
        clusters.append(cluster)
    # Build cluster summaries.
    out = []
    for cells in clusters:
        all_evts: list[dict] = []
        for c in cells: all_evts.extend(high[c])
        lats = [e["lat"] for e in all_evts]
        lngs = [e["lng"] for e in all_evts]
        times = [e["captured_at"] for e in all_evts]
        clat = sum(lats) / len(lats); clng = sum(lngs) / len(lngs)
        place_id = "fp_" + hashlib.sha1(
            f"{clat:.4f},{clng:.4f}".encode()).hexdigest()[:12]
        out.append({"place_id": place_id, "lat": clat, "lng": clng,
                              "visit_count": len(all_evts),
                              "first_seen": min(times), "last_seen": max(times),
                              "confidence": "high" if len(all_evts) >= 15
                                                          else "medium" if len(all_evts) >= 8 else "low"})
    return out


async def _places_enrich_label(lat: float, lng: float) -> dict:
    """Best-effort label via maps_client. Falls back to coordinates string."""
    try:
        from services.maps_client import probe_and_decide_client
        client = probe_and_decide_client()
        # MockMapsClient returns deterministic mock places.
        res = client.places_nearby(lat=lat, lng=lng, radius=100)
        if res:
            first = res[0]
            return {"label": first.get("name") or "Detected Place",
                          "category": first.get("category") or first.get("type") or "place"}
    except Exception as e:
        log.warning("[places] enrichment failed: %s", e)
    return {"label": f"Place at {lat:.3f},{lng:.3f}",
                  "category": "place"}


@router.get("/frequent")
async def get_frequent(request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    await _check_consent(db, user)
    out = []
    async for r in db.UserFrequentPlaces.find(
        {"user_id": user["user_id"], "user_hidden": {"$ne": True}}
    ).sort("last_seen", -1):
        r.pop("_id", None); out.append(r)
    return {"count": len(out), "places": out}


@router.post("/frequent/refresh")
async def refresh_frequent(request: Request,
                                                  user: dict = Depends(current_user)):
    db = request.app.state.db
    await _check_consent(db, user)
    cutoff = _now() - timedelta(days=LOOKBACK_DAYS)
    events = [e async for e in db.UserTravelEvents.find(
        {"user_id": user["user_id"], "captured_at": {"$gte": cutoff}})]
    clusters = _cluster_grid(events)
    inserted = updated = 0
    now = _now()
    for c in clusters:
        enrich = await _places_enrich_label(c["lat"], c["lng"])
        existing = await db.UserFrequentPlaces.find_one(
            {"user_id": user["user_id"], "place_id": c["place_id"]})
        doc = {**c, **enrich,
                      "user_id": user["user_id"],
                      "last_refreshed_at": now,
                      "first_seen": c["first_seen"], "last_seen": c["last_seen"]}
        if existing:
            await db.UserFrequentPlaces.update_one(
                {"_id": existing["_id"]}, {"$set": doc})
            updated += 1
        else:
            doc["_id"] = uuid.uuid4().hex
            doc["detected_at"] = now
            doc["user_confirmed"] = None
            doc["user_hidden"] = False
            await db.UserFrequentPlaces.insert_one(doc)
            inserted += 1
    return {"ok": True, "clusters_found": len(clusters),
                  "inserted": inserted, "updated": updated}


class ConfirmIn(BaseModel):
    confirmed: bool


@router.post("/frequent/{place_id}/confirm")
async def confirm_place(place_id: str, body: ConfirmIn, request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    await _check_consent(db, user)
    r = await db.UserFrequentPlaces.update_one(
        {"user_id": user["user_id"], "place_id": place_id},
        {"$set": {"user_confirmed": bool(body.confirmed),
                          "confirmed_at": _now()}})
    if r.matched_count == 0:
        raise HTTPException(404, "place_not_found")
    return {"ok": True, "place_id": place_id, "confirmed": body.confirmed}


@router.post("/frequent/{place_id}/hide")
async def hide_place(place_id: str, request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    await _check_consent(db, user)
    r = await db.UserFrequentPlaces.update_one(
        {"user_id": user["user_id"], "place_id": place_id},
        {"$set": {"user_hidden": True, "hidden_at": _now()}})
    if r.matched_count == 0:
        raise HTTPException(404, "place_not_found")
    return {"ok": True, "place_id": place_id, "hidden": True}


async def ensure_places_indexes(db) -> None:
    try:
        await db.UserFrequentPlaces.create_index(
            [("user_id", 1), ("last_seen", -1)], name="places_user_lastseen")
        await db.UserFrequentPlaces.create_index(
            [("user_id", 1), ("place_id", 1)], unique=True,
            name="places_user_placeid_unique")
        log.info("[places] indexes ensured")
    except Exception as e:
        log.warning("[places] ensure indexes failed: %s", e)
