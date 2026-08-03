"""Phase 9c — Local Commerce: business profiles, offers, coupons,
partner onboarding, POS scaffolds, redemption audit.

Concept distinction:
- A **gamification prize** (Phase 8a) is awarded probabilistically by a
  game outcome (spin, scratch, etc.).  Modeled in `game_prizes`.
- An **Offer** (Phase 9c) is a business's advertised deal available to
  any qualifying listener.  Modeled in `offers`.  An Offer can ALSO be
  used as a gamification prize via `prize.linked_offer_id`.

When a listener taps "Claim" on an offer, a **coupon** is created — a
single-use, time-bounded instance of that offer.  Coupons live in
`coupons` and carry a `qr_token` + `redemption_code` for partner-side
redemption (reusing the partner-token mechanism from Phase 8b).
"""
from __future__ import annotations

import logging
import re
import secrets
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("bigfm.commerce")

# ─── Enums / vocab ─────────────────────────────────────────────────────
OFFER_TYPES = {"percent_off", "flat_discount", "buy_one_get_one",
                  "free_item", "happy_hour", "prepaid_credit", "sampler",
                  "sponsored_meal"}
OFFER_STATUS = {"draft", "pending_approval", "active", "paused", "ended",
                    "rejected"}
CLAIM_SOURCES = {"public_page", "route_action_card", "map_search",
                    "rj_action_card", "game_prize_redemption"}
# Phase R.1.1 — Add "saved" (used by Phase H `save_coupon_v1`) alongside
# the pre-existing lifecycle statuses.  Legacy rows continue to use
# "claimed" as their initial state.
COUPON_STATUS = {"saved", "claimed", "redeemed", "expired", "revoked"}
REDEMPTION_METHODS = {"qr_code", "promo_code", "partner_pos_lookup"}
PARTNER_STATUSES = {"claimed", "verified", "suspended"}
POS_PROVIDERS = {"square", "toast", "clover", "lightspeed", "none"}

DEFAULT_REDEEM_WINDOW_SECONDS = 3600
DEFAULT_MAX_PER_USER = 1
MAX_CLAIM_RETRIES = 3


def _coerce_aware(dt):
    """Make a datetime timezone-aware (UTC) if it was returned naive by
    PyMongo / older inserts.  Returns None if input is None."""
    if dt is None:
        return None
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _now():
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _slugify(name: str, suffix: Optional[str] = None) -> str:
    """Conservative URL-safe slug: lowercase, ASCII, hyphenated."""
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    if not base:
        base = "business"
    if suffix:
        base = f"{base}-{re.sub(r'[^a-z0-9]+', '-', suffix.lower()).strip('-')}"
    return base[:80]


def _new_redemption_code() -> str:
    """8-char human-readable: BIGFM-XXXXX (10 total chars after prefix)."""
    chars = string.ascii_uppercase + "23456789"  # avoid 0/O/1/I
    return "BIGFM-" + "".join(secrets.choice(chars) for _ in range(5))


# ═══════════════════════════════════════════════════════════════════════
# Indexes
# ═══════════════════════════════════════════════════════════════════════
async def ensure_commerce_indexes(db) -> None:
    # businesses already has indexes from Phase 9a; add slug
    await db.businesses.create_index([("slug", 1)], unique=True, sparse=True)
    await db.businesses.create_index([("owner_user_ids", 1)])
    await db.businesses.create_index([("partner_status", 1)])
    # offers
    await db.offers.create_index([("offer_id", 1)], unique=True)
    await db.offers.create_index([("business_id", 1), ("status", 1)])
    await db.offers.create_index([("status", 1), ("end_at", 1)])
    # coupons
    await db.coupons.create_index([("coupon_id", 1)], unique=True)
    await db.coupons.create_index([("user_id", 1), ("status", 1)])
    await db.coupons.create_index([("offer_id", 1), ("claimed_at", -1)])
    await db.coupons.create_index([("qr_token", 1)], unique=True, sparse=True)
    await db.coupons.create_index([("redemption_code", 1)], unique=True,
                                              sparse=True)
    # partner POS scaffolds
    await db.partner_pos_integrations.create_index(
        [("integration_id", 1)], unique=True)
    await db.partner_pos_integrations.create_index(
        [("business_id", 1)])
    # redemption audit
    await db.offer_redemptions_audit.create_index(
        [("ts", -1)])
    await db.offer_redemptions_audit.create_index(
        [("business_id", 1), ("ts", -1)])
    await db.offer_redemptions_audit.create_index(
        [("coupon_id", 1)])


# ═══════════════════════════════════════════════════════════════════════
# Business helpers
# ═══════════════════════════════════════════════════════════════════════
async def assign_slug_if_missing(db, business_id: str) -> str:
    """If a business has no slug, mint one based on `name`.  Returns the
    resolved slug.  Re-runs safely."""
    biz = await db.businesses.find_one(
        {"business_id": business_id},
        {"slug": 1, "name": 1, "city": 1})
    if not biz:
        raise ValueError("business_not_found")
    if biz.get("slug"):
        return biz["slug"]
    base = _slugify(biz.get("name", "business"), biz.get("city"))
    candidate = base
    n = 0
    while await db.businesses.find_one({"slug": candidate}):
        n += 1
        candidate = f"{base}-{n}"
    await db.businesses.update_one(
        {"business_id": business_id}, {"$set": {"slug": candidate}})
    return candidate


def business_view(b: dict, *, public: bool = False) -> dict:
    """Sanitised business view.  Public mode strips owner/credential
    fields."""
    out = {
        "business_id": b.get("business_id"),
        "slug": b.get("slug"),
        "name": b.get("name"),
        "tagline": b.get("tagline"),
        "description": b.get("description"),
        "category": b.get("category"),
        "tags": b.get("tags") or b.get("cuisines") or [],
        "lat": b.get("lat"), "lng": b.get("lng"),
        "city": b.get("city"),
        "address": b.get("address"),
        "phone": b.get("phone"),
        "logo_url": b.get("logo_url"),
        "cover_image_url": b.get("cover_image_url"),
        "rating": b.get("rating"),
        "hours_json": b.get("hours_json") or b.get("hours"),
        "social_links_json": b.get("social_links_json") or {},
        "partner_status": b.get("partner_status"),
    }
    if not public:
        out.update({
            "owner_user_ids": b.get("owner_user_ids", []),
            "pos_integration": b.get("pos_integration"),
            "payout_method": b.get("payout_method"),
            "verified_at": b.get("verified_at"),
            "created_at": b.get("created_at"),
        })
    return {k: v for k, v in out.items() if v is not None}


async def claim_business(db, *, user_id: str,
                              slug: Optional[str] = None,
                              business_id: Optional[str] = None,
                              external_place_id: Optional[str] = None,
                              manual_business: Optional[dict] = None) -> dict:
    """Listener upgrades a business → partner relationship.

    Resolution priority: slug > business_id > external_place_id > manual.
    If none of the first three matches, a new business is created from
    `manual_business` (or a minimal scaffold).  The new partner_status
    becomes `claimed` and goes onto the admin verify queue.
    """
    biz = None
    if slug:
        biz = await db.businesses.find_one({"slug": slug})
    if not biz and business_id:
        biz = await db.businesses.find_one({"business_id": business_id})
    if not biz and external_place_id:
        biz = await db.businesses.find_one(
            {"external_place_id": external_place_id})
    if not biz:
        # Create a new scaffold
        m = manual_business or {}
        name = (m.get("name") or "").strip() or "New Business"
        new_id = _new_id("biz")
        lat_f = float(m.get("lat") or 0.0)
        lng_f = float(m.get("lng") or 0.0)
        biz = {
            "_id": new_id, "business_id": new_id,
            "name": name,
            "category": (m.get("category") or "other"),
            "lat": lat_f, "lng": lng_f,
            # Phase 9c.1 — GeoJSON `loc` is required for $nearSphere /
            # /public/businesses/nearby and the route_ad_engine offer
            # proximity scan.  Note: GeoJSON is [lng, lat] (longitude
            # first).
            "loc": {"type": "Point", "coordinates": [lng_f, lat_f]},
            "city": (m.get("city") or "dubai"),
            "address": m.get("address") or "",
            "phone": m.get("phone") or "",
            "rating": None,
            "external_place_id": external_place_id,
            "owner_user_ids": [],
            "created_at": _now(),
        }
        await db.businesses.insert_one(biz)
    bid = biz["business_id"]
    # If the existing row had scalar lat/lng but no GeoJSON loc, mirror
    # it now so future spatial queries find it.
    if biz.get("lat") is not None and biz.get("lng") is not None \
            and not biz.get("loc"):
        await db.businesses.update_one(
            {"business_id": bid},
            {"$set": {"loc": {"type": "Point",
                                  "coordinates": [float(biz["lng"]),
                                                       float(biz["lat"])]}}})
    await assign_slug_if_missing(db, bid)
    # Atomic add to owner_user_ids; set partner_status to claimed if
    # no prior verification has happened.
    update: dict = {
        "$addToSet": {"owner_user_ids": user_id},
        "$set": {"updated_at": _now()},
    }
    if not biz.get("partner_status"):
        update["$set"]["partner_status"] = "claimed"
    if not biz.get("claimed_at"):
        update["$set"]["claimed_at"] = _now()
    await db.businesses.update_one({"business_id": bid}, update)
    out = await db.businesses.find_one({"business_id": bid})
    return business_view(out)


# ═══════════════════════════════════════════════════════════════════════
# Offer lifecycle
# ═══════════════════════════════════════════════════════════════════════
def offer_view(o: dict, *, public: bool = False) -> dict:
    out = {
        "offer_id": o.get("offer_id"),
        "business_id": o.get("business_id"),
        "title": o.get("title"),
        "description": o.get("description"),
        "offer_type": o.get("offer_type"),
        "value_amount": o.get("value_amount"),
        "value_currency": o.get("value_currency"),
        "original_price": o.get("original_price"),
        "min_purchase": o.get("min_purchase"),
        "terms_text": o.get("terms_text"),
        "image_url": o.get("image_url"),
        "start_at": (o["start_at"].isoformat()
                       if isinstance(o.get("start_at"), datetime) else o.get("start_at")),
        "end_at": (o["end_at"].isoformat()
                     if isinstance(o.get("end_at"), datetime) else o.get("end_at")),
        "redeem_window_seconds": o.get("redeem_window_seconds"),
        "max_redemptions_total": o.get("max_redemptions_total"),
        "max_per_user": o.get("max_per_user"),
        "inventory_remaining": o.get("inventory_remaining"),
        "redemption_method": o.get("redemption_method"),
        "status": o.get("status"),
        # Phase 9c.1 — surface rejection state so the partner UI can
        # render a Revise CTA + show the reason.
        "rejection_reason": o.get("rejection_reason"),
        "rejected_at": (o["rejected_at"].isoformat()
                            if isinstance(o.get("rejected_at"), datetime)
                            else o.get("rejected_at")),
        "previous_rejections": o.get("previous_rejections", []),
    }
    if not public:
        out.update({
            "approved_by_user_id": o.get("approved_by_user_id"),
            "approved_at": (o["approved_at"].isoformat()
                                if isinstance(o.get("approved_at"), datetime)
                                else o.get("approved_at")),
            "created_at": (o["created_at"].isoformat()
                              if isinstance(o.get("created_at"), datetime)
                              else o.get("created_at")),
        })
    return {k: v for k, v in out.items() if v is not None}


async def create_offer(db, *, business_id: str, payload: dict) -> dict:
    """Partner creates an offer in `draft` state."""
    if payload.get("offer_type") not in OFFER_TYPES:
        raise ValueError(f"offer_type_invalid:{payload.get('offer_type')}")
    if payload.get("redemption_method", "qr_code") not in REDEMPTION_METHODS:
        raise ValueError("redemption_method_invalid")
    title = (payload.get("title") or "").strip()
    if not title or len(title) > 120:
        raise ValueError("title_required_max_120")
    now = _now()
    oid = _new_id("ofr")
    start_at = payload.get("start_at") or now
    end_at = payload.get("end_at") or (now + timedelta(days=30))
    if isinstance(start_at, str):
        start_at = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    if isinstance(end_at, str):
        end_at = datetime.fromisoformat(end_at.replace("Z", "+00:00"))
    inv_total = int(payload.get("max_redemptions_total") or 100)
    doc = {
        "_id": oid, "offer_id": oid, "business_id": business_id,
        "title": title,
        "description": payload.get("description", ""),
        "offer_type": payload["offer_type"],
        "value_amount": float(payload.get("value_amount") or 0),
        "value_currency": payload.get("value_currency", "AED"),
        "original_price": payload.get("original_price"),
        "min_purchase": payload.get("min_purchase"),
        "terms_text": payload.get("terms_text", ""),
        "image_url": payload.get("image_url"),
        "start_at": start_at, "end_at": end_at,
        "redeem_window_seconds": int(
            payload.get("redeem_window_seconds")
            or DEFAULT_REDEEM_WINDOW_SECONDS),
        "max_redemptions_total": inv_total,
        "max_per_user": int(payload.get("max_per_user")
                                  or DEFAULT_MAX_PER_USER),
        "inventory_remaining": inv_total,
        "redemption_method": payload.get("redemption_method", "qr_code"),
        "status": "draft",
        "created_at": now, "updated_at": now,
    }
    await db.offers.insert_one(doc)
    return offer_view(doc)


async def update_offer(db, *, offer_id: str, business_id: str,
                            patch: dict) -> Optional[dict]:
    """Partner edits.  Only fields a partner is allowed to mutate."""
    EDITABLE = {"title", "description", "value_amount", "value_currency",
                  "original_price", "min_purchase", "terms_text", "image_url",
                  "redeem_window_seconds", "max_redemptions_total",
                  "max_per_user", "redemption_method", "image_url",
                  "start_at", "end_at"}
    upd = {k: v for k, v in (patch or {}).items() if k in EDITABLE}
    if not upd:
        raise ValueError("no_editable_fields")
    # Coerce timestamps
    for k in ("start_at", "end_at"):
        if k in upd and isinstance(upd[k], str):
            upd[k] = datetime.fromisoformat(upd[k].replace("Z", "+00:00"))
    if "max_redemptions_total" in upd:
        upd["inventory_remaining"] = int(upd["max_redemptions_total"])
    upd["updated_at"] = _now()
    res = await db.offers.update_one(
        {"offer_id": offer_id, "business_id": business_id}, {"$set": upd})
    if res.matched_count == 0:
        return None
    o = await db.offers.find_one({"offer_id": offer_id})
    return offer_view(o)


async def submit_offer_for_approval(db, *, offer_id: str,
                                              business_id: str) -> dict:
    """Move draft → pending_approval.  No-op if already pending/active."""
    o = await db.offers.find_one(
        {"offer_id": offer_id, "business_id": business_id})
    if not o:
        raise ValueError("offer_not_found")
    if o["status"] not in ("draft", "paused"):
        raise ValueError(f"cannot_submit_from_status:{o['status']}")
    await db.offers.update_one(
        {"offer_id": offer_id},
        {"$set": {"status": "pending_approval", "updated_at": _now()}})
    o2 = await db.offers.find_one({"offer_id": offer_id})
    return offer_view(o2)


async def approve_offer(db, *, offer_id: str, admin_user_id: str) -> dict:
    o = await db.offers.find_one({"offer_id": offer_id})
    if not o:
        raise ValueError("offer_not_found")
    if o["status"] != "pending_approval":
        raise ValueError(f"cannot_approve_from_status:{o['status']}")
    now = _now()
    await db.offers.update_one(
        {"offer_id": offer_id},
        {"$set": {"status": "active", "approved_at": now,
                   "approved_by_user_id": admin_user_id,
                   "updated_at": now}})
    o2 = await db.offers.find_one({"offer_id": offer_id})
    return offer_view(o2)


async def reject_offer(db, *, offer_id: str, admin_user_id: str,
                            reason: str) -> dict:
    o = await db.offers.find_one({"offer_id": offer_id})
    if not o:
        raise ValueError("offer_not_found")
    if not reason or not reason.strip():
        raise ValueError("reason_required")
    now = _now()
    # Phase 9c.1 — go to a real "rejected" state.  The partner must call
    # `revise_offer` to acknowledge the reason before re-submitting.
    await db.offers.update_one(
        {"offer_id": offer_id},
        {"$set": {"status": "rejected", "rejected_at": now,
                   "rejected_by_user_id": admin_user_id,
                   "rejection_reason": reason.strip()[:500],
                   "updated_at": now}})
    o2 = await db.offers.find_one({"offer_id": offer_id})
    return offer_view(o2)


async def revise_offer(db, *, offer_id: str, business_id: str,
                            acknowledge_rejection_reason: bool) -> dict:
    """Phase 9c.1 — partner acknowledges a rejection and re-opens the
    offer for editing.  Archives the rejection reason in
    `previous_rejection_reason` so the audit trail survives.
    """
    o = await db.offers.find_one(
        {"offer_id": offer_id, "business_id": business_id})
    if not o:
        raise ValueError("offer_not_found")
    if o["status"] != "rejected":
        raise ValueError(f"cannot_revise_from_status:{o['status']}")
    if not acknowledge_rejection_reason:
        raise ValueError("acknowledge_rejection_reason_required")
    now = _now()
    prev_reason = o.get("rejection_reason")
    archive = {
        "reason": prev_reason,
        "rejected_at": (o.get("rejected_at").isoformat()
                            if hasattr(o.get("rejected_at"), "isoformat")
                            else o.get("rejected_at")),
        "rejected_by_user_id": o.get("rejected_by_user_id"),
        "acknowledged_at": now.isoformat(),
    }
    await db.offers.update_one(
        {"offer_id": offer_id},
        {"$set": {"status": "draft", "updated_at": now},
          "$push": {"previous_rejections": archive},
          "$unset": {"rejection_reason": "",
                      "rejected_at": "",
                      "rejected_by_user_id": ""}})
    return offer_view(await db.offers.find_one({"offer_id": offer_id}))


async def transition_offer_status(db, *, offer_id: str,
                                            business_id: Optional[str],
                                            new_status: str,
                                            allow_admin: bool = False) -> dict:
    """Pause / resume / end transitions.  business_id is required unless
    admin is overriding."""
    if new_status not in OFFER_STATUS:
        raise ValueError(f"invalid_status:{new_status}")
    q = {"offer_id": offer_id}
    if business_id and not allow_admin:
        q["business_id"] = business_id
    o = await db.offers.find_one(q)
    if not o:
        raise ValueError("offer_not_found")
    # Allowed status transitions are enforced inline below.
    if new_status == "active":
        if o["status"] not in ("paused",):
            raise ValueError(f"cannot_resume_from:{o['status']}")
    elif new_status == "paused":
        if o["status"] != "active":
            raise ValueError(f"cannot_pause_from:{o['status']}")
    elif new_status == "ended":
        if o["status"] not in ("active", "paused"):
            raise ValueError(f"cannot_end_from:{o['status']}")
    await db.offers.update_one(
        {"offer_id": offer_id},
        {"$set": {"status": new_status, "updated_at": _now()}})
    return offer_view(await db.offers.find_one({"offer_id": offer_id}))


# ═══════════════════════════════════════════════════════════════════════
# Listener: feed + claim
# ═══════════════════════════════════════════════════════════════════════
async def offers_feed(db, *, user_id: str, lat: Optional[float] = None,
                            lng: Optional[float] = None,
                            radius_m: int = 5000,
                            include_route: bool = True,
                            limit: int = 30) -> list[dict]:
    """Personalised feed of active offers."""
    out: list[dict] = []
    seen_ids: set[str] = set()
    # Route-aware first
    if include_route:
        cmt = await db.commute_sessions.find_one(
            {"user_id": user_id, "status": "active"})
        if cmt and cmt.get("route_polyline"):
            from services.maps_client import get_maps_client
            client = get_maps_client(db)
            try:
                places = await client.places_along_route(
                    cmt["route_polyline"], radius_m,
                    ["restaurant", "cafe", "fast_food", "bar",
                      "mall", "gym", "gas_station", "dessert", "grocery"],
                    10)
            except Exception as e:
                logger.warning(f"places_along_route in feed: {e}")
                places = []
            bids = [p.get("business_id") for p in places if p.get("business_id")]
            cur = db.offers.find(
                {"business_id": {"$in": bids}, "status": "active",
                  "end_at": {"$gte": _now()}}
            ).limit(limit)
            async for o in cur:
                ov = offer_view(o, public=True)
                ov["distance_from_route_m"] = next(
                    (p.get("distance_from_route_m") for p in places
                      if p.get("business_id") == o["business_id"]), None)
                ov["source"] = "route"
                if o["offer_id"] not in seen_ids:
                    seen_ids.add(o["offer_id"])
                    out.append(ov)
    # Then geo radius near (lat, lng).  We use businesses 2dsphere index.
    if lat is not None and lng is not None and len(out) < limit:
        bids_cur = db.businesses.find({
            "loc": {"$nearSphere": {
                "$geometry": {"type": "Point",
                                  "coordinates": [float(lng), float(lat)]},
                "$maxDistance": int(radius_m)}}}
        ).limit(80)
        bids = [b["business_id"] async for b in bids_cur]
        if bids:
            cur = db.offers.find(
                {"business_id": {"$in": bids}, "status": "active",
                  "end_at": {"$gte": _now()}}
            ).limit(limit - len(out))
            async for o in cur:
                if o["offer_id"] in seen_ids:
                    continue
                ov = offer_view(o, public=True)
                ov["source"] = "nearby"
                seen_ids.add(o["offer_id"])
                out.append(ov)
    # Fallback: any active offers
    if len(out) < limit:
        cur = db.offers.find(
            {"status": "active", "end_at": {"$gte": _now()}}
        ).limit(limit - len(out))
        async for o in cur:
            if o["offer_id"] in seen_ids:
                continue
            ov = offer_view(o, public=True)
            ov["source"] = "trending"
            seen_ids.add(o["offer_id"])
            out.append(ov)
    return out


async def claim_offer(db, *, offer_id: str, user_id: str,
                            claim_source: str = "public_page",
                            claim_context: Optional[dict] = None) -> dict:
    """Atomically claim a coupon against an offer.

    Enforces `max_per_user` and inventory decrement.  Returns the coupon
    payload (qr_token + redemption_code).
    """
    if claim_source not in CLAIM_SOURCES:
        raise ValueError(f"claim_source_invalid:{claim_source}")
    o = await db.offers.find_one({"offer_id": offer_id})
    if not o:
        raise ValueError("offer_not_found")
    if o["status"] != "active":
        raise ValueError(f"offer_not_active:{o['status']}")
    now = _now()
    end_at = _coerce_aware(o.get("end_at"))
    if end_at and end_at < now:
        raise ValueError("offer_ended")
    # max_per_user check
    max_per = int(o.get("max_per_user") or DEFAULT_MAX_PER_USER)
    if max_per > 0:
        existing = await db.coupons.count_documents(
            {"offer_id": offer_id, "user_id": user_id,
              "status": {"$in": ["claimed", "redeemed"]}})
        if existing >= max_per:
            raise ValueError("max_per_user_reached")
    # Atomic inventory decrement.  Only proceed if remaining > 0.
    upd = await db.offers.update_one(
        {"offer_id": offer_id, "status": "active",
          "inventory_remaining": {"$gt": 0}},
        {"$inc": {"inventory_remaining": -1}})
    if upd.modified_count != 1:
        raise ValueError("out_of_inventory")
    # Mint coupon
    cid = _new_id("cpn")
    qr_token = f"cqr_{secrets.token_urlsafe(18)}"
    # Generate a unique redemption code (retry once on collision)
    for _ in range(MAX_CLAIM_RETRIES):
        rc = _new_redemption_code()
        if not await db.coupons.find_one({"redemption_code": rc},
                                                    projection={"_id": 1}):
            break
    expires_at = now + timedelta(
        seconds=int(o.get("redeem_window_seconds")
                       or DEFAULT_REDEEM_WINDOW_SECONDS))
    doc = {
        "_id": cid, "coupon_id": cid,
        "offer_id": offer_id, "business_id": o["business_id"],
        "user_id": user_id, "claim_source": claim_source,
        "claim_context_json": claim_context or {},
        "claimed_at": now, "expires_at": expires_at,
        "redeemed_at": None, "status": "claimed",
        "redemption_code": rc, "qr_token": qr_token,
        "wallet_pass_url": None,
        "redeemed_by_partner_token_id": None,
        "redemption_audit_id": None,
        "created_at": now,
    }
    await db.coupons.insert_one(doc)
    # Phase 13b — attribute conversion to a recent clicked send_log row
    # (best-effort, no-op if no match). Uses offer's `value_amount` (real
    # schema) — falls back to legacy `discount_value` for any old docs.
    try:
        from services.conversion import attribute_conversion
        value = float(o.get("value_amount")
                            or o.get("discount_value") or 0.0)
        currency = (o.get("value_currency")
                          or o.get("currency") or "AED")
        await attribute_conversion(
            db, user_id=user_id, event_type="coupon_claimed",
            value=value, currency=currency,
            conversion_id=cid)
    except Exception:
        pass
    # Phase 10a — Social Passport: emit coupon_claimed for badge engine
    try:
        from services.badge_engine import evaluate as badge_evaluate
        biz = await db.businesses.find_one(
            {"business_id": o["business_id"]},
            {"category": 1, "categories": 1}) or {}
        cat = biz.get("category") or (biz.get("categories") or [None])[0]
        # Daypart from now() for lunch/dinner badges
        hour = now.hour
        if 11 <= hour < 15:
            daypart = "lunch"
        elif 18 <= hour < 23:
            daypart = "dinner"
        else:
            daypart = "other"
        await badge_evaluate(
            db, user_id, "coupon_claimed",
            {"coupon_id": cid, "offer_id": offer_id,
              "business_id": o["business_id"],
              "business_category": (cat or "").lower() or None,
              "campaign_tag": (o.get("campaign_tag") or "").lower() or None,
              "daypart": daypart,
              "offer_type": o.get("offer_type")})
    except Exception as _e:
        # Don't let badge eval break the user-visible claim
        pass
    return coupon_view(doc)


def coupon_view(c: dict, *, offer: Optional[dict] = None,
                          business: Optional[dict] = None) -> dict:
    """Phase 11.4 — defensive renderer.  Some legacy rows are missing
    `coupon_id` / `offer_id` / `business_id` due to an older claim path
    that didn't set them.  Fall back to `_id` for `coupon_id` so the
    listing endpoint doesn't 500 on a single bad row.

    Phase R.1.1 — when `offer` and/or `business` are passed, hydrate
    display-facing fields (offer_title, offer_discount_percent,
    business_name, business_category) so consumers can render a real
    coupon card without an extra round-trip.  When absent, those fields
    are None (backwards-compatible with pre-R.1.1 callers).
    """
    disc_pct: Optional[int] = None
    if offer:
        # `discount_percent` (Phase H seed) is the canonical field; some
        # older rows use `discount_value` as the numeric payload.  Accept
        # either when offer_type advertises a percentage discount.
        ot = offer.get("offer_type") or ""
        if ot in {"percent", "percent_off", "sponsored_meal"}:
            v = offer.get("discount_percent")
            if v is None:
                v = offer.get("discount_value")
            if isinstance(v, (int, float)):
                disc_pct = int(v)
    return {
        "coupon_id": c.get("coupon_id") or (
            str(c["_id"]) if c.get("_id") is not None else None),
        "offer_id": c.get("offer_id"),
        "business_id": c.get("business_id"),
        "user_id": c.get("user_id"),
        "claim_source": c.get("claim_source"),
        "claim_context_json": c.get("claim_context_json") or {},
        "claimed_at": (c["claimed_at"].isoformat()
                          if isinstance(c.get("claimed_at"), datetime)
                          else c.get("claimed_at")),
        "expires_at": (c["expires_at"].isoformat()
                          if isinstance(c.get("expires_at"), datetime)
                          else c.get("expires_at")),
        "redeemed_at": (c["redeemed_at"].isoformat()
                            if isinstance(c.get("redeemed_at"), datetime)
                            else c.get("redeemed_at")),
        "status": c.get("status"),
        # `redemption_code` was the canonical name pre-R.1.1; Phase H's
        # `save_coupon_v1` writes to `code` instead.  Coalesce both.
        "redemption_code": c.get("redemption_code") or c.get("code"),
        "qr_token": c.get("qr_token"),
        "wallet_pass_url": c.get("wallet_pass_url"),
        # Phase R.1.1 — hydrated snapshot fields (may be None).
        "offer_title": offer.get("title") if offer else None,
        "offer_description": offer.get("description") if offer else None,
        "offer_type": offer.get("offer_type") if offer else None,
        "offer_discount_percent": disc_pct,
        "business_name": business.get("name") if business else None,
        "business_category": business.get("category") if business else None,
    }


async def backfill_missing_coupon_ids(db) -> dict:
    """Phase 11.4 — one-shot backfill for legacy rows missing `coupon_id`.
    Sets `coupon_id = str(_id)` so the unique index `coupon_id_1` is
    populated correctly and the wallet listing renders without fallback.
    Idempotent.  Safe to re-run.
    """
    fixed = 0
    cur = db.coupons.find(
        {"$or": [{"coupon_id": {"$exists": False}},
                    {"coupon_id": None}]},
        {"_id": 1})
    async for row in cur:
        await db.coupons.update_one(
            {"_id": row["_id"]},
            {"$set": {"coupon_id": str(row["_id"])}})
        fixed += 1
    return {"backfilled": fixed}


async def list_user_coupons(db, *, user_id: str,
                                  status: Optional[str] = None,
                                  limit: int = 50) -> list[dict]:
    q = {"user_id": user_id}
    if status:
        if status not in COUPON_STATUS:
            raise ValueError(f"status_invalid:{status}")
        q["status"] = status
    cur = (db.coupons.find(q).sort("claimed_at", -1).limit(limit))
    coupons = [c async for c in cur]
    if not coupons:
        return []
    # Phase R.1.1 — batch-hydrate offer + business for display, in two
    # $in queries instead of N per-row round-trips.  Some legacy /
    # Phase-H rows carry `offer_id` but a null `business_id`; fall back
    # to `offers.business_id` so those still hydrate.
    offer_ids = {c["offer_id"] for c in coupons if c.get("offer_id")}
    offer_map: dict[str, dict] = {}
    if offer_ids:
        async for o in db.offers.find({"offer_id": {"$in": list(offer_ids)}}):
            offer_map[o["offer_id"]] = o
    biz_ids = {c["business_id"] for c in coupons if c.get("business_id")}
    for c in coupons:
        if not c.get("business_id"):
            o = offer_map.get(c.get("offer_id")) if c.get("offer_id") else None
            if o and o.get("business_id"):
                biz_ids.add(o["business_id"])
    biz_map: dict[str, dict] = {}
    if biz_ids:
        async for b in db.businesses.find({"business_id": {"$in": list(biz_ids)}}):
            biz_map[b["business_id"]] = b
    result: list[dict] = []
    for c in coupons:
        off = offer_map.get(c.get("offer_id")) if c.get("offer_id") else None
        bid = c.get("business_id") or (off.get("business_id") if off else None)
        biz = biz_map.get(bid) if bid else None
        result.append(coupon_view(c, offer=off, business=biz))
    return result


# ═══════════════════════════════════════════════════════════════════════
# Partner redemption
# ═══════════════════════════════════════════════════════════════════════
async def redeem_coupon_by_qr(db, *, qr_token: str,
                                       partner_token_id: str,
                                       business_id_check: str,
                                       ip: str = "",
                                       user_agent: str = "") -> dict:
    """Mark a coupon redeemed.  Strictly idempotent (replay → 4xx).

    Writes an `offer_redemptions_audit` row regardless of outcome so
    the partner can debug failures.
    """
    audit_id = _new_id("rda")
    audit: dict = {
        "_id": audit_id, "audit_id": audit_id,
        "qr_token_prefix": qr_token[:12],
        "partner_token_id": partner_token_id,
        "ip": ip, "user_agent": user_agent[:200],
        "ts": _now(),
    }
    c = await db.coupons.find_one({"qr_token": qr_token})
    if not c:
        audit["outcome"] = "not_found"
        await db.offer_redemptions_audit.insert_one(audit)
        raise ValueError("not_found")
    audit["coupon_id"] = c["coupon_id"]
    audit["offer_id"] = c["offer_id"]
    audit["business_id"] = c["business_id"]
    # Business mismatch guard
    if business_id_check and c["business_id"] != business_id_check:
        audit["outcome"] = "wrong_business"
        await db.offer_redemptions_audit.insert_one(audit)
        raise ValueError("wrong_business")
    if c["status"] == "redeemed":
        # Phase 12c Hotfix #3 — REAL double-redeem attempt: emit a
        # `one_time_use_double_redeem` fraud_event BEFORE raising the
        # idempotency error, so the audit trail is complete and partner
        # POS UIs receive structured `fraud_blocked` codes.
        fraud_id = None
        try:
            if c.get("one_time_use") or c.get("max_redemptions", 1) <= 1:
                from services.fraud import _emit_event as _fe
                ev = await _fe(
                    db, rule="one_time_use_double_redeem",
                    severity="high",
                    user_id=c.get("user_id") or "",
                    coupon_id=c.get("coupon_id"),
                    partner_id=c.get("business_id"),
                    detail={"prior_redeemed_at": c.get("redeemed_at"),
                              "double_scan": True,
                              "partner_token_id": partner_token_id})
                fraud_id = ev.get("fraud_id")
        except Exception as fe:
            import logging
            logging.getLogger("bigfm.fraud").error(
                f"fraud-guard double-scan emit failed: {fe}")
        audit["outcome"] = (
            f"fraud_block:one_time_use_double_redeem" if fraud_id
            else "already_redeemed")
        if fraud_id:
            audit["fraud_id"] = fraud_id
        await db.offer_redemptions_audit.insert_one(audit)
        # Encode the structured detail in the message; the route layer
        # parses this prefix and surfaces it as a 409 with detail body
        # `{code, rule, fraud_id}`.
        if fraud_id:
            raise ValueError(
                f"fraud_block:one_time_use_double_redeem:{fraud_id}")
        raise ValueError("already_redeemed")
    if c["status"] in ("expired", "revoked"):
        audit["outcome"] = c["status"]
        await db.offer_redemptions_audit.insert_one(audit)
        raise ValueError(c["status"])
    if c.get("expires_at") and _coerce_aware(c["expires_at"]) < _now():
        await db.coupons.update_one(
            {"coupon_id": c["coupon_id"]},
            {"$set": {"status": "expired", "updated_at": _now()}})
        audit["outcome"] = "expired"
        await db.offer_redemptions_audit.insert_one(audit)
        raise ValueError("expired")
    # Phase 12c — fraud guard (velocity / one_time_use / device dupe /
    # geo).  Runs BEFORE the atomic flip.  Block on action="block".
    try:
        from services.fraud import check_redeem
        owner = await db.users.find_one({"user_id": c.get("user_id")})
        partner = await db.businesses.find_one(
            {"business_id": c.get("business_id")})
        if owner:
            fr = await check_redeem(
                db, coupon=c, user=owner, partner=partner)
            if fr["action"] == "block":
                ev = (fr["events"] or [{}])[0]
                audit["outcome"] = f"fraud_block:{ev.get('rule')}"
                audit["fraud_id"] = ev.get("fraud_id")
                await db.offer_redemptions_audit.insert_one(audit)
                raise ValueError(
                    f"fraud_block:{ev.get('rule') or 'unknown'}")
    except ValueError:
        raise
    except Exception as fe:
        # Fail-open on fraud-guard infrastructure errors (don't break
        # legitimate redemptions if the fraud service itself crashes);
        # log loudly so the issue is visible.
        import logging
        logging.getLogger("bigfm.fraud").error(
            f"fraud guard infra error on redeem: {fe}")
    # Atomic flip
    upd = await db.coupons.update_one(
        {"coupon_id": c["coupon_id"], "status": "claimed"},
        {"$set": {"status": "redeemed", "redeemed_at": _now(),
                   "redeemed_by_partner_token_id": partner_token_id,
                   "redemption_audit_id": audit_id}})
    if upd.modified_count != 1:
        audit["outcome"] = "race"
        await db.offer_redemptions_audit.insert_one(audit)
        raise ValueError("already_redeemed")
    audit["outcome"] = "success"
    await db.offer_redemptions_audit.insert_one(audit)
    fresh = await db.coupons.find_one({"coupon_id": c["coupon_id"]})
    # Phase 10a — Social Passport: emit coupon_redeemed for badge engine
    try:
        from services.badge_engine import evaluate as badge_evaluate
        biz = await db.businesses.find_one(
            {"business_id": fresh["business_id"]},
            {"category": 1, "categories": 1}) or {}
        cat = biz.get("category") or (biz.get("categories") or [None])[0]
        await badge_evaluate(
            db, fresh["user_id"], "coupon_redeemed",
            {"coupon_id": fresh["coupon_id"],
              "offer_id": fresh["offer_id"],
              "business_id": fresh["business_id"],
              "business_category": (cat or "").lower() or None})
    except Exception:
        pass
    return {"coupon": coupon_view(fresh), "audit_id": audit_id}


# ═══════════════════════════════════════════════════════════════════════
# Analytics
# ═══════════════════════════════════════════════════════════════════════
async def offer_analytics(db, *, offer_id: str,
                                business_id: str) -> Optional[dict]:
    o = await db.offers.find_one(
        {"offer_id": offer_id, "business_id": business_id})
    if not o:
        return None
    claims = await db.coupons.count_documents({"offer_id": offer_id})
    redeemed = await db.coupons.count_documents(
        {"offer_id": offer_id, "status": "redeemed"})
    expired = await db.coupons.count_documents(
        {"offer_id": offer_id, "status": "expired"})
    # Top claim_source
    pipeline = [
        {"$match": {"offer_id": offer_id}},
        {"$group": {"_id": "$claim_source", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    sources = [{"source": s["_id"], "count": s["count"]}
                  async for s in db.coupons.aggregate(pipeline)]
    return {
        "offer_id": offer_id,
        "claims": claims,
        "redeemed": redeemed,
        "expired": expired,
        "redemption_rate": round(redeemed / claims, 4) if claims else 0.0,
        "inventory_remaining": o.get("inventory_remaining"),
        "max_redemptions_total": o.get("max_redemptions_total"),
        "by_claim_source": sources,
        "status": o.get("status"),
    }


__all__ = [
    "ensure_commerce_indexes",
    "business_view", "claim_business", "assign_slug_if_missing",
    "offer_view", "create_offer", "update_offer",
    "submit_offer_for_approval", "approve_offer", "reject_offer",
    "revise_offer",
    "transition_offer_status",
    "offers_feed", "claim_offer", "coupon_view", "list_user_coupons",
    "redeem_coupon_by_qr", "offer_analytics",
    "OFFER_TYPES", "OFFER_STATUS", "CLAIM_SOURCES", "COUPON_STATUS",
    "REDEMPTION_METHODS", "PARTNER_STATUSES", "POS_PROVIDERS",
]
