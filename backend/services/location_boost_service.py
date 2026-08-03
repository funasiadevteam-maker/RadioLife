"""Phase J — M2 Location-Boost Ads.

Layer on top of the existing ad primitives (AD.11 banner, AD.4 coupon,
AD.12 notification, AD.2 sponsored game).  A Location-Boost campaign
sits BESIDE a base ad and preferentially surfaces that ad when a
listener is inside a geofence (radius OR polygon) during optional
time-of-day windows.

Selection contract (`select_candidates`) is called at the TOP of each
existing ad auction with `(base_ad_type, user, lat, lng)`.  Return
value is a sorted list of up to `MAX_CANDIDATES` matches — each with
a computed `effective_bid = cost_per_impression_cents × boost_multiplier`
which the auction can compare against non-boosted candidates.

Impressions are atomic + idempotent per (campaign, user, 15-min bucket)
via a compound unique index.  Budget decrement + play-count increment
happens in a single `find_one_and_update`.  Same pattern as Phase G/H/I.

Money model:
    total_budget_cents = plays_target × cost_per_impression_cents
    platform_fee_cents = 20% of total_budget_cents  (M2 platform take)
    stripe_charge      = total_budget_cents + platform_fee_cents
    admin approval required when charge ≥ $500 (50000¢).
"""
from __future__ import annotations

import logging
import math
import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("bigfm.m2_location_boost")

PLATFORM_FEE_PCT                = 20
ADMIN_APPROVAL_THRESHOLD  = 50_000              # $500 in cents
MAX_CANDIDATES                    = 3
MAX_GEOFENCES                      = 3
MAX_POLYGON_VERTICES        = 20
MAX_RADIUS_METERS                = 50_000
MIN_COST_PER_IMPRESSION    = 5
MIN_PLAYS_TARGET                  = 10
PING_TTL_MINUTES                  = 60
DEDUP_BUCKET_MINUTES          = 15
NOTIFY_THROTTLE_MINUTES    = 60
EARTH_RADIUS_M                    = 6_371_000

BASE_AD_TYPES = ("banner", "coupon", "notification", "game_sponsorship")
_STATUSES = {"draft", "pending_admin", "active", "paused",
                        "completed", "cancelled"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _aware(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None
    return None


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _dedup_bucket(ts: Optional[datetime] = None) -> str:
    """15-minute floor bucket in UTC."""
    ts = ts or _now()
    q = (ts.minute // DEDUP_BUCKET_MINUTES) * DEDUP_BUCKET_MINUTES
    return ts.strftime("%Y-%m-%dT%H:") + f"{q:02d}"


# ─── Geofence math ──────────────────────────────────────────────────
def _haversine_m(lat1: float, lng1: float,
                                  lat2: float, lng2: float) -> float:
    """Distance in metres between two (lat, lng) pairs, WGS84 sphere."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + \
              math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def _point_in_polygon(lat: float, lng: float,
                                            vertices: List[List[float]]) -> bool:
    """Ray-casting on [(lat, lng), ...] treating the polygon as closed.
    Uses the standard even-odd rule.  Works fine for the small
    hand-drawn polygons M2 supports (≤20 vertices, ~50km max span)."""
    n = len(vertices)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = vertices[i][0], vertices[i][1]
        yj, xj = vertices[j][0], vertices[j][1]
        intersect = ((yi > lat) != (yj > lat)) and \
                              (lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside


def _distance_to_geofence(lat: float, lng: float,
                                                    geofence: Dict[str, Any]) -> float:
    """Return distance in metres from (lat, lng) to the fence boundary.
    0.0 when the point is INSIDE the fence.  For polygon fences, if
    outside we return the minimum haversine distance to any vertex — a
    reasonable "roughly how far off?" for the reporting UI, not
    exact-perp-distance to the edges."""
    if geofence.get("type") == "radius":
        d = _haversine_m(lat, lng,
                                          float(geofence["center_lat"]),
                                          float(geofence["center_lng"]))
        r = float(geofence.get("radius_meters") or 0)
        return max(0.0, d - r)
    if geofence.get("type") == "polygon":
        verts = geofence.get("vertices") or []
        if _point_in_polygon(lat, lng, verts):
            return 0.0
        # Approximation — closest vertex.
        min_d = float("inf")
        for v in verts:
            d = _haversine_m(lat, lng, float(v[0]), float(v[1]))
            if d < min_d:
                min_d = d
        return min_d
    return float("inf")


def _matches_any_geofence(lat: float, lng: float,
                                                    geofences: List[Dict[str, Any]]
                                                    ) -> Optional[float]:
    """Return the smallest distance (0 = inside) across all fences.
    None when the campaign has no fences (defensive)."""
    if not geofences:
        return None
    best = float("inf")
    for g in geofences:
        d = _distance_to_geofence(lat, lng, g)
        if d < best:
            best = d
    return best


# ─── Time-window filter ─────────────────────────────────────────────
def _matches_time_window(now: datetime,
                                                  windows: List[Dict[str, Any]]) -> bool:
    """`windows` is a list of {day_of_week: 0-6 (Mon=0), start_hour: 0-23,
    end_hour: 0-23 (inclusive)}.  An empty list = always-on."""
    if not windows:
        return True
    dow = now.weekday()
    hr = now.hour
    for w in windows:
        wd = int(w.get("day_of_week", -1))
        if wd not in (dow, -1):
            continue
        sh = int(w.get("start_hour") or 0)
        eh = int(w.get("end_hour") or 23)
        if sh <= hr <= eh:
            return True
    return False


# ─── Validation ────────────────────────────────────────────────────
def _validate_geofence(g: Dict[str, Any]) -> None:
    t = (g.get("type") or "").lower()
    if t == "radius":
        try:
            lat = float(g["center_lat"])
            lng = float(g["center_lng"])
            r   = float(g["radius_meters"])
        except (KeyError, ValueError, TypeError):
            raise ValueError("geofence_radius_invalid_shape")
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            raise ValueError("geofence_radius_bad_center")
        if not (10 <= r <= MAX_RADIUS_METERS):
            raise ValueError("geofence_radius_out_of_range")
    elif t == "polygon":
        v = g.get("vertices") or []
        if not (3 <= len(v) <= MAX_POLYGON_VERTICES):
            raise ValueError("geofence_polygon_vertex_count")
        for pt in v:
            try:
                lat, lng = float(pt[0]), float(pt[1])
            except Exception:
                raise ValueError("geofence_polygon_bad_point")
            if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                raise ValueError("geofence_polygon_bad_point")
    else:
        raise ValueError("geofence_unknown_type")


def _validate_windows(w: List[Dict[str, Any]]) -> None:
    for ww in (w or []):
        try:
            dow = int(ww.get("day_of_week", 0))
            sh  = int(ww.get("start_hour", 0))
            eh  = int(ww.get("end_hour", 23))
        except (TypeError, ValueError):
            raise ValueError("time_window_bad_shape")
        if not (0 <= dow <= 6 and 0 <= sh <= 23 and 0 <= eh <= 23 and sh <= eh):
            raise ValueError("time_window_out_of_range")


# ─── Cost math ─────────────────────────────────────────────────────
def _compute_costs(plays_target: int,
                                      cost_per_impression_cents: int) -> Dict[str, int]:
    if plays_target < MIN_PLAYS_TARGET:
        raise ValueError("plays_target_below_min")
    if cost_per_impression_cents < MIN_COST_PER_IMPRESSION:
        raise ValueError("cost_per_impression_below_min")
    media_cost = int(plays_target) * int(cost_per_impression_cents)
    fee = (media_cost * PLATFORM_FEE_PCT) // 100
    return {
        "media_cost_cents":      media_cost,
        "platform_fee_cents":  int(fee),
        "total_budget_cents":  media_cost + int(fee),
    }


# ─── Indexes ───────────────────────────────────────────────────────
async def ensure_location_boost_indexes(db) -> None:
    try:
        await db.location_boost_campaigns.create_index(
            [("advertiser_business_id", 1), ("status", 1)],
            name="lb_adv_status")
        await db.location_boost_campaigns.create_index(
            [("status", 1), ("base_ad_type", 1)],
            name="lb_status_type")
        await db.location_boost_impressions.create_index(
            [("campaign_id", 1),
              ("user_id", 1),
              ("dedup_bucket", 1)],
            unique=True, name="lbimp_dedup_uniq")
        await db.location_boost_impressions.create_index(
            [("campaign_id", 1), ("served_at", -1)],
            name="lbimp_camp_recent")
        # TTL index on user_location_pings — Mongo auto-expires rows
        # once `ttl_expires_at` is in the past.
        await db.user_location_pings.create_index(
            "ttl_expires_at", expireAfterSeconds=0,
            name="ulp_ttl")
        await db.user_location_pings.create_index(
            "user_id", name="ulp_user")
    except Exception as e:
        logger.warning("[m2_lb] index setup: %s", e)


# ─── Shape helpers ─────────────────────────────────────────────────
def _shape_campaign(c: Dict[str, Any]) -> Dict[str, Any]:
    if not c:
        return {}
    return {
        "campaign_id":                        c.get("id"),
        "advertiser_business_id":      c.get("advertiser_business_id"),
        "display_name":                      c.get("display_name"),
        "base_ad_type":                    c.get("base_ad_type"),
        "base_ad_id":                        c.get("base_ad_id"),
        "inline_creative":                c.get("inline_creative"),
        "geofences":                          c.get("geofences") or [],
        "time_windows":                    c.get("time_windows") or [],
        "boost_multiplier":                float(c.get("boost_multiplier") or 1.0),
        "cost_per_impression_cents":  int(c.get("cost_per_impression_cents") or 0),
        "plays_target":                    int(c.get("plays_target") or 0),
        "plays_delivered":                int(c.get("plays_delivered") or 0),
        "media_cost_cents":                int(c.get("media_cost_cents") or 0),
        "platform_fee_cents":            int(c.get("platform_fee_cents") or 0),
        "total_budget_cents":            int(c.get("total_budget_cents") or 0),
        "remaining_budget_cents":      int(c.get("remaining_budget_cents") or 0),
        "status":                              c.get("status"),
        "admin_notes":                      c.get("admin_notes"),
        "cancel_reason":                  c.get("cancel_reason"),
        "stripe_payment_intent_id":  c.get("stripe_payment_intent_id"),
        "stripe_refund_id":                c.get("stripe_refund_id"),
        "refunded_amount_cents":        int(c.get("refunded_amount_cents") or 0),
        "start_at":                          _iso(c.get("start_at")),
        "end_at":                              _iso(c.get("end_at")),
        "created_at":                      _iso(c.get("created_at")),
        "activated_at":                    _iso(c.get("activated_at")),
        "completed_at":                    _iso(c.get("completed_at")),
        "cancelled_at":                    _iso(c.get("cancelled_at")),
    }


# ─── Stripe (test-mode) ────────────────────────────────────────────
async def _charge_prepayment(*, amount_cents: int, campaign_id: str,
                                                          advertiser_business_id: str
                                                          ) -> Dict[str, Any]:
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        intent = _stripe.PaymentIntent.create(
            amount=int(amount_cents),
            currency="usd",
            payment_method_types=["card"],
            payment_method="pm_card_visa",
            confirm=True,
            metadata={
                "bigfm_flow":                      "m2_location_boost_prepay",
                "bigfm_campaign_id":          campaign_id,
                "bigfm_advertiser_id":      advertiser_business_id,
            },
            idempotency_key=f"m2_lb_prepay_{campaign_id}")
        return {"payment_intent_id": intent.id,
                        "amount_cents":        int(amount_cents),
                        "status":                  intent.status}
    except Exception as e:
        logger.exception("[m2_lb] stripe prepay failed")
        raise ValueError(f"stripe_error:{e}")


async def _refund(*, payment_intent_id: str, refund_cents: int,
                              campaign_id: str) -> Dict[str, Any]:
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        r = _stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=int(refund_cents),
            metadata={"bigfm_flow": "m2_lb_refund",
                                "bigfm_campaign_id": campaign_id},
            idempotency_key=f"m2_lb_refund_{campaign_id}")
        return {"refund_id": r.id,
                        "amount_cents": int(refund_cents),
                        "status": r.status}
    except Exception as e:
        logger.exception("[m2_lb] stripe refund failed")
        raise ValueError(f"stripe_error:{e}")


# ─── User location ping ────────────────────────────────────────────
async def record_user_location(db, *, user_id: str, lat: float, lng: float,
                                                              accuracy_meters: Optional[float] = None,
                                                              source: str = "browser"
                                                              ) -> Dict[str, Any]:
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise ValueError("bad_coordinates")
    if accuracy_meters is not None and accuracy_meters > 5000:
        raise ValueError("accuracy_too_coarse")
    # Respect the opt-out flag if the user previously deleted their
    # location.  They must re-enable via settings.
    u = await db.users.find_one({"user_id": user_id},
                                                              {"location_tracking_opt_out": 1})
    if u and u.get("location_tracking_opt_out"):
        raise ValueError("location_tracking_opted_out")

    now = _now()
    ttl = now + timedelta(minutes=PING_TTL_MINUTES)
    ping_id = _gen("ulp")
    doc = {
        "_id":                          ping_id,
        "id":                            ping_id,
        "user_id":                    user_id,
        "lat":                          float(lat),
        "lng":                          float(lng),
        "accuracy_meters":      float(accuracy_meters or 0),
        "source":                      source,
        "pinged_at":                now,
        "ttl_expires_at":        ttl,
    }
    await db.user_location_pings.insert_one(doc)
    # Mirror to `users.last_seen_location` for the ad-auction hook so
    # a single Mongo read resolves location without joining ping rows.
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"last_seen_location": {
                                "lat":        float(lat),
                                "lng":        float(lng),
                                "pinged_at": now,
                                "source":    source}}})
    return {"ping_id":              ping_id,
                    "pinged_at":        now.isoformat(),
                    "ttl_expires_at": ttl.isoformat()}


async def clear_user_location(db, *, user_id: str) -> Dict[str, Any]:
    await db.user_location_pings.delete_many({"user_id": user_id})
    await db.users.update_one(
        {"user_id": user_id},
        {"$set": {"location_tracking_opt_out": True,
                          "last_seen_location":            None}})
    return {"opted_out": True}


async def get_user_location(db, *, user_id: Optional[str]
                                                        ) -> Optional[Tuple[float, float]]:
    """Latest un-expired ping OR last_seen_location fallback.  Returns
    None when the user opted out OR has no fresh ping."""
    if not user_id:
        return None
    u = await db.users.find_one({"user_id": user_id},
                                                              {"last_seen_location": 1,
                                                                "location_tracking_opt_out": 1})
    if not u or u.get("location_tracking_opt_out"):
        return None
    p = await db.user_location_pings.find_one(
        {"user_id": user_id,
          "ttl_expires_at": {"$gt": _now()}},
        sort=[("pinged_at", -1)])
    if p:
        return (float(p["lat"]), float(p["lng"]))
    lsl = u.get("last_seen_location") or {}
    if lsl.get("lat") is not None and lsl.get("lng") is not None:
        return (float(lsl["lat"]), float(lsl["lng"]))
    return None


# ─── Campaign CRUD ─────────────────────────────────────────────────
async def create_campaign(db, *, advertiser_business_id: str,
                                                    body: Dict[str, Any],
                                                    user_id: str) -> Dict[str, Any]:
    base_ad_type = (body.get("base_ad_type") or "").strip()
    if base_ad_type not in BASE_AD_TYPES:
        raise ValueError("invalid_base_ad_type")

    base_ad_id = (body.get("base_ad_id") or "").strip() or None
    inline_creative = body.get("inline_creative") or None
    if not base_ad_id and not inline_creative:
        raise ValueError("base_ad_or_inline_required")

    fences = body.get("geofences") or []
    if not (1 <= len(fences) <= MAX_GEOFENCES):
        raise ValueError("geofence_count_out_of_range")
    for g in fences:
        _validate_geofence(g)

    windows = body.get("time_windows") or []
    _validate_windows(windows)

    try:
        boost = float(body.get("boost_multiplier") or 1.0)
    except (TypeError, ValueError):
        raise ValueError("boost_multiplier_invalid")
    if not (1.0 <= boost <= 5.0):
        raise ValueError("boost_multiplier_out_of_range")

    plays_target = int(body.get("plays_target") or 0)
    cost_per = int(body.get("cost_per_impression_cents") or 0)
    costs = _compute_costs(plays_target, cost_per)

    start = _aware(body.get("start_at")) or _now()
    end   = _aware(body.get("end_at"))
    if not end or end <= start:
        raise ValueError("invalid_time_window")

    if not (body.get("display_name") or "").strip():
        raise ValueError("display_name_required")

    campaign_id = _gen("lb")
    doc = {
        "_id":                                            campaign_id,
        "id":                                              campaign_id,
        "advertiser_business_id":            advertiser_business_id,
        "display_name":                              (body.get("display_name") or "")[:80],
        "base_ad_type":                            base_ad_type,
        "base_ad_id":                                base_ad_id,
        "inline_creative":                        inline_creative,
        "geofences":                                  fences,
        "time_windows":                            windows,
        "boost_multiplier":                        boost,
        "cost_per_impression_cents":        cost_per,
        "plays_target":                            plays_target,
        "plays_delivered":                        0,
        "media_cost_cents":                        costs["media_cost_cents"],
        "platform_fee_cents":                    costs["platform_fee_cents"],
        "total_budget_cents":                    costs["total_budget_cents"],
        "remaining_budget_cents":              costs["media_cost_cents"],
        "start_at":                                    start,
        "end_at":                                        end,
        "status":                                        "draft",
        "created_at":                                _now(),
        "created_by_user_id":                    user_id,
        "admin_approval_required":            costs["total_budget_cents"] >= ADMIN_APPROVAL_THRESHOLD,
    }
    await db.location_boost_campaigns.insert_one(doc)
    return _shape_campaign(doc)


async def confirm_payment(db, *, campaign_id: str,
                                                    advertiser_business_id: str
                                                    ) -> Dict[str, Any]:
    c = await db.location_boost_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if c["status"] != "draft":
        raise ValueError(f"campaign_{c['status']}")

    charge = await _charge_prepayment(
        amount_cents=int(c["total_budget_cents"]),
        campaign_id=campaign_id,
        advertiser_business_id=advertiser_business_id)

    tx_id = _gen("tx_lb")
    await db.payment_transactions_v2.insert_one({
        "_id":                                        tx_id,
        "transaction_id":                    tx_id,
        "stripe_payment_intent_id":  charge["payment_intent_id"],
        "flow":                                      "m2_location_boost_prepay",
        "event_source":                        "location_boost_prepay",
        "advertiser_id":                      advertiser_business_id,
        "bigfm_campaign_id":                campaign_id,
        "amount_cents":                        int(c["total_budget_cents"]),
        "application_fee_cents":        int(c["platform_fee_cents"]),
        "merchant_net_cents":              0,
        "currency":                                "usd",
        "status":                                    "posted",
        "created_at":                            _now(),
    })

    new_status = ("pending_admin"
                                if c.get("admin_approval_required")
                                else "active")
    now = _now()
    upd: Dict[str, Any] = {
        "status":                                          new_status,
        "stripe_payment_intent_id":          charge["payment_intent_id"],
        "stripe_prepayment_transaction_id": tx_id,
        "paid_at":                                        now,
    }
    if new_status == "active":
        upd["activated_at"] = now
    await db.location_boost_campaigns.update_one(
        {"id": campaign_id}, {"$set": upd})
    row = await db.location_boost_campaigns.find_one({"id": campaign_id})
    return {"campaign": _shape_campaign(row),
                    "charge": charge,
                    "transaction_id": tx_id}


async def list_campaigns(db, *,
                                                advertiser_business_id: Optional[str] = None,
                                                status: Optional[str] = None,
                                                limit: int = 100
                                                ) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if advertiser_business_id:
        q["advertiser_business_id"] = advertiser_business_id
    if status:
        q["status"] = status
    rows: List[Dict[str, Any]] = []
    async for d in db.location_boost_campaigns.find(q).sort(
                                                            "created_at", -1).limit(limit):
        rows.append(_shape_campaign(d))
    return rows


async def get_campaign(db, *, campaign_id: str,
                                              advertiser_business_id: Optional[str] = None
                                              ) -> Optional[Dict[str, Any]]:
    d = await db.location_boost_campaigns.find_one({"id": campaign_id})
    if not d:
        return None
    if advertiser_business_id and \
            d["advertiser_business_id"] != advertiser_business_id:
        return None
    return _shape_campaign(d)


async def cancel_campaign(db, *, campaign_id: str,
                                                    advertiser_business_id: str,
                                                    reason: str = "advertiser_cancelled"
                                                    ) -> Dict[str, Any]:
    c = await db.location_boost_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if c["status"] not in ("pending_admin", "active", "paused"):
        raise ValueError(f"campaign_{c['status']}")
    remaining = int(c.get("remaining_budget_cents") or 0)
    unspent_fee = (remaining * PLATFORM_FEE_PCT) // 100
    refund_cents = remaining + unspent_fee
    refund: Optional[Dict[str, Any]] = None
    if c.get("stripe_payment_intent_id") and refund_cents > 0:
        refund = await _refund(
            payment_intent_id=c["stripe_payment_intent_id"],
            refund_cents=refund_cents, campaign_id=campaign_id)
    upd = {"status":              "cancelled",
                  "cancel_reason":  reason,
                  "cancelled_at":    _now()}
    if refund:
        upd["stripe_refund_id"]                = refund["refund_id"]
        upd["refunded_amount_cents"]      = refund["amount_cents"]
    await db.location_boost_campaigns.update_one(
        {"id": campaign_id}, {"$set": upd})
    row = await db.location_boost_campaigns.find_one({"id": campaign_id})
    return {"campaign": _shape_campaign(row), "refund": refund}


# ─── Admin ─────────────────────────────────────────────────────────
async def admin_list(db, *, status: Optional[str] = None,
                                          limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    rows: List[Dict[str, Any]] = []
    async for d in db.location_boost_campaigns.find(q).sort(
                                                            "created_at", -1).limit(limit):
        rows.append(_shape_campaign(d))
    return rows


async def admin_approve(db, *, campaign_id: str,
                                                admin_user_id: str,
                                                admin_notes: Optional[str] = None
                                                ) -> Dict[str, Any]:
    c = await db.location_boost_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["status"] != "pending_admin":
        raise ValueError(f"campaign_{c['status']}")
    now = _now()
    await db.location_boost_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {"status": "active",
                          "activated_at":  now,
                          "decided_by_user_id": admin_user_id,
                          "decided_at":    now,
                          "admin_notes":  (admin_notes or "").strip() or None}})
    row = await db.location_boost_campaigns.find_one({"id": campaign_id})
    return _shape_campaign(row)


async def admin_reject(db, *, campaign_id: str,
                                            admin_user_id: str,
                                            admin_notes: str) -> Dict[str, Any]:
    c = await db.location_boost_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["status"] not in ("pending_admin", "draft"):
        raise ValueError(f"campaign_{c['status']}")
    refund: Optional[Dict[str, Any]] = None
    if c.get("stripe_payment_intent_id") and \
            int(c.get("total_budget_cents") or 0) > 0:
        refund = await _refund(
            payment_intent_id=c["stripe_payment_intent_id"],
            refund_cents=int(c["total_budget_cents"]),
            campaign_id=campaign_id)
    upd = {"status":                  "cancelled",
                  "cancel_reason":      "admin_rejected",
                  "admin_notes":          (admin_notes or "").strip() or None,
                  "decided_by_user_id": admin_user_id,
                  "decided_at":            _now(),
                  "cancelled_at":          _now()}
    if refund:
        upd["stripe_refund_id"]                = refund["refund_id"]
        upd["refunded_amount_cents"]      = refund["amount_cents"]
    await db.location_boost_campaigns.update_one(
        {"id": campaign_id}, {"$set": upd})
    row = await db.location_boost_campaigns.find_one({"id": campaign_id})
    return {"campaign": _shape_campaign(row), "refund": refund}


# ─── Selection (candidates) + impression ───────────────────────────
async def select_candidates(db, *, base_ad_type: str,
                                                        user_id: Optional[str],
                                                        lat: Optional[float] = None,
                                                        lng: Optional[float] = None
                                                        ) -> List[Dict[str, Any]]:
    """Called by the ad auction.  Returns up to `MAX_CANDIDATES` matching
    active campaigns for the caller's context.  Ordered by effective bid
    (cost_per_impression × boost_multiplier) DESC — the caller can then
    compare to non-boosted candidates.

    Empty return means "no location-boost applies here — proceed as
    usual".  Never raises.
    """
    if base_ad_type not in BASE_AD_TYPES:
        return []
    if lat is None or lng is None:
        pair = await get_user_location(db, user_id=user_id)
        if not pair:
            return []
        lat, lng = pair

    now = _now()
    q = {
        "status":                base_ad_type and "active",
        "base_ad_type":  base_ad_type,
        "start_at":          {"$lte": now},
        "end_at":              {"$gte": now},
        "$expr": {"$gte": ["$remaining_budget_cents",
                                                "$cost_per_impression_cents"]},
    }
    matches: List[Tuple[float, Dict[str, Any]]] = []
    async for c in db.location_boost_campaigns.find(q).limit(50):
        # Time-window
        if not _matches_time_window(now, c.get("time_windows") or []):
            continue
        # Geofence
        d = _matches_any_geofence(lat, lng, c.get("geofences") or [])
        if d is None or d > 0:
            continue
        matches.append((d, c))

    # Sort by effective_bid DESC, tie-break with lower distance.
    def _score(pair: Tuple[float, Dict[str, Any]]) -> Tuple[float, float]:
        d, c = pair
        eff = float(c.get("boost_multiplier") or 1.0) * \
                    float(c.get("cost_per_impression_cents") or 0)
        return (eff, -d)
    matches.sort(key=_score, reverse=True)

    return [{
        "campaign_id":                          c["id"],
        "advertiser_business_id":        c["advertiser_business_id"],
        "base_ad_type":                      c["base_ad_type"],
        "base_ad_id":                          c.get("base_ad_id"),
        "inline_creative":                  c.get("inline_creative"),
        "boost_multiplier":                  float(c.get("boost_multiplier") or 1.0),
        "cost_per_impression_cents":  int(c.get("cost_per_impression_cents") or 0),
        "effective_bid_cents":              int(float(c.get("boost_multiplier") or 1.0)
                                                                  * float(c.get("cost_per_impression_cents") or 0)),
        "distance_from_geofence_meters": round(d, 1),
        "display_name":                      c.get("display_name"),
    } for d, c in matches[:MAX_CANDIDATES]]


async def record_impression(db, *, campaign_id: str,
                                                        user_id: Optional[str],
                                                        session_id: Optional[str],
                                                        lat: float, lng: float,
                                                        base_ad_type: str,
                                                        base_ad_id: Optional[str] = None
                                                        ) -> Dict[str, Any]:
    """Idempotent per (campaign, user, 15-min bucket).  Atomically
    decrements remaining_budget + increments plays_delivered.  Auto-
    flips to completed on exhaustion."""
    c = await db.location_boost_campaigns.find_one({"id": campaign_id})
    if not c:
        raise ValueError("campaign_not_found")
    if c["status"] != "active":
        return {"deduped": True, "reason": c["status"]}

    dedup_key = user_id or session_id or "anon"
    bucket = _dedup_bucket()
    imp_id = _gen("lbimp")
    try:
        await db.location_boost_impressions.insert_one({
            "_id":                                                imp_id,
            "id":                                                  imp_id,
            "campaign_id":                                campaign_id,
            "advertiser_business_id":              c["advertiser_business_id"],
            "user_id":                                        dedup_key,
            "session_id":                                  session_id,
            "lat":                                              float(lat),
            "lng":                                              float(lng),
            "base_ad_type":                              base_ad_type,
            "base_ad_id":                                  base_ad_id,
            "dedup_bucket":                              bucket,
            "distance_from_geofence_meters":  round(
                _matches_any_geofence(lat, lng,
                                                              c.get("geofences") or []) or 0, 1),
            "served_at":                                    _now(),
            "budget_charged_cents":                  0,
        })
    except Exception:
        return {"deduped": True}

    cost = int(c.get("cost_per_impression_cents") or 0)
    r = await db.location_boost_campaigns.find_one_and_update(
        {"id": campaign_id,
          "remaining_budget_cents": {"$gte": cost}},
        {"$inc": {"remaining_budget_cents": -cost,
                            "plays_delivered": 1},
          "$set": {"last_served_at": _now()}},
        return_document=True)
    if not r:
        await db.location_boost_campaigns.update_one(
            {"id": campaign_id, "status": "active"},
            {"$set": {"status": "completed",
                              "completed_at": _now()}})
        return {"deduped": False,
                        "budget_exhausted": True,
                        "remaining_budget_cents": 0}
    # Backfill charge on the impression row.
    await db.location_boost_impressions.update_one(
        {"id": imp_id},
        {"$set": {"budget_charged_cents": cost}})
    remaining = int(r.get("remaining_budget_cents") or 0)
    if remaining < cost:
        await db.location_boost_campaigns.update_one(
            {"id": campaign_id, "status": "active"},
            {"$set": {"status": "completed",
                              "completed_at": _now()}})

    # Notification recipe (throttled per campaign+user to 60 min via
    # the ad12 dispatcher's own inbox dedup; kicked here best-effort).
    if user_id:
        try:
            from services.notification_trigger_dispatcher import dispatch_event
            await dispatch_event(
                db, event_name="location_boost_matched",
                user_id=user_id,
                payload={"campaign_id": campaign_id,
                                "advertiser_business_id": c["advertiser_business_id"],
                                "base_ad_type":  base_ad_type,
                                "display_name":  c.get("display_name")})
        except Exception as e:
            logger.warning("[m2_lb] dispatch_event failed: %s", e)

    return {"deduped": False,
                    "charged": True,
                    "remaining_budget_cents": remaining,
                    "plays_delivered": int(r.get("plays_delivered") or 0)}


__all__ = [
    "ensure_location_boost_indexes",
    "record_user_location", "clear_user_location", "get_user_location",
    "create_campaign", "confirm_payment",
    "list_campaigns", "get_campaign", "cancel_campaign",
    "admin_list", "admin_approve", "admin_reject",
    "select_candidates", "record_impression",
    "PLATFORM_FEE_PCT", "ADMIN_APPROVAL_THRESHOLD",
    "MAX_GEOFENCES", "MAX_POLYGON_VERTICES", "MAX_RADIUS_METERS",
    "MIN_COST_PER_IMPRESSION", "MIN_PLAYS_TARGET",
    "PING_TTL_MINUTES", "DEDUP_BUCKET_MINUTES", "BASE_AD_TYPES",
    "_haversine_m", "_point_in_polygon",
]
