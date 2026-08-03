"""Phase MER.4 — Shoppable Business Profile aggregator + Follow/Save service.

Aggregates everything Track 1 + MER.1-3 built for a merchant into a
single public payload, plus follow/save relations stored in
`user_business_relations` (a two-column many-to-many with a `kind`
discriminator so we get "user follows N businesses" AND "user has
bookmarked N businesses" from one collection).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("bigfm.mer4.profile")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _is_verified(biz: dict) -> bool:
    status = (biz.get("merchant_status") or biz.get("status") or "").lower()
    return bool(
        status in ("active", "approved")
        and biz.get("stripe_charges_enabled")
        and biz.get("stripe_payouts_enabled")
        and biz.get("stripe_details_submitted")
    )


async def resolve_merchant(db, slug_or_id: str) -> Optional[dict]:
    """Try slug first, then business_id, then _id."""
    v = (slug_or_id or "").strip()
    if not v:
        return None
    # slug
    b = await db.businesses.find_one({"slug": v})
    if b:
        return b
    # business_id
    b = await db.businesses.find_one({"business_id": v})
    if b:
        return b
    # legacy _id (string form)
    try:
        b = await db.businesses.find_one({"_id": v})
        if b:
            return b
    except Exception:
        pass
    return None


async def build_profile(db, *, slug_or_id: str,
                                              user: Optional[dict] = None) -> Optional[dict]:
    biz = await resolve_merchant(db, slug_or_id)
    if not biz:
        return None

    mid = biz.get("business_id") or str(biz.get("_id"))
    is_verified = _is_verified(biz)

    # ── Follow / save state for the current user ─────────────
    is_followed = False
    is_saved = False
    if user and user.get("user_id"):
        followed = await db.user_business_relations.find_one({
            "user_id": user["user_id"],
            "merchant_id": mid,
            "kind": "follow",
            "active": True})
        is_followed = bool(followed)
        saved = await db.user_business_relations.find_one({
            "user_id": user["user_id"],
            "merchant_id": mid,
            "kind": "save",
            "active": True})
        is_saved = bool(saved)

    # ── Locations (primary + any additional in `locations` array) ──
    locations = []
    prim = biz.get("primary_location")
    if prim and isinstance(prim, dict):
        locations.append({
            "is_primary":  True,
            "address":      prim.get("address"),
            "city":              prim.get("city"),
            "country":        prim.get("country"),
            "lat":                prim.get("lat"),
            "lng":                prim.get("lng"),
            "phone":          prim.get("phone") or biz.get("phone"),
            "hours":          prim.get("hours"),
        })
    for loc in (biz.get("locations") or []):
        if isinstance(loc, dict) and loc is not prim:
            locations.append({
                "is_primary":  False,
                "address":      loc.get("address"),
                "city":              loc.get("city"),
                "country":        loc.get("country"),
                "lat":                loc.get("lat"),
                "lng":                loc.get("lng"),
                "phone":          loc.get("phone"),
                "hours":          loc.get("hours"),
            })

    # ── Offers ──────────────────────────────────────────────────
    offers = []
    async for o in db.offers.find(
        {"business_id": mid,
          "status": {"$in": ["active", None]},
          "$or": [{"active": True}, {"active": {"$exists": False}}]}
    ).limit(20):
        offers.append({
            "offer_id":                    o.get("offer_id"),
            "title":                          o.get("title"),
            "description":            o.get("description"),
            "discount_percent":  o.get("discount_percent"),
            "offer_type":              o.get("offer_type"),
            "image_url":                o.get("image_url"),
            "expires_at":              _iso(o.get("expires_at")),
        })

    # ── Gift card SKUs (active only) ────────────────────────────
    gift_card_skus = []
    async for s in db.gift_card_skus.find(
        {"merchant_id": mid, "active": True}
    ).limit(20):
        gift_card_skus.append({
            "sku_id":                        s.get("sku_id"),
            "name":                            s.get("name"),
            "description":              s.get("description"),
            "denominations":          s.get("denominations"),
            "currency":                    s.get("currency"),
            "expires_days_after_purchase": s.get("expires_days_after_purchase"),
        })

    # ── Prepaid meal SKUs ───────────────────────────────────────
    prepaid_meal_skus = []
    async for s in db.prepaid_meal_skus.find(
        {"merchant_id": mid, "active": True}
    ).limit(20):
        prepaid_meal_skus.append({
            "sku_id":                        s.get("sku_id"),
            "name":                            s.get("name"),
            "description":              s.get("description"),
            "meal_count":                s.get("meal_count"),
            "total_price_cents":  s.get("total_price_cents"),
            "per_meal_value_cents": s.get("per_meal_value_cents"),
            "currency":                    s.get("currency"),
            "expires_days":            s.get("expires_days"),
        })

    # ── Payment links summary ───────────────────────────────────
    frontend_base = _frontend_base()
    general_link = None
    async for l in db.merchant_payment_links.find(
        {"merchant_id": mid,
          "active": True,
          "link_type": {"$in": ["general_payment", None]}}
    ).sort("created_at", -1).limit(1):
        general_link = l

    payment_links_summary = {
        "has_active_general_link":  bool(general_link),
        "general_payment_url":            (f"{frontend_base}/pay/{general_link['token']}"
                                                                if general_link else None),
        "general_payment_token":        general_link["token"] if general_link else None,
    }

    # ── Stats — total transactions this month (public rollup) ──
    from datetime import timedelta
    since = _now() - timedelta(days=30)
    total_tx_30d = await db.payment_transactions_v2.count_documents({
        "merchant_id": mid,
        "status": {"$in": ["succeeded", "refunded"]},
        "created_at": {"$gte": since},
    })

    # ── Phase PG.1 — flip play_and_win_active if any live campaign exists.
    now = _now()
    play_and_win_active = await db.game_campaigns.count_documents({
        "merchant_id": mid,
        "active": True,
        "start_at": {"$lte": now},
        "end_at": {"$gte": now},
    }) > 0
    active_game_campaign_id = None
    if play_and_win_active:
        c = await db.game_campaigns.find_one({
            "merchant_id": mid, "active": True,
            "start_at": {"$lte": now}, "end_at": {"$gte": now},
        }, {"campaign_id": 1, "game_type": 1, "name": 1})
        active_game_campaign_id = (c or {}).get("campaign_id")

    # ── Photos & logo (resolve relative URLs) ───────────────────
    logo_url = biz.get("logo_url")
    photos = biz.get("photos") or []

    return {
        "merchant": {
            "id":                              mid,
            "business_id":              mid,
            "slug":                          biz.get("slug"),
            "name":                          biz.get("name"),
            "category":                  biz.get("category") or biz.get("category_id"),
            "logo_url":                  logo_url,
            "photos":                      photos,
            "description":            biz.get("description"),
            "phone":                        biz.get("phone"),
            "website":                    biz.get("website"),
            "verified":                  is_verified,
            "is_followed":            is_followed,
            "is_saved":                  is_saved,
            "average_rating":        None,        # placeholder for a future ratings phase
        },
        "locations":                  locations,
        "offers":                          offers,
        "gift_card_skus":        gift_card_skus,
        "prepaid_meal_skus":  prepaid_meal_skus,
        "payment_links_summary": payment_links_summary,
        "activity_signals": {
            # PG.1 — flips true when merchant has a live play_and_win campaign.
            "play_and_win_active":      play_and_win_active,
            "active_game_campaign_id":  active_game_campaign_id,
            # Track 3 stubs — flip when those phases ship.
            "predict_and_win_active": False,
            "live_trivia_active":          False,
        },
        "stats": {
            "total_transactions_month": total_tx_30d,
        },
    }


def _frontend_base() -> str:
    import os
    origin = os.environ.get("FRONTEND_ORIGIN")
    if origin:
        return origin.rstrip("/")
    return ""


# ─── Follow / save helpers ─────────────────────────────────────
async def follow_merchant(db, *, user: dict, merchant_id: str,
                                              kind: str = "follow") -> dict:
    """Idempotent upsert.  `kind` ∈ {"follow", "save"}."""
    if kind not in ("follow", "save"):
        raise ValueError("invalid_kind")
    biz = await resolve_merchant(db, merchant_id)
    if not biz:
        raise ValueError("merchant_not_found")
    mid = biz.get("business_id") or str(biz.get("_id"))
    now = _now()
    existing = await db.user_business_relations.find_one({
        "user_id": user["user_id"], "merchant_id": mid, "kind": kind})
    if existing:
        if existing.get("active"):
            return {"kind": kind, "active": True,
                          "created_at": _iso(existing.get("created_at"))}
        await db.user_business_relations.update_one(
            {"_id": existing["_id"]},
            {"$set": {"active": True, "reactivated_at": now}})
        return {"kind": kind, "active": True,
                      "created_at": _iso(existing.get("created_at"))}

    rid = f"ubr_{uuid.uuid4().hex[:16]}"
    await db.user_business_relations.insert_one({
        "_id":                    rid,
        "relation_id":    rid,
        "user_id":            user["user_id"],
        "merchant_id":    mid,
        "kind":                  kind,
        "active":              True,
        "created_at":      now,
    })
    return {"kind": kind, "active": True, "created_at": _iso(now)}


async def unfollow_merchant(db, *, user: dict, merchant_id: str,
                                                        kind: str = "follow") -> dict:
    biz = await resolve_merchant(db, merchant_id)
    if not biz:
        raise ValueError("merchant_not_found")
    mid = biz.get("business_id") or str(biz.get("_id"))
    now = _now()
    result = await db.user_business_relations.update_one(
        {"user_id": user["user_id"], "merchant_id": mid, "kind": kind,
          "active": True},
        {"$set": {"active": False, "deactivated_at": now}})
    return {"kind": kind, "active": False,
                  "removed": result.modified_count > 0}


async def list_relations(db, *, user: dict, kind: str,
                                            limit: int = 100, offset: int = 0) -> dict:
    """Return the merchants the user has `follow`ed or `save`d."""
    q = {"user_id": user["user_id"], "kind": kind, "active": True}
    total = await db.user_business_relations.count_documents(q)
    rows = await db.user_business_relations.find(q) \
                                    .sort("created_at", -1).skip(offset) \
                                    .limit(limit).to_list(length=limit)

    items = []
    for r in rows:
        mid = r["merchant_id"]
        b = await db.businesses.find_one(
            {"$or": [{"business_id": mid}, {"_id": mid}]},
            {"business_id": 1, "slug": 1, "name": 1, "category": 1,
              "category_id": 1, "logo_url": 1,
              "stripe_charges_enabled": 1, "stripe_payouts_enabled": 1,
              "stripe_details_submitted": 1, "merchant_status": 1,
              "status": 1, "primary_location": 1})
        if not b:
            continue
        items.append({
            "merchant_id":    b.get("business_id") or str(b.get("_id")),
            "slug":                    b.get("slug"),
            "name":                    b.get("name"),
            "category":            b.get("category") or b.get("category_id"),
            "logo_url":            b.get("logo_url"),
            "verified":            _is_verified(b),
            "city":                    (b.get("primary_location") or {}).get("city"),
            "relation_id":    r.get("relation_id"),
            "created_at":      _iso(r.get("created_at")),
        })

    return {"total": total, "limit": limit, "offset": offset, "items": items}


# ─── Indexes ─────────────────────────────────────────────────────
async def ensure_mer4_profile_indexes(db) -> None:
    await db.user_business_relations.create_index(
        [("user_id", 1), ("kind", 1), ("merchant_id", 1)], unique=True)
    await db.user_business_relations.create_index(
        [("merchant_id", 1), ("kind", 1), ("active", 1)])
    await db.businesses.create_index("slug",
        partialFilterExpression={"slug": {"$type": "string"}})


__all__ = [
    "build_profile", "resolve_merchant",
    "follow_merchant", "unfollow_merchant", "list_relations",
    "ensure_mer4_profile_indexes",
]
