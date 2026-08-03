"""Phase F-1 — Historical backfill of `bigcoin_transactions` into the
unified `points_ledger`.

Idempotent on `idempotency_key = "legacy_bc:<original_tx_id>"` so the
script is safe to re-run.  Per-user reconciliation row stamped when a
drift is detected between the ledger sum and `users.bigcoin_balance`.

Usage:
    python3 backend/scripts/backfill_points_ledger.py --dry-run
    python3 backend/scripts/backfill_points_ledger.py             # write
    python3 backend/scripts/backfill_points_ledger.py --user user_demo_xxx --dry-run

Output ends with a summary block:
    users_touched=...  ledger_rows_written=...
    parity_ok=...      reconciliation_rows=...   drift_total=...
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from typing import Optional

# Allow running from /app or /app/backend.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


async def _ensure_indexes(db) -> None:
    from services.points_service import ensure_points_indexes, seed_earn_rules
    await ensure_points_indexes(db)
    await seed_earn_rules(db)


async def _backfill_user(db, user_id: str, *, dry_run: bool) -> dict:
    """Returns per-user stats."""
    written = 0
    skipped = 0
    cur = db.bigcoin_transactions.find({"user_id": user_id}).sort("created_at", 1)
    async for tx in cur:
        tx_id = str(tx.get("_id"))
        idem  = f"legacy_bc:{tx_id}"
        existing = await db.points_ledger.find_one({"idempotency_key": idem})
        if existing:
            skipped += 1
            continue
        amount = int(tx.get("amount") or 0)
        if amount == 0:
            continue
        ledger_row = {
            "_id": f"ple_legacy_{tx_id[:18]}",
            "user_id": user_id,
            "source": tx.get("source") or "legacy_unknown",
            "source_id": None,
            "delta": amount,
            "balance_after": int(tx.get("balance_after") or 0),
            "metadata": {
                "legacy_path": "backfill_bigcoin_transactions",
                "legacy_tx_id": tx_id,
                "legacy_type": tx.get("type"),
                "note": tx.get("note"),
                **(tx.get("metadata_json") or {}),
            },
            "idempotency_key": idem,
            "created_at": tx.get("created_at") or datetime.now(timezone.utc),
            "expires_at": None,
        }
        if not dry_run:
            try:
                await db.points_ledger.insert_one(ledger_row)
            except Exception as e:
                # Race / dup — count as skipped, continue.
                msg = str(e)
                if "idempotency_key" not in msg:
                    print(f"  WARN insert failed {tx_id}: {e}", file=sys.stderr)
                skipped += 1
                continue
        written += 1

    # Drift check: ledger sum vs legacy balance.
    pipe = [{"$match": {"user_id": user_id}},
                          {"$group": {"_id": None, "total": {"$sum": "$delta"}}}]
    ledger_sum = 0
    async for d in db.points_ledger.aggregate(pipe):
        ledger_sum = int(d.get("total") or 0)
    u = await db.users.find_one({"user_id": user_id}, {"bigcoin_balance": 1})
    legacy = int((u or {}).get("bigcoin_balance") or 0)
    drift = legacy - ledger_sum

    reconciled = False
    if drift != 0:
        if not dry_run:
            reconciliation_idem = f"legacy_recon:{user_id}"
            existing_recon = await db.points_ledger.find_one(
                {"idempotency_key": reconciliation_idem})
            if not existing_recon:
                try:
                    await db.points_ledger.insert_one({
                        "_id": f"ple_recon_{user_id[-12:]}",
                        "user_id": user_id,
                        "source": "legacy_backfill_reconciliation",
                        "source_id": None,
                        "delta": int(drift),
                        "balance_after": legacy,
                        "metadata": {
                            "legacy_path": "backfill_reconciliation",
                            "ledger_sum_pre_recon": ledger_sum,
                            "legacy_balance": legacy,
                            "drift": drift,
                        },
                        "idempotency_key": reconciliation_idem,
                        "created_at": datetime.now(timezone.utc),
                        "expires_at": None,
                    })
                    reconciled = True
                except Exception as e:
                    msg = str(e)
                    if "idempotency_key" not in msg:
                        print(f"  WARN recon insert {user_id}: {e}", file=sys.stderr)
        else:
            reconciled = True

    return {"user_id": user_id, "written": written, "skipped": skipped,
                      "ledger_sum_pre_recon": ledger_sum, "legacy_balance": legacy,
                      "drift": drift, "reconciliation_added": reconciled}


async def main(args: argparse.Namespace) -> int:
    mongo_url = os.environ["MONGO_URL"]
    db_name   = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    await _ensure_indexes(db)
    print(f"[backfill] dry_run={args.dry_run}  db={db_name}")

    if args.user:
        user_ids = [args.user]
    else:
        user_ids = await db.bigcoin_transactions.distinct("user_id")
    print(f"[backfill] users_to_process={len(user_ids)}")

    total_written = 0
    total_skipped = 0
    total_recon = 0
    parity_ok = 0
    drift_total = 0
    drift_users = []
    for uid in user_ids:
        st = await _backfill_user(db, uid, dry_run=args.dry_run)
        total_written += st["written"]
        total_skipped += st["skipped"]
        if st["reconciliation_added"]:
            total_recon += 1
        if st["drift"] == 0:
            parity_ok += 1
        else:
            drift_total += abs(st["drift"])
            if len(drift_users) < 8:
                drift_users.append({"uid": uid, "drift": st["drift"]})
        if args.verbose:
            print(f"  {uid}: written={st['written']:4d} "
                          f"skipped={st['skipped']:4d} "
                          f"ledger_sum={st['ledger_sum_pre_recon']:6d} "
                          f"legacy={st['legacy_balance']:6d} "
                          f"drift={st['drift']:+5d}")

    print("\n========== Phase F-1 backfill summary ==========")
    print(f"users_touched={len(user_ids)}")
    print(f"ledger_rows_written={total_written}")
    print(f"ledger_rows_skipped_idempotent={total_skipped}")
    print(f"parity_ok={parity_ok}")
    print(f"users_with_drift={len(user_ids) - parity_ok}")
    print(f"reconciliation_rows={total_recon}")
    print(f"drift_total_absolute={drift_total}")
    if drift_users:
        print("sample_drift_users:")
        for d in drift_users:
            print(f"  {d['uid']}: drift={d['drift']}")
    print("================================================")
    client.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                                    help="Report drift without writing rows.")
    ap.add_argument("--user", default=None, type=str,
                                    help="Process a single user_id (for debugging).")
    ap.add_argument("--verbose", action="store_true",
                                    help="Per-user output.")
    args = ap.parse_args()
    sys.exit(asyncio.run(main(args)))
