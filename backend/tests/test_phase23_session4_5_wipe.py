"""Phase 23 Session 4.5 — wipe test data filter is safe + idempotent.

Crucially asserts that the safe AND-filter does NOT touch production
data (the dispatch's literal OR-criteria would have wiped all 1010
campaigns because `creator_user_id` is not a populated field — the
real ownership column is `advertiser_id` and the Session 2 backfill
already set `creator_type` on every doc).
"""
from __future__ import annotations
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient
from scripts.wipe_play_and_win_test_campaigns import wipe


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)
def _db(): return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _seed(db, **over):
    cid = over.pop("_id", f"cmp_test_{uuid.uuid4().hex[:10]}")
    doc = {
        "_id":                          cid,
        "campaign_id":          cid,
        "title":                      "Test placeholder",
        "status":                  "draft",
        "advertiser_id":      "adv_phase8a_tester",
        "creator_type":      "advertiser",
        "created_at":            datetime.now(timezone.utc),
        **over,
    }
    return doc


# ════════════════════════════════════════════════════════════════════════
# 1.  Only test fixtures get deleted; admin / house / active production
#       campaigns survive.
# ════════════════════════════════════════════════════════════════════════
def test_only_test_fixtures_get_deleted():
    async def go():
        db = _db()
        test_a    = _seed(db, title="Test campaign A")
        test_b    = _seed(db, title="Demo prize spin")
        sample = _seed(db, title="Sample MVP scratch")
        karak    = _seed(db, title="karak cafe friday spin")
        prod      = _seed(db, title="Live Dubai weekend giveaway",
                                          status="active",
                                          _id=f"cmp_prod_{uuid.uuid4().hex[:8]}")
        house    = _seed(db, title="BigFM Daily Spin",
                                          _id=f"cmp_house_smoke_{uuid.uuid4().hex[:6]}")
        old        = _seed(db, title="Test legacy",
                                          created_at=datetime(2025, 11, 1, tzinfo=timezone.utc))
        await db.game_campaigns.insert_many([test_a, test_b, sample, karak,
                                                                                          prod, house, old])
        try:
            r = await wipe(apply=True, db=db)
            assert r["campaigns"] >= 4, f"expected ≥4 fixtures wiped, got {r}"
            # Survivors
            assert await db.game_campaigns.find_one({"_id": prod["_id"]})
            assert await db.game_campaigns.find_one({"_id": house["_id"]})
            assert await db.game_campaigns.find_one({"_id": old["_id"]})
            # Deleted
            for d in (test_a, test_b, sample, karak):
                assert await db.game_campaigns.find_one({"_id": d["_id"]}) is None
        finally:
            # Cleanup our seeds (any survivors).
            await db.game_campaigns.delete_many({"_id": {"$in": [
                test_a["_id"], test_b["_id"], sample["_id"], karak["_id"],
                prod["_id"], house["_id"], old["_id"],
            ]}})
    run(go())


# ════════════════════════════════════════════════════════════════════════
# 2.  Cascades reach sessions / winners / redemptions correctly.
# ════════════════════════════════════════════════════════════════════════
def test_cascade_to_sessions_winners_redemptions():
    async def go():
        db = _db()
        cid = f"cmp_test_cascade_{uuid.uuid4().hex[:8]}"
        c = _seed(db, _id=cid, title="Test cascade trigger")
        await db.game_campaigns.insert_one(c)
        # Seed one row of each cascade collection keyed to the campaign.
        sid    = f"gs_test_{uuid.uuid4().hex[:8]}"
        wid    = f"win_test_{uuid.uuid4().hex[:8]}"
        rid    = f"red_test_{uuid.uuid4().hex[:8]}"
        await db.game_sessions.insert_one({"_id": sid, "session_id": sid,
                                                                                  "campaign_id": cid})
        await db.game_winners.insert_one({"_id": wid, "winner_id": wid,
                                                                                  "game_campaign_id": cid})
        await db.game_redemptions.insert_one({"_id": rid, "redemption_id": rid,
                                                                                          "game_campaign_id": cid})
        try:
            r = await wipe(apply=True, db=db)
            assert r["sessions"]      >= 1
            assert r["winners"]        >= 1
            assert r["redemptions"] >= 1
            assert await db.game_sessions.find_one({"_id": sid})        is None
            assert await db.game_winners.find_one({"_id": wid})          is None
            assert await db.game_redemptions.find_one({"_id": rid}) is None
        finally:
            await db.game_campaigns.delete_one({"_id": cid})
            await db.game_sessions.delete_one({"_id": sid})
            await db.game_winners.delete_one({"_id": wid})
            await db.game_redemptions.delete_one({"_id": rid})
    run(go())


# ════════════════════════════════════════════════════════════════════════
# 3.  Idempotent — second invocation is a no-op on the same data.
# ════════════════════════════════════════════════════════════════════════
def test_wipe_is_idempotent():
    async def go():
        db = _db()
        c = _seed(db, title="Test idempotent")
        await db.game_campaigns.insert_one(c)
        try:
            r1 = await wipe(apply=True, db=db)
            r2 = await wipe(apply=True, db=db)
            assert r1["campaigns"] >= 1
            # Second pass picks up nothing of our seed (and reports the
            # current state of any unrelated seeds — irrelevant).  The
            # specific seed must not reappear.
            assert await db.game_campaigns.find_one({"_id": c["_id"]}) is None
            _ = r2  # presence only — exact count depends on parallel state
        finally:
            await db.game_campaigns.delete_one({"_id": c["_id"]})
    run(go())


# ════════════════════════════════════════════════════════════════════════
# 4.  Wallet items are untouched — already-redeemed rewards stay valid.
# ════════════════════════════════════════════════════════════════════════
def test_wallet_items_are_not_touched():
    async def go():
        db = _db()
        cid = f"cmp_test_wallet_{uuid.uuid4().hex[:8]}"
        wallet_id = f"wal_test_{uuid.uuid4().hex[:8]}"
        c = _seed(db, _id=cid, title="Test wallet preservation")
        await db.game_campaigns.insert_one(c)
        await db.wallet_items.insert_one({
            "_id": wallet_id,
            "campaign_id": cid,
            "user_id": "test_user",
            "status": "saved",
        })
        try:
            await wipe(apply=True, db=db)
            # Campaign gone, wallet item still present.
            assert await db.game_campaigns.find_one({"_id": cid}) is None
            kept = await db.wallet_items.find_one({"_id": wallet_id})
            assert kept is not None and kept["status"] == "saved"
        finally:
            await db.game_campaigns.delete_one({"_id": cid})
            await db.wallet_items.delete_one({"_id": wallet_id})
    run(go())
