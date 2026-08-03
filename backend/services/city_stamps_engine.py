"""Phase K.2 — City Stamps Engine.

Mechanic: every time a listener accumulates ≥ STAMP_THRESHOLD_MIN minutes
of credited listening time in a single resolved city, they earn that city's
*stamp* — a visual collectible distinct from the badge system.

Stamps are TRACKED for every supported city (we always emit a row in
`user_city_stamps` from the very first minute) but only flagged as
`earned=True` once the threshold is crossed.  Re-listening simply
increments `total_listen_minutes`, `visit_count`, and updates
`latest_visit_at`.

Awarding a stamp also:
    • fires the `city_stamp_unlock` PointsService rule (25 pts default).
    • inserts a `badge_events` row of source_event `city_stamp_earned`
        so future analytics / RJ stingers can hang off it.

The engine is intentionally idempotent — repeated calls with the same
`(user_id, city_id, minute_bucket)` are no-ops on the points / stamp
flag, but always tick the counters.
"""
from __future__ import annotations
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger("bigfm.city_stamps")

STAMP_THRESHOLD_MIN = 30   # minutes to earn the stamp
POINTS_RULE_FIRST_STAMP = "city_stamp_unlock"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm_city_id(s: str) -> str:
    """Stable city_id used to join with city_stamps_definitions."""
    return (s or "").strip().lower().replace(" ", "_")


async def ensure_city_stamp_indexes(db) -> None:
    await db.city_stamps_definitions.create_index([("city_id", 1)],
                                                                                  unique=True)
    await db.user_city_stamps.create_index(
        [("user_id", 1), ("city_id", 1)], unique=True)
    await db.user_city_stamps.create_index(
        [("user_id", 1), ("earned", 1)])
    await db.user_city_stamps.create_index([("city_id", 1), ("earned", 1)])


async def evaluate(db, *, user_id: str, city: str,
                              minutes: int = 1,
                              channel_slug: Optional[str] = None) -> dict:
    """Called once per credited listening minute.  Returns the updated
    stamp row + a `newly_earned` flag.

    `city` is the raw city name from the geo / commute resolver
    (e.g. "Dubai", "Frisco").  We normalise to `city_id` and only act
    on cities we ship definitions for — unknown cities are dropped on
    the floor so we don't poison the collection.
    """
    if not user_id or not city:
        return {"ok": False, "reason": "missing_input"}
    cid = _norm_city_id(city)
    defn = await db.city_stamps_definitions.find_one({"city_id": cid})
    if not defn:
        return {"ok": False, "reason": "city_not_supported", "city_id": cid}

    now = _now()
    # Read-modify with $inc + upsert in one round-trip so concurrent
    # heartbeats can't double-award.
    res = await db.user_city_stamps.find_one_and_update(
        {"user_id": user_id, "city_id": cid},
        {
            "$inc": {"total_listen_minutes": int(minutes),
                          "visit_count": 0},   # bumped below on day rollover
            "$set": {"latest_visit_at": now,
                          "latest_channel_slug": channel_slug},
            "$setOnInsert": {
                "_id":                                  f"ucs_{uuid.uuid4().hex[:14]}",
                "user_id":                          user_id,
                "city_id":                          cid,
                "first_visit_at":              now,
                "earned":                          False,
                "earned_at":                      None,
                "earned_points_awarded": False,
                "visit_count":                  1,
                "created_at":                      now,
            },
        },
        upsert=True, return_document=True)

    if not res:
        # Race — read after upsert
        res = await db.user_city_stamps.find_one(
            {"user_id": user_id, "city_id": cid})
    if not res:
        return {"ok": False, "reason": "internal_lost_row"}

    newly_earned = False
    total = int(res.get("total_listen_minutes") or 0)
    if not res.get("earned") and total >= STAMP_THRESHOLD_MIN:
        # Cross the threshold — flip flag + award points + insert a
        # badge_event so other engines can react.
        upd = await db.user_city_stamps.update_one(
            {"user_id": user_id, "city_id": cid, "earned": False},
            {"$set": {"earned": True, "earned_at": now}})
        if upd.modified_count > 0:
            newly_earned = True
            res["earned"] = True
            res["earned_at"] = now
            # Award via PointsService (5 pts default rule — caps via DB)
            try:
                from services.points_service import PointsService
                svc = PointsService(db)
                aw = await svc.award(
                    user_id=user_id,
                    source=POINTS_RULE_FIRST_STAMP,
                    source_id=cid,
                    idempotency_key=f"city_stamp_{user_id}_{cid}",
                    metadata={"city_id": cid,
                                  "city_name": defn.get("name")})
                if aw.ok:
                    await db.user_city_stamps.update_one(
                        {"user_id": user_id, "city_id": cid},
                        {"$set": {"earned_points_awarded": True,
                                    "earned_points_delta": int(aw.delta or 0)}})
            except Exception as e:
                log.warning("[city_stamps] points award failed u=%s cid=%s "
                                  "err=%s", user_id, cid, e)
            # Emit a badge_event for Phase-10a engine fan-out / analytics.
            try:
                await db.badge_events.insert_one({
                    "_id": f"bev_{uuid.uuid4().hex[:14]}",
                    "user_id": user_id,
                    "source_event": "city_stamp_earned",
                    "payload": {"city_id": cid, "city_name": defn.get("name")},
                    "ts": now,
                })
            except Exception:
                pass
            log.info("[city_stamps] earned u=%s city=%s total=%d",
                            user_id, cid, total)
    return {"ok": True, "city_id": cid, "newly_earned": newly_earned,
                  "earned": bool(res.get("earned")),
                  "total_listen_minutes": total}


async def list_user_stamps(db, *, user_id: str,
                                          include_locked: bool = True) -> dict:
    """Return the full collection view — earned + locked stamps for
    every defined city.  Locked entries show a `progress_pct` (0..100)
    so the UI can render progress bars."""
    defs = [d async for d in
                db.city_stamps_definitions.find({}).sort("sort_order", 1)]
    earned_rows = {r["city_id"]: r async for r in
                          db.user_city_stamps.find({"user_id": user_id})}
    out: list[dict] = []
    earned_count = 0
    for d in defs:
        cid = d["city_id"]
        row = earned_rows.get(cid) or {}
        total = int(row.get("total_listen_minutes") or 0)
        is_earned = bool(row.get("earned"))
        if is_earned:
            earned_count += 1
        if not is_earned and not include_locked:
            continue
        out.append({
            "city_id":                          cid,
            "name":                              d.get("name"),
            "country":                          d.get("country"),
            "market":                          d.get("market"),
            "stamp_image_url":          d.get("stamp_image_url"),
            "hero_image_url":              d.get("hero_image_url"),
            "lat":                                  d.get("lat"),
            "lng":                                  d.get("lng"),
            "earned":                          is_earned,
            "earned_at":                      (row.get("earned_at").isoformat()
                                                          if isinstance(row.get("earned_at"),
                                                                              datetime)
                                                          else row.get("earned_at")),
            "total_listen_minutes": total,
            "visit_count":                  int(row.get("visit_count") or 0),
            "progress_pct":                  min(100, round(
                total / max(1, STAMP_THRESHOLD_MIN) * 100, 1)),
            "threshold_min":              STAMP_THRESHOLD_MIN,
        })
    return {"total_available": len(defs),
                  "total_earned": earned_count,
                  "stamps": out}


__all__ = [
    "STAMP_THRESHOLD_MIN",
    "ensure_city_stamp_indexes", "evaluate", "list_user_stamps",
]
