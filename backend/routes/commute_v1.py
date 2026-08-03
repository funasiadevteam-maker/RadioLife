"""Phase H v1 — Commute Mode MVP endpoints.

Mounted at prefix `/api/commute/v1` so it does NOT collide with the
pre-existing Phase 9a router at `/api/commute/*`.

Endpoints:
    POST /api/commute/v1/start                     Start a session
    GET  /api/commute/v1/session/{session_id}      Fetch a session
    POST /api/commute/v1/session/{session_id}/end  End a session
    POST /api/commute/v1/save-coupon/{offer_id}    Save an offer coupon

Collections:
    commute_sessions          (docs distinguished by `phase == 'h_v1'`)
    route_ad_opportunities    (docs distinguished by `phase == 'h_v1'`)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from auth import current_user
from services import google_maps_service as gmaps

logger = logging.getLogger("bigfm.commute_v1")

router = APIRouter(prefix="/api/commute/v1", tags=["commute_v1"])

VALID_ACTIVITIES = {"commute", "lunch", "dinner", "nightlife"}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _resolve_point(raw: dict, label: str) -> dict:
    """Accept either { lat, lng } or { address } — geocode if address only.
    Returns { lat, lng, formatted_address?, place_id? }.
    """
    if not isinstance(raw, dict):
        raise HTTPException(400, f"{label}_required")
    if "lat" in raw and "lng" in raw:
        try:
            return {
                "lat": float(raw["lat"]),
                "lng": float(raw["lng"]),
                "formatted_address": raw.get("formatted_address"),
                "place_id": raw.get("place_id"),
            }
        except (TypeError, ValueError):
            raise HTTPException(400, f"{label}_invalid_coords")
    addr = (raw.get("address") or "").strip()
    if not addr:
        raise HTTPException(400, f"{label}_requires_lat_lng_or_address")
    try:
        g = await gmaps.geocode(addr)
    except Exception as e:
        logger.warning(f"[commute_v1] geocode error for {label!r}: {e}")
        raise HTTPException(502, f"{label}_geocode_failed")
    if not g:
        raise HTTPException(404, f"{label}_address_not_found")
    return g


async def _match_offers_along_route(db, *, route_points: list[tuple[float, float]],
                                                     waypoints: list[tuple[float, float]],
                                                     activity: str,
                                                     max_matches: int = 8) -> list[dict]:
    """Match businesses/offers along a route using two strategies:
      1) Places API nearby search around 3-5 route waypoints; cross-reference
         `businesses.google_place_id`.
      2) Fallback: iterate businesses with lat/lng and include those within
         1500m of any route vertex.

    Returns a list of matched offer objects ready for the frontend.
    """
    if not route_points:
        return []
    place_types = gmaps.ACTIVITY_TO_PLACE_TYPES.get(activity, ["restaurant"])
    # ── Strategy 1 — Places API + google_place_id cross-ref ─────────────
    candidate_place_ids: set[str] = set()
    for wp in waypoints:
        try:
            places = await gmaps.nearby_places(
                lat=wp[0], lng=wp[1], radius_m=1500,
                place_types=place_types, max_results=10)
        except Exception as e:
            logger.warning(f"[commute_v1] places lookup error: {e}")
            continue
        for p in places:
            pid = p.get("place_id")
            if pid:
                candidate_place_ids.add(pid)

    matched: dict[str, dict] = {}  # keyed by business_id, preserves first-seen priority
    if candidate_place_ids:
        cur = db.businesses.find({
            "google_place_id": {"$in": list(candidate_place_ids)},
        })
        async for biz in cur:
            matched[biz["business_id"]] = {"biz": biz, "match_reason": "google_place_id"}

    # ── Strategy 2 — lat/lng fallback (within 1500m of route) ───────────
    # Cap the scan to a reasonable size — this collection has ~113 rows
    # in the current DB, but future-proof with a limit.
    if len(matched) < max_matches:
        cur = db.businesses.find({
            "latitude": {"$exists": True, "$ne": None},
            "longitude": {"$exists": True, "$ne": None},
            "active": True,
        }).limit(500)
        async for biz in cur:
            if biz["business_id"] in matched:
                continue
            try:
                bp = (float(biz["latitude"]), float(biz["longitude"]))
            except (TypeError, ValueError):
                continue
            d = gmaps.min_distance_to_polyline_m(bp, route_points)
            if d <= 1500:
                matched[biz["business_id"]] = {
                    "biz": biz, "match_reason": "lat_lng_proximity", "distance_m": d}
            if len(matched) >= max_matches * 2:
                break

    # ── Look up active offers for matched businesses ────────────────────
    if not matched:
        return []
    biz_ids = list(matched.keys())
    offers_cur = db.offers.find({
        "business_id": {"$in": biz_ids},
        "status": "active",
    })
    offers_out: list[dict] = []
    async for offer in offers_cur:
        m = matched.get(offer["business_id"])
        if not m:
            continue
        biz = m["biz"]
        try:
            biz_lat = float(biz.get("latitude")) if biz.get("latitude") is not None else None
            biz_lng = float(biz.get("longitude")) if biz.get("longitude") is not None else None
        except (TypeError, ValueError):
            biz_lat, biz_lng = None, None
        distance_m = m.get("distance_m")
        if distance_m is None and biz_lat is not None and biz_lng is not None:
            distance_m = gmaps.min_distance_to_polyline_m(
                (biz_lat, biz_lng), route_points)
        # Rough "extra drive time": add ~30s per 100m of detour beyond the
        # first 100m — a linear MVP heuristic.
        extra_time_s = int(max(0, (distance_m or 0) - 100) * 0.3)
        offers_out.append({
            "offer_id": offer["offer_id"],
            "title": offer.get("title"),
            "description": offer.get("description"),
            "discount_percent": offer.get("discount_percent"),
            "offer_type": offer.get("offer_type"),
            "business_id": biz["business_id"],
            "business_name": biz.get("name"),
            "business_category": biz.get("category"),
            "business_address": biz.get("address"),
            "business_lat": biz_lat,
            "business_lng": biz_lng,
            "distance_from_route_m": round(distance_m, 1) if distance_m is not None else None,
            "extra_drive_time_s": extra_time_s,
            "match_reason": m["match_reason"],
        })
    offers_out.sort(key=lambda o: (o["extra_drive_time_s"], o["distance_from_route_m"] or 0))
    return offers_out[:max_matches]


# ─── Endpoints ──────────────────────────────────────────────────────────
@router.post("/start")
async def start_commute_v1(request: Request, body: dict,
                                    user: dict = Depends(current_user)):
    db = request.app.state.db
    if not gmaps.api_key_present():
        raise HTTPException(503, "google_maps_api_key_not_configured")
    activity = (body.get("activity") or "commute").lower()
    if activity not in VALID_ACTIVITIES:
        raise HTTPException(400, f"invalid_activity. Allowed: {sorted(VALID_ACTIVITIES)}")

    origin = await _resolve_point(body.get("origin") or {}, "origin")
    destination = await _resolve_point(body.get("destination") or {}, "destination")

    # Route
    try:
        route = await gmaps.compute_route(origin=origin, destination=destination)
    except Exception as e:
        logger.warning(f"[commute_v1] compute_route error: {e}")
        raise HTTPException(502, f"routes_api_failed: {str(e)[:200]}")

    encoded = route.get("encoded_polyline") or ""
    poly_pts = gmaps.decode_polyline(encoded)
    waypoints = gmaps.sample_polyline_waypoints(poly_pts, n=4)

    # Weather (best-effort, degrades to null per user answer #4)
    weather = None
    try:
        weather = await gmaps.current_weather(lat=origin["lat"], lng=origin["lng"])
    except Exception as e:
        logger.warning(f"[commute_v1] weather error (ignored): {e}")

    # Matched offers
    matched_offers = await _match_offers_along_route(
        db, route_points=poly_pts, waypoints=waypoints,
        activity=activity, max_matches=8)

    # Persist commute session
    session_id = _new_id("cv1")
    now = _now()
    session_doc = {
        "_id": session_id,
        "session_id": session_id,
        "commute_id": session_id,  # satisfy Phase 9a unique index on commute_id
        "phase": "h_v1",
        "user_id": user["user_id"],
        "activity": activity,
        "origin_lat": origin["lat"],
        "origin_lng": origin["lng"],
        "origin_address": origin.get("formatted_address"),
        "origin_place_id": origin.get("place_id"),
        "destination_lat": destination["lat"],
        "destination_lng": destination["lng"],
        "destination_address": destination.get("formatted_address"),
        "destination_place_id": destination.get("place_id"),
        "route_polyline": encoded,
        "eta_seconds": route.get("duration_seconds"),
        "distance_meters": route.get("distance_meters"),
        "traffic_status": route.get("traffic_status"),
        "weather_json": weather,
        "matched_offer_count": len(matched_offers),
        "started_at": now,
        "ended_at": None,
        "status": "active",
    }
    await db.commute_sessions.insert_one(session_doc)

    # Persist route_ad_opportunities
    if matched_offers:
        opps = []
        for o in matched_offers:
            opp_id = _new_id("rao")
            opps.append({
                "_id": opp_id,
                "opp_id": opp_id,
                "phase": "h_v1",
                "commute_session_id": session_id,
                "user_id": user["user_id"],
                "business_id": o["business_id"],
                "offer_id": o["offer_id"],
                "distance_from_route_m": o["distance_from_route_m"],
                "extra_drive_time_s": o["extra_drive_time_s"],
                "reason": o["match_reason"],
                "shown_at": now,
                "saved": False,
                "redeemed": False,
            })
        await db.route_ad_opportunities.insert_many(opps)

    return {
        "session_id": session_id,
        "activity": activity,
        "origin": origin,
        "destination": destination,
        "route": {
            "encoded_polyline": encoded,
            "distance_meters": route.get("distance_meters"),
            "eta_seconds": route.get("duration_seconds"),
            "static_duration_seconds": route.get("static_duration_seconds"),
            "traffic_status": route.get("traffic_status"),
        },
        "weather": weather,
        "matched_offers": matched_offers,
        "started_at": now.isoformat(),
    }


@router.get("/session/{session_id}")
async def get_session_v1(session_id: str, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    doc = await db.commute_sessions.find_one({
        "session_id": session_id, "user_id": user["user_id"], "phase": "h_v1"})
    if not doc:
        raise HTTPException(404, "session_not_found")
    opps_cur = db.route_ad_opportunities.find({
        "commute_session_id": session_id, "user_id": user["user_id"]})
    opps = []
    biz_ids: set[str] = set()
    offer_ids: set[str] = set()
    async for o in opps_cur:
        opps.append(o)
        biz_ids.add(o["business_id"])
        offer_ids.add(o["offer_id"])
    # Bulk-hydrate related biz + offer
    biz_map: dict[str, dict] = {}
    async for b in db.businesses.find({"business_id": {"$in": list(biz_ids)}}):
        biz_map[b["business_id"]] = b
    offer_map: dict[str, dict] = {}
    async for f in db.offers.find({"offer_id": {"$in": list(offer_ids)}}):
        offer_map[f["offer_id"]] = f
    matched_offers = []
    for o in opps:
        biz = biz_map.get(o["business_id"]) or {}
        offer = offer_map.get(o["offer_id"]) or {}
        matched_offers.append({
            "offer_id": o["offer_id"],
            "title": offer.get("title"),
            "description": offer.get("description"),
            "discount_percent": offer.get("discount_percent"),
            "offer_type": offer.get("offer_type"),
            "business_id": o["business_id"],
            "business_name": biz.get("name"),
            "business_category": biz.get("category"),
            "business_address": biz.get("address"),
            "business_lat": biz.get("latitude"),
            "business_lng": biz.get("longitude"),
            "distance_from_route_m": o.get("distance_from_route_m"),
            "extra_drive_time_s": o.get("extra_drive_time_s"),
            "match_reason": o.get("reason"),
            "saved": bool(o.get("saved")),
        })
    matched_offers.sort(key=lambda x: (x["extra_drive_time_s"] or 0,
                                                    x["distance_from_route_m"] or 0))
    started = doc.get("started_at")
    ended = doc.get("ended_at")
    return {
        "session_id": session_id,
        "activity": doc.get("activity"),
        "origin": {"lat": doc["origin_lat"], "lng": doc["origin_lng"],
                      "address": doc.get("origin_address")},
        "destination": {"lat": doc["destination_lat"], "lng": doc["destination_lng"],
                              "address": doc.get("destination_address")},
        "route": {
            "encoded_polyline": doc.get("route_polyline"),
            "distance_meters": doc.get("distance_meters"),
            "eta_seconds": doc.get("eta_seconds"),
            "traffic_status": doc.get("traffic_status"),
        },
        "weather": doc.get("weather_json"),
        "matched_offers": matched_offers,
        "status": doc.get("status"),
        "started_at": started.isoformat() if started else None,
        "ended_at": ended.isoformat() if ended else None,
    }


@router.post("/session/{session_id}/end")
async def end_session_v1(session_id: str, request: Request,
                                user: dict = Depends(current_user)):
    db = request.app.state.db
    row = await db.commute_sessions.find_one({
        "session_id": session_id, "user_id": user["user_id"], "phase": "h_v1"})
    if not row:
        raise HTTPException(404, "session_not_found")
    if row.get("status") != "active":
        return {"ok": True, "already_ended": True, "session_id": session_id}
    await db.commute_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"status": "completed", "ended_at": _now()}})
    return {"ok": True, "session_id": session_id, "status": "completed"}


@router.post("/save-coupon/{offer_id}")
async def save_coupon_v1(offer_id: str, request: Request,
                                  body: Optional[dict] = None,
                                  user: dict = Depends(current_user)):
    """Reuses the same coupon-save shape as `/api/ads/action/save_coupon`
    but without the ad_pod_id requirement."""
    db = request.app.state.db
    offer = await db.offers.find_one({"offer_id": offer_id})
    if not offer:
        raise HTTPException(404, "offer_not_found")
    session_id = (body or {}).get("session_id")
    # Idempotency: if this user already has an active saved coupon for
    # this offer, return it — do NOT mint a duplicate.
    existing = await db.coupons.find_one({
        "user_id": user["user_id"],
        "offer_id": offer_id,
        "status": "saved",
    })
    if existing:
        # Mark opportunity as saved, best-effort.
        if session_id:
            await db.route_ad_opportunities.update_many(
                {"commute_session_id": session_id, "offer_id": offer_id,
                  "user_id": user["user_id"]},
                {"$set": {"saved": True, "saved_at": _now()}})
        return {
            "ok": True,
            "coupon_id": existing["coupon_id"],
            "code": existing["code"],
            "already_saved": True,
            "expires_at": (existing["expires_at"].isoformat()
                              if hasattr(existing.get("expires_at"), "isoformat")
                              else existing.get("expires_at")),
        }
    coupon_id = f"cp_{uuid.uuid4().hex[:14]}"
    code = f"BIGFM-{coupon_id[-6:].upper()}"
    now = _now()
    expires = now + timedelta(days=30)
    await db.coupons.insert_one({
        "_id": coupon_id, "coupon_id": coupon_id,
        "user_id": user["user_id"], "offer_id": offer_id,
        "code": code, "status": "saved",
        "saved_at": now, "expires_at": expires,
        "source": "commute_v1",
        "commute_session_id": session_id,
    })
    await db.user_wallet_items.insert_one({
        "_id": f"wi_{coupon_id}",
        "user_id": user["user_id"],
        "item_type": "coupon",
        "source_ad_pod_id": None,
        "source_campaign_id": None,
        "offer_id": offer_id,
        "coupon_id": coupon_id,
        "title": offer.get("title"),
        "description": offer.get("description"),
        "value_cents": offer.get("discount_value_cents") or 0,
        "status": "active",
        "expiration": expires.isoformat(),
        "created_at": now,
    })
    if session_id:
        await db.route_ad_opportunities.update_many(
            {"commute_session_id": session_id, "offer_id": offer_id,
              "user_id": user["user_id"]},
            {"$set": {"saved": True, "saved_at": now}})
    # Award BigCoin for coupon save (mirrors ads_public.action_save_coupon)
    try:
        from services.bigcoin import award as _bc_award
        await _bc_award(db, user["user_id"], 5, "commute_coupon_save",
                              metadata={"offer_id": offer_id,
                                          "coupon_id": coupon_id,
                                          "commute_session_id": session_id})
    except Exception as e:
        logger.warning(f"[commute_v1] bigcoin award failed (ignored): {e}")
    return {
        "ok": True,
        "coupon_id": coupon_id,
        "code": code,
        "already_saved": False,
        "expires_at": expires.isoformat(),
    }


async def ensure_commute_v1_indexes(db) -> None:
    """Called on background bootstrap.  Idempotent."""
    await db.commute_sessions.create_index([("session_id", 1)])
    await db.commute_sessions.create_index([("user_id", 1), ("status", 1),
                                                              ("started_at", -1)])
    await db.route_ad_opportunities.create_index([("commute_session_id", 1)])
    await db.route_ad_opportunities.create_index([("user_id", 1),
                                                                     ("offer_id", 1)])


__all__ = ["router", "ensure_commute_v1_indexes"]
