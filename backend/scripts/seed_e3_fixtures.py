"""Sub-Phase E3 — seed business-campaign fixtures for e2e + tester.

Creates (idempotent):
  • A DRAFT business campaign on the verified `s3a-smoke-karak` station.
  • A LIVE business campaign on the same station with lock_time = now+10m
      and two seeded entries so a "/resolve" smoke test can exercise the
      award pipeline against real entry rows.
  • A paired TV display for the live campaign so the kiosk URL is
      reachable for screenshots.

Run:
    python3 backend/scripts/seed_e3_fixtures.py

Prints campaign_ids + the TV pairing code for the tester to consume.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

STATION_SLUG = "s3a-smoke-karak"
DRAFT_TITLE = "E3 Draft: Tonight's Karaoke Pick"
LIVE_TITLE  = "E3 Live: Friday Karaoke Champion"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:14]}"


def _pairing_code() -> str:
    a = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    r = "".join(secrets.choice(a) for _ in range(8))
    return f"{r[:4]}-{r[4:]}"


async def _upsert_campaign(db, *, title: str, owner_user_id: str,
                                                station_slug: str, compliance_id: str,
                                                provider_id: str, lock_offset_min: int,
                                                approval_status: str, lifecycle: str) -> str:
    existing = await db.predict_win_campaigns.find_one(
        {"title": title, "business_station_slug": station_slug})
    now = _now()
    start = now - timedelta(minutes=5)
    lock = now + timedelta(minutes=lock_offset_min)
    resolve_by = now + timedelta(hours=24)
    if existing:
        cid = existing["campaign_id"]
        await db.predict_win_campaigns.update_one(
            {"campaign_id": cid},
            {"$set": {
                "start_time": start, "lock_time": lock, "resolve_by": resolve_by,
                "approval_status": approval_status, "status": lifecycle,
                "approved_by": owner_user_id if approval_status == "approved" else None,
                "approved_at": now if approval_status == "approved" else None,
                "updated_at": now, "deleted_at": None,
            }})
    else:
        cid = _new_id("pwc")
        await db.predict_win_campaigns.insert_one({
            "_id": cid, "campaign_id": cid,
            "title": title,
            "description": "Seeded for E3 tester — venue prediction smoke.",
            "event_type": "restaurant_bar",
            "event_label": "Karaoke Night", "category": "venue",
            "city": "Dubai", "region": "AE", "language": "en",
            "cover_image_url": None,
            "question": {
                "prompt": "Who's going to win tonight's karaoke?",
                "answer_options": [
                    {"option_id": "opt_1", "label": "Alex", "kind": "multiple_choice"},
                    {"option_id": "opt_2", "label": "Sara", "kind": "multiple_choice"},
                    {"option_id": "opt_3", "label": "Raj",   "kind": "multiple_choice"},
                ],
            },
            "start_time": start, "lock_time": lock, "resolve_by": resolve_by,
            "winner_rules_json": {
                "scoring": "winner_takes_all", "max_winners": 1,
                "tiebreaker": "first_to_pick",
                "selection_rule": "first_n_correct",
            },
            "data_provider_id": provider_id,
            "compliance_settings_id": compliance_id,
            "creator_type": "business",
            "business_station_slug": station_slug,
            "business_owner_user_id": owner_user_id,
            "checkin_required": True,
            "approval_status": approval_status,
            "approved_by": owner_user_id if approval_status == "approved" else None,
            "approved_at": now if approval_status == "approved" else None,
            "rejected_by": None, "rejected_at": None, "approval_reason": None,
            "status": lifecycle,
            "created_by": owner_user_id,
            "created_at": now, "updated_at": now, "deleted_at": None,
        })

    # Ensure a prize.
    prize = await db.predict_win_prizes.find_one(
        {"campaign_id": cid, "active": True})
    if not prize:
        pid = _new_id("pwp")
        await db.predict_win_prizes.insert_one({
            "_id": pid, "prize_id": pid, "campaign_id": cid,
            "rank": 1, "title": "200 BigCoin reward",
            "description": "Auto-credited to winners' FUUSIC wallet.",
            "prize_kind": "bigcoin", "value_amount": 200,
            "value_currency": "BC", "image_url": None,
            "inventory_total": 5, "inventory_remaining": 5,
            "active": True, "created_at": now, "updated_at": now,
        })
    return cid


async def _seed_entries(db, cid: str, demo_uid: str, test_uid: str) -> None:
    """Add two entries (different picks) so /resolve has something to evaluate.

    Idempotent re-set: if entries already exist for this campaign / user,
    reset their status back to `submitted` (clears any winner / loser
    flag from a prior resolve test) so the seed produces the same
    starting state on every run.
    """
    now = _now()
    for uid, opt in [(demo_uid, "opt_1"), (test_uid, "opt_2")]:
        existing = await db.predict_win_entries.find_one(
            {"campaign_id": cid, "user_id": uid})
        if existing:
            await db.predict_win_entries.update_one(
                {"campaign_id": cid, "user_id": uid},
                {"$set": {
                    "picked_option_id": opt,
                    "status": "submitted",
                    "evaluated_at": None,
                    "submitted_at": now.isoformat(),
                }})
            continue
        entry_id = _new_id("pwe")
        await db.predict_win_entries.insert_one({
            "_id": f"pwe_{cid}_{uid}",
            "entry_id": entry_id,
            "campaign_id": cid,
            "user_id": uid,
            "picked_option_id": opt,
            "confidence": 7,
            "submitted_at": now.isoformat(),
            "status": "submitted",
            "evaluated_at": None,
            "ip_geo_city": "Dubai", "ip_geo_country": "AE",
            "source_context": "app",
            "venue_checkin_id": None,
        })


async def _reset_resolution_state(db, cid: str) -> dict:
    """Wipe prior /resolve side-effects on the LIVE fixture campaign so
    re-running the seed restores a fully-enterable state.  Also clears
    other listeners' entries (predictest etc.) that may have been
    submitted during the E3 smoke run, AND refunds the BigCoin balance
    of any winner so the demo/test bigcoin_balance is stable across
    re-runs.

    Steps:
      1. Find every award row for this campaign.  For each, decrement
          the winner user's `bigcoin_balance` + `bigcoin_lifetime_earned`
          by the prize value so the seed is balance-neutral.
      2. Delete `predict_win_awards` rows for this campaign.
      3. Restore prize inventory_remaining to inventory_total.
      4. Delete the `predict_win_resolutions` row for this campaign.
      5. Delete entries belonging to NON-fixture users (anyone other
          than demo / test) so the seed leaves exactly the 2 canonical
          fixture entries in place.

    Returns a tiny dict of counts for the seed log line.
    """
    counts = {"awards_reverted": 0, "awards_deleted": 0,
                      "resolutions_deleted": 0, "non_fixture_entries_deleted": 0,
                      "prize_inventory_restored": 0}
    awards = [a async for a in db.predict_win_awards.find({"campaign_id": cid})]
    for a in awards:
        prize = await db.predict_win_prizes.find_one({"prize_id": a["prize_id"]})
        if prize and prize.get("prize_kind") in {"bigcoin", "points"}:
            try:
                val = float(prize.get("value_amount") or 0)
            except (TypeError, ValueError):
                val = 0.0
            if val:
                await db.users.update_one(
                    {"user_id": a["winner_user_id"]},
                    {"$inc": {
                        "bigcoin_balance": -val,
                        "bigcoin_lifetime_earned": -val,
                    }})
                counts["awards_reverted"] += 1
    if awards:
        r = await db.predict_win_awards.delete_many({"campaign_id": cid})
        counts["awards_deleted"] = r.deleted_count
    inv_res = await db.predict_win_prizes.update_many(
        {"campaign_id": cid, "active": True},
        [{"$set": {"inventory_remaining": "$inventory_total"}}])
    counts["prize_inventory_restored"] = inv_res.modified_count
    r2 = await db.predict_win_resolutions.delete_many({"campaign_id": cid})
    counts["resolutions_deleted"] = r2.deleted_count
    # Find demo + test user_ids to whitelist.
    demo = await db.users.find_one({"email": "demo@bigfm.dubai"})
    test = await db.users.find_one({"email": "test@bigfm.dubai"})
    fixture_uids = {u["user_id"] for u in (demo, test) if u}
    r3 = await db.predict_win_entries.delete_many({
        "campaign_id": cid,
        "user_id": {"$nin": list(fixture_uids)},
    })
    counts["non_fixture_entries_deleted"] = r3.deleted_count
    return counts


async def _ensure_tv_pairing(db, cid: str, owner_uid: str, slug: str) -> str:
    existing = await db.predict_win_tv_displays.find_one(
        {"campaign_id": cid, "active": True})
    if existing:
        return existing["pairing_code"]
    now = _now()
    pairing_code = _pairing_code()
    display_id = _new_id("pwt")
    await db.predict_win_tv_displays.insert_one({
        "_id": display_id, "display_id": display_id,
        "campaign_id": cid,
        "business_station_slug": slug,
        "business_owner_user_id": owner_uid,
        "pairing_code": pairing_code,
        "pairing_issued_at": now,
        "pairing_expires_at": now + timedelta(minutes=15),
        "label": "Seeded floor TV",
        "active": True,
        "last_seen_at": None, "poll_count": 0,
        "created_at": now, "updated_at": now,
    })
    return pairing_code


async def main() -> None:
    mongo = AsyncIOMotorClient(
        os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = mongo[os.environ.get("DB_NAME", "bigfm")]

    station = await db.community_radio_stations.find_one({"slug": STATION_SLUG})
    if not station:
        print(f"ERROR: station {STATION_SLUG} missing — run Phase 41 S3.A seed first.",
                  file=sys.stderr)
        sys.exit(2)
    owner_uid = station["owner_user_id"]

    compliance = await db.prediction_compliance_settings.find_one(
        {"is_default": True, "active": True})
    if not compliance:
        print("ERROR: default compliance row missing — run E1 seed first.",
                  file=sys.stderr)
        sys.exit(2)

    provider = await db.prediction_data_providers.find_one(
        {"provider_name": "manual"})
    if not provider:
        print("ERROR: manual data provider missing.", file=sys.stderr)
        sys.exit(2)

    demo = await db.users.find_one({"email": "demo@bigfm.dubai"})
    test = await db.users.find_one({"email": "test@bigfm.dubai"})
    if not demo or not test:
        print("ERROR: demo / test fixture users missing.", file=sys.stderr)
        sys.exit(2)

    draft_cid = await _upsert_campaign(
        db, title=DRAFT_TITLE, owner_user_id=owner_uid,
        station_slug=STATION_SLUG, compliance_id=compliance["settings_id"],
        provider_id=provider["provider_id"], lock_offset_min=60,
        approval_status="draft", lifecycle="draft")

    live_cid = await _upsert_campaign(
        db, title=LIVE_TITLE, owner_user_id=owner_uid,
        station_slug=STATION_SLUG, compliance_id=compliance["settings_id"],
        provider_id=provider["provider_id"], lock_offset_min=60,
        approval_status="approved", lifecycle="live")
    # Restore the live fixture to a fully re-runnable state — wipe any
    # prior resolution/awards/non-fixture entries, refund any granted
    # BigCoin, and reset the 2 canonical entries back to `submitted`.
    reset_counts = await _reset_resolution_state(db, live_cid)
    await _seed_entries(db, live_cid, demo["user_id"], test["user_id"])
    pairing_code = await _ensure_tv_pairing(
        db, live_cid, owner_uid, STATION_SLUG)

    print(f"draft_campaign_id={draft_cid}")
    print(f"live_campaign_id={live_cid}")
    print(f"tv_pairing_code={pairing_code}")
    print(f"station_slug={STATION_SLUG}")
    print(f"station_owner_email={station.get('owner_email') or 'test@bigfm.dubai'}")
    print(f"reset_counts={reset_counts}")
    mongo.close()


if __name__ == "__main__":
    asyncio.run(main())
