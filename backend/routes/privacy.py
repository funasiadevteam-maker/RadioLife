"""Phase 39 Session 4 — Location consent + privacy control center.

5-endpoint surface for the 4-level consent ladder + travel event ingestion
+ data export + soft-delete + audit log retrieval.

All consent changes go through `POST /api/privacy/consent`.  No other code
path is permitted to mutate `users.location_consent_level`.  Every change
is recorded append-only in `LocationPrivacyAuditLogs`.

Rate limit: 10 consent level changes per user per 24h (anti-abuse).
"""
from __future__ import annotations
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import current_user

router = APIRouter(prefix="/api/privacy", tags=["privacy"])
log = logging.getLogger("bigfm.privacy")

CONSENT_LEVELS = {0: "off", 1: "city_only",
                                  2: "session_foreground", 3: "travel_history"}

RATE_LIMIT_CHANGES_PER_24H = 10
TRAVEL_EVENT_TTL_DAYS              = 90


def _now() -> datetime: return datetime.now(timezone.utc)
def _now_iso() -> str: return _now().isoformat()


async def ensure_privacy_indexes(db) -> None:
    """Idempotent.  Wired into FastAPI startup."""
    try:
        await db.UserTravelEvents.create_index(
            [("user_id", 1), ("captured_at", -1)],
            name="travel_events_user_time")
        # 90-day TTL on captured_at.
        await db.UserTravelEvents.create_index(
            "captured_at", expireAfterSeconds=TRAVEL_EVENT_TTL_DAYS * 86400,
            name="travel_events_ttl")
        await db.LocationPrivacyAuditLogs.create_index(
            [("user_id", 1), ("timestamp", -1)],
            name="privacy_audit_user_time")
        log.info("[privacy] indexes ensured")
    except Exception as e:
        log.warning("[privacy] ensure indexes failed: %s", e)


async def write_audit(db, *, user_id: str, action: str,
                                          prev_level: Optional[int] = None,
                                          new_level: Optional[int] = None,
                                          details: Optional[dict] = None,
                                          request: Optional[Request] = None) -> None:
    """Append-only.  Never raises into the request path."""
    try:
        row = {
            "_id":              uuid.uuid4().hex,
            "user_id":      user_id,
            "action":        action,
            "prev_level":  prev_level,
            "new_level":  new_level,
            "details_json": details or {},
            "timestamp":  _now_iso(),
            "ip_address": (request.client.host
                                          if request and getattr(request, "client", None) else None),
            "user_agent": (request.headers.get("user-agent")
                                          if request and request.headers else None),
        }
        await db.LocationPrivacyAuditLogs.insert_one(row)
    except Exception as e:
        log.warning("[privacy] audit insert failed action=%s: %s", action, e)


class ConsentIn(BaseModel):
    level: int = Field(..., ge=0, le=3)


class TravelEventIn(BaseModel):
    lat:                  float = Field(..., ge=-90, le=90)
    lng:                  float = Field(..., ge=-180, le=180)
    accuracy_m: float = Field(default=0, ge=0)
    app_state:    str   = Field(default="foreground",
                                                pattern="^(foreground|background)$")
    session_id:  Optional[str] = None


class DeleteIn(BaseModel):
    confirm: str


@router.get("/consent")
async def get_consent(request: Request, user: dict = Depends(current_user)):
    db = request.app.state.db
    fresh = await db.users.find_one({"user_id": user["user_id"]}) or {}
    return {
        "level":                fresh.get("location_consent_level", 0),
        "level_name":      CONSENT_LEVELS.get(
                                              fresh.get("location_consent_level", 0), "off"),
        "last_updated_at": fresh.get("location_consent_updated_at"),
    }


async def _consent_rate_limit_ok(db, user_id: str) -> bool:
    cutoff = (_now() - timedelta(hours=24)).isoformat()
    n = await db.LocationPrivacyAuditLogs.count_documents({
        "user_id":  user_id,
        "action":    "consent_change",
        "timestamp": {"$gte": cutoff},
    })
    return n < RATE_LIMIT_CHANGES_PER_24H


@router.post("/consent")
async def post_consent(body: ConsentIn, request: Request,
                                            user: dict = Depends(current_user)):
    db = request.app.state.db
    if not await _consent_rate_limit_ok(db, user["user_id"]):
        raise HTTPException(429, {"code": "consent_rate_limit",
                                                      "message":
                                                          f"max {RATE_LIMIT_CHANGES_PER_24H} consent changes per 24h"})
    fresh = await db.users.find_one({"user_id": user["user_id"]}) or {}
    prev = int(fresh.get("location_consent_level", 0))
    new_level = int(body.level)
    now_iso = _now_iso()
    await db.users.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"location_consent_level":          new_level,
                          "location_consent_updated_at": now_iso}})
    await write_audit(db, user_id=user["user_id"],
                                    action="consent_change",
                                    prev_level=prev, new_level=new_level,
                                    details={"changed_at": now_iso},
                                    request=request)
    # Downgrade nudge — fire (best-effort) when user lowered.
    if new_level < prev:
        try:
            from services.mailgun_client import send_email, is_live
            if is_live() and fresh.get("email"):
                send_email(
                    to=fresh["email"],
                    subject="FUUSIC privacy level lowered",
                    html=(f"<p>You just lowered your FUUSIC location consent "
                                f"from level {prev} to {new_level}. "
                                f"If this wasn't you, secure your account.</p>"))
        except Exception as e:
            log.warning("[privacy] downgrade nudge failed: %s", e)
    return {"ok": True, "level": new_level,
                  "level_name": CONSENT_LEVELS.get(new_level)}


@router.post("/travel_event")
async def post_travel_event(body: TravelEventIn, request: Request,
                                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    fresh = await db.users.find_one({"user_id": user["user_id"]}) or {}
    consent = int(fresh.get("location_consent_level", 0))
    required = 3 if body.app_state == "background" else 2
    if consent < required:
        raise HTTPException(403, {"code": "consent_required",
                                                      "required_level": required,
                                                      "current_level": consent})
    doc = {
        "_id":                uuid.uuid4().hex,
        "user_id":      user["user_id"],
        "lat":                body.lat,
        "lng":                body.lng,
        "accuracy_m": body.accuracy_m,
        "captured_at": _now(),
        "source":        "user_post",
        "session_id": body.session_id,
        "app_state":  body.app_state,
        "purged":        False,
    }
    await db.UserTravelEvents.insert_one(doc)
    return {"ok": True, "event_id": doc["_id"]}


@router.get("/export")
async def export_data(request: Request,
                                          user: dict = Depends(current_user)):
    db = request.app.state.db
    uid = user["user_id"]
    profile = await db.users.find_one({"user_id": uid}) or {}
    profile.pop("password_hash", None)
    profile.pop("_id", None)
    # Audit log (last 200).
    audit = []
    async for row in db.LocationPrivacyAuditLogs.find(
        {"user_id": uid}).sort("timestamp", -1).limit(200):
        row.pop("_id", None); audit.append(row)
    # Travel events (last 1000).
    events = []
    async for row in db.UserTravelEvents.find(
        {"user_id": uid}).sort("captured_at", -1).limit(1000):
        row.pop("_id", None)
        row["captured_at"] = row["captured_at"].isoformat() \
              if hasattr(row.get("captured_at"), "isoformat") \
              else row.get("captured_at")
        events.append(row)
    # Phase 39 Session 7 — extend export with the new S6 collections.
    trips = []
    async for row in db.UserTrips.find({"user_id": uid}).sort("started_at", -1).limit(500):
        row.pop("_id", None)
        for k in ("started_at", "ended_at", "detected_at"):
            v = row.get(k)
            if hasattr(v, "isoformat"): row[k] = v.isoformat()
        trips.append(row)
    route_patterns = []
    async for row in db.UserRoutePatterns.find({"user_id": uid}).sort("last_seen", -1):
        row.pop("_id", None)
        for k in ("first_seen", "last_seen", "detected_at"):
            v = row.get(k)
            if hasattr(v, "isoformat"): row[k] = v.isoformat()
        route_patterns.append(row)
    business_visits = []
    async for row in db.UserBusinessVisits.find({"user_id": uid}).sort("visited_at", -1).limit(500):
        row.pop("_id", None)
        for k in ("visited_at", "detected_at"):
            v = row.get(k)
            if hasattr(v, "isoformat"): row[k] = v.isoformat()
        business_visits.append(row)
    frequent_places = []
    async for row in db.UserFrequentPlaces.find({"user_id": uid}):
        row.pop("_id", None)
        for k in ("first_seen", "last_seen", "detected_at",
                  "last_refreshed_at", "confirmed_at", "hidden_at"):
            v = row.get(k)
            if hasattr(v, "isoformat"): row[k] = v.isoformat()
        frequent_places.append(row)
    # Wallet
    wallet = []
    async for row in db.wallet_items.find({"user_id": uid}):
        row.pop("_id", None); wallet.append(row)
    await write_audit(db, user_id=uid, action="export",
                                      details={"audit_count": len(audit),
                                                          "travel_events_count": len(events),
                                                          "trips_count": len(trips),
                                                          "route_patterns_count": len(route_patterns),
                                                          "business_visits_count": len(business_visits),
                                                          "wallet_count": len(wallet)},
                                      request=request)
    return {"ok": True, "exported_at": _now_iso(),
                  "user_profile":  profile,
                  "audit_log":      audit,
                  "travel_events": events,
                  "trips":              trips,
                  "route_patterns":  route_patterns,
                  "business_visits": business_visits,
                  "frequent_places": frequent_places,
                  "wallet":          wallet}


@router.post("/delete")
async def soft_delete(body: DeleteIn, request: Request,
                                          user: dict = Depends(current_user)):
    if body.confirm != "DELETE_MY_DATA":
        raise HTTPException(400, {"code": "confirm_required",
                                                      "message": "send confirm='DELETE_MY_DATA'"})
    db = request.app.state.db
    uid = user["user_id"]
    now_iso = _now_iso()
    hard_delete_at = (_now() + timedelta(days=30)).isoformat()
    await db.users.update_one(
        {"user_id": uid},
        {"$set": {"deleted_at":          now_iso,
                          "hard_delete_at": hard_delete_at,
                          "location_consent_level": 0,
                          "subscription_status": "free",
                          "selected_persona_id": None}})
    await write_audit(db, user_id=uid, action="soft_delete",
                                      details={"hard_delete_at": hard_delete_at},
                                      request=request)
    return {"ok": True, "soft_deleted_at": now_iso,
                  "hard_delete_at": hard_delete_at,
                  "recovery_window_days": 30}


@router.get("/audit_log")
async def get_audit_log(request: Request,
                                              user: dict = Depends(current_user)):
    db = request.app.state.db
    rows = []
    async for r in db.LocationPrivacyAuditLogs.find(
        {"user_id": user["user_id"]}).sort("timestamp", -1).limit(200):
        r.pop("_id", None); rows.append(r)
    return {"count": len(rows), "entries": rows}


# ─── advertiser-safe aggregation guard (Session 7 dep) ────────────────
MIN_SEGMENT_SIZE = 20

def is_advertiser_safe_aggregation(segment_user_count: int) -> bool:
    """Server-side gate — refuses to return aggregate segments smaller than
    20 users (re-identification risk).  Wired from advertiser endpoints."""
    return segment_user_count >= MIN_SEGMENT_SIZE
