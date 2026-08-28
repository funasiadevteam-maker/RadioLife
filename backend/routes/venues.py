"""
Phase 16c — Venue staff + TV display REST + WebSocket routes.

REST (cookie-auth, gated by `venue_staff` membership unless noted):
    POST   /api/venue                           create venue (any authed user)
    GET    /api/venue/me                        list venues for caller
    GET    /api/venue/{id}                      venue details (staff-only)
    POST   /api/venue/{id}/staff                invite staff by email (owner)
    DELETE /api/venue/{id}/staff/{uid}         remove staff (owner)
    POST   /api/venue/{id}/tvs/pair            issue 6-digit pairing code (staff)
    GET    /api/venue/{id}/tvs                  list paired TVs (staff)
    POST   /api/venue/{id}/tvs/{tv}/revoke    revoke TV token (staff)
    POST   /api/venue/{id}/trivia/start        start venue-branded trivia room (staff)
    POST   /api/venue/{id}/announcement        broadcast announcement (staff)
    POST   /api/venue/{id}/coupons/redeem     redeem a coupon code (staff)
    GET    /api/venue/{id}/stats               analytics (staff)
    GET    /api/venue/{id}/players              live player list (staff)
    DELETE /api/venue/{id}/rooms/{code}/players/{uid}   kick via venue dashboard (staff)

TV surface (token-auth, NO session cookie required):
    POST   /api/tv/claim                       body {pairing_code}  → tv_token
    GET    /api/tv/me?token=<tv_token>         venue snapshot for paired TV
    WS     /api/tv/ws?token=<tv_token>         live updates

Public:
    POST   /api/venue/onboard                  same as POST /api/venue (UX alias)
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import (
    APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.venue_tv_hub import TVHub
from services.trivia_rooms import RoomHub
from services.trivia_ai import pick_for_user
from routes.trivia_room_routes import notify_room_followers
from auth import SESSION_COOKIE

logger = logging.getLogger("bigfm.venues")

PAIRING_CODE_TTL_SEC = 600       # 10 minutes
PAIRING_DIGITS         = 6


def _now_ms() -> int:
    return int(time.time() * 1000)


def _gen_pairing_code() -> str:
    # 6 numeric digits, formatted as "XXX-XXX" for readability.
    n = secrets.randbelow(10 ** PAIRING_DIGITS)
    s = str(n).zfill(PAIRING_DIGITS)
    return f"{s[:3]}-{s[3:]}"


def _gen_tv_token() -> str:
    return "tv_" + secrets.token_urlsafe(24)


class CreateVenueReq(BaseModel):
    name:            str
    address:         Optional[str] = None
    lat:              Optional[float] = None
    lng:              Optional[float] = None
    market:           Optional[str] = "dubai"
    google_place_id: Optional[str] = None
    phone:            Optional[str] = None
    website:          Optional[str] = None
    hours:            Optional[dict] = None
    plan_tier:       str = "starter"


class StaffInviteReq(BaseModel):
    email: str
    role:    str = "staff"


class TVClaimReq(BaseModel):
    pairing_code: str


class TriviaStartReq(BaseModel):
    category_id: str


class AnnouncementReq(BaseModel):
    message:    str
    emoji:       Optional[str] = None
    target:      str = "all_rooms"   # "all_rooms" | "specific_room"
    room_code: Optional[str] = None


class RedeemReq(BaseModel):
    code: str


class OfferCreateReq(BaseModel):
    title:                str
    description:         Optional[str] = None
    offer_type:          str = "percent"   # percent | flat | free_item | bogo
    discount_value:    float = 0
    start_time:          Optional[datetime] = None
    end_time:            Optional[datetime] = None
    max_redemptions:  Optional[int] = None
    daily_cap:           Optional[int] = None
    budget_cap_usd:  Optional[float] = None
    redemption_method: str = "qr_scan"
    terms:                Optional[str] = None
    hero_image_url:    Optional[str] = None


class OfferPatchReq(BaseModel):
    title:                Optional[str] = None
    description:         Optional[str] = None
    offer_type:          Optional[str] = None
    discount_value:    Optional[float] = None
    start_time:          Optional[datetime] = None
    end_time:            Optional[datetime] = None
    max_redemptions:  Optional[int] = None
    daily_cap:           Optional[int] = None
    budget_cap_usd:  Optional[float] = None
    redemption_method: Optional[str] = None
    terms:                Optional[str] = None
    hero_image_url:    Optional[str] = None
    status:               Optional[str] = None   # active|paused


# ─── Phase 17b body models (must live at module scope so FastAPI's
# Pydantic v2 body detection works — inline classes get treated as
# query params).
class TrackReq(BaseModel):
    stage:           str
    channel:        Optional[str] = None
    variant_slug: Optional[str] = None


class VariantReq(BaseModel):
    headline:        str
    description:     Optional[str] = None
    weight:           int = 50
    hero_image_url: Optional[str] = None


class CreateOrgReq(BaseModel):
    name:           str
    logo_url:      Optional[str] = None
    primary_color: Optional[str] = "#FF2D8A"


class LinkVenueReq(BaseModel):
    parent_org_id: Optional[str] = None


class BoostReq(BaseModel):
    duration_hours:      Optional[int]  = None
    discount_bump_pct: Optional[float] = None


def build_router(db, get_current_user) -> APIRouter:
    router = APIRouter(tags=["venues"])

    async def _staff_membership(venue_id: str, user_id: str) -> Optional[dict]:
        m = await db.venue_staff.find_one({"venue_id": venue_id, "user_id": user_id})
        return m

    async def _require_staff(venue_id: str, user: dict, *, owner: bool = False) -> dict:
        venue = await db.venues.find_one({"id": venue_id, "active": True})
        if not venue:
            raise HTTPException(status_code=404, detail="Venue not found")
        m = await _staff_membership(venue_id, user["user_id"])
        if not m:
            raise HTTPException(status_code=403, detail="Not a staff member of this venue")
        if owner and m["role"] != "owner":
            raise HTTPException(status_code=403, detail="Owner role required")
        return venue

    # ─── REST: create venue ────────────────────────────────────────────
    @router.post("/api/venue")
    async def create_venue(req: CreateVenueReq, request: Request,
                                  user: dict = Depends(get_current_user)):
        vid = "venue_" + uuid.uuid4().hex[:12]
        doc = {
            "id":               vid,
            "name":              req.name,
            "owner_user_id":   user["user_id"],
            "address":           req.address,
            "lat":                req.lat,
            "lng":                req.lng,
            "market":             req.market or "dubai",
            "google_place_id": req.google_place_id,
            "hours":              req.hours or {},
            "phone":              req.phone,
            "website":            req.website,
            "plan_tier":         req.plan_tier or "starter",
            "logo_url":          None,
            "primary_color":   "#FF2D8A",
            "business_id":      None,
            "active":             True,
            "created_at":        datetime.now(timezone.utc),
        }
        await db.venues.insert_one(doc)
        await db.venue_staff.insert_one({
            "id":          "vstaff_" + uuid.uuid4().hex[:12],
            "venue_id":   vid,
            "user_id":    user["user_id"],
            "role":        "owner",
            "created_at": datetime.now(timezone.utc),
        })
        return {"venue": _public_venue(doc)}

    # UX alias used by the marketing /for-business CTA.
    @router.post("/api/venue/onboard")
    async def onboard_venue(req: CreateVenueReq, request: Request,
                                    user: dict = Depends(get_current_user)):
        return await create_venue(req, request, user)

    @router.get("/api/venue/me")
    async def my_venues(request: Request,
                              user: dict = Depends(get_current_user)):
        memberships = await db.venue_staff.find({"user_id": user["user_id"]}).to_list(50)
        ids = [m["venue_id"] for m in memberships]
        if not ids:
            return {"venues": []}
        venues = await db.venues.find({"id": {"$in": ids}, "active": True}).to_list(50)
        # Attach role for the caller.
        role_by_vid = {m["venue_id"]: m["role"] for m in memberships}
        out = []
        for v in venues:
            pub = _public_venue(v)
            pub["my_role"] = role_by_vid.get(v["id"], "staff")
            out.append(pub)
        return {"venues": out}

    @router.get("/api/venue/{venue_id}")
    async def get_venue(venue_id: str, request: Request,
                                user: dict = Depends(get_current_user)):
        venue = await _require_staff(venue_id, user)
        staff = await db.venue_staff.find({"venue_id": venue_id}).to_list(50)
        # Hydrate staff names from users.
        uids = [s["user_id"] for s in staff]
        users = await db.users.find({"user_id": {"$in": uids}},
                                              {"_id": 0, "user_id": 1, "name": 1, "email": 1}).to_list(50)
        u_by_id = {u["user_id"]: u for u in users}
        staff_out = []
        for s in staff:
            u = u_by_id.get(s["user_id"], {})
            staff_out.append({
                "user_id":   s["user_id"],
                "role":       s["role"],
                "name":       u.get("name"),
                "email":      u.get("email"),
                "created_at": s.get("created_at"),
            })
        return {"venue": _public_venue(venue), "staff": staff_out}

    # ─── REST: staff invite/remove ────────────────────────────────────
    @router.post("/api/venue/{venue_id}/staff")
    async def invite_staff(venue_id: str, req: StaffInviteReq, request: Request,
                                  user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user, owner=True)
        if req.role not in ("manager", "staff"):
            raise HTTPException(status_code=400, detail="Invalid role")
        invitee = await db.users.find_one({"email": req.email.lower().strip()},
                                                  {"_id": 0, "user_id": 1, "name": 1, "email": 1})
        if not invitee:
            raise HTTPException(status_code=404, detail="No user with that email")
        existing = await db.venue_staff.find_one({"venue_id": venue_id,
                                                            "user_id": invitee["user_id"]})
        if existing:
            return {"ok": True, "already_member": True}
        await db.venue_staff.insert_one({
            "id":          "vstaff_" + uuid.uuid4().hex[:12],
            "venue_id":   venue_id,
            "user_id":    invitee["user_id"],
            "role":        req.role,
            "created_at": datetime.now(timezone.utc),
        })
        return {"ok": True, "user_id": invitee["user_id"]}

    @router.delete("/api/venue/{venue_id}/staff/{user_id}")
    async def remove_staff(venue_id: str, user_id: str, request: Request,
                                    user: dict = Depends(get_current_user)):
        venue = await _require_staff(venue_id, user, owner=True)
        if user_id == venue["owner_user_id"]:
            raise HTTPException(status_code=400, detail="Cannot remove the owner")
        await db.venue_staff.delete_one({"venue_id": venue_id, "user_id": user_id})
        return {"ok": True}

    # ─── REST: TV pairing ─────────────────────────────────────────────
    @router.post("/api/venue/{venue_id}/tvs/pair")
    async def issue_pairing_code(venue_id: str, request: Request,
                                            user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        code = _gen_pairing_code()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=PAIRING_CODE_TTL_SEC)
        await db.tv_pairings.insert_one({
            "id":             "tvp_" + uuid.uuid4().hex[:12],
            "venue_id":      venue_id,
            "pairing_code": code,
            "tv_token":      None,
            "status":         "pending",
            "created_by":    user["user_id"],
            "expires_at":    expires_at,
            "paired_at":     None,
            "last_seen":     None,
            "label":           None,
            "active":          True,
            "created_at":     datetime.now(timezone.utc),
        })
        return {"pairing_code": code,
                  "expires_at":     expires_at.isoformat(),
                  "ttl_sec":         PAIRING_CODE_TTL_SEC}

    @router.get("/api/venue/{venue_id}/tvs")
    async def list_tvs(venue_id: str, request: Request,
                              user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        pairings = await db.tv_pairings.find({"venue_id": venue_id, "active": True})\
                                                  .sort("created_at", -1).to_list(100)
        out = []
        for p in pairings:
            p.pop("_id", None)
            # Expire pending codes lazily.
            if (p["status"] == "pending" and p["expires_at"]
                    and _utc(p["expires_at"]) < datetime.now(timezone.utc)):
                await db.tv_pairings.update_one({"id": p["id"]},
                                                          {"$set": {"status": "expired"}})
                p["status"] = "expired"
            # Mask the long-lived token.
            tok = p.get("tv_token")
            if tok:
                p["tv_token_preview"] = tok[:8] + "…"
                p.pop("tv_token", None)
            out.append(p)
        return {"tvs": out}

    @router.post("/api/venue/{venue_id}/tvs/{tv_id}/revoke")
    async def revoke_tv(venue_id: str, tv_id: str, request: Request,
                                user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        p = await db.tv_pairings.find_one({"venue_id": venue_id, "id": tv_id})
        if not p:
            raise HTTPException(status_code=404, detail="TV not found")
        await db.tv_pairings.update_one(
            {"id": tv_id},
            {"$set": {"status": "revoked", "active": False}},
        )
        # Knock the live WS off if it's still attached.
        hub: TVHub = request.app.state.venue_tv_hub
        await hub.revoke(venue_id, tv_id)
        return {"ok": True}

    # ─── TV-side: claim + identify ────────────────────────────────────
    @router.post("/api/tv/claim")
    async def claim_tv(req: TVClaimReq, request: Request):
        # No session auth — pairing code IS the auth.
        code = (req.pairing_code or "").strip().upper()
        # Allow with or without the hyphen for ergonomics.
        digits = "".join(c for c in code if c.isdigit())
        if len(digits) != PAIRING_DIGITS:
            raise HTTPException(status_code=400, detail={
                "code":    "bad_pairing_code",
                "message": f"Pairing code must be {PAIRING_DIGITS} digits.",
            })
        canon = f"{digits[:3]}-{digits[3:]}"
        p = await db.tv_pairings.find_one({"pairing_code": canon,
                                                      "status":         "pending"})
        if not p:
            raise HTTPException(status_code=404, detail={
                "code":    "pairing_not_found",
                "message": "No matching pairing code. Ask staff to generate a new one.",
            })
        if p["expires_at"] and _utc(p["expires_at"]) < datetime.now(timezone.utc):
            await db.tv_pairings.update_one({"id": p["id"]},
                                                      {"$set": {"status": "expired"}})
            raise HTTPException(status_code=410, detail={
                "code":    "pairing_expired",
                "message": "Pairing code expired. Ask staff to generate a new one.",
            })
        token = _gen_tv_token()
        await db.tv_pairings.update_one(
            {"id": p["id"]},
            {"$set": {
                "tv_token":   token,
                "status":     "active",
                "paired_at":  datetime.now(timezone.utc),
                "last_seen":  datetime.now(timezone.utc),
            }},
        )
        venue = await db.venues.find_one({"id": p["venue_id"]})
        return {
            "tv_token": token,
            "tv_id":     p["id"],
            "venue":     _public_venue(venue) if venue else {"id": p["venue_id"]},
        }

    @router.get("/api/tv/me")
    async def tv_me(request: Request, token: str = Query(...)):
        p = await db.tv_pairings.find_one({"tv_token": token, "status": "active"})
        if not p:
            raise HTTPException(status_code=401, detail="Invalid or revoked TV token")
        await db.tv_pairings.update_one({"id": p["id"]},
                                                  {"$set": {"last_seen": datetime.now(timezone.utc)}})
        venue = await db.venues.find_one({"id": p["venue_id"]})
        rh: RoomHub = request.app.state.trivia_room_hub
        active = [r.to_public() for r in rh.all_rooms().values()
                       if getattr(r, "venue_id", None) == p["venue_id"] and r.phase != "done"]
        return {"tv_id": p["id"],
                  "venue":  _public_venue(venue) if venue else None,
                  "active_rooms": active}

    # ─── REST: venue-branded trivia + announcement + redeem ────────────
    @router.post("/api/venue/{venue_id}/trivia/start")
    async def venue_trivia_start(venue_id: str, req: TriviaStartReq, request: Request,
                                          user: dict = Depends(get_current_user)):
        venue = await _require_staff(venue_id, user)
        cat = await db.trivia_categories.find_one({"id": req.category_id, "active": True})
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        hub: RoomHub = request.app.state.trivia_room_hub
        room = await hub.create(
            host_user={"user_id": user["user_id"],
                            "name":     venue["name"],
                            "avatar":   venue.get("logo_url")},
            category_id=req.category_id,
            category_slug=cat["slug"],
            market=venue.get("market") or "dubai",
            is_private=False,
            max_players=50,
        )
        # Stamp the room with venue_id so TVs + analytics can correlate.
        room.venue_id = venue_id   # in-memory tag
        await db.trivia_rooms.update_one(
            {"id": room.id} if hasattr(room, "id") else {"code": room.code},
            {"$set": {"venue_id": venue_id,
                        "started_at": datetime.now(timezone.utc),
                        "code":         room.code}},
            upsert=True,
        )
        # Tell paired TVs there's a new active room.
        tv_hub: TVHub = request.app.state.venue_tv_hub
        await tv_hub.broadcast(venue_id, {
            "type":  "venue_room_started",
            "room":   room.to_public(),
            "venue": _public_venue(venue),
        })
        # Notify followers / venue regulars about the new room
        asyncio.create_task(
            notify_room_followers(db, room, user,
                                  venue_name=venue.get("name")))
        return {"room_code": room.code, "room": room.to_public()}

    @router.post("/api/venue/{venue_id}/announcement")
    async def venue_announcement(venue_id: str, req: AnnouncementReq, request: Request,
                                          user: dict = Depends(get_current_user)):
        venue = await _require_staff(venue_id, user)
        msg = (req.message or "").strip()
        if not msg:
            raise HTTPException(status_code=400, detail="Message is empty")
        emoji = (req.emoji or "").strip() or None
        ann_id = "ann_" + uuid.uuid4().hex[:12]
        payload = {
            "type":          "venue_announcement",
            "id":             ann_id,
            "venue_id":      venue_id,
            "venue_name":   venue["name"],
            "message":       msg,
            "emoji":          emoji,
            "broadcast_at": _now_ms(),
        }
        # Persist for analytics + audit.
        await db.venue_announcements.insert_one({
            **payload,
            "created_by":    user["user_id"],
            "target":         req.target,
            "room_code":    req.room_code,
            "created_at":    datetime.now(timezone.utc),
        })
        # Broadcast to phones (via trivia RoomHub) + TVs (via TVHub).
        tv_hub: TVHub = request.app.state.venue_tv_hub
        await tv_hub.broadcast(venue_id, payload)
        rh: RoomHub = request.app.state.trivia_room_hub
        target_codes: List[str] = []
        if req.target == "specific_room" and req.room_code:
            target_codes = [req.room_code.upper()]
        else:
            for c, room in rh.all_rooms().items():
                if getattr(room, "venue_id", None) == venue_id:
                    target_codes.append(c)
        for code in target_codes:
            await rh.broadcast(code, payload)
        return {"ok": True, "id": ann_id, "rooms": target_codes,
                  "tvs":  tv_hub.tvs_for(venue_id)}

    @router.post("/api/venue/{venue_id}/coupons/redeem")
    async def redeem_coupon(venue_id: str, req: RedeemReq, request: Request,
                                    user: dict = Depends(get_current_user)):
        venue = await _require_staff(venue_id, user)
        code = (req.code or "").strip()
        if not code:
            raise HTTPException(status_code=400, detail="Code is empty")
        # Match either coupon_id or a short_code field; accept upper/lower.
        c = await db.coupons.find_one({"$or": [
            {"coupon_id": code}, {"coupon_id": code.upper()},
            {"short_code": code}, {"short_code": code.upper()},
        ]})
        if not c:
            raise HTTPException(status_code=404, detail={
                "code":    "coupon_not_found",
                "message": "No coupon with that code.",
            })
        # Make sure the coupon belongs to a business attached to this venue.
        own_biz_id = venue.get("business_id")
        if own_biz_id and c.get("business_id") != own_biz_id:
            raise HTTPException(status_code=403, detail={
                "code":    "wrong_venue",
                "message": "Coupon is not redeemable at this venue.",
            })
        if c.get("redeemed_at"):
            raise HTTPException(status_code=409, detail={
                "code":         "already_redeemed",
                "message":      "This coupon has already been redeemed.",
                "redeemed_at": c["redeemed_at"].isoformat() if hasattr(c["redeemed_at"], "isoformat") else str(c.get("redeemed_at")),
            })
        now = datetime.now(timezone.utc)
        await db.coupons.update_one(
            {"coupon_id": c["coupon_id"]},
            {"$set": {"redeemed_at": now,
                        "redeemed_by": user["user_id"],
                        "redeemed_venue_id": venue_id,
                        "status": "redeemed"}},
        )
        return {"ok": True,
                  "coupon_id":    c["coupon_id"],
                  "redeemed_at": now.isoformat()}

    @router.get("/api/venue/{venue_id}/stats")
    async def venue_stats(venue_id: str, request: Request, period: str = "today",
                                user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        now = datetime.now(timezone.utc)
        since = {
            "today": now - timedelta(days=1),
            "week":   now - timedelta(days=7),
            "month": now - timedelta(days=30),
        }.get(period, now - timedelta(days=1))
        rooms = await db.trivia_rooms.count_documents(
            {"venue_id": venue_id, "started_at": {"$gte": since}})
        coupons = await db.coupons.count_documents(
            {"redeemed_venue_id": venue_id, "redeemed_at": {"$gte": since}})
        anns = await db.venue_announcements.count_documents(
            {"venue_id": venue_id, "created_at": {"$gte": since}})
        # Live player count from the in-memory hub.
        rh: RoomHub = request.app.state.trivia_room_hub
        live_players = 0
        live_rooms   = 0
        for room in rh.all_rooms().values():
            if getattr(room, "venue_id", None) == venue_id and room.phase != "done":
                live_rooms   += 1
                live_players += len(room.players)
        return {
            "period":         period,
            "rooms":          rooms,
            "coupons":        coupons,
            "announcements": anns,
            "live_players":  live_players,
            "live_rooms":    live_rooms,
        }

    @router.get("/api/venue/{venue_id}/players")
    async def venue_players(venue_id: str, request: Request,
                                  user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        rh: RoomHub = request.app.state.trivia_room_hub
        out = []
        for room in rh.all_rooms().values():
            if getattr(room, "venue_id", None) != venue_id or room.phase == "done":
                continue
            for p in room.players.values():
                out.append({
                    "user_id":   p.user_id,
                    "name":       p.name,
                    "score":      p.score,
                    "connected": p.ws is not None,
                    "room_code": room.code,
                })
        return {"players": out}

    @router.delete("/api/venue/{venue_id}/rooms/{code}/players/{user_id}")
    async def venue_kick(venue_id: str, code: str, user_id: str, request: Request,
                                user: dict = Depends(get_current_user)):
        """Staff-driven kick — re-uses Phase 16b `RoomHub.kick` (targeted
        kicked event + 4001 close + player_left broadcast)."""
        await _require_staff(venue_id, user)
        rh: RoomHub = request.app.state.trivia_room_hub
        room = rh.get(code)
        if not room or getattr(room, "venue_id", None) != venue_id:
            raise HTTPException(status_code=404, detail="Room not found in this venue")
        await rh.kick(code, user_id)
        return {"ok": True}

    # ─── REST: offers CRUD + caps + bulk import (Phase 17a) ───────────
    from services.offers import (
        public_offer, CSV_HEADER, CSV_EXAMPLES,
        CapacityError, issue_coupon_for_offer,
    )

    async def _edit_role(venue_id: str, user: dict) -> dict:
        """Owner OR manager can mutate offers; staff is view-only."""
        venue = await db.venues.find_one({"id": venue_id, "active": True})
        if not venue:
            raise HTTPException(404, "Venue not found")
        m = await db.venue_staff.find_one({"venue_id": venue_id, "user_id": user["user_id"]})
        if not m:
            raise HTTPException(403, "Not a staff member")
        if m["role"] not in ("owner", "manager"):
            raise HTTPException(403, {"code": "role_required",
                                              "message": "Owner or manager role required."})
        return venue

    @router.post("/api/venue/{venue_id}/offers")
    async def create_offer(venue_id: str, req: OfferCreateReq, request: Request,
                                    user: dict = Depends(get_current_user)):
        venue = await _edit_role(venue_id, user)
        new_id = "ofr_" + uuid.uuid4().hex[:12]
        doc = {
            "id":                  new_id,
            "offer_id":           new_id,   # legacy unique index parity (Phase 6)
            "venue_id":           venue_id,
            "business_id":      venue.get("business_id"),
            "market":              venue.get("market") or "dubai",
            **req.model_dump(),
            "status":              "active",
            "issued_count":     0,
            "redeemed_count": 0,
            "created_by":       user["user_id"],
            "created_at":       datetime.now(timezone.utc),
            "updated_at":       datetime.now(timezone.utc),
        }
        await db.offers.insert_one(doc)
        return {"offer": public_offer(doc)}

    @router.patch("/api/venue/{venue_id}/offers/{offer_id}")
    async def patch_offer(venue_id: str, offer_id: str, req: OfferPatchReq, request: Request,
                                  user: dict = Depends(get_current_user)):
        await _edit_role(venue_id, user)
        patch = {k: v for k, v in req.model_dump(exclude_unset=True).items() if v is not None}
        if "status" in patch and patch["status"] not in ("active", "paused", "archived"):
            raise HTTPException(400, "Invalid status")
        patch["updated_at"] = datetime.now(timezone.utc)
        r = await db.offers.update_one({"id": offer_id, "venue_id": venue_id},
                                                      {"$set": patch})
        if r.matched_count == 0:
            raise HTTPException(404, "Offer not found")
        o = await db.offers.find_one({"id": offer_id})
        return {"offer": public_offer(o)}

    @router.delete("/api/venue/{venue_id}/offers/{offer_id}")
    async def delete_offer(venue_id: str, offer_id: str, request: Request,
                                    user: dict = Depends(get_current_user)):
        await _edit_role(venue_id, user)
        r = await db.offers.update_one(
            {"id": offer_id, "venue_id": venue_id},
            {"$set": {"status": "archived",
                        "archived_at": datetime.now(timezone.utc),
                        "updated_at":  datetime.now(timezone.utc)}},
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Offer not found")
        return {"ok": True}

    @router.get("/api/venue/{venue_id}/offers")
    async def list_offers(venue_id: str, request: Request,
                                status: Optional[str] = Query(None),
                                limit: int = Query(50, ge=1, le=200),
                                user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        q: dict = {"venue_id": venue_id}
        if status:
            q["status"] = status
        cur = db.offers.find(q).sort("created_at", -1).limit(limit)
        offers = [public_offer(o) for o in await cur.to_list(limit)]
        return {"offers": offers, "count": len(offers)}

    @router.get("/api/venue/{venue_id}/offers/{offer_id}")
    async def get_offer(venue_id: str, offer_id: str, request: Request,
                                user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        o = await db.offers.find_one({"id": offer_id, "venue_id": venue_id})
        if not o:
            raise HTTPException(404, "Offer not found")
        coupon_count = await db.coupons.count_documents({"offer_id": offer_id})
        return {"offer": public_offer(o), "coupon_count": coupon_count}

    @router.post("/api/venue/{venue_id}/offers/{offer_id}/resume")
    async def resume_offer(venue_id: str, offer_id: str, request: Request,
                                    user: dict = Depends(get_current_user)):
        """Idempotent — calling resume on an already-active offer is a no-op."""
        await _edit_role(venue_id, user)
        r = await db.offers.update_one(
            {"id": offer_id, "venue_id": venue_id},
            {"$set": {"status":            "active",
                        "auto_paused_at":    None,
                        "auto_paused_reason": None,
                        "updated_at":         datetime.now(timezone.utc)}},
        )
        if r.matched_count == 0:
            raise HTTPException(404, "Offer not found")
        o = await db.offers.find_one({"id": offer_id})
        return {"ok": True, "offer": public_offer(o)}

    # ─── Bulk CSV import ─────────────────────────────────────────────
    BULK_MAX_ROWS = 500
    REQUIRED_COLS  = {"title", "offer_type", "discount_value"}

    def _parse_dt(v: str):
        if not v:
            return None
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception:
            return None

    @router.post("/api/venue/{venue_id}/offers/bulk_import")
    async def bulk_import(venue_id: str, request: Request,
                                  file: UploadFile = File(...),
                                  dry_run: bool = Query(False),
                                  user: dict = Depends(get_current_user)):
        venue = await _edit_role(venue_id, user)
        body = (await file.read()).decode("utf-8-sig", errors="ignore")
        reader = csv.DictReader(io.StringIO(body))
        # Validate header.
        missing = REQUIRED_COLS - set([h.strip() for h in (reader.fieldnames or [])])
        if missing:
            raise HTTPException(400, {"code": "missing_columns",
                                              "message": f"CSV missing columns: {sorted(missing)}"})
        results: list[dict] = []
        to_insert: list[dict] = []
        for idx, row in enumerate(reader, start=2):   # 2 = first data row in 1-indexed CSV
            if idx > BULK_MAX_ROWS + 1:
                # Header counted as row 1, so 501 data rows max.
                raise HTTPException(400, {"code": "too_many_rows",
                                                  "message": f"Max {BULK_MAX_ROWS} rows per import."})
            r = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            err = None
            if not r.get("title"):                       err = "title is required"
            elif not r.get("offer_type"):              err = "offer_type is required"
            elif r.get("offer_type") not in ("percent", "flat", "free_item", "bogo"):
                err = "offer_type must be percent|flat|free_item|bogo"
            try:
                discount = float(r.get("discount_value") or 0)
            except ValueError:
                err = "discount_value must be a number"
                discount = 0
            try:
                max_red = int(r.get("max_redemptions")) if r.get("max_redemptions") else None
            except ValueError:
                err = "max_redemptions must be an integer"
                max_red = None
            start_dt = _parse_dt(r.get("start_time"))
            end_dt   = _parse_dt(r.get("end_time"))
            if r.get("start_time") and start_dt is None:  err = "start_time invalid ISO-8601"
            if r.get("end_time")    and end_dt   is None:  err = "end_time invalid ISO-8601"

            if err:
                results.append({"row": idx, "status": "failed", "error": err})
                continue
            new_id = "ofr_" + uuid.uuid4().hex[:12]
            doc = {
                "id":                  new_id,
                "offer_id":           new_id,
                "venue_id":           venue_id,
                "business_id":      venue.get("business_id"),
                "market":              venue.get("market") or "dubai",
                "title":                r["title"],
                "description":       r.get("description") or None,
                "offer_type":        r["offer_type"],
                "discount_value":  discount,
                "start_time":        start_dt,
                "end_time":          end_dt,
                "max_redemptions": max_red,
                "redemption_method": r.get("redemption_method") or "qr_scan",
                "terms":              r.get("terms") or None,
                "status":             "active",
                "issued_count":     0,
                "redeemed_count": 0,
                "created_by":       user["user_id"],
                "created_at":       datetime.now(timezone.utc),
                "updated_at":       datetime.now(timezone.utc),
            }
            results.append({"row": idx, "status": "created", "offer_id": doc["id"]})
            to_insert.append(doc)

        if dry_run:
            return {"results": results, "dry_run": True,
                      "would_create": len(to_insert),
                      "failed": sum(1 for r in results if r["status"] == "failed")}
        if to_insert:
            await db.offers.insert_many(to_insert)
        return {"results": results, "dry_run": False,
                  "created": len(to_insert),
                  "failed":   sum(1 for r in results if r["status"] == "failed")}

    @router.get("/api/venue/offers/csv_template")
    async def csv_template():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(CSV_HEADER)
        for row in CSV_EXAMPLES:
            w.writerow(row)
        buf.seek(0)
        return StreamingResponse(
            iter([buf.read()]),
            media_type="text/csv",
            headers={"Content-Disposition":
                       'attachment; filename="bigfm_offers_template.csv"'},
        )

    # ─── Phase 17b — Funnel analytics, A/B variants, orgs, payouts ────
    from services.offer_analytics import (
        track_event, funnel_for_offer, variant_results,
        assign_variant, org_rollup, payout_summary, STAGES,
    )

    @router.post("/api/offers/{offer_id}/track")
    async def track_offer_event(offer_id: str, req: TrackReq, request: Request,
                                          user: dict = Depends(get_current_user)):
        if req.stage not in STAGES:
            raise HTTPException(400, "Invalid stage")
        offer = await db.offers.find_one({"id": offer_id})
        if not offer:
            raise HTTPException(404, "Offer not found")
        await track_event(db, offer_id=offer_id, stage=req.stage,
                                user_id=user["user_id"], venue_id=offer.get("venue_id"),
                                channel=req.channel, variant_slug=req.variant_slug)
        return {"ok": True}

    def _period_window(period: str) -> tuple[datetime, datetime]:
        now = datetime.now(timezone.utc)
        if period == "today":
            return now - timedelta(days=1), now
        if period == "week":
            return now - timedelta(days=7), now
        if period == "month":
            return now - timedelta(days=30), now
        return now - timedelta(days=30), now

    @router.get("/api/venue/{venue_id}/offers/{offer_id}/funnel")
    async def get_funnel(venue_id: str, offer_id: str, request: Request,
                                period: str = Query("month"),
                                user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        frm, to = _period_window(period)
        return await funnel_for_offer(db, offer_id=offer_id, frm=frm, to=to)

    # ─── Phase 17c — Boost endpoints ───────────────────────────────
    from services.offer_boost import (start_boost, list_boosts,
                                                            compute_boost_eligibility)

    @router.post("/api/venue/{venue_id}/offers/{offer_id}/boost")
    async def boost_offer(venue_id: str, offer_id: str, req: BoostReq,
                                      user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user, owner=True)
        try:
            out = await start_boost(
                db, venue_id=venue_id, offer_id=offer_id,
                duration_hours=req.duration_hours or 24,
                discount_bump_pct=req.discount_bump_pct or 5.0)
            return {"ok": True, "boost": out}
        except LookupError:
            raise HTTPException(404, "offer not found")
        except PermissionError as pe:
            raise HTTPException(409, pe.args[0])

    @router.get("/api/venue/{venue_id}/offers/{offer_id}/boosts")
    async def list_offer_boosts(venue_id: str, offer_id: str,
                                                limit: int = Query(10, ge=1, le=50),
                                                user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        return {"boosts": await list_boosts(db, venue_id=venue_id,
                                                              offer_id=offer_id, limit=limit)}

    @router.post("/api/venue/{venue_id}/offers/{offer_id}/variants")
    async def create_variant(venue_id: str, offer_id: str, req: VariantReq, request: Request,
                                      user: dict = Depends(get_current_user)):
        await _edit_role(venue_id, user)
        offer = await db.offers.find_one({"id": offer_id, "venue_id": venue_id})
        if not offer:
            raise HTTPException(404, "Offer not found")
        variants = offer.get("variants") or []
        if not variants:
            # Lazy-seed the control variant from the offer fields.
            variants = [{
                "slug":            "control",
                "headline":      offer.get("title"),
                "description": offer.get("description"),
                "weight":         50,
                "status":         "active",
            }]
        slug = f"v{len(variants)}"
        new = {
            "slug":            slug,
            "headline":      req.headline,
            "description": req.description,
            "weight":         int(req.weight),
            "status":         "active",
            "hero_image_url": req.hero_image_url,
        }
        variants.append(new)
        await db.offers.update_one(
            {"id": offer_id},
            {"$set": {"variants": variants, "updated_at": datetime.now(timezone.utc)}},
        )
        return {"variants": variants, "added": new}

    @router.get("/api/venue/{venue_id}/offers/{offer_id}/variants/results")
    async def variant_results_endpoint(venue_id: str, offer_id: str, request: Request,
                                                          period: str = Query("month"),
                                                          user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        offer = await db.offers.find_one({"id": offer_id, "venue_id": venue_id})
        if not offer:
            raise HTTPException(404, "Offer not found")
        variants = offer.get("variants") or [{
            "slug":     "control",
            "headline": offer.get("title"),
            "weight":   100,
            "status":   "active",
        }]
        frm, to = _period_window(period)
        return await variant_results(db, offer_id=offer_id, frm=frm, to=to,
                                                    variants=variants)

    @router.post("/api/venue/{venue_id}/offers/{offer_id}/variants/{slug}/promote")
    async def promote_winner(venue_id: str, offer_id: str, slug: str, request: Request,
                                          user: dict = Depends(get_current_user)):
        """Sets the named variant to weight 100, all others to 0."""
        await _edit_role(venue_id, user)
        offer = await db.offers.find_one({"id": offer_id, "venue_id": venue_id})
        if not offer:
            raise HTTPException(404, "Offer not found")
        variants = offer.get("variants") or []
        found = False
        for v in variants:
            if v["slug"] == slug:
                v["weight"] = 100
                found = True
            else:
                v["weight"] = 0
        if not found:
            raise HTTPException(404, "Variant not found")
        await db.offers.update_one({"id": offer_id},
                                              {"$set": {"variants": variants,
                                                          "winning_variant": slug,
                                                          "updated_at": datetime.now(timezone.utc)}})
        return {"ok": True, "variants": variants}

    # ─── Orgs ─────────────────────────────────────────────────────────
    @router.post("/api/venue/orgs")
    async def create_org(req: CreateOrgReq, request: Request,
                                user: dict = Depends(get_current_user)):
        org_id = "org_" + uuid.uuid4().hex[:12]
        doc = {
            "id":               org_id,
            "name":              req.name,
            "owner_user_id":   user["user_id"],
            "logo_url":          req.logo_url,
            "primary_color":   req.primary_color or "#FF2D8A",
            "created_at":       datetime.now(timezone.utc),
        }
        await db.venue_orgs.insert_one(doc)
        return {"org": {k: v for k, v in doc.items() if k != "_id"}}

    @router.get("/api/venue/orgs/me")
    async def my_orgs(request: Request,
                              user: dict = Depends(get_current_user)):
        orgs = await db.venue_orgs.find({"owner_user_id": user["user_id"]}).to_list(50)
        return {"orgs": [{k: v for k, v in o.items() if k != "_id"} for o in orgs]}

    @router.get("/api/venue/orgs/{org_id}")
    async def get_org(org_id: str, request: Request,
                            user: dict = Depends(get_current_user)):
        org = await db.venue_orgs.find_one({"id": org_id})
        if not org:
            raise HTTPException(404, "Org not found")
        if org["owner_user_id"] != user["user_id"]:
            raise HTTPException(403, "Only the org owner can view the rollup")
        return {"org": {k: v for k, v in org.items() if k != "_id"}}

    @router.get("/api/venue/orgs/{org_id}/rollup")
    async def get_org_rollup(org_id: str, request: Request,
                                      period: str = Query("month"),
                                      user: dict = Depends(get_current_user)):
        org = await db.venue_orgs.find_one({"id": org_id})
        if not org:
            raise HTTPException(404, "Org not found")
        if org["owner_user_id"] != user["user_id"]:
            raise HTTPException(403, "Only the org owner can view the rollup")
        frm, _to = _period_window(period)
        rh = request.app.state.trivia_room_hub
        rollup = await org_rollup(db, org_id=org_id, since=frm, rh=rh)
        rollup["org"] = {"id": org["id"], "name": org["name"],
                                "logo_url": org.get("logo_url"),
                                "primary_color": org.get("primary_color")}
        return rollup

    # Link / unlink a venue under an org.
    @router.patch("/api/venue/{venue_id}/org")
    async def link_venue_to_org(venue_id: str, req: LinkVenueReq, request: Request,
                                            user: dict = Depends(get_current_user)):
        venue = await _require_staff(venue_id, user, owner=True)
        if req.parent_org_id:
            org = await db.venue_orgs.find_one({"id": req.parent_org_id})
            if not org:
                raise HTTPException(404, "Org not found")
            if org["owner_user_id"] != user["user_id"]:
                raise HTTPException(403, "You don't own that org")
        await db.venues.update_one({"id": venue_id},
                                              {"$set": {"parent_org_id": req.parent_org_id}})
        return {"ok": True}

    # ─── Payouts ──────────────────────────────────────────────────────
    @router.get("/api/venue/{venue_id}/payouts")
    async def payouts_report(venue_id: str, request: Request,
                                      period: str = Query("month"),
                                      user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        frm, to = _period_window(period)
        return await payout_summary(db, venue_id=venue_id, since=frm, until=to)

    @router.get("/api/venue/{venue_id}/payouts/export.csv")
    async def payouts_csv(venue_id: str, request: Request,
                                 period: str = Query("month"),
                                 user: dict = Depends(get_current_user)):
        await _require_staff(venue_id, user)
        frm, to = _period_window(period)
        rep = await payout_summary(db, venue_id=venue_id, since=frm, until=to)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["day", "redemptions", "value_usd", "bigcoin_usd"])
        for b in rep["time_buckets"]:
            w.writerow([b["day"], b["redemptions"], b["value_usd"], b["bigcoin_usd"]])
        # Footer summary.
        w.writerow([])
        w.writerow(["Summary"])
        w.writerow(["cash_redemptions_value_usd",      rep["cash_redemptions_value_usd"]])
        w.writerow(["bigcoin_liability_usd",              rep["bigcoin_liability_usd"]])
        w.writerow(["net_platform_revenue_share_usd", rep["net_platform_revenue_share_usd"]])
        w.writerow(["expected_payout_to_venue_usd",   rep["expected_payout_to_venue_usd"]])
        buf.seek(0)
        return StreamingResponse(
            iter([buf.read()]), media_type="text/csv",
            headers={"Content-Disposition":
                       f'attachment; filename="payouts_{venue_id}_{period}.csv"'},
        )

    # ─── WebSocket: TV display ────────────────────────────────────────
    @router.websocket("/api/tv/ws")
    async def tv_ws(websocket: WebSocket, token: str = Query(...)):
        await websocket.accept()
        p = await db.tv_pairings.find_one({"tv_token": token, "status": "active"})
        if not p:
            await websocket.send_text(json.dumps({"type": "error",
                                                      "code": "invalid_token"}))
            await websocket.close(code=4401)
            return
        venue = await db.venues.find_one({"id": p["venue_id"]}) or {}
        tv_hub: TVHub = websocket.app.state.venue_tv_hub
        rh: RoomHub  = websocket.app.state.trivia_room_hub
        tv_hub.attach(p["venue_id"], p["id"], websocket)
        # Initial snapshot: venue + currently active rooms for it.
        active = []
        for room in rh.all_rooms().values():
            if getattr(room, "venue_id", None) == p["venue_id"] and room.phase != "done":
                active.append(room.to_public())
        await websocket.send_text(json.dumps({
            "type":          "hello",
            "server_now":   _now_ms(),
            "tv_id":         p["id"],
            "venue":          _public_venue(venue),
            "active_rooms": active,
        }, default=str))
        try:
            while True:
                _ = await websocket.receive_text()   # TV is read-only; ignore client msgs
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning("[tv_ws] %s/%s socket error: %s", p["venue_id"], p["id"], e)
        finally:
            tv_hub.detach(p["venue_id"], p["id"], websocket)

    return router


# ─── Helpers ───────────────────────────────────────────────────────────
def _public_venue(v: Optional[dict]) -> dict:
    if not v:
        return {}
    return {
        "id":               v.get("id"),
        "name":              v.get("name"),
        "address":           v.get("address"),
        "market":             v.get("market"),
        "phone":              v.get("phone"),
        "website":            v.get("website"),
        "hours":              v.get("hours") or {},
        "logo_url":          v.get("logo_url"),
        "primary_color":   v.get("primary_color") or "#FF2D8A",
        "plan_tier":         v.get("plan_tier") or "starter",
        "owner_user_id": v.get("owner_user_id"),
        "business_id":     v.get("business_id"),
    }


def _utc(dt) -> datetime:
    if dt is None:
        return datetime.now(timezone.utc)
    if getattr(dt, "tzinfo", None) is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
