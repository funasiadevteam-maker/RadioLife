"""Phase 36e Turn 3 — First-episode publish nudge tests."""
from __future__ import annotations
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception: pass

# Force SendGrid mock mode (no live key) AND clear any Mailgun env from
# host .env so this legacy test still exercises the mock fallback path.
os.environ.pop("SENDGRID_API_KEY", None)
os.environ.pop("MAILGUN_API_KEY", None)
os.environ.pop("EMAIL_PROVIDER", None)

from motor.motor_asyncio import AsyncIOMotorClient
from services import nudges as fn


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


async def _seed_creator(db, *, hours_ago: float = 0, paused: bool = False,
                                                already_published: bool = False,
                                                sent_24h: bool = False, sent_72h: bool = False) -> dict:
    cid = f"crt_t36e3_{uuid.uuid4().hex[:8]}"
    uid = f"usr_t36e3_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    doc = {"id": cid, "user_id": uid,
                "display_name": "Test Creator",
                "email": f"test_{cid}@bigfm.dubai",
                "application_status": "approved",
                "approved_at": now - timedelta(hours=hours_ago),
                "nudges_paused": paused,
                "nudge_email_24h_sent_at": now if sent_24h else None,
                "nudge_email_72h_sent_at": now if sent_72h else None,
                "first_episode_published_at": now if already_published else None,
                "created_at": now}
    await db.podcast_creators.insert_one(doc)
    return doc


async def _cleanup(db, creator_ids: list[str]):
    if creator_ids:
        await db.podcast_creators.delete_many({"id": {"$in": creator_ids}})
        await db.creator_nudge_events.delete_many(
            {"creator_id": {"$in": creator_ids}})


# ─── 1. Qualifies when approved + no episodes + not paused ───
def test_nudge_qualifies_when_no_episodes_and_not_paused():
    async def go():
        db = _db()
        cr = await _seed_creator(db)
        try:
            res = await fn.qualifies_for_nudge(db, creator=cr)
            assert res["qualifies"] is True
            payload = await fn.get_status_payload(db, creator=cr)
            assert payload["qualifies"] is True
            assert payload["banner_message"]
        finally: await _cleanup(db, [cr["id"]])
    run(go())


# ─── 2. Publish hook clears qualification ────────────────────
def test_nudge_skips_already_published_creator():
    async def go():
        db = _db()
        cr = await _seed_creator(db, hours_ago=25)
        ch_id = f"pch_t36e3_{uuid.uuid4().hex[:8]}"
        await db.podcast_channels.insert_one(
            {"id": ch_id, "creator_id": cr["id"], "title": "T"})
        try:
            res = await fn.mark_first_episode_published(db, channel_id=ch_id)
            assert res is not None
            assert res.get("first_episode_published_at") is not None
            # Refresh creator + re-check.
            cr2 = await db.podcast_creators.find_one({"id": cr["id"]})
            q = await fn.qualifies_for_nudge(db, creator=cr2)
            assert q["qualifies"] is False
            assert q["reason"] == "already_published"
            # Idempotent: calling again leaves stamp intact (compare seconds —
            # Mongo strips tzinfo on round-trip).
            res2 = await fn.mark_first_episode_published(db, channel_id=ch_id)
            t1 = res["first_episode_published_at"].replace(tzinfo=None)
            t2 = res2["first_episode_published_at"].replace(tzinfo=None)
            assert (t1 - t2).total_seconds() < 1
        finally:
            await _cleanup(db, [cr["id"]])
            await db.podcast_channels.delete_many({"id": ch_id})
    run(go())


# ─── 3. 24h window logic ─────────────────────────────────────
def test_nudge_24h_window_logic():
    async def go():
        db = _db()
        # 23h: too soon. 25h: in window. 27h: past 24h window AND past 26h end.
        cr_23 = await _seed_creator(db, hours_ago=23)
        cr_25 = await _seed_creator(db, hours_ago=25)
        cr_27 = await _seed_creator(db, hours_ago=27)
        ids = [c["id"] for c in (cr_23, cr_25, cr_27)]
        try:
            r = await fn.tick_first_episode_nudges(db)
            assert r["window_24h_sent"] == 1, r
            # Verify cr_25 got stamped.
            cr_25_r = await db.podcast_creators.find_one({"id": cr_25["id"]})
            assert cr_25_r["nudge_email_24h_sent_at"] is not None
            cr_23_r = await db.podcast_creators.find_one({"id": cr_23["id"]})
            assert cr_23_r["nudge_email_24h_sent_at"] is None
            cr_27_r = await db.podcast_creators.find_one({"id": cr_27["id"]})
            assert cr_27_r["nudge_email_24h_sent_at"] is None
            # Idempotent re-run: no extra sends.
            r2 = await fn.tick_first_episode_nudges(db)
            assert r2["window_24h_sent"] == 0
        finally: await _cleanup(db, ids)
    run(go())


# ─── 4. 72h window logic ─────────────────────────────────────
def test_nudge_72h_window_logic():
    async def go():
        db = _db()
        # Already-sent-24h flag so this creator only competes for the 72h window.
        cr_73 = await _seed_creator(db, hours_ago=73, sent_24h=True)
        cr_75 = await _seed_creator(db, hours_ago=75, sent_24h=True)
        ids = [c["id"] for c in (cr_73, cr_75)]
        try:
            r = await fn.tick_first_episode_nudges(db)
            assert r["window_72h_sent"] == 1, r
            cr_73_r = await db.podcast_creators.find_one({"id": cr_73["id"]})
            assert cr_73_r["nudge_email_72h_sent_at"] is not None
            cr_75_r = await db.podcast_creators.find_one({"id": cr_75["id"]})
            assert cr_75_r["nudge_email_72h_sent_at"] is None
        finally: await _cleanup(db, ids)
    run(go())


# ─── 5. Pause / resume flip ──────────────────────────────────
def test_pause_resume_flip():
    async def go():
        db = _db()
        cr = await _seed_creator(db, hours_ago=25)
        try:
            # Pause → next tick skips this creator.
            await fn.set_paused(db, creator_id=cr["id"], paused=True)
            r = await fn.tick_first_episode_nudges(db)
            assert r["window_24h_sent"] == 0
            assert r["skipped"] >= 1
            row = await db.podcast_creators.find_one({"id": cr["id"]})
            assert row["nudge_email_24h_sent_at"] is None
            # Resume → next tick sends.
            await fn.set_paused(db, creator_id=cr["id"], paused=False)
            r2 = await fn.tick_first_episode_nudges(db)
            assert r2["window_24h_sent"] == 1
        finally: await _cleanup(db, [cr["id"]])
    run(go())


# ─── 6. Admin dispatch dry-run returns counts ────────────────
def test_admin_dispatch_dry_run_returns_counts():
    async def go():
        db = _db()
        cr_a = await _seed_creator(db, hours_ago=25)
        cr_b = await _seed_creator(db, hours_ago=73, sent_24h=True)
        try:
            r = await fn.tick_first_episode_nudges(db, dry_run=True)
            assert r["dry_run"] is True
            assert r["window_24h_sent"] == 0
            assert r["window_72h_sent"] == 0
            assert r["skipped"] >= 2
            # No stamps persisted on dry_run.
            row_a = await db.podcast_creators.find_one({"id": cr_a["id"]})
            assert row_a["nudge_email_24h_sent_at"] is None
        finally: await _cleanup(db, [cr_a["id"], cr_b["id"]])
    run(go())


# ─── 7. SendGrid mock mode produces sg_mock_* + ledger event ─
def test_sendgrid_mock_mode_logs_payload_and_persists_event():
    # Defensive: clear any Mailgun env left over by a prior test in the same
    # session so this test exercises the pure mock fallback path.
    os.environ.pop("MAILGUN_API_KEY", None)
    os.environ.pop("EMAIL_PROVIDER", None)
    async def go():
        db = _db()
        cr = await _seed_creator(db, hours_ago=25)
        try:
            r = await fn.tick_first_episode_nudges(db)
            assert r["window_24h_sent"] == 1
            events = await db.creator_nudge_events.find(
                {"creator_id": cr["id"]}, {"_id": 0}).to_list(10)
            sent_ev = [e for e in events if e["event_type"] == "email_24h_sent"]
            assert len(sent_ev) == 1
            ev = sent_ev[0]
            assert ev["sendgrid_message_id"]
            assert ev["sendgrid_message_id"].startswith("sg_mock_")
            assert ev["reason"] == "mock_mode"
        finally: await _cleanup(db, [cr["id"]])
    run(go())
