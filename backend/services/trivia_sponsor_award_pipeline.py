"""Phase H — AD.5 Trivia Sponsorship award pipeline.

Called INLINE from the trivia room `done` transition in
`routes/trivia_room_routes.py` right after the base BigCoin payout.
The room passes in its final_scores list and (optionally) its
`sponsorship_id` — if that ID is present and the sponsorship is
still active, we grant per-rank / per-threshold prizes to the
matching players, minting BigCoin via `PointsService` or USD vouchers
via the `coupons` collection (same pattern as Phase G).

Idempotent per `(sponsorship_id, user_id, room_code)` via a compound
unique index on `trivia_sponsor_awards`.  Multi-sponsor fan-out is
allowed (spec §H.4).

Contract:
    await on_trivia_room_done(db, room_code=..., category_id=...,
                                                        sponsorship_id=..., final_scores=[...])
    → {"awards": [{...}], "count": N}

Where `final_scores` = [{user_id, name, rank, score, bigcoin_awarded}, ...]
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("bigfm.ad5.pipeline")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v):
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


def _gen(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(7)}"


def _iso(v):
    return _aware(v).isoformat() if isinstance(v, datetime) else v


async def _award_bigcoin(db, *, user_id: str, sponsorship_id: str,
                                              room_code: str, points: int) -> Dict[str, Any]:
    from services.points_service import PointsService
    result = await PointsService(db).award(
        user_id=user_id,
        source="trivia_sponsorship_reward",
        source_id=f"{sponsorship_id}:{room_code}",
        delta=int(points),
        idempotency_key=f"ts_{sponsorship_id}_{user_id}_{room_code}",
        metadata={"sponsorship_id": sponsorship_id,
                            "room_code":            room_code,
                            "note": "AD.5 trivia sponsorship prize"},
        enforce_caps=False)
    return {"ok": result.ok,
                    "wallet_item_id": result.entry_id,
                    "wallet_item_type": "trivia_prize_reward",
                    "balance_after": result.balance_after,
                    "reason": result.reason}


async def _award_voucher(db, *, user_id: str, sponsorship_id: str,
                                              room_code: str, amount_cents: int,
                                              advertiser_business_id: str,
                                              display_name: str) -> Dict[str, Any]:
    now = _now()
    coupon_id = _gen("cpn_ts")
    code = secrets.token_urlsafe(8).upper().replace("_", "").replace("-", "")[:10]
    offer_id = f"ofr_ts_{sponsorship_id[:12]}"
    if not await db.offers.find_one({"offer_id": offer_id}):
        try:
            await db.offers.insert_one({
                "_id":                        offer_id,
                "offer_id":              offer_id,
                "business_id":        advertiser_business_id,
                "title":                    (display_name or "Trivia prize voucher")[:100],
                "discount_percent":  0,
                "offer_type":          "dollar_off",
                "amount_cents":      int(amount_cents),
                "campaign_source": "ad5_trivia_sponsorship",
                "created_at":          now,
            })
        except Exception:
            pass
    doc = {
        "_id":                            coupon_id,
        "coupon_id":              coupon_id,
        "code":                        code,
        "user_id":                    user_id,
        "offer_id":                offer_id,
        "status":                    "saved",
        "amount_cents":        int(amount_cents),
        "source":                    "ad5_trivia_sponsorship",
        "sponsorship_id":    sponsorship_id,
        "room_code":              room_code,
        "created_at":            now,
    }
    await db.coupons.insert_one(doc)
    return {"ok": True,
                    "wallet_item_id": coupon_id,
                    "wallet_item_type": "trivia_prize_reward",
                    "coupon_code": code}


async def _find_matching_sponsorships(db, *, room_sponsorship_id: Optional[str],
                                                                                    category_id: str
                                                                                    ) -> List[Dict[str, Any]]:
    """The room may have been created with a specific sponsorship
    (`room_sponsorship_id`) that binds one advertiser to it.  In
    addition, any `sponsor_target_type="any"` sponsorships apply to
    ALL rooms in-window — those fan out on top of the bound
    sponsor.  `sponsor_target_type="category"` sponsorships apply to
    every room of the matching category (whether the host chose them
    or not) — this makes advertiser bidding on categories the
    "sponsored radio" default."""
    now = _now()
    q: Dict[str, Any] = {
        "status":      "active",
        "start_at": {"$lte": now},
        "end_at":    {"$gt":  now},
    }
    or_clauses: List[Dict[str, Any]] = [
        {"sponsor_target_type": "any"},
        {"sponsor_target_type": {"$in": ["category", "question_set"]},
          "target_id": category_id},
    ]
    if room_sponsorship_id:
        or_clauses.append({"id": room_sponsorship_id})
    q["$or"] = or_clauses
    return [s async for s in db.trivia_sponsorships.find(q)]


def _winners_top_n(final_scores: List[Dict[str, Any]],
                                      prize_pool: List[Dict[str, Any]]
                                      ) -> List[Dict[str, Any]]:
    """Match sorted rank tiers to the prize pool ranks.  If a tier has
    quantity=Q, it awards positions [tier_start, tier_start+Q-1]."""
    # Sort pool by rank ASC so rank 1 comes first.
    pool_sorted = sorted(prize_pool, key=lambda p: int(p.get("rank") or 999))
    # Sort players by score DESC (final_scores is already sorted this way).
    players_sorted = sorted(final_scores, key=lambda p: -(p.get("score") or 0))
    winners: List[Dict[str, Any]] = []
    idx = 0    # position in players list
    for tier in pool_sorted:
        quantity  = int(tier.get("quantity") or 1)
        for _ in range(quantity):
            if idx >= len(players_sorted):
                return winners
            p = players_sorted[idx]
            winners.append({
                "user_id":        p.get("user_id"),
                "user_name":    p.get("name"),
                "rank":            int(tier.get("rank") or (idx + 1)),
                "score":          int(p.get("score") or 0),
                "points_reward": int(tier.get("points_reward") or 0),
                "currency":    (tier.get("currency") or "bc").lower(),
            })
            idx += 1
    return winners


def _winners_threshold(final_scores: List[Dict[str, Any]],
                                              prize_pool: List[Dict[str, Any]],
                                              threshold: int) -> List[Dict[str, Any]]:
    """Everyone above threshold gets the top-tier prize, capped by
    the top tier's quantity."""
    top = sorted(prize_pool, key=lambda p: int(p.get("rank") or 999))[0]
    capacity  = int(top.get("quantity") or 1)
    reward    = int(top.get("points_reward") or 0)
    currency  = (top.get("currency") or "bc").lower()
    winners: List[Dict[str, Any]] = []
    for p in sorted(final_scores, key=lambda x: -(x.get("score") or 0)):
        if int(p.get("score") or 0) < int(threshold):
            break
        if len(winners) >= capacity:
            break
        winners.append({
            "user_id":        p.get("user_id"),
            "user_name":    p.get("name"),
            "rank":            int(top.get("rank") or 1),
            "score":          int(p.get("score") or 0),
            "points_reward": reward,
            "currency":      currency,
        })
    return winners


async def _try_award_sponsorship(db, *, sponsorship: Dict[str, Any],
                                                                        room_code: str,
                                                                        winners: List[Dict[str, Any]]
                                                                        ) -> List[Dict[str, Any]]:
    """Grant prizes for a single sponsorship.  Reserves budget
    atomically per winner (rolls back on grant failure)."""
    granted: List[Dict[str, Any]] = []
    sponsorship_id            = sponsorship["id"]
    advertiser_business_id = sponsorship["advertiser_business_id"]
    display_name                    = sponsorship.get("display_name") or ""

    for w in winners:
        # Cost = the points_reward value (bc: 1pt=1¢, usd: reward is already cents).
        cost = int(w.get("points_reward") or 0)
        if cost <= 0:
            continue
        # Reserve budget atomically.
        reserved = await db.trivia_sponsorships.find_one_and_update(
            {"id":                              sponsorship_id,
              "status":                        "active",
              "remaining_budget_cents":  {"$gte": cost},
              "$expr": {"$lt": ["$awarded_count", "$max_total_awards"]}},
            {"$inc": {"remaining_budget_cents": -cost, "awarded_count": 1},
              "$set": {"last_award_at": _now()}},
            return_document=True)
        if not reserved:
            # Budget out / cap hit — try to flip to completed.
            try:
                await db.trivia_sponsorships.update_one(
                    {"id":      sponsorship_id, "status": "active",
                      "$or":  [
                            {"$expr": {"$gte": ["$awarded_count", "$max_total_awards"]}},
                            {"remaining_budget_cents": {"$lt": cost}}]},
                    {"$set": {"status": "completed", "completed_at": _now()}})
            except Exception:
                pass
            break

        currency  = w.get("currency") or "bc"
        try:
            if currency == "bc":
                grant = await _award_bigcoin(
                    db, user_id=w["user_id"], sponsorship_id=sponsorship_id,
                    room_code=room_code, points=int(w["points_reward"]))
            else:
                grant = await _award_voucher(
                    db, user_id=w["user_id"], sponsorship_id=sponsorship_id,
                    room_code=room_code,
                    amount_cents=int(w["points_reward"]),
                    advertiser_business_id=advertiser_business_id,
                    display_name=display_name)
        except Exception as e:
            logger.exception("[ad5] grant failed sp=%s uid=%s: %s",
                                              sponsorship_id, w["user_id"], e)
            await db.trivia_sponsorships.update_one(
                {"id": sponsorship_id},
                {"$inc": {"remaining_budget_cents": cost,
                                  "awarded_count": -1}})
            continue

        award_id = _gen("tsa")
        award_doc = {
            "_id":                                        award_id,
            "id":                                          award_id,
            "sponsorship_id":                    sponsorship_id,
            "room_code":                              room_code,
            "user_id":                                w["user_id"],
            "user_name":                            w.get("user_name"),
            "rank":                                      w["rank"],
            "score":                                    w["score"],
            "points_awarded":                    int(w["points_reward"]),
            "currency":                                currency,
            "wallet_item_id":                    grant.get("wallet_item_id"),
            "wallet_item_type":                grant.get("wallet_item_type"),
            "sponsor_display_name":            display_name,
            "advertiser_business_id":        advertiser_business_id,
            "advertiser_charge_cents":        int(w["points_reward"]),
            "redemption_status":                "pending",
            "awarded_at":                              _now(),
        }
        try:
            await db.trivia_sponsor_awards.insert_one(award_doc)
        except Exception as e:
            # Duplicate — same (sponsorship, user, room) already awarded.
            if "duplicate" in str(e).lower() or "E11000" in str(e):
                await db.trivia_sponsorships.update_one(
                    {"id": sponsorship_id},
                    {"$inc": {"remaining_budget_cents": cost,
                                      "awarded_count": -1}})
                continue
            raise
        granted.append({
            "award_id":                            award_id,
            "sponsorship_id":                sponsorship_id,
            "room_code":                          room_code,
            "user_id":                            w["user_id"],
            "rank":                                  w["rank"],
            "points_awarded":                int(w["points_reward"]),
            "currency":                          currency,
            "wallet_item_id":                grant.get("wallet_item_id"),
            "wallet_item_type":            grant.get("wallet_item_type"),
            "coupon_code":                    grant.get("coupon_code"),
            "advertiser_business_id":  advertiser_business_id,
            "sponsor_display_name":    display_name,
            "awarded_at":                      _iso(award_doc["awarded_at"]),
        })

        # Fire per-winner notification.
        try:
            from services.notification_trigger_dispatcher import dispatch_event
            await dispatch_event(
                db, event_name="trivia_prize_won",
                user_id=w["user_id"],
                payload={
                    "sponsorship_id":                sponsorship_id,
                    "award_id":                          award_id,
                    "room_code":                        room_code,
                    "rank":                                w["rank"],
                    "score":                              w["score"],
                    "points_awarded":                int(w["points_reward"]),
                    "currency":                          currency,
                    "sponsor_display_name":    display_name,
                    "advertiser_business_id":  advertiser_business_id,
                })
        except Exception:
            pass

    # After granting, check if the sponsorship should flip to completed.
    refreshed = await db.trivia_sponsorships.find_one(
        {"id": sponsorship_id},
        {"remaining_budget_cents": 1, "awarded_count": 1,
          "max_total_awards": 1, "status": 1})
    if refreshed and refreshed.get("status") == "active":
        rem = int(refreshed.get("remaining_budget_cents") or 0)
        aw  = int(refreshed.get("awarded_count") or 0)
        cap = int(refreshed.get("max_total_awards") or 0)
        # Consider completed when we can no longer pay the cheapest prize in the pool.
        if cap > 0 and aw >= cap:
            await db.trivia_sponsorships.update_one(
                {"id": sponsorship_id, "status": "active"},
                {"$set": {"status": "completed", "completed_at": _now()}})
        elif rem == 0:
            await db.trivia_sponsorships.update_one(
                {"id": sponsorship_id, "status": "active"},
                {"$set": {"status": "completed", "completed_at": _now()}})

    return granted


async def on_trivia_room_done(db, *,
                                                            room_code: str,
                                                            category_id: str,
                                                            sponsorship_id: Optional[str] = None,
                                                            final_scores: List[Dict[str, Any]] = None
                                                            ) -> Dict[str, Any]:
    """Entrypoint from `trivia_room_routes.py` inside the room driver's
    `done` block, right after the base BigCoin payouts."""
    final_scores = final_scores or []
    if not final_scores or not room_code:
        return {"awards": [], "count": 0}
    try:
        matching = await _find_matching_sponsorships(
            db, room_sponsorship_id=sponsorship_id,
            category_id=category_id or "")
    except Exception as e:
        logger.warning("[ad5] sponsorship lookup failed: %s", e)
        return {"awards": [], "count": 0}

    all_awards: List[Dict[str, Any]] = []
    for s in matching:
        pool                  = s.get("prize_pool") or []
        selection          = s.get("winner_selection") or "top_n"
        threshold          = s.get("score_threshold")
        try:
            winners = (_winners_top_n(final_scores, pool)
                                  if selection == "top_n"
                                  else _winners_threshold(final_scores, pool,
                                                                                        int(threshold or 0)))
            if not winners:
                continue
            granted = await _try_award_sponsorship(
                db, sponsorship=s, room_code=room_code, winners=winners)
            all_awards.extend(granted)
        except Exception as e:
            logger.warning("[ad5] award sweep failed sp=%s: %s", s.get("id"), e)
    return {"awards": all_awards, "count": len(all_awards)}


__all__ = ["on_trivia_room_done"]
