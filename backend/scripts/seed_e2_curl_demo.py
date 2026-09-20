"""Sub-Phase E2 — seed a synthetic "entries-closed" demo campaign.

Creates a Predict & Win campaign with `lock_time = now + 90 seconds`
so the tester can prove the `entries_closed` error path on /enter
without waiting hours.

Idempotent: re-running this script reuses the same campaign_id
(`pwc_e2_curl_demo_closed`) by looking up the canonical title.

Outputs the campaign_id + key timings on stdout — pipe into the
curl proof harness.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

CANONICAL_TITLE = "E2 Curl Demo: Closed-Picks Path"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


async def main() -> None:
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "bigfm")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # Reuse the existing default compliance row (UAE General Default).
    compliance = await db.prediction_compliance_settings.find_one(
        {"is_default": True, "active": True}
    )
    if not compliance:
        print("ERROR: no default compliance row found — seed E1 first.",
              file=sys.stderr)
        sys.exit(1)
    settings_id = compliance["settings_id"]

    # Lookup an admin for created_by.
    admin = await db.users.find_one({"email": "admin@bigfm.dubai"})
    if not admin:
        print("ERROR: admin user not found.", file=sys.stderr)
        sys.exit(1)

    now = _now()
    existing = await db.predict_win_campaigns.find_one({"title": CANONICAL_TITLE})

    # Always refresh times so the campaign is genuinely "live with imminent
    # lock" — even on re-runs.
    start_time = now - timedelta(seconds=5)
    lock_time = now + timedelta(seconds=90)
    resolve_by = now + timedelta(hours=24)

    if existing:
        cid = existing["campaign_id"]
        await db.predict_win_campaigns.update_one(
            {"campaign_id": cid},
            {"$set": {
                "start_time": start_time,
                "lock_time": lock_time,
                "resolve_by": resolve_by,
                "approval_status": "approved",
                "approved_by": admin["user_id"],
                "approved_at": now,
                "status": "live",
                "updated_at": now,
                "deleted_at": None,
            }},
        )
    else:
        cid = _new_id("pwc")
        await db.predict_win_campaigns.insert_one({
            "_id": cid,
            "campaign_id": cid,
            "title": CANONICAL_TITLE,
            "description": "Synthetic E2 demo for the entries-closed path.",
            "event_type": "club_event",
            "event_label": "FUUSIC QA Demo",
            "category": "demo",
            "city": "Dubai",
            "region": "AE",
            "language": "en",
            "cover_image_url": None,
            "question": {
                "prompt": "Which option will win this demo prediction?",
                "answer_options": [
                    {"option_id": "opt_1", "label": "Option A", "kind": "multiple_choice"},
                    {"option_id": "opt_2", "label": "Option B", "kind": "multiple_choice"},
                ],
            },
            "start_time": start_time,
            "lock_time": lock_time,
            "resolve_by": resolve_by,
            "winner_rules_json": {
                "scoring": "winner_takes_all",
                "max_winners": 1,
                "tiebreaker": "first_to_pick",
                "selection_rule": "first_n_correct",
            },
            "data_provider_id": None,
            "compliance_settings_id": settings_id,
            "approval_status": "approved",
            "approved_by": admin["user_id"],
            "approved_at": now,
            "rejected_by": None,
            "rejected_at": None,
            "approval_reason": None,
            "status": "live",
            "created_by": admin["user_id"],
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        })
    # Ensure a single prize.
    p = await db.predict_win_prizes.find_one(
        {"campaign_id": cid, "active": True})
    if not p:
        pid = _new_id("pwp")
        await db.predict_win_prizes.insert_one({
            "_id": pid,
            "prize_id": pid,
            "campaign_id": cid,
            "rank": 1,
            "title": "QA Demo Reward",
            "description": "Synthetic prize — proof that the closed-picks path is reachable.",
            "prize_kind": "points",
            "value_amount": 50,
            "value_currency": "BC",
            "image_url": None,
            "inventory_total": 5,
            "inventory_remaining": 5,
            "active": True,
            "created_at": now,
            "updated_at": now,
        })

    print(f"campaign_id={cid}")
    print(f"lock_time={lock_time.isoformat()}")
    print(f"seconds_to_lock={int((lock_time - now).total_seconds())}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
