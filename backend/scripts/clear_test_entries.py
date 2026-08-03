"""Sub-Phase E2 — clear Predict & Win entries for a user/campaign.

Lets QA reset state between repeated modal-verification runs without
needing the admin API.  Usage examples:

    # Wipe ALL entries for a user (any campaign):
    python3 backend/scripts/clear_test_entries.py --user predictest@bigfm.dubai

    # Wipe one specific entry pair:
    python3 backend/scripts/clear_test_entries.py \
        --user demo@bigfm.dubai --campaign pwc_6f9af6f5ed6840

The script always operates on `predict_win_entries` only.  It will NOT
touch `predict_win_awards` or `predict_win_resolutions` (those are
audit records that must not be retroactively erased).
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient


async def main(email: str, campaign_id: str | None) -> int:
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "bigfm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    user = await db.users.find_one({"email": email})
    if not user:
        print(f"ERROR: no user with email={email}", file=sys.stderr)
        return 2

    q: dict = {"user_id": user["user_id"]}
    if campaign_id:
        q["campaign_id"] = campaign_id

    # List before deleting so the operator sees what's being touched.
    cur = db.predict_win_entries.find(q, sort=[("submitted_at", -1)])
    rows = [r async for r in cur]
    if not rows:
        print(f"no entries to clear (user={email} campaign={campaign_id or 'ANY'})")
        return 0
    print(f"about to clear {len(rows)} entries:")
    for r in rows:
        print(f"  - entry_id={r['entry_id']}  campaign={r['campaign_id']}  "
              f"status={r['status']}  pick={r['picked_option_id']}")

    deleted = await db.predict_win_entries.delete_many(q)
    print(f"deleted={deleted.deleted_count}")

    # If any of the deleted entries pointed at award rows, surface that
    # to the operator as a heads-up (we deliberately do NOT delete awards).
    if not campaign_id:
        award_count = 0
        for r in rows:
            n = await db.predict_win_awards.count_documents({
                "entry_id": r["entry_id"]})
            award_count += n
        if award_count:
            print(f"NOTE: {award_count} predict_win_awards rows reference "
                  f"these entries and are preserved (audit-only). Listener's "
                  f"award history will still surface via /my-wins.")
    client.close()
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Clear Predict & Win entries for a user.")
    p.add_argument("--user", required=True,
                                  help="User email (e.g. predictest@bigfm.dubai).")
    p.add_argument("--campaign", default=None,
                                  help="Optional campaign_id; defaults to ALL of the user's entries.")
    args = p.parse_args()
    code = asyncio.run(main(args.user, args.campaign))
    sys.exit(code)
