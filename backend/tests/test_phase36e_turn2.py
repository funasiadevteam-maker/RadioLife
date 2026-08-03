"""Phase 36e Turn 2 — Conversion funnel tests.

Covers event instrumentation (dedupe), summary ratio math, daily series
zero-fill, and the creator-or-admin gate. Hermetic — no external HTTP.
"""
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

from motor.motor_asyncio import AsyncIOMotorClient
from services import funnel as fn


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


async def _seed_funnel_events(db, *, channel_id: str, event_type: str,
                                                        count: int, days_ago: int = 0):
    """Bulk-insert N synthetic funnel events for a channel/day, bypassing the
    dedupe unique index (uses unique listener_user_ids)."""
    occurred = datetime.now(timezone.utc) - timedelta(days=days_ago)
    docs = [{
        "id": f"fne_{uuid.uuid4().hex[:12]}_{i}",
        "event_type": event_type,
        "listener_user_id": f"usr_seed_{uuid.uuid4().hex[:10]}_{i}",
        "channel_id": channel_id,
        "episode_id": None,
        "day_bucket": occurred.strftime("%Y-%m-%d"),
        "occurred_at": occurred,
    } for i in range(count)]
    if docs: await db.funnel_events.insert_many(docs)


async def _seed_sub_events(db, *, sub_id: str, channel_id: str,
                                                  event_type: str, count: int, days_ago: int = 0):
    """Seed subscription_events bound to a fake listener_subscription row."""
    occurred = datetime.now(timezone.utc) - timedelta(days=days_ago)
    # Listener_subscriptions row (referenced via subscription_id join).
    await db.listener_subscriptions.update_one(
        {"id": sub_id},
        {"$setOnInsert": {"id": sub_id, "channel_id": channel_id,
                                            "listener_user_id": "usr_seed",
                                            "status": "active"}}, upsert=True)
    docs = [{
        "id": f"sev_{uuid.uuid4().hex[:12]}_{i}",
        "subscription_id": sub_id,
        "event_type": event_type,
        "created_at": occurred,
    } for i in range(count)]
    if docs: await db.subscription_events.insert_many(docs)


async def _cleanup(db, *, channel_id: str, creator_id: str):
    await db.funnel_events.delete_many({"channel_id": channel_id})
    sub_ids = [s["id"] async for s in db.listener_subscriptions.find(
        {"channel_id": channel_id}, {"_id": 0, "id": 1})]
    if sub_ids:
        await db.subscription_events.delete_many(
            {"subscription_id": {"$in": sub_ids}})
        await db.listener_subscriptions.delete_many(
            {"channel_id": channel_id})
    await db.podcast_channels.delete_many({"id": channel_id})
    await db.podcast_creators.delete_many({"id": creator_id})


# ─── 1. channel_visit dedupe within 24h (per-day bucket) ────────
def test_channel_visit_event_inserts_with_24h_dedupe():
    async def go():
        db = _db()
        cid = f"pch_fn_{uuid.uuid4().hex[:8]}"
        uid = f"usr_fn_{uuid.uuid4().hex[:8]}"
        try:
            r1 = await fn.record_event(db, event_type="channel_visit",
                                                                listener_user_id=uid, channel_id=cid)
            r2 = await fn.record_event(db, event_type="channel_visit",
                                                                listener_user_id=uid, channel_id=cid)
            r3 = await fn.record_event(db, event_type="channel_visit",
                                                                listener_user_id=uid, channel_id=cid)
            assert r1["recorded"] is True
            assert r2["recorded"] is False
            assert r3["recorded"] is False
            cnt = await db.funnel_events.count_documents(
                {"channel_id": cid, "event_type": "channel_visit",
                  "listener_user_id": uid})
            assert cnt == 1, f"expected 1 event after 3 attempts, got {cnt}"
        finally:
            await db.funnel_events.delete_many({"channel_id": cid})
    run(go())


# ─── 2. episode_play records with channel_id ────────────────────
def test_episode_play_event_records_with_channel_id():
    async def go():
        db = _db()
        cid = f"pch_fn_{uuid.uuid4().hex[:8]}"
        uid = f"usr_fn_{uuid.uuid4().hex[:8]}"
        eid = f"pep_fn_{uuid.uuid4().hex[:8]}"
        try:
            r = await fn.record_event(db, event_type="episode_play",
                                                              listener_user_id=uid, channel_id=cid,
                                                              episode_id=eid)
            assert r["recorded"] is True
            row = await db.funnel_events.find_one(
                {"channel_id": cid, "event_type": "episode_play"})
            assert row is not None
            assert row["channel_id"] == cid
            assert row["episode_id"] == eid
            assert row["listener_user_id"] == uid
        finally:
            await db.funnel_events.delete_many({"channel_id": cid})
    run(go())


# ─── 3. cta_clicked dedupes per day via HTTP route ──────────────
def test_cta_clicked_endpoint_dedupes_per_day():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        cid = f"pch_fn_cta_{uuid.uuid4().hex[:8]}"
        creator_id = f"crt_fn_cta_{uuid.uuid4().hex[:8]}"
        await db.podcast_creators.insert_one({
            "id": creator_id, "user_id": "usr_dummy",
            "display_name": "T", "application_status": "approved"})
        await db.podcast_channels.insert_one({
            "id": cid, "creator_id": creator_id, "title": "T"})
        try:
            async with AsyncClient(transport=ASGITransport(app=server.app),
                                                          base_url="http://test") as ac:
                login = await ac.post("/api/auth/login",
                    json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
                tok = login.json()["session_token"]
                hdrs = {"Authorization": f"Bearer {tok}"}
                r1 = await ac.post(
                    f"/api/podcasts/channels/{cid}/funnel/cta-clicked",
                    headers=hdrs)
                r2 = await ac.post(
                    f"/api/podcasts/channels/{cid}/funnel/cta-clicked",
                    headers=hdrs)
                assert r1.status_code == 200, r1.text
                assert r1.json()["recorded"] is True
                assert r2.status_code == 200, r2.text
                assert r2.json()["recorded"] is False
        finally:
            await _cleanup(db, channel_id=cid, creator_id=creator_id)
    run(go())


# ─── 4. summary ratio math ───────────────────────────────────────
def test_funnel_summary_calculates_ratios_correctly():
    """Seed exactly 100/50/20/10/4 events across the 5 stages and assert
    visit_to_play=0.5, play_to_cta=0.4, cta_to_trial=0.5, trial_to_paid=0.4."""
    async def go():
        db = _db()
        creator_id = f"crt_fn_ratio_{uuid.uuid4().hex[:8]}"
        cid = f"pch_fn_ratio_{uuid.uuid4().hex[:8]}"
        sub_id = f"lsub_fn_ratio_{uuid.uuid4().hex[:8]}"
        await db.podcast_creators.insert_one({"id": creator_id,
                                                                                  "user_id": "usr_dummy",
                                                                                  "application_status": "approved"})
        await db.podcast_channels.insert_one({"id": cid,
                                                                                  "creator_id": creator_id,
                                                                                  "title": "Ratio"})
        try:
            await _seed_funnel_events(db, channel_id=cid,
                                                                  event_type="channel_visit", count=100)
            await _seed_funnel_events(db, channel_id=cid,
                                                                  event_type="episode_play", count=50)
            await _seed_funnel_events(db, channel_id=cid,
                                                                  event_type="subscribe_cta_click", count=20)
            await _seed_sub_events(db, sub_id=sub_id, channel_id=cid,
                                                            event_type="trial_started", count=10)
            await _seed_sub_events(db, sub_id=sub_id, channel_id=cid,
                                                            event_type="trial_converted", count=4)

            res = await fn.summary(db, creator_id=creator_id, window_days=7)
            o = res["overall"]
            assert o["visits"]      == 100
            assert o["plays"]        == 50
            assert o["cta_clicks"] == 20
            assert o["trials"]        == 10
            assert o["conversions"] == 4
            assert o["visit_to_play"]  == 0.5
            assert o["play_to_cta"]     == 0.4
            assert o["cta_to_trial"]    == 0.5
            assert o["trial_to_paid"] == 0.4
            assert len(res["per_channel"]) == 1
            assert res["per_channel"][0]["channel_id"] == cid
        finally:
            await _cleanup(db, channel_id=cid, creator_id=creator_id)
    run(go())


# ─── 5. daily returns sorted series with zero-fill gap day ──────
def test_funnel_daily_returns_sorted_series_with_zero_fill():
    async def go():
        db = _db()
        creator_id = f"crt_fn_daily_{uuid.uuid4().hex[:8]}"
        cid = f"pch_fn_daily_{uuid.uuid4().hex[:8]}"
        await db.podcast_creators.insert_one({"id": creator_id,
                                                                                  "user_id": "usr_dummy",
                                                                                  "application_status": "approved"})
        await db.podcast_channels.insert_one({"id": cid,
                                                                                  "creator_id": creator_id})
        try:
            # Day 0 (today): 3 visits. Day 2-back: 2 visits. Day 1-back: gap (0).
            await _seed_funnel_events(db, channel_id=cid,
                event_type="channel_visit", count=3, days_ago=0)
            await _seed_funnel_events(db, channel_id=cid,
                event_type="channel_visit", count=2, days_ago=2)

            res = await fn.daily(db, creator_id=creator_id, days=5)
            series = res["series"]
            assert len(series) == 5
            # Sorted ascending.
            dates = [r["date"] for r in series]
            assert dates == sorted(dates)
            # Every day present (gap-fill).
            day_set = {r["date"]: r for r in series}
            today = datetime.now(timezone.utc).date().isoformat()
            assert today in day_set
            assert day_set[today]["visits"] == 3
            # Day-back-1: should be zero (gap-filled).
            d1 = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
            assert day_set[d1]["visits"] == 0
            # Each entry has all 5 stage keys.
            for r in series:
                for k in ("visits", "plays", "cta_clicks", "trials", "conversions"):
                    assert k in r
        finally:
            await _cleanup(db, channel_id=cid, creator_id=creator_id)
    run(go())


# ─── 6. creator-only OR admin gate ──────────────────────────────
def test_funnel_summary_creator_only_or_admin():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        owner_uid = f"usr_owner_{uuid.uuid4().hex[:8]}"
        owner_crt = f"crt_owner_{uuid.uuid4().hex[:8]}"
        cid = f"pch_gate_{uuid.uuid4().hex[:8]}"
        await db.podcast_creators.insert_one({"id": owner_crt,
                                                                                  "user_id": owner_uid,
                                                                                  "display_name": "Owner",
                                                                                  "application_status": "approved"})
        await db.podcast_channels.insert_one({"id": cid,
                                                                                  "creator_id": owner_crt})

        # Register an outsider user.
        outsider_email = f"out_t36e2_{uuid.uuid4().hex[:6]}@bigfm.dubai"
        try:
            async with AsyncClient(transport=ASGITransport(app=server.app),
                                                          base_url="http://test") as ac:
                reg = await ac.post("/api/auth/register",
                    json={"email": outsider_email, "password": "TestPass123!",
                              "name": "Outsider"})
                assert reg.status_code == 200, reg.text
                outsider_tok = reg.json()["session_token"]
                outsider_uid = reg.json()["user_id"]
                hdrs_out = {"Authorization": f"Bearer {outsider_tok}"}

                # Outsider attempts to read OWNER's funnel → 403.
                r403 = await ac.get(
                    f"/api/podcasts/creators/{owner_crt}/funnel/summary",
                    headers=hdrs_out)
                assert r403.status_code == 403, r403.text

                # Admin reads same → 200.
                adm = await ac.post("/api/auth/login",
                    json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
                hdrs_adm = {"Authorization": f"Bearer {adm.json()['session_token']}"}
                r200 = await ac.get(
                    f"/api/podcasts/creators/{owner_crt}/funnel/summary",
                    headers=hdrs_adm)
                assert r200.status_code == 200, r200.text
                assert "overall" in r200.json()
                assert "per_channel" in r200.json()
        finally:
            await _cleanup(db, channel_id=cid, creator_id=owner_crt)
            await db.users.delete_many({"email": outsider_email})
    run(go())
