"""Phase F-2 — Legacy `users.bigcoin_balance` reconciliation script.

This is the ONE-TIME freeze: for every user, write the current ledger
sum (from PointsService) into `users.bigcoin_balance` so the legacy
field is correct at the flip moment.  After this runs, the dual-write
mirror is disabled and `bigcoin_balance` becomes a frozen breadcrumb
(no future writes).  All future reads go through PointsService.

Usage:
    python3 backend/scripts/reconcile_legacy_balance_field.py
    python3 backend/scripts/reconcile_legacy_balance_field.py --dry-run
    python3 backend/scripts/reconcile_legacy_balance_field.py --user demo@bigfm.dubai
"""
from __future__ import annotations
import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from dotenv import load_dotenv
load_dotenv(BASE / ".env")

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("bigfm.reconcile_balance")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--user", help="Email or user_id; runs for ONE user.")
    args = ap.parse_args()

    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    from services.points_service import PointsService
    svc = PointsService(db)

    q: dict = {}
    if args.user:
        q = {"$or": [{"email": args.user.lower()},
                              {"user_id": args.user}]}

    scanned = updated = matched = errors = 0
    diffs_sample: list[dict] = []
    async for u in db.users.find(q, {"_id": 0, "user_id": 1,
                                                                    "email": 1, "bigcoin_balance": 1}):
        scanned += 1
        uid = u.get("user_id")
        if not uid:
            continue
        try:
            # PointsService.get_balance returns an int directly.
            ledger = int(await svc.get_balance(uid) or 0)
        except Exception as e:
            errors += 1
            log.warning("[reconcile] get_balance failed u=%s err=%s", uid, e)
            continue
        legacy = int(u.get("bigcoin_balance") or 0)
        if ledger == legacy:
            matched += 1
            continue
        if len(diffs_sample) < 10:
            diffs_sample.append({"user_id": uid, "email": u.get("email"),
                                                    "legacy": legacy, "ledger": ledger,
                                                    "diff": ledger - legacy})
        if not args.dry_run:
            await db.users.update_one(
                {"user_id": uid},
                {"$set": {"bigcoin_balance": ledger,
                              "bigcoin_balance_reconciled_at":
                                  __import__('datetime').datetime.now(
                                      __import__('datetime').timezone.utc),
                              "bigcoin_balance_reconciled_to": ledger}})
            updated += 1

    print(f"[reconcile] scanned={scanned} matched={matched} "
                f"updated={updated} errors={errors} "
                f"dry_run={args.dry_run}")
    if diffs_sample:
        print("[reconcile] sample diffs:")
        for d in diffs_sample:
            print(f"  {d}")


if __name__ == "__main__":
    asyncio.run(main())
