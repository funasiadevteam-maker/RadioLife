"""Phase K — M3 Wallet-Deal Marketplace.

Indexer + featured-slot service.  The marketplace is a listener-facing
surface that unions active, save-able items from multiple source
collections into a browsable grid.  We DO NOT copy the source-of-truth
payload into `marketplace_listings` — only the display metadata plus a
`(source_type, source_id)` reference.  When the listener saves a
listing, we dispatch to the SOURCE collection's existing save primitive.

Source registry (v1):
    source_type              collection                              save primitive
    ─────────────────────────────────────────────────────────────────────────
    "coupon_campaign"      coupon_campaigns                    POST /api/coupon-campaigns/{id}/save
    "merchant_offer"        offers                                        services.offers.issue_coupon_for_offer()

Featured slots (advertiser-paid):
    Positions 1-3 for a given `region_code`.  MVP charge model =
    `cost_per_day_cents` per unique (slot, user, YYYY-MM-DD) VIEW.
    This keeps the auction simple and predictable — the advertiser
    knows exactly what they'll be billed for a given daily impression
    volume without needing a per-view fraction that shifts with
    traffic.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("bigfm.m3_marketplace")

# ── Constants ──────────────────────────────────────────────────────
PLATFORM_FEE_PCT                = 25
ADMIN_APPROVAL_THRESHOLD  = 50_000            # $500 cents
MAX_SLOT_POSITION                = 3
MIN_COST_PER_DAY_CENTS      = 100              # $1/day
MIN_DAYS_PURCHASED              = 1
SWEEP_INTERVAL_SECONDS      = 3600            # 1 h
SOURCE_TYPES = ("coupon_campaign", "merchant_offer",
                                "sponsored_deal", "predict_win_campaign")
CTA_TYPES = ("save_coupon", "claim_voucher", "visit_merchant",
                          "play_game", "predict_win")
STATUSES = {"draft", "pending_admin", "active",
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


def _day_bucket(ts: Optional[datetime] = None) -> str:
    return (ts or _now()).strftime("%Y-%m-%d")


# ═════════════════════════════════════════════════════════════════════
# INDEXER — sweep source collections into `marketplace_listings`
# ═════════════════════════════════════════════════════════════════════
async def ensure_marketplace_indexes(db) -> None:
    try:
        await db.marketplace_listings.create_index(
            [("source_type", 1), ("source_id", 1)],
            unique=True, name="ml_source_uniq")
        await db.marketplace_listings.create_index(
            [("status", 1), ("region_codes", 1), ("valid_until", -1)],
            name="ml_status_region_expiry")
        await db.marketplace_listings.create_index(
            [("featured_slot_id", 1)], sparse=True,
            name="ml_featured_slot")
        await db.marketplace_featured_slots.create_index(
            [("advertiser_business_id", 1), ("status", 1)],
            name="mfs_adv_status")
        await db.marketplace_featured_slots.create_index(
            [("status", 1), ("region_code", 1), ("slot_position", 1)],
            name="mfs_status_region_pos")
        await db.marketplace_slot_views.create_index(
            [("slot_id", 1), ("user_id", 1), ("day_bucket", 1)],
            unique=True, name="msv_dedup_uniq")
        await db.marketplace_saves.create_index(
            [("user_id", 1), ("listing_id", 1)],
            unique=True, name="msave_dedup_uniq")
    except Exception as e:
        logger.warning("[m3] index setup: %s", e)


# ── Coupon-campaign adapter ─────────────────────────────────────────
async def _index_coupon_campaigns(db) -> Dict[str, int]:
    """Upsert each active `coupon_campaigns` row into
    `marketplace_listings`.  Category derived from `category_tags[0]`.
    Region_codes derived from `targeting.country_codes` when present,
    else global."""
    now = _now()
    upserts = 0
    delistings = 0
    async for cc in db.coupon_campaigns.find({}):
        camp_id = cc.get("campaign_id") or cc.get("id")
        if not camp_id:
            continue
        valid_until = _aware(cc.get("end_time")) or \
                                _aware(cc.get("end_at")) or \
                                _aware(cc.get("valid_until"))
        active = (cc.get("status") in ("live", "active")
                            and (not valid_until or valid_until > now))

        # Base merchant / region — dereference sponsoring_merchant_id if any.
        merchant_id = (cc.get("sponsoring_merchant_id")
                                      or cc.get("advertiser_id"))
        region_codes: List[str] = []
        for k in ("country_codes", "regions", "market_codes"):
            v = cc.get(k) or (cc.get("targeting") or {}).get(k)
            if v:
                region_codes = [str(c).lower() for c in v]
                break
        cat = None
        for k in ("category_tags", "categories"):
            v = cc.get(k)
            if v:
                cat = str(v[0]) if isinstance(v, list) else str(v)
                break

        listing_doc = {
            "source_type":            "coupon_campaign",
            "source_id":              str(camp_id),
            "title":                    cc.get("title") or cc.get("description")
                                                  or f"Coupon offer {camp_id[:8]}",
            "subtitle":                cc.get("description") or None,
            "image_url":              cc.get("hero_image_url") or cc.get("logo_url"),
            "merchant_business_id": merchant_id,
            "category":                cat or "coupon",
            "region_codes":          region_codes,
            "tags":                      list(cc.get("category_tags") or []),
            "deal_value_cents":  int(cc.get("retail_value_cents") or 0),
            "currency":                "usd",
            "cta_type":                "save_coupon",
            "cta_url_or_id":        f"/api/coupon-campaigns/{camp_id}/save",
            "valid_from":            _aware(cc.get("start_time")) or
                                                    _aware(cc.get("created_at")) or now,
            "valid_until":          valid_until,
            "status":                  "active" if active else "expired",
            "updated_at":            now,
        }
        existing = await db.marketplace_listings.find_one(
            {"source_type": "coupon_campaign", "source_id": str(camp_id)})
        if existing:
            listing_doc.setdefault("view_count", existing.get("view_count", 0))
            listing_doc.setdefault("save_count", existing.get("save_count", 0))
            listing_doc.setdefault("featured_slot_id",
                                                        existing.get("featured_slot_id"))
            await db.marketplace_listings.update_one(
                {"_id": existing["_id"]}, {"$set": listing_doc})
        else:
            listing_id = _gen("ml")
            listing_doc.update({
                "_id":                  listing_id,
                "id":                    listing_id,
                "view_count":      0,
                "save_count":      0,
                "created_at":      now,
                "featured_slot_id": None,
            })
            await db.marketplace_listings.insert_one(listing_doc)
        if listing_doc["status"] == "expired":
            delistings += 1
        upserts += 1
    return {"upserted": upserts, "delisted": delistings}


# ── Merchant-offer adapter ─────────────────────────────────────────
async def _index_merchant_offers(db) -> Dict[str, int]:
    """Same shape for `offers` — merchant local commerce coupons."""
    now = _now()
    upserts = 0
    delistings = 0
    async for o in db.offers.find({}):
        offer_id = o.get("offer_id") or o.get("id")
        if not offer_id:
            continue
        active = (o.get("status") == "active")
        country = (o.get("country") or "").lower() or None
        market  = (o.get("market") or "").lower() or None
        regions = [c for c in {country, market} if c]

        value_cents = int(o.get("discount_amount_cents") or 0)
        if not value_cents and o.get("discount_percent"):
            # Coarse fallback — 20% off a "$50 average bill" is $10 = 1000¢.
            #    Just so the UI has a number; the source is authoritative.
            value_cents = int(50_00 * float(o["discount_percent"]) / 100.0)

        listing_doc = {
            "source_type":            "merchant_offer",
            "source_id":              str(offer_id),
            "title":                    o.get("title") or f"Merchant offer {offer_id[:8]}",
            "subtitle":                o.get("description"),
            "image_url":              o.get("hero_image_url") or o.get("image_url"),
            "merchant_business_id": o.get("business_id"),
            "category":                o.get("offer_type") or "merchant",
            "region_codes":          regions,
            "tags":                      list(o.get("tags") or []),
            "deal_value_cents":  value_cents,
            "currency":                "usd",
            "cta_type":                "claim_voucher",
            "cta_url_or_id":        f"offer:{offer_id}",
            "valid_from":            _aware(o.get("valid_from")) or
                                                    _aware(o.get("created_at")) or now,
            "valid_until":          _aware(o.get("valid_until")),
            "status":                  "active" if active else "expired",
            "updated_at":            now,
        }
        existing = await db.marketplace_listings.find_one(
            {"source_type": "merchant_offer", "source_id": str(offer_id)})
        if existing:
            listing_doc.setdefault("view_count", existing.get("view_count", 0))
            listing_doc.setdefault("save_count", existing.get("save_count", 0))
            listing_doc.setdefault("featured_slot_id",
                                                        existing.get("featured_slot_id"))
            await db.marketplace_listings.update_one(
                {"_id": existing["_id"]}, {"$set": listing_doc})
        else:
            listing_id = _gen("ml")
            listing_doc.update({
                "_id":                  listing_id,
                "id":                    listing_id,
                "view_count":      0,
                "save_count":      0,
                "created_at":      now,
                "featured_slot_id": None,
            })
            await db.marketplace_listings.insert_one(listing_doc)
        if listing_doc["status"] == "expired":
            delistings += 1
        upserts += 1
    return {"upserted": upserts, "delisted": delistings}


async def run_indexer(db) -> Dict[str, Dict[str, int]]:
    """Full sweep — one-shot on boot + hourly."""
    cc = await _index_coupon_campaigns(db)
    mo = await _index_merchant_offers(db)
    logger.info("[m3] indexer run: coupon_campaigns=%s merchant_offers=%s",
                              cc, mo)
    return {"coupon_campaign": cc, "merchant_offer": mo}


async def start_hourly_indexer(db) -> None:
    """Fire-and-forget background task registered on boot.  Runs the
    indexer immediately and then every SWEEP_INTERVAL_SECONDS."""
    async def _loop():
        while True:
            try:
                await run_indexer(db)
            except Exception as e:
                logger.exception("[m3] indexer loop: %s", e)
            await asyncio.sleep(SWEEP_INTERVAL_SECONDS)
    asyncio.create_task(_loop())


# ═════════════════════════════════════════════════════════════════════
# LISTING QUERY + SAVE + VIEW
# ═════════════════════════════════════════════════════════════════════
def _shape_listing(d: Dict[str, Any]) -> Dict[str, Any]:
    if not d:
        return {}
    return {
        "listing_id":                        d.get("id"),
        "source_type":                    d.get("source_type"),
        "source_id":                      d.get("source_id"),
        "title":                              d.get("title"),
        "subtitle":                        d.get("subtitle"),
        "image_url":                      d.get("image_url"),
        "merchant_business_id":  d.get("merchant_business_id"),
        "category":                        d.get("category"),
        "region_codes":                  list(d.get("region_codes") or []),
        "tags":                              list(d.get("tags") or []),
        "deal_value_cents":            int(d.get("deal_value_cents") or 0),
        "currency":                        d.get("currency"),
        "cta_type":                        d.get("cta_type"),
        "cta_url_or_id":                d.get("cta_url_or_id"),
        "valid_from":                    _iso(d.get("valid_from")),
        "valid_until":                    _iso(d.get("valid_until")),
        "status":                            d.get("status"),
        "featured_slot_id":            d.get("featured_slot_id"),
        "view_count":                    int(d.get("view_count") or 0),
        "save_count":                    int(d.get("save_count") or 0),
    }


async def list_listings(db, *, region_code: Optional[str] = None,
                                              category: Optional[str] = None,
                                              search: Optional[str] = None,
                                              sort_by: str = "featured",
                                              limit: int = 30,
                                              offset: int = 0
                                              ) -> Dict[str, Any]:
    """Featured-first pagination.  Featured items always populate the
    first 3 positions when `sort_by="featured"` — post-featured items
    follow the requested secondary sort strategy."""
    now = _now()
    base_q: Dict[str, Any] = {
        "status": "active",
        "$or": [
            {"valid_until": None},
            {"valid_until": {"$gte": now}},
        ],
    }
    if region_code:
        # Include listings targeting this region OR empty region_codes (global).
        base_q["$or"] = base_q["$or"] + \
                                      [{"region_codes": region_code}]
        # Restructure with a compound $and.
        base_q = {"$and": [
            {"status": "active"},
            {"$or": [{"valid_until": None},
                              {"valid_until": {"$gte": now}}]},
            {"$or": [{"region_codes": region_code},
                              {"region_codes": {"$size": 0}}]},
        ]}
    if category:
        base_q.setdefault("$and", []).append({"category": category})
    if search:
        base_q.setdefault("$and", []).append({"$or": [
            {"title":    {"$regex": search, "$options": "i"}},
            {"subtitle": {"$regex": search, "$options": "i"}},
        ]})

    # Featured: pull active slots for this region_code sorted by position.
    featured_listings: List[Dict[str, Any]] = []
    featured_ids: set = set()
    if sort_by == "featured" and region_code:
        async for slot in db.marketplace_featured_slots.find({
                "status": "active", "region_code": region_code,
                "start_at": {"$lte": now}, "end_at": {"$gte": now},
                "$expr": {"$gte": ["$remaining_budget_cents",
                                                        "$cost_per_day_cents"]},
                }).sort([("slot_position", 1), ("cost_per_day_cents", -1)]):
            ref = slot.get("listing_ref") or {}
            listing = await db.marketplace_listings.find_one({
                "source_type": ref.get("source_type"),
                "source_id":    ref.get("source_id"),
                "status":            "active"})
            if listing:
                doc = _shape_listing(listing)
                doc["featured_slot_id"]        = slot["id"]
                doc["featured_slot_position"] = int(slot.get("slot_position") or 0)
                featured_listings.append(doc)
                featured_ids.add(listing["id"])
            if len(featured_listings) >= MAX_SLOT_POSITION:
                break

    if sort_by == "newest":
        sort = [("valid_from", -1)]
    elif sort_by == "value":
        sort = [("deal_value_cents", -1)]
    else:
        sort = [("valid_from", -1)]

    if featured_ids:
        base_q.setdefault("$and", []).append({"id": {"$nin": list(featured_ids)}})

    items: List[Dict[str, Any]] = []
    async for d in db.marketplace_listings.find(base_q).sort(sort) \
                                                        .skip(offset).limit(limit):
        items.append(_shape_listing(d))
    total = await db.marketplace_listings.count_documents(base_q)
    # Featured slice is prepended and is ALWAYS included on page 1.
    if offset == 0:
        items = featured_listings + items
    return {"items": items, "total": total,
                    "featured_count": len(featured_listings)}


async def get_listing(db, *, listing_id: str) -> Optional[Dict[str, Any]]:
    d = await db.marketplace_listings.find_one({"id": listing_id})
    return _shape_listing(d) if d else None


async def record_view(db, *, listing_id: str,
                                          user_id: Optional[str],
                                          region_code: Optional[str] = None
                                          ) -> Dict[str, Any]:
    """Impression tracking.  Increments listing.view_count always.  If
    the listing occupies a featured slot for `region_code`, atomically
    charges `cost_per_day_cents` ONCE per (slot, user, calendar-day)."""
    d = await db.marketplace_listings.find_one({"id": listing_id})
    if not d:
        raise ValueError("listing_not_found")

    await db.marketplace_listings.update_one(
        {"id": listing_id}, {"$inc": {"view_count": 1}})

    slot_charged: Optional[Dict[str, Any]] = None
    if region_code and user_id:
        slot = await db.marketplace_featured_slots.find_one({
            "status": "active",
            "region_code": region_code,
            "listing_ref.source_type": d["source_type"],
            "listing_ref.source_id":    d["source_id"],
            "start_at": {"$lte": _now()},
            "end_at":    {"$gte": _now()},
            "$expr": {"$gte": ["$remaining_budget_cents",
                                                    "$cost_per_day_cents"]},
        })
        if slot:
            slot_charged = await _try_charge_slot_view(
                db, slot=slot, user_id=user_id)
    return {"view_count": int(d.get("view_count") or 0) + 1,
                    "slot_charged": slot_charged}


async def _try_charge_slot_view(db, *, slot: Dict[str, Any],
                                                                    user_id: str
                                                                    ) -> Optional[Dict[str, Any]]:
    """MVP charge model: `cost_per_day_cents` ONCE per (slot, user, day).
    Guarded by a unique index on `marketplace_slot_views`."""
    day = _day_bucket()
    view_id = _gen("msv")
    try:
        await db.marketplace_slot_views.insert_one({
            "_id":              view_id,
            "id":                view_id,
            "slot_id":        slot["id"],
            "user_id":        user_id,
            "day_bucket":  day,
            "viewed_at":    _now(),
        })
    except Exception:
        return {"deduped": True}
    cost = int(slot.get("cost_per_day_cents") or 0)
    r = await db.marketplace_featured_slots.find_one_and_update(
        {"id": slot["id"],
          "remaining_budget_cents": {"$gte": cost}},
        {"$inc": {"remaining_budget_cents": -cost,
                            "days_delivered": 1},
          "$set": {"last_charged_at": _now()}},
        return_document=True)
    if not r:
        # Budget snapped between our check and update — flip to completed.
        await db.marketplace_featured_slots.update_one(
            {"id": slot["id"], "status": "active"},
            {"$set": {"status": "completed", "completed_at": _now()}})
        return {"deduped": False, "budget_exhausted": True,
                        "remaining_budget_cents": 0}
    remaining = int(r.get("remaining_budget_cents") or 0)
    if remaining < cost:
        await db.marketplace_featured_slots.update_one(
            {"id": slot["id"], "status": "active"},
            {"$set": {"status": "completed", "completed_at": _now()}})
    return {"deduped": False, "charged": True,
                    "remaining_budget_cents": remaining,
                    "days_delivered": int(r.get("days_delivered") or 0)}


async def save_listing(db, *, listing_id: str,
                                            user_id: str, user_email: Optional[str] = None
                                            ) -> Dict[str, Any]:
    """Save a listing → dispatch to source's save primitive.  Idempotent
    per (user, listing) via unique index.  Increments listing.save_count.
    """
    d = await db.marketplace_listings.find_one({"id": listing_id})
    if not d:
        raise ValueError("listing_not_found")
    if d.get("status") != "active":
        raise ValueError("listing_expired")

    save_id = _gen("msave")
    try:
        await db.marketplace_saves.insert_one({
            "_id":                          save_id,
            "id":                            save_id,
            "user_id":                    user_id,
            "listing_id":              listing_id,
            "source_type":            d["source_type"],
            "source_id":              d["source_id"],
            "saved_at":                _now(),
            "wallet_item_id":        None,
        })
    except Exception:
        # Already saved — return the existing row.
        existing = await db.marketplace_saves.find_one(
            {"user_id": user_id, "listing_id": listing_id})
        return {"already_saved": True,
                        "save_id": existing["id"] if existing else None,
                        "wallet_item_id": existing.get("wallet_item_id")
                                                    if existing else None,
                        "source_type": d["source_type"],
                        "source_id":    d["source_id"]}

    wallet_item_id = None
    err: Optional[str] = None

    if d["source_type"] == "coupon_campaign":
        try:
            wallet_item_id = await _save_coupon_campaign_row(
                db, campaign_id=d["source_id"], user_id=user_id)
        except Exception as e:
            err = str(e)
    elif d["source_type"] == "merchant_offer":
        try:
            from services.offers import issue_coupon_for_offer
            r = await issue_coupon_for_offer(
                db, offer_id=d["source_id"], user_id=user_id)
            wallet_item_id = (r or {}).get("coupon_id")
        except Exception as e:
            err = str(e)
    else:
        err = "unsupported_source_type"

    if err:
        # Roll back the save record so the user can try again once the
        # source-side error is resolved (rare — mostly happens if the
        # source's save primitive throws for policy reasons).
        await db.marketplace_saves.delete_one({"id": save_id})
        raise ValueError(f"save_failed:{err}")

    await db.marketplace_saves.update_one(
        {"id": save_id}, {"$set": {"wallet_item_id": wallet_item_id}})
    await db.marketplace_listings.update_one(
        {"id": listing_id}, {"$inc": {"save_count": 1}})
    return {"save_id": save_id,
                    "wallet_item_id": wallet_item_id,
                    "source_type": d["source_type"],
                    "source_id":    d["source_id"]}


async def _save_coupon_campaign_row(db, *, campaign_id: str,
                                                                        user_id: str) -> str:
    """Mirror of `routes/ads_public.action_save_coupon` — but callable
    from the marketplace save path without duplicating http glue.
    Idempotent per (user, campaign) since the AD.4 save flow itself
    dedupes on `coupons.{user_id, offer_id}` when `offer_id` is set."""
    cc = await db.coupon_campaigns.find_one(
        {"campaign_id": campaign_id})
    if not cc:
        raise ValueError("coupon_campaign_missing")
    if cc.get("status") not in ("live", "active"):
        raise ValueError("coupon_campaign_not_active")

    # Reuse the existing coupon row shape.
    coupon_id = _gen("cp")
    now = _now()
    code = secrets.token_hex(4).upper()
    await db.coupons.insert_one({
        "_id":                          coupon_id,
        "coupon_id":              coupon_id,
        "user_id":                  user_id,
        "campaign_id":            campaign_id,
        "advertiser_id":        cc.get("advertiser_id"),
        "offer_id":                None,
        "code":                        code,
        "status":                    "saved",
        "retail_value_cents":  int(cc.get("retail_value_cents") or 0),
        "saved_at":                now,
        "expires_at":              _aware(cc.get("end_time")),
        "source":                    "marketplace_save",
    })
    await db.coupon_campaigns.update_one(
        {"campaign_id": campaign_id},
        {"$inc": {"saves_count": 1}})
    return coupon_id


# ═════════════════════════════════════════════════════════════════════
# FEATURED SLOTS — advertiser CRUD, Stripe prepay/refund, admin
# ═════════════════════════════════════════════════════════════════════
def _shape_slot(s: Dict[str, Any]) -> Dict[str, Any]:
    if not s:
        return {}
    return {
        "slot_id":                          s.get("id"),
        "advertiser_business_id":  s.get("advertiser_business_id"),
        "listing_ref":                  s.get("listing_ref"),
        "region_code":                  s.get("region_code"),
        "slot_position":              int(s.get("slot_position") or 0),
        "cost_per_day_cents":      int(s.get("cost_per_day_cents") or 0),
        "days_purchased":            int(s.get("days_purchased") or 0),
        "days_delivered":            int(s.get("days_delivered") or 0),
        "total_budget_cents":      int(s.get("total_budget_cents") or 0),
        "platform_fee_cents":      int(s.get("platform_fee_cents") or 0),
        "remaining_budget_cents": int(s.get("remaining_budget_cents") or 0),
        "status":                          s.get("status"),
        "admin_notes":                  s.get("admin_notes"),
        "cancel_reason":              s.get("cancel_reason"),
        "stripe_payment_intent_id": s.get("stripe_payment_intent_id"),
        "stripe_refund_id":          s.get("stripe_refund_id"),
        "refunded_amount_cents":  int(s.get("refunded_amount_cents") or 0),
        "start_at":                      _iso(s.get("start_at")),
        "end_at":                          _iso(s.get("end_at")),
        "created_at":                  _iso(s.get("created_at")),
        "activated_at":                _iso(s.get("activated_at")),
        "completed_at":                _iso(s.get("completed_at")),
        "cancelled_at":                _iso(s.get("cancelled_at")),
    }


async def _charge_prepayment(*, amount_cents: int, slot_id: str,
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
            metadata={"bigfm_flow":            "m3_marketplace_slot_prepay",
                                "bigfm_slot_id":      slot_id,
                                "bigfm_advertiser_id": advertiser_business_id},
            idempotency_key=f"m3_slot_prepay_{slot_id}")
        return {"payment_intent_id": intent.id,
                        "amount_cents": int(amount_cents),
                        "status": intent.status}
    except Exception as e:
        logger.exception("[m3] stripe prepay failed")
        raise ValueError(f"stripe_error:{e}")


async def _refund(*, payment_intent_id: str, refund_cents: int,
                              slot_id: str) -> Dict[str, Any]:
    try:
        import stripe as _stripe
        _stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or ""
        r = _stripe.Refund.create(
            payment_intent=payment_intent_id,
            amount=int(refund_cents),
            metadata={"bigfm_flow": "m3_slot_refund",
                                "bigfm_slot_id":  slot_id},
            idempotency_key=f"m3_slot_refund_{slot_id}")
        return {"refund_id": r.id, "amount_cents": int(refund_cents),
                        "status": r.status}
    except Exception as e:
        logger.exception("[m3] stripe refund failed")
        raise ValueError(f"stripe_error:{e}")


async def create_slot(db, *, advertiser_business_id: str,
                                          body: Dict[str, Any],
                                          user_id: str) -> Dict[str, Any]:
    listing_ref = body.get("listing_ref") or {}
    st = listing_ref.get("source_type")
    sid = str(listing_ref.get("source_id") or "").strip()
    if st not in SOURCE_TYPES or not sid:
        raise ValueError("invalid_listing_ref")
    # The underlying listing must exist (indexer must have run).
    listing = await db.marketplace_listings.find_one(
        {"source_type": st, "source_id": sid})
    if not listing:
        raise ValueError("listing_not_indexed")
    if listing.get("status") != "active":
        raise ValueError("listing_not_active")

    region_code = (body.get("region_code") or "").lower()
    if not region_code:
        raise ValueError("region_code_required")

    try:
        position = int(body.get("slot_position") or 0)
    except (TypeError, ValueError):
        raise ValueError("slot_position_invalid")
    if not (1 <= position <= MAX_SLOT_POSITION):
        raise ValueError("slot_position_out_of_range")

    try:
        cost_per_day = int(body.get("cost_per_day_cents") or 0)
        days = int(body.get("days_purchased") or 0)
    except (TypeError, ValueError):
        raise ValueError("cost_or_days_invalid")
    if cost_per_day < MIN_COST_PER_DAY_CENTS:
        raise ValueError("cost_per_day_below_min")
    if days < MIN_DAYS_PURCHASED:
        raise ValueError("days_below_min")

    media_cost = cost_per_day * days
    fee = (media_cost * PLATFORM_FEE_PCT) // 100
    total = media_cost + fee

    start = _aware(body.get("start_at")) or _now()
    end   = _aware(body.get("end_at"))
    if not end or end <= start:
        raise ValueError("invalid_time_window")

    slot_id = _gen("mfs")
    doc = {
        "_id":                                          slot_id,
        "id":                                            slot_id,
        "advertiser_business_id":            advertiser_business_id,
        "listing_ref":                              {"source_type": st, "source_id": sid},
        "region_code":                              region_code,
        "slot_position":                          position,
        "cost_per_day_cents":                  cost_per_day,
        "days_purchased":                        days,
        "days_delivered":                        0,
        "media_cost_cents":                      media_cost,
        "platform_fee_cents":                  fee,
        "total_budget_cents":                  total,
        "remaining_budget_cents":            media_cost,
        "status":                                    "draft",
        "start_at":                                  start,
        "end_at":                                      end,
        "created_at":                              _now(),
        "created_by_user_id":                  user_id,
        "admin_approval_required":          total >= ADMIN_APPROVAL_THRESHOLD,
    }
    await db.marketplace_featured_slots.insert_one(doc)
    return _shape_slot(doc)


async def confirm_payment(db, *, slot_id: str,
                                                    advertiser_business_id: str
                                                    ) -> Dict[str, Any]:
    s = await db.marketplace_featured_slots.find_one({"id": slot_id})
    if not s:
        raise ValueError("slot_not_found")
    if s["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if s["status"] != "draft":
        raise ValueError(f"slot_{s['status']}")

    charge = await _charge_prepayment(
        amount_cents=int(s["total_budget_cents"]),
        slot_id=slot_id, advertiser_business_id=advertiser_business_id)

    tx_id = _gen("tx_mfs")
    await db.payment_transactions_v2.insert_one({
        "_id":                                          tx_id,
        "transaction_id":                      tx_id,
        "stripe_payment_intent_id":      charge["payment_intent_id"],
        "flow":                                        "m3_marketplace_slot_prepay",
        "event_source":                          "marketplace_slot_prepay",
        "advertiser_id":                        advertiser_business_id,
        "bigfm_slot_id":                        slot_id,
        "amount_cents":                          int(s["total_budget_cents"]),
        "application_fee_cents":            int(s["platform_fee_cents"]),
        "merchant_net_cents":                0,
        "currency":                                "usd",
        "status":                                    "posted",
        "created_at":                              _now(),
    })

    new_status = "pending_admin" if s.get("admin_approval_required") else "active"
    now = _now()
    upd: Dict[str, Any] = {
        "status":                                          new_status,
        "stripe_payment_intent_id":          charge["payment_intent_id"],
        "stripe_prepayment_transaction_id": tx_id,
        "paid_at":                                        now,
    }
    if new_status == "active":
        upd["activated_at"] = now
    await db.marketplace_featured_slots.update_one(
        {"id": slot_id}, {"$set": upd})
    row = await db.marketplace_featured_slots.find_one({"id": slot_id})
    return {"slot": _shape_slot(row), "charge": charge, "transaction_id": tx_id}


async def list_slots(db, *,
                                    advertiser_business_id: Optional[str] = None,
                                    status: Optional[str] = None,
                                    limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if advertiser_business_id:
        q["advertiser_business_id"] = advertiser_business_id
    if status:
        q["status"] = status
    rows: List[Dict[str, Any]] = []
    async for d in db.marketplace_featured_slots.find(q).sort(
                                                            "created_at", -1).limit(limit):
        rows.append(_shape_slot(d))
    return rows


async def get_slot(db, *, slot_id: str,
                                    advertiser_business_id: Optional[str] = None
                                    ) -> Optional[Dict[str, Any]]:
    d = await db.marketplace_featured_slots.find_one({"id": slot_id})
    if not d:
        return None
    if advertiser_business_id and \
            d["advertiser_business_id"] != advertiser_business_id:
        return None
    return _shape_slot(d)


async def cancel_slot(db, *, slot_id: str,
                                          advertiser_business_id: str,
                                          reason: str = "advertiser_cancelled"
                                          ) -> Dict[str, Any]:
    s = await db.marketplace_featured_slots.find_one({"id": slot_id})
    if not s:
        raise ValueError("slot_not_found")
    if s["advertiser_business_id"] != advertiser_business_id:
        raise ValueError("not_owner")
    if s["status"] not in ("pending_admin", "active", "paused"):
        raise ValueError(f"slot_{s['status']}")
    remaining = int(s.get("remaining_budget_cents") or 0)
    unspent_fee = (remaining * PLATFORM_FEE_PCT) // 100
    refund_cents = remaining + unspent_fee
    refund: Optional[Dict[str, Any]] = None
    if s.get("stripe_payment_intent_id") and refund_cents > 0:
        refund = await _refund(
            payment_intent_id=s["stripe_payment_intent_id"],
            refund_cents=refund_cents, slot_id=slot_id)
    upd = {"status":            "cancelled",
                  "cancel_reason": reason,
                  "cancelled_at":  _now()}
    if refund:
        upd["stripe_refund_id"]                = refund["refund_id"]
        upd["refunded_amount_cents"]      = refund["amount_cents"]
    await db.marketplace_featured_slots.update_one(
        {"id": slot_id}, {"$set": upd})
    row = await db.marketplace_featured_slots.find_one({"id": slot_id})
    return {"slot": _shape_slot(row), "refund": refund}


# ── Admin ──────────────────────────────────────────────────────────
async def admin_list(db, *, status: Optional[str] = None,
                                          limit: int = 100) -> List[Dict[str, Any]]:
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    rows: List[Dict[str, Any]] = []
    async for d in db.marketplace_featured_slots.find(q).sort(
                                                            "created_at", -1).limit(limit):
        rows.append(_shape_slot(d))
    return rows


async def admin_approve(db, *, slot_id: str, admin_user_id: str,
                                                admin_notes: Optional[str] = None
                                                ) -> Dict[str, Any]:
    s = await db.marketplace_featured_slots.find_one({"id": slot_id})
    if not s:
        raise ValueError("slot_not_found")
    if s["status"] != "pending_admin":
        raise ValueError(f"slot_{s['status']}")
    now = _now()
    await db.marketplace_featured_slots.update_one(
        {"id": slot_id},
        {"$set": {"status": "active",
                          "activated_at": now,
                          "decided_by_user_id": admin_user_id,
                          "decided_at": now,
                          "admin_notes": (admin_notes or "").strip() or None}})
    row = await db.marketplace_featured_slots.find_one({"id": slot_id})
    return _shape_slot(row)


async def admin_reject(db, *, slot_id: str, admin_user_id: str,
                                            admin_notes: str) -> Dict[str, Any]:
    s = await db.marketplace_featured_slots.find_one({"id": slot_id})
    if not s:
        raise ValueError("slot_not_found")
    if s["status"] not in ("pending_admin", "draft"):
        raise ValueError(f"slot_{s['status']}")
    refund: Optional[Dict[str, Any]] = None
    if s.get("stripe_payment_intent_id") and \
            int(s.get("total_budget_cents") or 0) > 0:
        refund = await _refund(
            payment_intent_id=s["stripe_payment_intent_id"],
            refund_cents=int(s["total_budget_cents"]), slot_id=slot_id)
    upd = {"status":                  "cancelled",
                  "cancel_reason":      "admin_rejected",
                  "admin_notes":          (admin_notes or "").strip() or None,
                  "decided_by_user_id":  admin_user_id,
                  "decided_at":            _now(),
                  "cancelled_at":          _now()}
    if refund:
        upd["stripe_refund_id"]                = refund["refund_id"]
        upd["refunded_amount_cents"]      = refund["amount_cents"]
    await db.marketplace_featured_slots.update_one(
        {"id": slot_id}, {"$set": upd})
    row = await db.marketplace_featured_slots.find_one({"id": slot_id})
    return {"slot": _shape_slot(row), "refund": refund}


__all__ = [
    "ensure_marketplace_indexes",
    "run_indexer", "start_hourly_indexer",
    "list_listings", "get_listing", "record_view", "save_listing",
    "create_slot", "confirm_payment", "list_slots", "get_slot",
    "cancel_slot", "admin_list", "admin_approve", "admin_reject",
    "SOURCE_TYPES", "PLATFORM_FEE_PCT", "MAX_SLOT_POSITION",
    "ADMIN_APPROVAL_THRESHOLD",
]
