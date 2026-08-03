"""Phase 23 Session 1.5 — backfill game_redemptions from existing data.

The existing `redemption_audit_log` collection (176 rows per audit) is
*ad-pod*-scoped — `partner_token_id` + `qr_token_prefix` schema, NOT
games_v2-scoped.  So this script does NOT read from `redemption_audit_log`;
instead it walks `user_wallet_items` where `redeemed_at` is set + source
is `game_win`, and reconstructs game_redemptions rows.

Each existing wallet redemption becomes one `game_redemptions` row with
status='success' and `redeemed_by_staff_id = wallet_item.redeemed_by_actor`.
Idempotent — keyed on `wallet_item_id`.

Run manually via:
    python /app/backend/scripts/backfill_game_redemptions_from_audit_log.py
Or via admin endpoint:
    POST /api/games_v2/admin/backfill/redemptions
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str, length: int = 14) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:length]}"


async def backfill(db) -> dict:
    summary = {"walked": 0, "migrated": 0,
                  "skipped_already_migrated": 0,
                  "missing_winner_row": 0,
                  "missing_qr_token": 0,
                  "duplicate_code_skipped": 0,
                  "errors": 0}

    cursor = db.user_wallet_items.find(
        {"source": "game_win", "redeemed_at": {"$ne": None}})
    async for wi in cursor:
        summary["walked"] += 1
        try:
            wallet_id = wi.get("_id") or wi.get("wallet_item_id")
            if not wi.get("qr_token"):
                # No QR was generated — staff redemption was likely
                # promo_code or in_app_wallet; we can still record it,
                # but UNIQUE on redemption_code requires SOMETHING.
                # Fall back to wallet_id as the code.
                code = wallet_id
                summary["missing_qr_token"] += 1
            else:
                code = wi["qr_token"]

            # Idempotency: any row already pointing at this wallet_item?
            existing = await db.game_redemptions.find_one(
                {"wallet_item_id": wallet_id})
            if existing:
                summary["skipped_already_migrated"] += 1
                continue

            # Find the linked winner (created by the winners backfill).
            winner = await db.game_winners.find_one(
                {"wallet_item_id": wallet_id})
            if not winner:
                summary["missing_winner_row"] += 1
                continue

            campaign = await db.game_campaigns.find_one(
                {"campaign_id": winner["game_campaign_id"]})
            business_id = (campaign or {}).get("business_id")

            rid = _new_id("rdmp")
            row = {
                "_id": rid,
                "redemption_id": rid,
                "winner_id": winner["winner_id"],
                "wallet_item_id": wallet_id,
                "business_id": business_id,
                "redemption_code": code,
                "staff_user_id": wi.get("redeemed_by_actor"),
                "staff_note": None,
                "geo_lat": None,
                "geo_lng": None,
                "client_metadata_json": {"_backfilled": True},
                "redeemed_at": wi.get("redeemed_at") or _now(),
                "status": "success",
                "created_at": _now(),
            }
            try:
                await db.game_redemptions.insert_one(row)
                summary["migrated"] += 1
                # Flip winner.status=redeemed if not already
                if winner.get("status") != "redeemed":
                    await db.game_winners.update_one(
                        {"winner_id": winner["winner_id"]},
                        {"$set": {"status": "redeemed",
                                       "redeemed_at": wi["redeemed_at"],
                                       "updated_at": _now()}})
            except DuplicateKeyError:
                summary["duplicate_code_skipped"] += 1
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
