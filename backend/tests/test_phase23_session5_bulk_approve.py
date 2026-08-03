"""Phase 23 Session 5 — bulk-approve route tests."""
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient


def _run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


async def _seed(db, status="pending_approval"):
    cid = f"cmp_bulk_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    await db.game_campaigns.insert_one({
        "_id": cid, "campaign_id": cid,
        "title": f"Test bulk {cid[-4:]}",
        "status": status,
        "creator_type": "advertiser",
        "advertiser_id": "user_test_adv",
        "template_id": "tpl_scratch_card",
        "created_at": now, "updated_at": now,
    })
    await db.game_compliance_settings.insert_one({
        "_id": cid, "campaign_id": cid,
        "terms_text": "Test", "approval_status": "pending",
    })
    return cid


async def _cleanup(db, cids):
    await db.game_campaigns.delete_many({"campaign_id": {"$in": cids}})
    await db.game_compliance_settings.delete_many({"campaign_id": {"$in": cids}})
    await db.game_campaign_audit_logs.delete_many({"campaign_id": {"$in": cids}})


@pytest.fixture
def db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def test_bulk_approve_partial_success(db):
    """Approves 2 pending + reports 1 not-pending as failed."""
    async def go():
        from services.games_v2_audit_log import write_audit_log
        c1 = await _seed(db, status="pending_approval")
        c2 = await _seed(db, status="pending_approval")
        c3 = await _seed(db, status="draft")  # cannot be approved
        try:
            from routes.games_v2_admin_campaigns import admin_bulk_approve
            class FakeReq:
                class _S: pass
                app = type("A", (), {"state": _S()})()
                def __init__(self, db_):
                    self.app.state.db = db_
            req = FakeReq(db)
            res = await admin_bulk_approve(
                {"campaign_ids": [c1, c2, c3]}, req,
                u={"user_id": "user_admin_test"})
            assert set(res["approved"]) == {c1, c2}
            assert len(res["failed"]) == 1
            assert res["failed"][0]["id"] == c3
            assert "not_pending" in res["failed"][0]["reason"]

            # Audit log rows written for the 2 approved
            audits = await db.game_campaign_audit_logs.find(
                {"campaign_id": {"$in": [c1, c2]},
                  "action": "approve_bulk"}).to_list(10)
            assert len(audits) == 2
            actors = {a["actor_user_id"] for a in audits}
            assert actors == {"user_admin_test"}
        finally:
            await _cleanup(db, [c1, c2, c3])
    _run(go())


def test_bulk_approve_caps_at_100(db):
    async def go():
        from routes.games_v2_admin_campaigns import admin_bulk_approve
        from fastapi import HTTPException
        class FakeReq:
            class _S: pass
            app = type("A", (), {"state": _S()})()
            def __init__(self, db_):
                self.app.state.db = db_
        req = FakeReq(db)
        ids = [f"cmp_x_{i}" for i in range(101)]
        try:
            await admin_bulk_approve({"campaign_ids": ids}, req,
                                                            u={"user_id": "u1"})
            assert False, "expected HTTPException"
        except HTTPException as e:
            assert e.status_code == 400
            assert "max_100" in str(e.detail)
    _run(go())


def test_bulk_approve_empty_payload_rejected(db):
    async def go():
        from routes.games_v2_admin_campaigns import admin_bulk_approve
        from fastapi import HTTPException
        class FakeReq:
            class _S: pass
            app = type("A", (), {"state": _S()})()
            def __init__(self, db_):
                self.app.state.db = db_
        req = FakeReq(db)
        try:
            await admin_bulk_approve({"campaign_ids": []}, req,
                                                            u={"user_id": "u1"})
            assert False, "expected HTTPException"
        except HTTPException as e:
            assert e.status_code == 400
    _run(go())
