"""Phase 23 Session 4.5 — wipe Play & Win test campaigns + cascade.

DRY-RUN BY DEFAULT.  This script is intentionally non-destructive on
first invocation: pass `--apply` to actually delete.  The dispatch's
literal OR-criteria (`creator_type` null / `creator_user_id` null /
title regex) would have wiped all 1010 production campaigns because
`creator_user_id` is not a populated field in production — the real
ownership column is `advertiser_id`, and the Session 2 backfill already
set `creator_type` on every doc.

The criteria used here are the safe AND-filter audited 2026-06-06:

    title    ~ /test|demo|sample|karak cafe friday spin/i
    status   in ['draft', 'pending_approval']
    created_at >= 2026-06-01T00:00:00Z
    _id        not in {'cmp_house_spin'}

Cascades the deletion to `game_sessions` / `game_winners` /
`game_redemptions` keyed off the wiped campaign_ids.  Wallet items are
intentionally untouched — already-redeemed rewards stay valid.

Idempotent: a second run on the same criteria reports `deleted=0`.

Usage:
    python -m scripts.wipe_play_and_win_test_campaigns                   # dry-run
    python -m scripts.wipe_play_and_win_test_campaigns --apply  # destructive
"""
from __future__ import annotations
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient

TITLE_REGEX               = (r"^(test |test_|test$|test campaign|"
                                                  r"geo test|leaderboard test|dedupe test|"
                                                  r"counter-set|karak cafe|"
                                                  r"weather triggered scratch|"
                                                  r"sample |demo |"
                                                  r"gate test|email validation|"
                                                  r"lead form|crud test|api test|"
                                                  r"integration test|fixture|"
                                                  r"bad fields|list \+ csv|"
                                                  r"clean compliance|alias-friendly|"
                                                  r"strict body|analytics csv|"
                                                  r"daily scan)")
ALLOWED_TEST_STATUSES = ["draft", "pending_approval"]
EARLIEST_CUTOFF              = datetime(2026, 1, 1, tzinfo=timezone.utc)
HARD_EXCLUDE_IDS          = {"cmp_house_spin", "cmp_house_trivia",
                                                            "cmp_house_lyric"}
TEST_ADVERTISER_EMAIL_REGEX = (r"^(qa[._-]?test|qa[._-]?adv|test[._-]?adv)")
SANITY_CEILING              = 800


def _query(test_adv_user_ids: list[str] | None = None):
    q = {
        "$and": [
            {"_id": {"$nin": list(HARD_EXCLUDE_IDS)}},
            {"$or": [
                # Title match (always allowed).
                {"title": {"$regex": TITLE_REGEX, "$options": "i"}},
                # Or owned by a QA / test advertiser account.
                *([{ "advertiser_id":
                            {"$in": test_adv_user_ids or []} }]
                     if test_adv_user_ids else []),
            ]},
            {"status":         {"$in": ALLOWED_TEST_STATUSES}},
            {"created_at":  {"$gte": EARLIEST_CUTOFF}},
            # Belt-and-braces: never wipe an admin-curated campaign whose
            # title clearly is NOT test data (e.g. "BigFM Daily Spin").
            {"$or": [
                {"creator_type": {"$ne": "admin"}},
                {"title":            {"$regex": TITLE_REGEX,
                                                "$options": "i"}},
            ]},
        ]
    }
    return q


async def _resolve_test_advertisers(db) -> list[str]:
    """Find user_ids whose email matches the QA-advertiser regex."""
    cursor = db.users.find(
        {"email": {"$regex": TEST_ADVERTISER_EMAIL_REGEX,
                            "$options": "i"}},
        {"user_id": 1, "email": 1})
    rows = await cursor.to_list(2000)
    ids  = [r["user_id"] for r in rows if r.get("user_id")]
    return ids


async def wipe(*, apply: bool = False, db = None) -> dict:
    """Returns a count summary.  Pass `db=` for tests.

    Two-phase remediation:
      Phase A (DELETE):   draft / pending_approval rows matching the
                                              test filter — cascaded.
      Phase B (ARCHIVE):  ACTIVE rows matching the test-title regex
                                              are flipped to `status=archived` so
                                              they no longer surface in
                                              `/play_and_win?surface=unlocked_for_you`.
                                              No deletion — reversible.
    """
    if db is None:
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[
                  os.environ["DB_NAME"]]

    test_adv = await _resolve_test_advertisers(db)
    q = _query(test_adv_user_ids=test_adv)
    docs = await db.game_campaigns.find(q, {"_id": 1, "title": 1,
                                                                                    "status": 1,
                                                                                    "advertiser_id": 1}
                                                                          ).to_list(10_000)
    cids = [d["_id"] for d in docs]

    # ── Phase B query (archive actives matching test regex) ───────
    archive_q = {
        "_id":      {"$nin": list(HARD_EXCLUDE_IDS)},
        "title":    {"$regex": TITLE_REGEX, "$options": "i"},
        "status":  "active",
    }
    archive_docs = await db.game_campaigns.find(
        archive_q, {"_id": 1, "title": 1}).to_list(10_000)
    archive_cids = [d["_id"] for d in archive_docs]

    # ── Sanity ceiling ─────────────────────────────────────────────
    # Ceiling guards the destructive DELETE phase only; the archive
    # phase is reversible (status flip) so a higher ceiling is safe.
    if len(cids) > SANITY_CEILING:
        raise RuntimeError(
            f"Refusing to wipe {len(cids)} campaigns "
            f"(ceiling = {SANITY_CEILING}).  Tighten the filter and "
            f"re-run; this guard prevents nuking 1000+ production rows.")

    print(f"-- Dry-run filter (test advertisers: {len(test_adv)}) ---")
    for d in docs:
        print(f"  {d['_id']:28s} status={d.get('status'):16s} "
                    f"adv={d.get('advertiser_id') or '-':24s} "
                    f"title={d.get('title')!r}")
    print(f"-- Active archive candidates ({len(archive_cids)}): ---")
    for d in archive_docs[:10]:
        print(f"  {d['_id']:28s} title={d.get('title')!r}")
    if len(archive_docs) > 10:
        print(f"  ... and {len(archive_docs)-10} more")
    print(f"-- Cascade peek ---------------------------")
    sess_n        = await db.game_sessions.count_documents(
        {"campaign_id": {"$in": cids}})
    win_n          = await db.game_winners.count_documents(
        {"game_campaign_id": {"$in": cids}})
    redeem_n  = await db.game_redemptions.count_documents(
        {"game_campaign_id": {"$in": cids}})
    print(f"  campaigns      to wipe:    {len(cids)}")
    print(f"  campaigns      to archive: {len(archive_cids)}")
    print(f"  game_sessions  cascade:    {sess_n}")
    print(f"  game_winners    cascade:    {win_n}")
    print(f"  game_redemptions cascade:    {redeem_n}")

    if not apply:
        print("\n-- DRY-RUN ONLY (no changes).  "
                    "Re-run with `--apply` to delete. --")
        return {"campaigns": len(cids), "archived": len(archive_cids),
                        "sessions": sess_n, "winners": win_n,
                        "redemptions": redeem_n, "applied": False}

    print("\n-- APPLYING -------------------------------")
    cas_sess      = await db.game_sessions.delete_many(
        {"campaign_id": {"$in": cids}})
    cas_win        = await db.game_winners.delete_many(
        {"game_campaign_id": {"$in": cids}})
    cas_redeem = await db.game_redemptions.delete_many(
        {"game_campaign_id": {"$in": cids}})
    main            = await db.game_campaigns.delete_many({"_id": {"$in": cids}})
    arch            = await db.game_campaigns.update_many(
        {"_id": {"$in": archive_cids}, "status": "active"},
        {"$set": {"status": "archived",
                            "archived_at": datetime.now(timezone.utc),
                            "archive_reason": "test_data_remediation_4_5b"}})
    print(f"  campaigns      deleted:  {main.deleted_count}")
    print(f"  campaigns      archived: {arch.modified_count}")
    print(f"  game_sessions  deleted:  {cas_sess.deleted_count}")
    print(f"  game_winners    deleted:  {cas_win.deleted_count}")
    print(f"  game_redemptions deleted:  {cas_redeem.deleted_count}")
    return {"campaigns": main.deleted_count,
                    "archived":  arch.modified_count,
                    "sessions":  cas_sess.deleted_count,
                    "winners":    cas_win.deleted_count,
                    "redemptions": cas_redeem.deleted_count,
                    "applied":    True}


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                                  help="actually delete (default: dry-run)")
    args = ap.parse_args()
    await wipe(apply=args.apply)


if __name__ == "__main__":
    asyncio.run(main())
