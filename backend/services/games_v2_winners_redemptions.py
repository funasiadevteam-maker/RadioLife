"""Phase 23 Session 1.5 — winners + redemptions service.

Two collections, two flows:

1. `game_winners` — canonical immutable record of every win event.
   - Hook into existing `submit_session()` writes one row per winning session
     (idempotent on session_id).
   - `prize_snapshot_json` captures prize state at win time — never edited.
2. `game_redemptions` — append-only audit log of every staff-scan attempt.
   - UNIQUE index on `redemption_code` enforces one-time-use at storage level.

Mongo single-doc atomicity is leveraged where possible; multi-collection
updates use compensating actions documented at each call site.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from pymongo.errors import DuplicateKeyError


logger = logging.getLogger("bigfm.games_v2.winners")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str, length: int = 14) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:length]}"


def _prize_snapshot(prize: dict) -> dict[str, Any]:
    """Immutable copy of the prize fields a user needs to redeem.
    Captured at win time so post-win advertiser edits don't change the
    user's promised reward."""
    return {
        "prize_id": prize["prize_id"],
        "title": prize.get("title"),
        "description": prize.get("description"),
        "prize_type": prize.get("prize_type"),
        "value_amount": prize.get("value_amount"),
        "value_currency": prize.get("value_currency"),
        "redemption_method": prize.get("redemption_method"),
        "requires_staff_validation": bool(prize.get("requires_staff_validation")),
        "requires_location": bool(prize.get("requires_location")),
        "expiration_policy_json": prize.get("expiration_policy_json"),
        "linked_offer_id": prize.get("linked_offer_id"),
    }


# =====================================================================
# Index bootstrap
# =====================================================================
async def ensure_phase23_indexes(db) -> None:
    # game_winners
    await db.game_winners.create_index([("winner_id", 1)], unique=True)
    await db.game_winners.create_index([("game_session_id", 1)], unique=True)
    await db.game_winners.create_index([("user_id", 1), ("status", 1)])
    await db.game_winners.create_index([("game_campaign_id", 1), ("won_at", -1)])
    await db.game_winners.create_index([("prize_id", 1)])
    await db.game_winners.create_index([("wallet_item_id", 1)], sparse=True)
    # game_redemptions
    await db.game_redemptions.create_index([("redemption_id", 1)], unique=True)
    await db.game_redemptions.create_index([("winner_id", 1)])
    await db.game_redemptions.create_index([("wallet_item_id", 1)])
    await db.game_redemptions.create_index(
        [("business_id", 1), ("redeemed_at", -1)])
    await db.game_redemptions.create_index(
        [("redemption_code", 1)],
        unique=True,
        partialFilterExpression={"status": "success"},
        name="redemption_code_unique_success")


# =====================================================================
# Winner recording (the hook fired from submit_session)
# =====================================================================
async def record_winner(db, session_id: str, *,
                                          source: str = "post_win_hook") -> dict:
    """Insert a game_winners row for a winning session.

    Idempotent on session_id — second call returns the existing winner.
    Caller MUST have verified the session is a win (this is invoked by the
    existing submit_session() flow which already decremented inventory
    atomically via _atomic_claim_prize). We re-validate defensively to
    guard against future call-sites and admin replays.

    Raises ValueError with one of:
      - 'session_not_found'
      - 'not_a_win'
      - 'prize_missing'
      - 'max_per_user_reached'  (compensating: inventory restored)
      - 'inventory_exhausted'   (extremely rare — pre-decrement was negative)
    """
    sess = await db.game_sessions.find_one({"session_id": session_id})
    if not sess:
        raise ValueError("session_not_found")

    # Idempotency check FIRST
    existing = await db.game_winners.find_one({"game_session_id": session_id})
    if existing:
        return existing

    if sess.get("result") != "win" or not sess.get("prize_id"):
        raise ValueError("not_a_win")

    prize = await db.game_prizes.find_one({"prize_id": sess["prize_id"]})
    if not prize:
        raise ValueError("prize_missing")

    # max_per_user defensive check (race against concurrent wins).
    # We count COMPLETED winner rows for (user_id, campaign_id) — note
    # this counts the current session if a prior call inserted it,
    # which is fine because we returned early on the idempotency check.
    max_per_user = int(prize.get("max_per_user") or 0)
    if max_per_user > 0:
        prior_wins = await db.game_winners.count_documents({
            "user_id": sess["user_id"],
            "game_campaign_id": sess["campaign_id"],
            "status": {"$ne": "voided"},
        })
        if prior_wins >= max_per_user:
            # Compensate: the prize was already atomically decremented by
            # submit_session.  Restore inventory and void the session result
            # so the user sees a 'lose' outcome on retry.
            await db.game_prizes.update_one(
                {"prize_id": prize["prize_id"]},
                {"$inc": {"inventory_remaining": 1}})
            await db.game_inventory_ledger.insert_one({
                "_id": _new_id("led"),
                "campaign_id": sess["campaign_id"],
                "prize_id": prize["prize_id"],
                "delta": 1,
                "session_id": session_id,
                "reason": "winner_record_max_per_user_compensation",
                "inventory_after": int(prize.get("inventory_remaining") or 0) + 1,
                "ts": _now(),
            })
            await db.game_sessions.update_one(
                {"session_id": session_id},
                {"$set": {"result": "lose", "prize_id": None,
                              "compensated_at": _now(),
                              "compensation_reason": "max_per_user"}})
            raise ValueError("max_per_user_reached")

    now = _now()
    winner = {
        "_id": _new_id("win"),
        "winner_id": _new_id("win"),
        "game_campaign_id": sess["campaign_id"],
        "game_session_id": session_id,
        "user_id": sess["user_id"],
        "prize_id": prize["prize_id"],
        "prize_snapshot_json": _prize_snapshot(prize),
        "wallet_item_id": sess.get("wallet_item_id"),
        "won_at": sess.get("completed_at") or now,
        "status": ("in_wallet" if sess.get("wallet_item_id")
                       else "pending_wallet_save"),
        "voided_reason": None,
        "created_at": now,
        "updated_at": now,
        "source": source,
    }
    # winner_id is the canonical handle (route param); _id is mongo-only
    winner["_id"] = winner["winner_id"]

    try:
        await db.game_winners.insert_one(winner)
    except DuplicateKeyError:
        # Race: a concurrent record_winner call won — return the row that
        # landed first.
        return await db.game_winners.find_one(
            {"game_session_id": session_id})
    # Phase A Item 3 — game_win_high_value trigger.  Fires when the prize
    # value is >=100 (points / currency-agnostic — matches recipe copy
    # "≥100 points in any game session").  Silent-on-error hook.
    try:
        _prize_value = int(prize.get("value_amount") or 0)
        if _prize_value >= 100 and sess.get("user_id"):
            import asyncio as _aio
            from services.notification_trigger_dispatcher import dispatch_event
            _aio.create_task(dispatch_event(
                db, event_name="game_win_high_value",
                user_id=sess["user_id"],
                payload={"prize_id":                prize["prize_id"],
                                  "prize_value":          _prize_value,
                                  "prize_type":            prize.get("prize_type"),
                                  "game_campaign_id": sess["campaign_id"],
                                  "winner_id":              winner["winner_id"]}))
    except Exception:
        pass                                # never break record_winner
    return winner


# =====================================================================
# Save winner -> wallet
# =====================================================================
async def save_winner_to_wallet(db, user: dict, winner_id: str) -> dict:
    """Materialize a user_wallet_items row for an existing winner.

    Idempotent — second call returns the existing wallet_item without
    duplicating.  Reuses the existing claim_to_wallet flow (which already
    handles redemption_rules expiration computation + analytics)."""
    winner = await db.game_winners.find_one({"winner_id": winner_id})
    if not winner:
        raise ValueError("winner_not_found")
    if winner["user_id"] != user["user_id"]:
        raise PermissionError("not_owner")
    if winner["status"] == "voided":
        raise ValueError("winner_voided")

    # Already saved?
    if winner.get("wallet_item_id"):
        wi = await db.user_wallet_items.find_one(
            {"_id": winner["wallet_item_id"]})
        return {"wallet_item_id": winner["wallet_item_id"],
                  "winner_id": winner_id,
                  "status": winner["status"],
                  "wallet_item": wi}

    # Delegate to existing flow (handles expiration / analytics / etc.)
    from services.games_v2 import claim_to_wallet
    claim_res = await claim_to_wallet(db, user, winner["game_session_id"])

    wallet_item = claim_res.get("wallet_item")
    wallet_item_id: Optional[str] = None
    if wallet_item:
        wallet_item_id = wallet_item.get("wallet_item_id") \
                                  or wallet_item.get("_id")
    if not wallet_item_id:
        # claim_to_wallet returned None (e.g. bigcoin auto-credit case).
        # We still flip status — no wallet item for that path.
        wallet_item_id = None

    now = _now()
    await db.game_winners.update_one(
        {"winner_id": winner_id},
        {"$set": {"wallet_item_id": wallet_item_id,
                       "status": "in_wallet" if wallet_item_id else "redeemed",
                       "updated_at": now}})

    updated = await db.game_winners.find_one({"winner_id": winner_id})
    return {"wallet_item_id": wallet_item_id,
              "winner_id": winner_id,
              "status": updated["status"],
              "wallet_item": wallet_item}


# =====================================================================
# Admin: void winner
# =====================================================================
async def admin_void_winner(db, winner_id: str, *,
                                                admin_user_id: str,
                                                voided_reason: str) -> dict:
    """Admin override.  Restores inventory + voids the winner.  Idempotent
    on already-voided winners (returns the existing row)."""
    winner = await db.game_winners.find_one({"winner_id": winner_id})
    if not winner:
        raise ValueError("winner_not_found")
    if winner["status"] == "voided":
        return winner
    now = _now()
    # Restore inventory (if not already redeemed — redeemed prizes are
    # consumed, do NOT restore).
    if winner["status"] != "redeemed":
        await db.game_prizes.update_one(
            {"prize_id": winner["prize_id"]},
            {"$inc": {"inventory_remaining": 1}})
        prize = await db.game_prizes.find_one({"prize_id": winner["prize_id"]})
        await db.game_inventory_ledger.insert_one({
            "_id": _new_id("led"),
            "campaign_id": winner["game_campaign_id"],
            "prize_id": winner["prize_id"],
            "delta": 1,
            "session_id": winner["game_session_id"],
            "reason": f"admin_void:{voided_reason}",
            "inventory_after": int((prize or {}).get("inventory_remaining") or 0),
            "ts": now,
        })
    # Mark linked wallet item as voided (if any)
    if winner.get("wallet_item_id"):
        await db.user_wallet_items.update_one(
            {"_id": winner["wallet_item_id"]},
            {"$set": {"status": "voided",
                          "voided_at": now,
                          "voided_by_admin": admin_user_id}})
    await db.game_winners.update_one(
        {"winner_id": winner_id},
        {"$set": {"status": "voided",
                       "voided_reason": voided_reason,
                       "voided_by_admin": admin_user_id,
                       "voided_at": now,
                       "updated_at": now}})
    return await db.game_winners.find_one({"winner_id": winner_id})


# =====================================================================
# Redemption validation (staff scan)
# =====================================================================
async def validate_redemption(db, *,
                                                  redemption_code: str,
                                                  business_id: Optional[str] = None,
                                                  staff_user_id: Optional[str] = None,
                                                  staff_note: Optional[str] = None,
                                                  geo_lat: Optional[float] = None,
                                                  geo_lng: Optional[float] = None,
                                                  client_metadata: Optional[dict] = None,
                                                  ) -> dict:
    """Atomic-ish staff-scan flow:

    1. Look up wallet item by qr_token (= redemption_code)
    2. Look up winner by wallet_item_id
    3. Validate not-yet-redeemed, not expired, business match
    4. Insert game_redemptions row (UNIQUE on redemption_code enforces
       one-time-use at storage layer — second attempt raises DuplicateKey)
    5. Flip winner.status=redeemed, wallet_item.redeemed_at
    6. Return shaped response

    On any rejection: insert a `game_redemptions` row with status != success
    for audit, but do NOT flip the winner.

    Raises ValueError with status code string.
    """
    now = _now()
    audit_base: dict[str, Any] = {
        "redemption_id": _new_id("rdmp"),
        "redemption_code": redemption_code,
        "business_id": business_id,
        "staff_user_id": staff_user_id,
        "staff_note": staff_note,
        "geo_lat": geo_lat,
        "geo_lng": geo_lng,
        "client_metadata_json": client_metadata or {},
        "redeemed_at": now,
        "created_at": now,
    }
    audit_base["_id"] = audit_base["redemption_id"]

    wi = await db.user_wallet_items.find_one({"qr_token": redemption_code})
    if not wi:
        raise ValueError("not_found")

    winner = await db.game_winners.find_one(
        {"wallet_item_id": wi.get("_id") or wi.get("wallet_item_id")})
    if not winner:
        # No winner row → may be a pre-Phase23 wallet item.  Reject for
        # safety until backfill runs.
        raise ValueError("winner_not_found")

    audit_base["winner_id"] = winner["winner_id"]
    audit_base["wallet_item_id"] = wi.get("_id") or wi.get("wallet_item_id")

    # Already redeemed?
    if winner["status"] == "redeemed":
        await db.game_redemptions.insert_one(
            {**audit_base, "status": "already_redeemed"})
        raise ValueError("already_redeemed")

    if winner["status"] == "voided":
        await db.game_redemptions.insert_one(
            {**audit_base, "status": "fraud_block"})
        raise ValueError("fraud_block")

    # Expiration check
    expires_at = wi.get("expires_at")
    if expires_at and isinstance(expires_at, datetime):
        # Existing wallet items may store naive datetimes; treat as UTC
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now:
            await db.game_redemptions.insert_one(
                {**audit_base, "status": "expired"})
            # Also flip wallet + winner to expired for cleanup
            await db.user_wallet_items.update_one(
                {"_id": wi["_id"]},
                {"$set": {"status": "expired"}})
            await db.game_winners.update_one(
                {"winner_id": winner["winner_id"]},
                {"$set": {"status": "expired", "updated_at": now}})
            raise ValueError("expired")

    # Business id match (when supplied)
    if business_id:
        campaign = await db.game_campaigns.find_one(
            {"campaign_id": winner["game_campaign_id"]})
        owning = (campaign or {}).get("business_id")
        if owning and owning != business_id:
            await db.game_redemptions.insert_one(
                {**audit_base, "status": "staff_rejected",
                  "staff_note": "business_mismatch"})
            raise ValueError("business_mismatch")

    # Insert the SUCCESS audit row — UNIQUE constraint on redemption_code
    # is the source of truth for "already redeemed by another scan".
    try:
        await db.game_redemptions.insert_one(
            {**audit_base, "status": "success"})
    except DuplicateKeyError:
        raise ValueError("already_redeemed")

    # Flip winner + wallet
    await db.game_winners.update_one(
        {"winner_id": winner["winner_id"]},
        {"$set": {"status": "redeemed",
                       "redeemed_at": now,
                       "updated_at": now}})
    await db.user_wallet_items.update_one(
        {"_id": wi["_id"]},
        {"$set": {"status": "redeemed",
                       "redeemed_at": now,
                       "redeemed_by_actor": staff_user_id}})

    return {
        "redemption_id": audit_base["redemption_id"],
        "status": "success",
        "winner": {
            "winner_id": winner["winner_id"],
            "user_id": winner["user_id"],
            "prize_title": (winner.get("prize_snapshot_json") or {}).get("title"),
            "prize_value": (winner.get("prize_snapshot_json") or {}).get("value_amount"),
            "won_at": winner["won_at"],
        },
    }


# =====================================================================
# List helpers (used by routes)
# =====================================================================
async def list_user_winners(db, user_id: str, *,
                                              status: Optional[str] = None,
                                              limit: int = 25,
                                              cursor: Optional[str] = None) -> dict:
    q: dict = {"user_id": user_id}
    if status:
        q["status"] = status
    if cursor:
        q["winner_id"] = {"$lt": cursor}
    rows = await db.game_winners.find(q).sort(
        "winner_id", -1).limit(limit + 1).to_list(limit + 1)
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1]["winner_id"]
        rows = rows[:limit]
    return {"items": [_view(w) for w in rows],
              "next_cursor": next_cursor,
              "limit": limit}


async def list_campaign_winners(db, campaign_id: str, *,
                                                      status: Optional[str] = None,
                                                      limit: int = 50,
                                                      cursor: Optional[str] = None) -> dict:
    q: dict = {"game_campaign_id": campaign_id}
    if status:
        q["status"] = status
    if cursor:
        q["winner_id"] = {"$lt": cursor}
    rows = await db.game_winners.find(q).sort(
        "winner_id", -1).limit(limit + 1).to_list(limit + 1)
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1]["winner_id"]
        rows = rows[:limit]
    return {"items": [_view(w) for w in rows],
              "next_cursor": next_cursor,
              "limit": limit}


async def list_admin_winners(db, *,
                                              game_campaign_id: Optional[str] = None,
                                              status: Optional[str] = None,
                                              limit: int = 50,
                                              cursor: Optional[str] = None) -> dict:
    q: dict = {}
    if game_campaign_id:
        q["game_campaign_id"] = game_campaign_id
    if status:
        q["status"] = status
    if cursor:
        q["winner_id"] = {"$lt": cursor}
    rows = await db.game_winners.find(q).sort(
        "winner_id", -1).limit(limit + 1).to_list(limit + 1)
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1]["winner_id"]
        rows = rows[:limit]
    return {"items": [_view(w) for w in rows],
              "next_cursor": next_cursor,
              "limit": limit}


async def list_admin_redemptions(db, *,
                                                      business_id: Optional[str] = None,
                                                      status: Optional[str] = None,
                                                      limit: int = 50,
                                                      cursor: Optional[str] = None) -> dict:
    q: dict = {}
    if business_id:
        q["business_id"] = business_id
    if status:
        q["status"] = status
    if cursor:
        q["redemption_id"] = {"$lt": cursor}
    rows = await db.game_redemptions.find(q).sort(
        "redemption_id", -1).limit(limit + 1).to_list(limit + 1)
    next_cursor = None
    if len(rows) > limit:
        next_cursor = rows[limit - 1]["redemption_id"]
        rows = rows[:limit]
    return {"items": [_redemption_view(r) for r in rows],
              "next_cursor": next_cursor,
              "limit": limit}


def _view(w: dict) -> dict:
    if not w:
        return {}
    return {
        "winner_id": w.get("winner_id"),
        "game_campaign_id": w.get("game_campaign_id"),
        "game_session_id": w.get("game_session_id"),
        "user_id": w.get("user_id"),
        "prize_id": w.get("prize_id"),
        "prize_snapshot": w.get("prize_snapshot_json"),
        "wallet_item_id": w.get("wallet_item_id"),
        "won_at": w.get("won_at"),
        "status": w.get("status"),
        "voided_reason": w.get("voided_reason"),
    }


def _redemption_view(r: dict) -> dict:
    if not r:
        return {}
    return {
        "redemption_id": r.get("redemption_id"),
        "winner_id": r.get("winner_id"),
        "wallet_item_id": r.get("wallet_item_id"),
        "business_id": r.get("business_id"),
        "staff_user_id": r.get("staff_user_id"),
        "redeemed_at": r.get("redeemed_at"),
        "status": r.get("status"),
        "staff_note": r.get("staff_note"),
        "geo_lat": r.get("geo_lat"),
        "geo_lng": r.get("geo_lng"),
    }
