"""Phase 8c — Prize inventory ledger reconciliation.

The 8a inventory_ledger collection records every award/revoke event with
`inventory_after` snapshots.  This module computes the expected
`inventory_remaining` per prize from the ledger and compares it with the
authoritative value stored on `game_prizes`, then optionally repairs
drift with a clearly-labelled audit row.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from services.games_v2 import _new_id, _now

logger = logging.getLogger("bigfm.gameinventory")

DAILY_SCAN_INTERVAL_SECONDS = 86400


async def ensure_inventory_indexes(db) -> None:
    await db.game_inventory_ledger.create_index(
        [("prize_id", 1), ("created_at", -1)])
    await db.game_inventory_ledger.create_index(
        [("campaign_id", 1), ("created_at", -1)])
    await db.game_inventory_ledger.create_index([("action", 1)])
    await db.inventory_reconcile_alerts.create_index(
        [("ts", -1)])
    await db.inventory_reconcile_alerts.create_index(
        [("campaign_id", 1), ("resolved", 1)])


async def reconcile_campaign(db, campaign_id: str) -> dict:
    prizes = await db.game_prizes.find(
        {"campaign_id": campaign_id}).to_list(50)
    discrepancies: list[dict] = []
    for p in prizes:
        ledger_total = await _ledger_expected(db, p)
        actual = int(p.get("inventory_remaining") or 0)
        if ledger_total != actual:
            discrepancies.append({
                "prize_id": p["prize_id"],
                "title": p.get("title"),
                "inventory_total": int(p.get("inventory_total") or 0),
                "inventory_remaining_stored": actual,
                "inventory_remaining_expected": ledger_total,
                "delta": actual - ledger_total,
            })
    return {
        "campaign_id": campaign_id,
        "checked_prizes": len(prizes),
        "discrepancies": discrepancies,
        "clean": len(discrepancies) == 0,
        "checked_at": _now().isoformat(),
    }


async def _ledger_expected(db, prize: dict) -> int:
    """expected_remaining = inventory_total - awards + revokes"""
    pid = prize["prize_id"]
    total = int(prize.get("inventory_total") or 0)
    awards = await db.game_inventory_ledger.count_documents(
        {"prize_id": pid, "action": "award"})
    revokes = await db.game_inventory_ledger.count_documents(
        {"prize_id": pid, "action": "revoke"})
    corrections = 0
    async for r in db.game_inventory_ledger.find(
            {"prize_id": pid, "action": "admin_correction"}):
        # admin corrections snapshot the post-correction remaining
        corrections = int(r.get("inventory_after",
                                       total - awards + revokes))
    expected = total - awards + revokes
    if corrections:
        expected = corrections
    return max(0, expected)


async def force_correct(db, campaign_id: str, actor_user_id: str) -> dict:
    report = await reconcile_campaign(db, campaign_id)
    if not report["discrepancies"]:
        return {"campaign_id": campaign_id, "corrected": 0, "no_op": True}
    corrected = []
    for d in report["discrepancies"]:
        expected = d["inventory_remaining_expected"]
        await db.game_prizes.update_one(
            {"prize_id": d["prize_id"]},
            {"$set": {"inventory_remaining": expected}})
        await db.game_inventory_ledger.insert_one({
            "_id": _new_id("ilg"),
            "prize_id": d["prize_id"],
            "campaign_id": campaign_id,
            "action": "admin_correction",
            "reason": "admin_correction",
            "delta": -d["delta"],
            "inventory_after": expected,
            "created_at": _now(),
            "actor_user_id": actor_user_id,
        })
        corrected.append({"prize_id": d["prize_id"],
                              "from": d["inventory_remaining_stored"],
                              "to": expected})
    # Resolve any existing alert
    await db.inventory_reconcile_alerts.update_many(
        {"campaign_id": campaign_id, "resolved": False},
        {"$set": {"resolved": True,
                   "resolved_at": _now(),
                   "resolved_by": actor_user_id}})
    return {"campaign_id": campaign_id,
              "corrected": len(corrected),
              "items": corrected}


async def daily_scan_once(db) -> dict:
    """Iterate active campaigns once and surface alerts for any
    discrepancies."""
    n_alerts = 0
    async for c in db.game_campaigns.find(
            {"status": {"$in": ["active", "paused"]}},
            {"campaign_id": 1}):
        rep = await reconcile_campaign(db, c["campaign_id"])
        if rep["discrepancies"]:
            n_alerts += 1
            await db.inventory_reconcile_alerts.update_one(
                {"campaign_id": c["campaign_id"], "resolved": False},
                {"$set": {
                    "campaign_id": c["campaign_id"],
                    "discrepancies": rep["discrepancies"],
                    "ts": _now(),
                    "resolved": False,
                }},
                upsert=True,
            )
    return {"alerts_generated": n_alerts, "scanned_at": _now().isoformat()}


async def list_active_alerts(db) -> list[dict]:
    out = []
    async for r in (db.inventory_reconcile_alerts
                        .find({"resolved": False}).sort("ts", -1).limit(100)):
        out.append({
            "campaign_id": r["campaign_id"],
            "ts": r["ts"].isoformat() if r.get("ts") else None,
            "discrepancies": r.get("discrepancies", []),
        })
    return out
