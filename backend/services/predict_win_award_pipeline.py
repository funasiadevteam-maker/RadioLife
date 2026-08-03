"""Sub-Phase E2 — Predict & Win award fan-out pipeline.

Called synchronously from `predict_win_admin.force_resolve_campaign`
(and later from the E4 auto-resolve cron sweeper).  Given a campaign
in `status="resolved"` plus the winning option:

  1. Read every `predict_win_entries` row for the campaign.
  2. Set `status="winner"` on matches and `"loser"` on non-matches
       (E1 already did this — we keep it idempotent here).
  3. Apply the `winner_rules_json.selection_rule` to narrow the
       winners (random-N, first-N, leaderboard, or all-correct).
  4. For each selected winner, create a `predict_win_awards` row AND
       credit their wallet / bigcoin balance / badge.
  5. Write a `predict_win_analytics_events` row per winner.
  6. Drop an in-app notification (`station_notifications.type =
       "prediction_award"`) per winner.

Re-entrancy: the function is idempotent on a per-(campaign, entry)
basis — re-running it produces no duplicate awards (`predict_win_awards`
has a unique compound index on `(campaign_id, entry_id)`).
"""
from __future__ import annotations
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("bigfm.predict_win.award_pipeline")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime] = None) -> str:
    return (dt or _now()).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


# ─── Selection rules ──────────────────────────────────────────────────
def _select_winners(
    *,
    matching_entries: List[dict],
    rule: str,
    max_winners: Optional[int],
    resolution_id: str,
) -> List[dict]:
    """Apply the selection rule.  Returns the subset of matching entries
    who actually win the prize."""
    if not matching_entries:
        return []

    if rule == "all_correct":
        # Everyone with the right answer wins (capped by max_winners if set).
        out = list(matching_entries)
    elif rule == "first_n_correct":
        # Earliest entries win.
        out = sorted(matching_entries,
                              key=lambda e: e.get("submitted_at") or "")
    elif rule == "leaderboard_score":
        # Confidence DESC, then earliest first.
        out = sorted(
            matching_entries,
            key=lambda e: (-(e.get("confidence") or 0),
                                      e.get("submitted_at") or ""),
        )
    elif rule == "random_n_correct":
        # Seed with resolution_id for reproducibility (so two re-runs
        # of the pipeline draw the same winners).
        rng = random.Random(resolution_id)
        shuffled = list(matching_entries)
        rng.shuffle(shuffled)
        out = shuffled
    else:
        log.warning("[award] unknown selection_rule=%s — defaulting to all_correct",
                              rule)
        out = list(matching_entries)

    if max_winners is not None and max_winners > 0:
        out = out[:max_winners]
    return out


# ─── Prize credit dispatch ────────────────────────────────────────────
async def _credit_prize_to_user(
    db, *,
    user_id: str,
    prize: dict,
    award_id: str,
    campaign_id: str,
) -> Tuple[Optional[str], str]:
    """Credit the prize per `prize_kind`.  Returns
    `(wallet_item_id_or_None, delivery_status)`.

    Delivery statuses:
      • `delivered`        — credit applied immediately (points / badge).
      • `in_wallet`        — wallet_item row created, user redeems later.
      • `pending`             — couldn't deliver (e.g. inventory depleted),
                                          admin must reconcile.
    """
    kind = (prize.get("prize_kind") or "").lower()

    # Points / BigCoin — increment users.bigcoin_balance + lifetime.
    if kind in ("points", "bigcoin"):
        amount = int((prize.get("value_amount") or 0) or 0)
        if amount > 0:
            res = await db.users.find_one_and_update(
                {"user_id": user_id},
                {"$inc": {
                    "bigcoin_balance": amount,
                    "bigcoin_lifetime_earned": amount,
                }},
                return_document=True,
                projection={"bigcoin_balance": 1, "_id": 0},
            )
            new_balance = int((res or {}).get("bigcoin_balance") or 0)
            # Phase F-1 — mirror predict-win prize into the unified
            # Points ledger so the new endpoints can attribute it under
            # `predict_win_correct`.  Idempotent on award_id so a
            # re-run of the pipeline can't double-count.  TODO Phase
            # F-2: switch the $inc above to flow through PointsService
            # only.
            try:
                from services.points_service import PointsService
                await PointsService(db).award(
                    user_id=user_id,
                    source="predict_win_correct",
                    source_id=award_id,
                    delta=amount,
                    metadata={"campaign_id": campaign_id,
                                      "award_id": award_id,
                                      "legacy_path": "predict_win_award_pipeline"},
                    idempotency_key=f"predict_win_correct:{award_id}",
                    mirror_only=True,
                    balance_after_override=new_balance,
                )
            except Exception as e:
                log.warning("[predict_win] points-ledger mirror failed: %s", e)
            # Phase AD.12 bundle — fire the `predict_win_correct` trigger
            # for any live trigger-based notification campaigns.
            try:
                from services.notification_trigger_dispatcher import dispatch_event
                await dispatch_event(
                    db, event_name="predict_win_correct",
                    user_id=user_id,
                    payload={"campaign_id": campaign_id,
                                      "award_id": award_id,
                                      "amount": amount})
            except Exception:
                pass
        return None, "delivered"

    # Passport badge — direct upsert on user_badges.
    if kind == "passport_badge":
        badge_id = prize.get("badge_id") or f"badge_pwin_{campaign_id}"
        try:
            await db.user_badges.update_one(
                {"user_id": user_id, "badge_id": badge_id},
                {"$setOnInsert": {
                    "_id": _new_id("ub"),
                    "user_id": user_id,
                    "badge_id": badge_id,
                    "earned_at": _now(),
                    "source": "prediction_win",
                    "source_award_id": award_id,
                }},
                upsert=True,
            )
        except Exception as e:
            log.warning("[award] badge insert failed: %s", e)
        return None, "delivered"

    # All other physical / experiential / coupon prizes → wallet item.
    # (`merchandise`, `experience`, `coupon`, `gift_card`, `ticket`,
    #  `free_item`, `prepaid_meal`, `product_sample`, `giveaway_entry`,
    #  `custom`)
    wallet_item_id = _new_id("wi_pwin")
    await db.user_wallet_items.insert_one({
        "_id": wallet_item_id,
        "wallet_item_id": wallet_item_id,
        "user_id": user_id,
        "item_type": "prediction_award",
        "prize_kind": kind or "custom",
        "title": prize.get("title") or "Prediction prize",
        "description": prize.get("description"),
        "value_amount": prize.get("value_amount"),
        "value_currency": prize.get("value_currency"),
        "image_url": prize.get("image_url"),
        "status": "in_wallet",
        "redemption_source": "predict_win",
        "source_award_id": award_id,
        "source_campaign_id": campaign_id,
        "source_prize_id": prize.get("prize_id"),
        "created_at": _now(),
    })
    return wallet_item_id, "in_wallet"


# ─── In-app notification ──────────────────────────────────────────────
async def _notify_winner(
    db, *,
    user_id: str,
    campaign: dict,
    prize: dict,
    award_id: str,
    wallet_item_id: Optional[str],
) -> None:
    nid = _new_id("notif_pwin")
    related_slug = campaign.get("related_station_slug") or "predict-win"
    try:
        await db.station_notifications.insert_one({
            "_id": nid,
            "id": nid,
            "owner_user_id": user_id,
            "station_id": campaign.get("related_station_id") or "_predict_win_",
            "station_slug": related_slug,
            "type": "prediction_award",
            "payload": {
                "campaign_id": campaign["campaign_id"],
                "campaign_title": campaign.get("title"),
                "award_id": award_id,
                "wallet_item_id": wallet_item_id,
                "prize_title": prize.get("title"),
                "prize_kind": prize.get("prize_kind"),
                "value_amount": prize.get("value_amount"),
                "value_currency": prize.get("value_currency"),
                "cta": "/predict-win/my-wins",
            },
            "created_at": _iso(),
            "read_at": None,
            "dedupe_key": f"prediction_award:{award_id}",
        })
    except Exception as e:
        # Idempotency guard — duplicate dedupe_key just silently skips.
        if "duplicate" not in str(e).lower():
            log.warning("[award] notification insert failed: %s", e)


# ─── Analytics event ──────────────────────────────────────────────────
async def _emit_analytics(
    db, *,
    user_id: str,
    campaign: dict,
    award_id: str,
    prize: dict,
) -> None:
    await db.predict_win_analytics_events.insert_one({
        "_id": _new_id("pwae"),
        "campaign_id": campaign["campaign_id"],
        "event_type": "win",
        "user_id": user_id,
        "session_id": None,
        "timestamp": _now(),
        "metadata_json": {
            "award_id": award_id,
            "prize_id": prize.get("prize_id"),
            "prize_kind": prize.get("prize_kind"),
            "value_amount": prize.get("value_amount"),
        },
    })


# ─── Entry status fan-out (matching / losing) ─────────────────────────
async def _flip_entry_statuses(
    db, *,
    campaign_id: str,
    winning_option_id: str,
    now: datetime,
) -> List[dict]:
    """Idempotent: E1 already flipped winners/losers on force-resolve.
    We re-run with the same outcome and return the winner list."""
    await db.predict_win_entries.update_many(
        {"campaign_id": campaign_id,
          "picked_option_id": winning_option_id,
          "status": {"$nin": ["winner", "void"]}},
        {"$set": {"status": "winner", "evaluated_at": now}},
    )
    await db.predict_win_entries.update_many(
        {"campaign_id": campaign_id,
          "picked_option_id": {"$ne": winning_option_id},
          "status": {"$nin": ["loser", "void"]}},
        {"$set": {"status": "loser", "evaluated_at": now}},
    )
    winners_cur = db.predict_win_entries.find({
        "campaign_id": campaign_id, "status": "winner",
    })
    return [e async for e in winners_cur]


# ─── Main pipeline ────────────────────────────────────────────────────
async def run_award_pipeline(
    db, *,
    campaign_id: str,
    winning_option_id: str,
    resolution_id: str,
) -> Dict[str, Any]:
    """Run the full award fan-out for a campaign that has just been
    resolved.  Safe to re-invoke; uses the unique compound index
    `predict_win_awards.(campaign_id, entry_id)` to short-circuit
    duplicates."""
    campaign = await db.predict_win_campaigns.find_one(
        {"campaign_id": campaign_id})
    if not campaign:
        log.warning("[award] campaign %s not found — skipping", campaign_id)
        return {"ok": False, "reason": "campaign_not_found"}

    now = _now()
    winners = await _flip_entry_statuses(
        db, campaign_id=campaign_id,
        winning_option_id=winning_option_id, now=now)

    rules = campaign.get("winner_rules_json") or {}
    selection_rule = (rules.get("selection_rule")
                                      or _legacy_to_selection_rule(rules.get("scoring")))
    max_winners = rules.get("max_winners")

    # Get the prize(s) — E2 awards a single primary prize per winner
    # (rank=1 active).  Multiple-tier prizes is an E4 enhancement.
    prize = await db.predict_win_prizes.find_one(
        {"campaign_id": campaign_id, "active": True},
        sort=[("rank", 1)],
    )
    if not prize:
        log.info("[award] campaign %s has no active prize — skipping fan-out",
                          campaign_id)
        return {"ok": True, "winners_count": 0,
                      "reason": "no_active_prize",
                      "selection_rule": selection_rule}

    selected = _select_winners(
        matching_entries=winners,
        rule=selection_rule,
        max_winners=max_winners,
        resolution_id=resolution_id,
    )
    awarded: List[Dict[str, Any]] = []
    skipped_duplicate = 0

    for entry in selected:
        # Inventory check.
        live_prize = await db.predict_win_prizes.find_one(
            {"prize_id": prize["prize_id"]})
        if (live_prize or {}).get("inventory_remaining", 1) <= 0:
            log.info("[award] inventory exhausted for prize=%s", prize["prize_id"])
            break

        # Idempotent guard on existing award row.
        existing = await db.predict_win_awards.find_one({
            "campaign_id": campaign_id,
            "entry_id": entry["entry_id"],
        })
        if existing:
            skipped_duplicate += 1
            continue

        award_id = _new_id("pwa")
        wallet_item_id, delivery_status = await _credit_prize_to_user(
            db, user_id=entry["user_id"], prize=live_prize or prize,
            award_id=award_id, campaign_id=campaign_id,
        )
        try:
            await db.predict_win_awards.insert_one({
                "_id": award_id,
                "award_id": award_id,
                "campaign_id": campaign_id,
                "entry_id": entry["entry_id"],
                "prize_id": prize["prize_id"],
                "winner_user_id": entry["user_id"],
                "awarded_by": "pipeline",
                "awarded_at": now,
                "delivery_status": delivery_status,
                "award_reason": f"selection_rule:{selection_rule}",
                "delivery_notes": None,
                "wallet_item_id": wallet_item_id,
                "resolution_id": resolution_id,
            })
        except Exception as e:
            if "duplicate" in str(e).lower():
                skipped_duplicate += 1
                continue
            log.warning("[award] insert failed for entry=%s: %s",
                                  entry["entry_id"], e)
            continue

        # Decrement inventory.
        await db.predict_win_prizes.update_one(
            {"prize_id": prize["prize_id"]},
            {"$inc": {"inventory_remaining": -1}},
        )

        await _emit_analytics(
            db, user_id=entry["user_id"], campaign=campaign,
            award_id=award_id, prize=live_prize or prize)
        await _notify_winner(
            db, user_id=entry["user_id"], campaign=campaign,
            prize=live_prize or prize,
            award_id=award_id, wallet_item_id=wallet_item_id)

        awarded.append({
            "award_id": award_id,
            "entry_id": entry["entry_id"],
            "user_id": entry["user_id"],
            "wallet_item_id": wallet_item_id,
            "delivery_status": delivery_status,
        })

    log.info(
        "[award] campaign=%s selection=%s winners=%d awarded=%d skipped=%d",
        campaign_id, selection_rule, len(selected), len(awarded), skipped_duplicate,
    )
    return {
        "ok": True,
        "selection_rule": selection_rule,
        "winners_count": len(winners),
        "selected_count": len(selected),
        "awarded_count": len(awarded),
        "skipped_duplicate": skipped_duplicate,
        "awards": awarded,
    }


def _legacy_to_selection_rule(scoring: Optional[str]) -> str:
    """Map E1's `winner_rules_json.scoring` to E2's `selection_rule` so
    the 3 demo campaigns from E1 work without a DB migration."""
    if scoring == "points_per_correct":
        return "leaderboard_score"
    return "all_correct"


async def ensure_e2_indexes(db) -> None:
    """E2 index additions."""
    # Idempotency: one award row per (campaign, entry).
    await db.predict_win_awards.create_index(
        [("campaign_id", 1), ("entry_id", 1)],
        unique=True,
        name="predict_win_awards_unique_per_entry",
    )
    await db.user_wallet_items.create_index(
        [("user_id", 1), ("item_type", 1), ("created_at", -1)],
        name="user_wallet_items_user_type",
    )
    log.info("[award] E2 indexes ensured")
