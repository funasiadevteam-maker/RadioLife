"""Phase PG.1 — Play & Win + Scratch & Win game engine.

Weighted-random prize selection with server-side race-safety.  Dispatches
minting to the existing MER.3 wallet services (`gift_card_service`,
`prepaid_meal_service`) and `bigcoin.award` for points.  Coupons are
minted directly here since game-won coupons bypass the offer-cap
machinery in `services/offers.py`.

Atomicity strategy:
  * `game_campaigns.prizes[].quantity_won` / `campaign.current_plays_count`
    are incremented via a single `find_one_and_update` with `$inc` +
    positional index filter, guarded by `quantity_won < quantity_available`
    or `current_plays_count < max_total_plays`.  If the guard fails, we
    retry weighted-random with the exhausted prize removed from the pool
    (up to 3 retries), then fall back to `nothing`.
  * `game_sessions` insert is idempotent-safe via unique
    `(campaign_id, user_id, sequence_n)` index.
"""
from __future__ import annotations

import logging
import random
import secrets
import string
import uuid
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("bigfm.pg1.game")

# ─── Constants ─────────────────────────────────────────────────
GAME_TYPES = ("spin_win", "scratch_win")
PRIZE_TYPES = ("points", "coupon", "gift_card",
                              "prepaid_meal", "badge", "nothing")
MAX_RETRY_ON_EXHAUST = 3

_CODE_ALPHABET = string.ascii_uppercase + "23456789"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v):
    return v.isoformat() if isinstance(v, datetime) else v


def _coerce_utc(dt):
    if dt is None: return None
    if isinstance(dt, datetime) and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _short_code(prefix: str = "BIGFM-PG-") -> str:
    return prefix + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))


# ─── Templates ─────────────────────────────────────────────────
DEFAULT_TEMPLATES = [
    {
        "template_id": "tpl_spin_default_6",
        "game_type": "spin_win",
        "name": "Spin & Win — 6 wedge",
        "description": "Classic 6-wedge spinning wheel.  Great starter.",
        "default_config": {
            "wedges": 6,
            "colors": ["#a855f7", "#ec4899", "#f59e0b", "#10b981",
                                "#0ea5e9", "#f43f5e"],
            "spin_duration_ms": 4200,
            "min_rotations": 5,
        },
        "active": True,
    },
    {
        "template_id": "tpl_scratch_default_3x3",
        "game_type": "scratch_win",
        "name": "Scratch & Win — 3×3 grid",
        "description": "Reveal 3 cells; match 3 icons to win.",
        "default_config": {
            "grid_rows": 3,
            "grid_cols": 3,
            "reveals_allowed": 3,
            "match_to_win": 3,
        },
        "active": True,
    },
]


async def seed_templates(db) -> None:
    """Idempotent seed on boot."""
    for t in DEFAULT_TEMPLATES:
        await db.game_templates.update_one(
            {"template_id": t["template_id"]},
            {"$setOnInsert": {**t, "created_at": _now()}},
            upsert=True)


async def list_templates(db) -> list:
    rows = await db.game_templates.find({"active": True}).to_list(length=20)
    return rows


# ─── Campaigns — CRUD ──────────────────────────────────────────
def _validate_prize(p: dict) -> dict:
    ptype = p.get("prize_type")
    if ptype not in PRIZE_TYPES:
        raise ValueError(f"invalid_prize_type:{ptype}")
    return {
        "prize_id":                  p.get("prize_id") or f"pz_{uuid.uuid4().hex[:12]}",
        "prize_type":              ptype,
        "value_cents":            int(p.get("value_cents") or 0),
        "sku_id":                    p.get("sku_id"),        # gift_card_id or prepaid_meal_id
        "coupon_offer_id":  p.get("coupon_offer_id"),
        "points_amount":    int(p.get("points_amount") or 0),
        "badge_slug":            p.get("badge_slug"),
        "quantity_available": int(p.get("quantity_available") or 0),
        "quantity_won":        0,
        "weight":                    float(p.get("weight") or 1),
        "display_label":    (p.get("display_label") or "Prize").strip()[:80],
        "display_color":    p.get("display_color") or "#a855f7",
    }


async def create_campaign(db, *, merchant_id: Optional[str],
                                                    actor: dict, **fields) -> dict:
    game_type = fields.get("game_type")
    if game_type not in GAME_TYPES:
        raise ValueError("invalid_game_type")

    template_id = fields.get("template_id")
    tpl = await db.game_templates.find_one({"template_id": template_id})
    if not tpl:
        raise ValueError("template_not_found")

    prizes = [_validate_prize(p) for p in (fields.get("prizes") or [])]
    if not prizes:
        raise ValueError("no_prizes")

    name = (fields.get("name") or "").strip()
    if not name:
        raise ValueError("name_required")

    start_at = _coerce_utc(fields.get("start_at")) or _now()
    end_at = _coerce_utc(fields.get("end_at"))
    if not end_at:
        # 90-day default window
        from datetime import timedelta
        end_at = _now().replace(microsecond=0) + timedelta(days=90)

    cid = f"gc_{uuid.uuid4().hex[:14]}"
    now = _now()
    doc = {
        "_id":                          cid,
        "campaign_id":          cid,
        "template_id":          template_id,
        "game_type":              game_type,
        "merchant_id":          merchant_id,
        "name":                      name,
        "description":        (fields.get("description") or "").strip() or None,
        "active":                  bool(fields.get("active", True)),
        "start_at":              start_at,
        "end_at":                  end_at,
        "max_plays_per_user":  int(fields.get("max_plays_per_user") or 1),
        "max_total_plays":  int(fields["max_total_plays"]) if fields.get("max_total_plays") else None,
        "current_plays_count": 0,
        "prizes":                  prizes,
        "terms":                    (fields.get("terms") or "").strip() or None,
        "hero_color":          fields.get("hero_color") or "#a855f7",
        "created_at":          now,
        "created_by":          (actor or {}).get("user_id"),
        "updated_at":          now,
    }
    await db.game_campaigns.insert_one(doc)
    logger.info(f"[pg1] campaign created cid={cid} mid={merchant_id} "
                          f"type={game_type} prizes={len(prizes)}")
    return doc


async def update_campaign(db, *, campaign_id: str, merchant_id: Optional[str],
                                                    patch: dict, actor: dict) -> dict:
    row = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not row:
        raise ValueError("campaign_not_found")
    if merchant_id and row.get("merchant_id") != merchant_id:
        raise ValueError("wrong_merchant")

    allowed = {"name", "description", "active", "start_at", "end_at",
                        "max_plays_per_user", "max_total_plays", "prizes",
                        "terms", "hero_color"}
    filtered = {k: v for k, v in (patch or {}).items()
                          if k in allowed and v is not None}
    if "prizes" in filtered:
        filtered["prizes"] = [_validate_prize(p) for p in filtered["prizes"]]
        # preserve quantity_won on the existing prizes to avoid double-issue
        prev_by_id = {p["prize_id"]: p for p in row.get("prizes", [])}
        for p in filtered["prizes"]:
            if p["prize_id"] in prev_by_id:
                p["quantity_won"] = int(prev_by_id[p["prize_id"]].get("quantity_won") or 0)
    if "start_at" in filtered:
        filtered["start_at"] = _coerce_utc(filtered["start_at"])
    if "end_at" in filtered:
        filtered["end_at"] = _coerce_utc(filtered["end_at"])
    filtered["updated_at"] = _now()
    await db.game_campaigns.update_one({"campaign_id": campaign_id},
                                                                              {"$set": filtered})
    return await db.game_campaigns.find_one({"campaign_id": campaign_id})


async def list_campaigns(db, *, merchant_id: Optional[str] = None,
                                                active: Optional[bool] = None,
                                                limit: int = 100, offset: int = 0) -> dict:
    q = {}
    if merchant_id is not None:
        q["merchant_id"] = merchant_id
    if active is not None:
        q["active"] = active
    total = await db.game_campaigns.count_documents(q)
    rows = await db.game_campaigns.find(q).sort("created_at", -1) \
                                    .skip(offset).limit(limit).to_list(length=limit)
    return {"total": total, "limit": limit, "offset": offset, "items": rows}


async def get_campaign(db, *, campaign_id: str) -> Optional[dict]:
    return await db.game_campaigns.find_one({"campaign_id": campaign_id})


# ─── Play eligibility ──────────────────────────────────────────
async def can_user_play(db, *, campaign_id: str,
                                              user_id: str) -> dict:
    campaign = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not campaign:
        return {"can_play": False, "reason": "campaign_not_found"}
    if not campaign.get("active"):
        return {"can_play": False, "reason": "inactive"}
    now = _now()
    if _coerce_utc(campaign.get("start_at")) and _coerce_utc(campaign["start_at"]) > now:
        return {"can_play": False, "reason": "not_started",
                      "starts_at": _iso(campaign["start_at"])}
    if _coerce_utc(campaign.get("end_at")) and _coerce_utc(campaign["end_at"]) < now:
        return {"can_play": False, "reason": "ended"}
    max_total = campaign.get("max_total_plays")
    if max_total and int(campaign.get("current_plays_count", 0)) >= int(max_total):
        return {"can_play": False, "reason": "sold_out"}

    max_per_user = int(campaign.get("max_plays_per_user") or 1)
    played = await db.game_sessions.count_documents({
        "campaign_id": campaign_id,
        "user_id": user_id,
    })
    if played >= max_per_user:
        return {"can_play": False, "reason": "max_plays_reached",
                      "played": played, "max": max_per_user}

    return {"can_play": True, "played": played, "max": max_per_user}


# ─── Weighted-random selection ─────────────────────────────────
def _pick_prize(prizes: list, exclude_ids: set = None) -> Optional[dict]:
    exclude_ids = exclude_ids or set()
    pool = [p for p in prizes
                    if p["prize_id"] not in exclude_ids
                    and (p.get("quantity_available", 0) <= 0
                              or int(p.get("quantity_won", 0)) < int(p.get("quantity_available", 0)))]
    if not pool:
        return None
    total = sum(float(p.get("weight") or 1) for p in pool)
    if total <= 0:
        return random.choice(pool)
    r = random.uniform(0, total)
    acc = 0.0
    for p in pool:
        acc += float(p.get("weight") or 1)
        if r <= acc:
            return p
    return pool[-1]


# ─── Prize minting dispatch ────────────────────────────────────
async def _mint_prize(db, *, campaign: dict, prize: dict, user: dict,
                                          session_id: str) -> dict:
    """Returns `{minted:True, wallet_item_id, wallet_item_type, code?, points?}`
    OR `{minted:False, reason}`."""
    ptype = prize.get("prize_type")
    now = _now()
    metadata = {"game_session_id": session_id,
                          "campaign_id": campaign["campaign_id"],
                          "prize_id": prize["prize_id"],
                          "source_id": session_id}

    if ptype == "nothing":
        return {"minted": False, "reason": "nothing"}

    if ptype == "points":
        pts = int(prize.get("points_amount") or 0)
        if pts <= 0:
            return {"minted": False, "reason": "invalid_points"}
        try:
            from services.bigcoin import award
            res = await award(db, user_id=user["user_id"], amount=pts,
                                                source="game_win", metadata=metadata,
                                                note=f"Game win — {prize.get('display_label')}")
            return {"minted": True, "wallet_item_type": "points",
                          "points": pts,
                          "balance_after": (res or {}).get("balance_after")}
        except Exception as e:
            logger.exception("[pg1] points award failed")
            return {"minted": False, "reason": f"award_failed:{e}"}

    if ptype == "gift_card":
        sku_id = prize.get("sku_id")
        amt = int(prize.get("value_cents") or 0)
        if not sku_id or amt <= 0:
            return {"minted": False, "reason": "invalid_gc_config"}
        from services.gift_card_service import mint_gift_card
        try:
            gc = await mint_gift_card(
                db, sku_id=sku_id,
                merchant_id=campaign.get("merchant_id"),
                amount_cents=amt,
                owner_user_id=user["user_id"],
                owner_email=(user.get("email") or "").lower() or None,
                purchased_transaction_id=f"game_{session_id}")
            # Stamp game metadata on the card
            await db.user_gift_cards.update_one(
                {"gift_card_id": gc["gift_card_id"]},
                {"$set": {"source": "game_win",
                                    "source_game_session_id": session_id,
                                    "source_campaign_id": campaign["campaign_id"]}})
            return {"minted": True, "wallet_item_type": "gift_card",
                          "wallet_item_id": gc["gift_card_id"],
                          "code": gc["code"],
                          "balance_cents": int(gc["current_balance_cents"])}
        except Exception as e:
            logger.exception("[pg1] gift card mint failed")
            return {"minted": False, "reason": f"mint_failed:{e}"}

    if ptype == "prepaid_meal":
        sku_id = prize.get("sku_id")
        if not sku_id:
            return {"minted": False, "reason": "invalid_pm_config"}
        from services.prepaid_meal_service import mint_prepaid_meal
        try:
            pm = await mint_prepaid_meal(
                db, sku_id=sku_id,
                merchant_id=campaign.get("merchant_id"),
                owner_user_id=user["user_id"],
                owner_email=(user.get("email") or "").lower() or None,
                purchased_transaction_id=f"game_{session_id}")
            await db.user_prepaid_meals.update_one(
                {"meal_pack_id": pm["meal_pack_id"]},
                {"$set": {"source": "game_win",
                                    "source_game_session_id": session_id,
                                    "source_campaign_id": campaign["campaign_id"]}})
            return {"minted": True, "wallet_item_type": "prepaid_meal",
                          "wallet_item_id": pm["meal_pack_id"],
                          "code": pm["code"],
                          "meals": int(pm["remaining_meals"])}
        except Exception as e:
            logger.exception("[pg1] prepaid meal mint failed")
            return {"minted": False, "reason": f"mint_failed:{e}"}

    if ptype == "coupon":
        offer_id = prize.get("coupon_offer_id")
        if not offer_id:
            return {"minted": False, "reason": "invalid_coupon_config"}
        offer = await db.offers.find_one(
            {"$or": [{"offer_id": offer_id}, {"id": offer_id}]})
        if not offer:
            return {"minted": False, "reason": "offer_not_found"}
        coupon_id = f"cp_pg1_{uuid.uuid4().hex[:16]}"
        code = _short_code("BIGFM-")
        for _ in range(4):
            if not await db.coupons.find_one({"code": code}):
                break
            code = _short_code("BIGFM-")
        # Store WITH offer_id in offer's native key (offer.get('offer_id') or 'id')
        offer_key = offer.get("offer_id") or offer.get("id")
        doc = {
            "_id":                  coupon_id,
            "coupon_id":      coupon_id,
            "code":                code,
            "offer_id":        offer_key,
            "business_id":  offer.get("business_id") or campaign.get("merchant_id"),
            "user_id":          user["user_id"],
            "status":            "saved",
            "created_at":    now,
            "expires_at":    offer.get("end_time") or offer.get("expires_at"),
            "source":            "game_win",
            "source_game_session_id": session_id,
            "source_campaign_id":      campaign["campaign_id"],
        }
        await db.coupons.insert_one(doc)
        return {"minted": True, "wallet_item_type": "coupon",
                      "wallet_item_id": coupon_id, "code": code,
                      "offer_id": offer_key,
                      "offer_title": offer.get("title") or offer.get("name")}

    if ptype == "badge":
        # Best-effort — write to social_passport if present, else skip.
        slug = prize.get("badge_slug") or "game_winner"
        try:
            await db.social_passport.update_one(
                {"user_id": user["user_id"]},
                {"$addToSet": {"badges": {"slug": slug,
                                                                            "awarded_at": now,
                                                                            "source": "game_win",
                                                                            "source_game_session_id": session_id}}},
                upsert=True)
        except Exception:
            logger.exception("[pg1] badge award failed (non-blocking)")
        return {"minted": True, "wallet_item_type": "badge",
                      "wallet_item_id": slug, "badge_slug": slug}

    return {"minted": False, "reason": "unknown_prize_type"}


# ─── Play (spin/scratch) ────────────────────────────────────────
async def play(db, *, campaign_id: str, user: dict,
                            client_ip_hash: str = None, ua: str = None) -> dict:
    """Executes one play.  Server-side eligibility re-check + atomic
    inventory decrement.  Returns `{outcome, session, wallet_item}`."""
    eligibility = await can_user_play(db, campaign_id=campaign_id,
                                                                          user_id=user["user_id"])
    if not eligibility.get("can_play"):
        raise ValueError(eligibility.get("reason") or "ineligible")

    campaign = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not campaign:
        raise ValueError("campaign_not_found")

    session_id = f"gs_{uuid.uuid4().hex[:16]}"
    exclude: set = set()
    prize = None
    picked_prize_id = None

    for attempt in range(MAX_RETRY_ON_EXHAUST):
        picked = _pick_prize(campaign["prizes"], exclude_ids=exclude)
        if not picked:
            break        # nothing left in pool
        picked_prize_id = picked["prize_id"]

        # Atomic decrement: increment prize.quantity_won only if
        # (unlimited quantity: 0) OR (quantity_won < quantity_available)
        qty_avail = int(picked.get("quantity_available") or 0)
        max_total = campaign.get("max_total_plays")

        # Build query: match by campaign_id + specific prize + guard
        query = {"campaign_id": campaign_id,
                        "active": True}
        if qty_avail > 0:
            query["prizes"] = {"$elemMatch": {
                "prize_id": picked["prize_id"],
                "quantity_won": {"$lt": qty_avail}}}
        else:
            query["prizes.prize_id"] = picked["prize_id"]
        if max_total:
            query["current_plays_count"] = {"$lt": int(max_total)}

        update = {
            "$inc": {"current_plays_count": 1,
                              "prizes.$[p].quantity_won": 1},
        }

        result = await db.game_campaigns.find_one_and_update(
            query, update,
            array_filters=[{"p.prize_id": picked["prize_id"]}],
            return_document=True)

        if result:
            prize = picked
            break

        # Guard failed — either this prize sold out during our race, or
        # the campaign hit max_total.  Exclude this prize and retry.
        exclude.add(picked["prize_id"])
        # If we lost to max_total (not prize-level), abort altogether
        fresh = await db.game_campaigns.find_one({"campaign_id": campaign_id},
                                                                                              {"current_plays_count": 1,
                                                                                                "max_total_plays": 1})
        if fresh and fresh.get("max_total_plays") and \
              int(fresh.get("current_plays_count", 0)) >= int(fresh["max_total_plays"]):
            raise ValueError("sold_out")

    if prize is None:
        # Fall back to a synthetic "nothing" outcome; still record the play.
        await db.game_campaigns.update_one(
            {"campaign_id": campaign_id},
            {"$inc": {"current_plays_count": 1}})
        prize = {"prize_id": "nothing_fallback",
                        "prize_type": "nothing",
                        "display_label": "Better luck next time",
                        "display_color": "#6b7280"}

    # ── Mint the prize ──
    mint_result = await _mint_prize(db, campaign=campaign, prize=prize,
                                                                      user=user, session_id=session_id)

    now = _now()
    session = {
        "_id":                        session_id,
        "session_id":          session_id,
        "campaign_id":        campaign_id,
        "merchant_id":        campaign.get("merchant_id"),
        "user_id":                user["user_id"],
        "played_at":            now,
        "outcome_prize_id": prize["prize_id"],
        "outcome_type":      prize["prize_type"],
        "outcome_label":    prize.get("display_label"),
        "outcome_color":    prize.get("display_color"),
        "value_cents":        int(prize.get("value_cents") or 0),
        "wallet_item_id":  mint_result.get("wallet_item_id"),
        "wallet_item_type": mint_result.get("wallet_item_type"),
        "code":                      mint_result.get("code"),
        "points_awarded":  mint_result.get("points") or 0,
        "minted":                mint_result.get("minted", False),
        "mint_reason":      mint_result.get("reason"),
        "client_ip_hash":  client_ip_hash,
        "ua":                          ua,
    }
    await db.game_sessions.insert_one(session)

    # Winners table (denormalized for analytics — skip on `nothing`).
    # Legacy Phase 8a `game_winners` has a unique index on `game_session_id`
    # — use it as the primary FK, not `session_id`, to avoid null collisions.
    # Non-blocking: an audit-row failure MUST NOT reverse the player's win.
    if prize["prize_type"] != "nothing":
        wid = f"win_{uuid.uuid4().hex[:16]}"
        try:
            await db.game_winners.insert_one({
                "_id":                          wid,
                "winner_id":              wid,
                "campaign_id":          campaign_id,
                "merchant_id":          campaign.get("merchant_id"),
                "user_id":                user["user_id"],
                "session_id":          session_id,
                "game_session_id":  session_id,      # legacy 8a unique index
                "prize_id":              prize["prize_id"],
                "prize_type":          prize["prize_type"],
                "value_cents":        int(prize.get("value_cents") or 0),
                "wallet_item_id":  mint_result.get("wallet_item_id"),
                "wallet_item_type": mint_result.get("wallet_item_type"),
                "awarded_at":        now,
                "redemption_status": "issued",
            })
        except Exception:
            logger.exception("[pg1] winners insert failed (non-blocking)")

    logger.info(f"[pg1] play cid={campaign_id} user={user['user_id']} "
                          f"outcome={prize['prize_type']}:{prize['prize_id']} "
                          f"minted={mint_result.get('minted')}")

    return {"session": session, "prize": prize, "mint": mint_result}


# ─── Discovery ────────────────────────────────────────────────
async def discover(db, *, merchant_id: Optional[str] = None,
                                    limit: int = 20) -> list:
    now = _now()
    q = {
        "active": True,
        "start_at": {"$lte": now},
        "end_at": {"$gte": now},
    }
    if merchant_id:
        q["merchant_id"] = merchant_id
    rows = await db.game_campaigns.find(q).sort("created_at", -1) \
                                    .limit(limit).to_list(length=limit)
    # Enrich with merchant name + logo
    items = []
    for r in rows:
        biz = None
        if r.get("merchant_id"):
            biz = await db.businesses.find_one(
                {"$or": [{"business_id": r["merchant_id"]},
                                {"_id": r["merchant_id"]}]},
                {"name": 1, "logo_url": 1, "slug": 1})
        items.append({
            **r,
            "merchant_name": (biz or {}).get("name"),
            "merchant_logo_url": (biz or {}).get("logo_url"),
            "merchant_slug": (biz or {}).get("slug"),
        })
    return items


# ─── Analytics ────────────────────────────────────────────────
async def campaign_analytics(db, *, campaign_id: str) -> dict:
    campaign = await db.game_campaigns.find_one({"campaign_id": campaign_id})
    if not campaign:
        return {}
    total_plays = await db.game_sessions.count_documents({"campaign_id": campaign_id})
    total_wins = await db.game_winners.count_documents({"campaign_id": campaign_id})
    unique_players = len(await db.game_sessions.distinct("user_id",
                                                                                                                  {"campaign_id": campaign_id}))
    cost_pipeline = [
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": None, "s": {"$sum": "$value_cents"}}},
    ]
    cost_docs = await db.game_winners.aggregate(cost_pipeline).to_list(length=1)
    cost = cost_docs[0]["s"] if cost_docs else 0
    # Prize distribution
    dist = []
    async for row in db.game_sessions.aggregate([
        {"$match": {"campaign_id": campaign_id}},
        {"$group": {"_id": {"prize_id": "$outcome_prize_id",
                                                "prize_type": "$outcome_type",
                                                "label": "$outcome_label"},
                                "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]):
        dist.append({"prize_id": row["_id"]["prize_id"],
                                  "prize_type": row["_id"]["prize_type"],
                                  "display_label": row["_id"]["label"],
                                  "count": row["count"]})
    return {"campaign_id": campaign_id,
                  "plays": total_plays,
                  "wins": total_wins,
                  "cost_estimate_cents": int(cost),
                  "unique_players": unique_players,
                  "prize_distribution": dist,
                  "current_plays_count": int(campaign.get("current_plays_count") or 0)}


# ─── Indexes ──────────────────────────────────────────────────
async def ensure_game_indexes(db) -> None:
    await db.game_templates.create_index("template_id", unique=True)
    await db.game_campaigns.create_index("campaign_id", unique=True)
    await db.game_campaigns.create_index([("merchant_id", 1),
                                                                                    ("active", 1),
                                                                                    ("end_at", -1)])
    await db.game_sessions.create_index([("campaign_id", 1), ("user_id", 1)])
    await db.game_sessions.create_index("played_at")
    await db.game_winners.create_index("campaign_id")
    await db.game_winners.create_index([("user_id", 1), ("awarded_at", -1)])
    # Seed default templates
    await seed_templates(db)


__all__ = [
    "GAME_TYPES", "PRIZE_TYPES",
    "seed_templates", "list_templates",
    "create_campaign", "update_campaign", "list_campaigns", "get_campaign",
    "can_user_play", "play", "discover", "campaign_analytics",
    "ensure_game_indexes",
]
