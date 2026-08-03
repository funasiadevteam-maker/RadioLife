"""Phase 9a — Commute session service.

Saved locations CRUD + commute lifecycle (start / heartbeat / end / abandon)
+ driving-mode integration + commute_completed milestone unlock fire.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from services.games_v2 import _new_id, _now
from services.maps_client import get_maps_client

logger = logging.getLogger("bigfm.commute")

COMMUTE_MODES = {"driver", "passenger", "transit"}
# Phase 9b — expanded label vocab.  Any free-text up to 32 chars is also
# accepted as a fallback (saved in label_custom; commute_label coerced
# to "other").
COMMUTE_LABELS = {"commute", "home_to_work", "work_to_home", "lunch_run",
                       "errand", "club_night", "concert", "movie_night",
                       "devotional", "school_run", "airport", "gym",
                       "other"}
COMMUTE_STATUSES = {"active", "completed", "abandoned"}


def _coerce_label(label: Optional[str]) -> tuple[str, Optional[str]]:
    """Return (canonical_label, label_custom_or_None)."""
    if not label:
        return "other", None
    raw = str(label).strip()
    if not raw:
        return "other", None
    if raw in COMMUTE_LABELS:
        return raw, None
    if len(raw) > 32:
        raw = raw[:32]
    return "other", raw


# ─── Saved locations ────────────────────────────────────────────────────
async def list_saved_locations(db, user_id: str) -> list[dict]:
    out = []
    async for r in db.saved_locations.find({"user_id": user_id}) \
                                          .sort("created_at", 1):
        out.append(_loc_view(r))
    return out


def _loc_view(r: dict) -> dict:
    return {
        "loc_id": r["loc_id"],
        "label": r.get("label"),
        "lat": r.get("lat"), "lng": r.get("lng"),
        "formatted_address": r.get("formatted_address"),
        "place_id": r.get("place_id"),
        "is_default_origin": bool(r.get("is_default_origin")),
        "is_default_destination": bool(r.get("is_default_destination")),
        "created_at": (r["created_at"].isoformat()
                          if r.get("created_at") else None),
    }


async def create_saved_location(db, user_id: str, *,
                                       label: str,
                                       address: Optional[str] = None,
                                       lat: Optional[float] = None,
                                       lng: Optional[float] = None,
                                       is_default_origin: bool = False,
                                       is_default_destination: bool = False) -> dict:
    if not label or len(label) > 60:
        raise ValueError("invalid_label")
    place_id = None
    formatted = None
    if address and (lat is None or lng is None):
        client = get_maps_client(db)
        g = await client.geocode(address)
        lat, lng = g["lat"], g["lng"]
        formatted = g["formatted_address"]
        place_id = g.get("place_id")
    elif lat is not None and lng is not None:
        client = get_maps_client(db)
        rg = await client.reverse_geocode(lat, lng)
        formatted = rg.get("formatted_address")
        place_id = rg.get("place_id")
    else:
        raise ValueError("address_or_coords_required")
    lid = _new_id("loc")
    doc = {
        "_id": lid, "loc_id": lid, "user_id": user_id,
        "label": label.strip(),
        "lat": float(lat), "lng": float(lng),
        "formatted_address": formatted, "place_id": place_id,
        "is_default_origin": bool(is_default_origin),
        "is_default_destination": bool(is_default_destination),
        "created_at": _now(),
    }
    if is_default_origin:
        await db.saved_locations.update_many(
            {"user_id": user_id, "is_default_origin": True},
            {"$set": {"is_default_origin": False}})
    if is_default_destination:
        await db.saved_locations.update_many(
            {"user_id": user_id, "is_default_destination": True},
            {"$set": {"is_default_destination": False}})
    await db.saved_locations.insert_one(doc)
    return _loc_view(doc)


async def update_saved_location(db, user_id: str, loc_id: str,
                                       patch: dict) -> dict:
    allowed = {"label", "lat", "lng", "is_default_origin",
                  "is_default_destination", "formatted_address"}
    unknown = [k for k in patch.keys() if k not in allowed]
    if unknown:
        raise ValueError(f"unknown_fields:{','.join(unknown)}")
    row = await db.saved_locations.find_one(
        {"loc_id": loc_id, "user_id": user_id})
    if not row:
        raise ValueError("not_found")
    if patch.get("is_default_origin"):
        await db.saved_locations.update_many(
            {"user_id": user_id, "is_default_origin": True,
              "loc_id": {"$ne": loc_id}},
            {"$set": {"is_default_origin": False}})
    if patch.get("is_default_destination"):
        await db.saved_locations.update_many(
            {"user_id": user_id, "is_default_destination": True,
              "loc_id": {"$ne": loc_id}},
            {"$set": {"is_default_destination": False}})
    await db.saved_locations.update_one(
        {"loc_id": loc_id}, {"$set": patch})
    row = await db.saved_locations.find_one({"loc_id": loc_id})
    return _loc_view(row)


async def delete_saved_location(db, user_id: str, loc_id: str) -> None:
    await db.saved_locations.delete_one(
        {"loc_id": loc_id, "user_id": user_id})


# ─── Route preview ──────────────────────────────────────────────────────
async def route_preview(db, *, origin: dict, destination: dict,
                              departure_time: Optional[str] = None) -> dict:
    client = get_maps_client(db)
    route = await client.compute_route(origin, destination, departure_time)
    weather = await client.current_weather(origin["lat"], origin["lng"])
    return {"route": route, "weather": weather,
              "origin": origin, "destination": destination}


# ─── Commute lifecycle ──────────────────────────────────────────────────
async def start_commute(db, user_id: str, *,
                              origin: dict, destination: dict,
                              mode: str = "driver",
                              label: str = "other") -> dict:
    if mode not in COMMUTE_MODES:
        raise ValueError(f"invalid_mode:{mode}")
    canonical_label, label_custom = _coerce_label(label)
    # End any existing active commute first
    await db.commute_sessions.update_many(
        {"user_id": user_id, "status": "active"},
        {"$set": {"status": "abandoned", "ended_at": _now(),
                   "abandon_reason": "superseded_by_new_start"}})

    client = get_maps_client(db)
    route = await client.compute_route(origin, destination)
    weather = await client.current_weather(origin["lat"], origin["lng"])
    cid = _new_id("cmt")
    now = _now()
    # Remember the user's prior driving_mode so we can restore on end
    u = await db.users.find_one({"user_id": user_id},
                                          {"driving_mode_on": 1})
    prior_dm = bool((u or {}).get("driving_mode_on"))
    doc = {
        "_id": cid, "commute_id": cid, "user_id": user_id,
        "origin": origin, "destination": destination,
        "route_polyline": route["polyline_encoded"],
        "route_distance_m": route["distance_meters"],
        "route_duration_s": route["duration_seconds"],
        "route_duration_in_traffic_s": route["duration_in_traffic_seconds"],
        "traffic_status": route["traffic_status"],
        "weather_snapshot": weather,
        "mode": mode, "started_at": now, "ended_at": None,
        "status": "active",
        "actual_track_log": [],
        "commute_label": canonical_label,
        "label_custom": label_custom,
        "prior_driving_mode_on": prior_dm,
        "created_at": now, "updated_at": now,
    }
    await db.commute_sessions.insert_one(doc)
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"active_commute_id": cid}})
    if mode == "driver" and not prior_dm:
        await db.users.update_one(
            {"user_id": user_id}, {"$set": {"driving_mode_on": True}})
    # Phase 9b — kick the route-opportunities background task.
    try:
        import asyncio
        from services.route_ad_engine import compute_route_opportunities
        asyncio.create_task(compute_route_opportunities(db, cid))
    except Exception as e:
        logger.warning(f"route_opp compute kick failed: {e}")
    return _commute_view(doc)


def _commute_view(doc: dict) -> dict:
    return {
        "commute_id": doc["commute_id"],
        "user_id": doc.get("user_id"),
        "origin": doc.get("origin"),
        "destination": doc.get("destination"),
        "route_polyline": doc.get("route_polyline"),
        "route_distance_m": doc.get("route_distance_m"),
        "route_duration_s": doc.get("route_duration_s"),
        "route_duration_in_traffic_s": doc.get("route_duration_in_traffic_s"),
        "traffic_status": doc.get("traffic_status"),
        "weather_snapshot": doc.get("weather_snapshot"),
        "mode": doc.get("mode"),
        "started_at": (doc["started_at"].isoformat()
                          if doc.get("started_at") else None),
        "ended_at": (doc["ended_at"].isoformat()
                        if doc.get("ended_at") else None),
        "status": doc.get("status"),
        "commute_label": doc.get("commute_label"),
        # Phase 9b.1 — original free-text label preserved when the
        # caller sent something outside the canonical enum.  Null when
        # the label matched a canonical value.
        "label_custom": doc.get("label_custom"),
    }


async def heartbeat_commute(db, user_id: str, commute_id: str,
                                   *, current_lat: Optional[float] = None,
                                   current_lng: Optional[float] = None,
                                   eta_remaining_s: Optional[int] = None) -> dict:
    row = await db.commute_sessions.find_one(
        {"commute_id": commute_id, "user_id": user_id})
    if not row:
        raise ValueError("not_found")
    if row["status"] != "active":
        raise ValueError("not_active")
    update = {"updated_at": _now()}
    if eta_remaining_s is not None:
        update["eta_remaining_s"] = int(eta_remaining_s)
    if current_lat is not None and current_lng is not None:
        update["last_ping"] = {"lat": current_lat, "lng": current_lng,
                                       "ts": _now()}
    await db.commute_sessions.update_one(
        {"commute_id": commute_id}, {"$set": update})
    return {"ok": True}


async def end_commute(db, user_id: str, commute_id: str,
                            *, abandon: bool = False) -> dict:
    row = await db.commute_sessions.find_one(
        {"commute_id": commute_id, "user_id": user_id})
    if not row:
        raise ValueError("not_found")
    if row["status"] != "active":
        # Idempotent: re-ending a completed/abandoned session is a no-op
        return {**_commute_view(row), "milestone": None}
    new_status = "abandoned" if abandon else "completed"
    await db.commute_sessions.update_one(
        {"commute_id": commute_id},
        {"$set": {"status": new_status, "ended_at": _now()}})
    # Restore driving_mode to the prior value
    prior_dm = bool(row.get("prior_driving_mode_on"))
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"driving_mode_on": prior_dm,
                   "active_commute_id": None}})
    # Fire commute_completed milestone (NOT on abandon)
    milestone = None
    if not abandon:
        try:
            milestone = await on_commute_completed(db, user_id, commute_id)
        except Exception as e:
            logger.warning(f"commute milestone fire failed: {e}")
        # Phase 9b — enqueue a one-shot "arrival" context for the next RJ
        # break.  Cooldown is enforced inside the helper.
        try:
            from services.route_ad_engine import enqueue_commute_arrival_rj_extra
            await enqueue_commute_arrival_rj_extra(db, user_id=user_id, cmt=row)
        except Exception as e:
            logger.warning(f"commute arrival rj extra: {e}")
        # Phase 10a — Social Passport: emit commute_completed
        try:
            from services.badge_engine import evaluate as badge_evaluate
            weather = (row.get("weather_at_start") or {}).get("condition") \
                          or row.get("weather_hint") or ""
            daypart = row.get("daypart") or ""
            await badge_evaluate(
                db, user_id, "commute_completed",
                {"commute_id": commute_id,
                  "weather": weather.lower() if weather else None,
                  "daypart": daypart, "mode": row.get("mode")})
        except Exception as e:
            logger.warning(f"badge eval commute_completed: {e}")
    refreshed = await db.commute_sessions.find_one({"commute_id": commute_id})
    out = _commute_view(refreshed)
    out["milestone"] = milestone
    return out


async def get_active_commute(db, user_id: str) -> Optional[dict]:
    row = await db.commute_sessions.find_one(
        {"user_id": user_id, "status": "active"},
        sort=[("started_at", -1)])
    return _commute_view(row) if row else None


async def get_driving_state(db, user_id: str) -> dict:
    u = await db.users.find_one({"user_id": user_id},
                                          {"driving_mode_on": 1})
    cmt = await get_active_commute(db, user_id)
    eta = None
    if cmt:
        row = await db.commute_sessions.find_one(
            {"commute_id": cmt["commute_id"]}, {"eta_remaining_s": 1})
        eta = (row or {}).get("eta_remaining_s")
    return {
        "driving_mode_on": bool((u or {}).get("driving_mode_on")),
        "commute_id": cmt["commute_id"] if cmt else None,
        "mode": cmt.get("mode") if cmt else None,
        "eta_remaining_s": eta,
        "active_commute": cmt,
    }


async def list_history(db, user_id: str, limit: int = 20) -> list[dict]:
    cur = (db.commute_sessions
              .find({"user_id": user_id, "status": {"$ne": "active"}})
              .sort("started_at", -1).limit(limit))
    return [_commute_view(r) async for r in cur]


# ─── Milestone integration ──────────────────────────────────────────────
async def on_commute_completed(db, user_id: str,
                                       commute_id: str) -> Optional[dict]:
    from services.game_unlock_engine import (
        _award_unlock, _pick_target_campaign, _period_bucket)
    rules = await db.unlock_rules.find(
        {"trigger_type": "commute_completed", "active": True}).to_list(10)
    awarded = None
    for rule in rules:
        bucket = _period_bucket(rule["period"], _now())
        # Idempotent per (user_id, commute_id) — encode in metadata
        cid = await _pick_target_campaign(db, rule, user_id)
        if not cid:
            continue
        doc = await _award_unlock(
            db, rule=rule, user_id=user_id, campaign_id=cid,
            period_bucket=f"{bucket}:{commute_id}",
            metadata={"commute_id": commute_id})
        if doc:
            awarded = doc
    return awarded


async def activate_commute_unlock_rule(db) -> dict:
    """Phase 8b seeded rule_commute_completed with active=False.  Phase 9a
    activates it so /commute/end actually grants the unlock."""
    res = await db.unlock_rules.update_one(
        {"rule_id": "rule_commute_completed"},
        {"$set": {"active": True,
                   "title": "Drive home and play & win",
                   "description": "Complete a commute to earn a play."}})
    return {"matched": res.matched_count, "modified": res.modified_count}
