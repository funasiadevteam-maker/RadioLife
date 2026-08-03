"""Phase 23 Session 1.5 — backfill game_winners from existing game_sessions.

Walks every `game_sessions` row where `result='win'` (or the legacy typo
`result='won'`) and inserts a `game_winners` row.  Idempotent — second run
reports `migrated: 0`.

The row's `prize_snapshot_json` is rebuilt from the CURRENT state of the
linked prize.  This is acceptable for backfill because pre-Phase 23 winners
predate the snapshot semantics; future post-snapshot edits will be guarded.

Run manually via:
    python /app/backend/scripts/backfill_game_winners_from_sessions.py
Or via admin endpoint:
    POST /api/games_v2/admin/backfill/winners
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str, length: int = 14) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:length]}"


def _prize_snapshot(prize: dict) -> dict:
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
        "_backfilled": True,
    }


async def backfill(db) -> dict:
    summary = {"walked": 0, "migrated": 0, "skipped_already_migrated": 0,
                  "missing_prize_row": 0, "missing_session_data": 0,
                  "errors": 0}

    # also normalize legacy `result='won'` to `result='win'` for clarity
    typo_res = await db.game_sessions.update_many(
        {"result": "won"}, {"$set": {"result": "win"}})
    summary["legacy_won_typo_fixed"] = typo_res.modified_count

    cursor = db.game_sessions.find({"result": "win"})
    async for sess in cursor:
        summary["walked"] += 1
        try:
            session_id = sess.get("session_id") or sess.get("_id")
            if not session_id or not sess.get("user_id") \
                    or not sess.get("campaign_id"):
                summary["missing_session_data"] += 1
                continue

            existing = await db.game_winners.find_one(
                {"game_session_id": session_id})
            if existing:
                summary["skipped_already_migrated"] += 1
                continue

            prize_id = sess.get("prize_id")
            if not prize_id:
                summary["missing_prize_row"] += 1
                continue
            prize = await db.game_prizes.find_one({"prize_id": prize_id})
            if not prize:
                summary["missing_prize_row"] += 1
                continue

            # Link wallet item if one already exists for this session
            wallet_item = None
            if sess.get("wallet_item_id"):
                wallet_item = await db.user_wallet_items.find_one(
                    {"_id": sess["wallet_item_id"]})
            if not wallet_item:
                # Fallback: search by (user_id, session_id)
                wallet_item = await db.user_wallet_items.find_one({
                    "user_id": sess["user_id"],
                    "session_id": session_id,
                    "source": "game_win",
                })

            wallet_item_id: str | None = None
            if wallet_item:
                wallet_item_id = wallet_item.get("_id") \
                                          or wallet_item.get("wallet_item_id")

            redeemed = bool(wallet_item and wallet_item.get("redeemed_at"))
            status = ("redeemed" if redeemed
                          else "in_wallet" if wallet_item_id
                          else "pending_wallet_save")

            wid = _new_id("win")
            now = _now()
            await db.game_winners.insert_one({
                "_id": wid,
                "winner_id": wid,
                "game_campaign_id": sess["campaign_id"],
                "game_session_id": session_id,
                "user_id": sess["user_id"],
                "prize_id": prize_id,
                "prize_snapshot_json": _prize_snapshot(prize),
                "wallet_item_id": wallet_item_id,
                "won_at": sess.get("completed_at") or now,
                "status": status,
                "voided_reason": None,
                "created_at": now,
                "updated_at": now,
                "source": "backfill",
            })
            summary["migrated"] += 1
        except Exception as exc:  # noqa: BLE001
            summary["errors"] += 1
            summary.setdefault("error_samples", []).append(str(exc)[:120])
    return summary


async def _main():
    sys.path.insert(0, "/app/backend")
    try:
        from dotenv import load_dotenv
        load_dotenv("/app/backend/.env")
    except Exception:
        pass
    from motor.motor_asyncio import AsyncIOMotorClient
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    summary = await backfill(db)
    print(summary)


if __name__ == "__main__":
    asyncio.run(_main())
