"""Phase 23 Session 5 — queue-stats endpoint tests."""
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass
import asyncio
import os
import uuid
from datetime import datetime, timezone, timedelta

import pytest
from motor.motor_asyncio import AsyncIOMotorClient


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


@pytest.fixture
def db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def test_queue_stats_counts_pending(db):
    async def go():
        from routes.games_v2_admin_campaigns import admin_queue_stats
        from services.games_v2_audit_log import stats_cache_bust
        stats_cache_bust()
        # Seed 3 pending + 1 active(approved today) + 1 rejected(today)
        now = datetime.now(timezone.utc)
        seeded = []
        for _ in range(3):
            cid = f"cmp_qs_p_{uuid.uuid4().hex[:8]}"
            seeded.append(cid)
            await db.game_campaigns.insert_one({
                "_id": cid, "campaign_id": cid,
                "status": "pending_approval", "created_at": now,
                "updated_at": now, "title": "qstest pending",
                "template_id": "tpl_spin_wheel",
            })
        appr = f"cmp_qs_a_{uuid.uuid4().hex[:8]}"
        seeded.append(appr)
        await db.game_campaigns.insert_one({
            "_id": appr, "campaign_id": appr,
            "status": "active",
            "created_at": now - timedelta(hours=2),
            "approved_at": now - timedelta(minutes=30),
            "title": "qstest active", "template_id": "tpl_spin_wheel",
        })
        rej = f"cmp_qs_r_{uuid.uuid4().hex[:8]}"
        seeded.append(rej)
        await db.game_campaigns.insert_one({
            "_id": rej, "campaign_id": rej,
            "status": "rejected",
            "created_at": now - timedelta(hours=1),
            "rejected_at": now - timedelta(minutes=15),
            "title": "qstest rejected", "template_id": "tpl_spin_wheel",
        })
        try:
            class FakeReq:
                class _S: pass
                app = type("A", (), {"state": _S()})()
                def __init__(self, db_):
                    self.app.state.db = db_
            req = FakeReq(db)
            res = await admin_queue_stats(req, _u={"user_id": "u1"})
            assert res["pending"] >= 3
            assert res["approved_today"] >= 1
            assert res["rejected_today"] >= 1
            # avg_decision_minutes should be a positive number
            assert res["avg_decision_minutes"] is None \
                      or res["avg_decision_minutes"] >= 0
            assert res["cached"] is False
        finally:
            await db.game_campaigns.delete_many(
                {"campaign_id": {"$in": seeded}})
    _run(go())


def test_queue_stats_cache_hit_within_60s(db):
    async def go():
        from routes.games_v2_admin_campaigns import admin_queue_stats
        from services.games_v2_audit_log import stats_cache_bust
        stats_cache_bust()
        class FakeReq:
            class _S: pass
            app = type("A", (), {"state": _S()})()
            def __init__(self, db_):
                self.app.state.db = db_
        req = FakeReq(db)
        res1 = await admin_queue_stats(req, _u={"user_id": "u1"})
        assert res1["cached"] is False
        res2 = await admin_queue_stats(req, _u={"user_id": "u1"})
        assert res2["cached"] is True
        # Values match
        for k in ("pending", "approved_today", "rejected_today"):
            assert res1[k] == res2[k]
    _run(go())


def test_reject_reasons_endpoint_returns_taxonomy(db):
    async def go():
        from routes.games_v2_admin_campaigns import admin_reject_reasons
        res = await admin_reject_reasons(_u={"user_id": "u1"})
        codes = [r["code"] for r in res["reasons"]]
        assert "prize_value_too_low" in codes
        assert "other" in codes
        assert len(codes) >= 10
        # Each reason has a label.
        assert all(r.get("label") for r in res["reasons"])
    _run(go())
