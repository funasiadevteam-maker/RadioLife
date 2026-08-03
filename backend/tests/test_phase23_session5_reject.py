"""Phase 23 Session 5 — reject taxonomy + audit log tests."""
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
    cid = f"cmp_test_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc)
    await db.game_campaigns.insert_one({
        "_id": cid, "campaign_id": cid,
        "title": f"Test reject {cid[-4:]}",
        "status": status,
        "creator_type": "advertiser",
        "advertiser_id": "user_test_adv",
        "template_id": "tpl_scratch_card",
        "created_at": now, "updated_at": now,
    })
    await db.game_compliance_settings.insert_one({
        "_id": cid, "campaign_id": cid,
        "terms_text": "Test terms",
        "approval_status": "pending",
    })
    return cid


async def _cleanup(db, cid):
    await db.game_campaigns.delete_many({"campaign_id": cid})
    await db.game_compliance_settings.delete_many({"campaign_id": cid})
    await db.game_campaign_audit_logs.delete_many({"campaign_id": cid})


@pytest.fixture
def db():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    return db


def test_reject_taxonomy_codes_exposed(db):
    from services.games_v2_audit_log import REJECT_REASON_CODES
    assert "prize_value_too_low" in REJECT_REASON_CODES
    assert "other" in REJECT_REASON_CODES
    assert len(REJECT_REASON_CODES) >= 10


def test_reject_writes_audit_log_with_taxonomy(db):
    async def go():
        cid = await _seed(db)
        try:
            from services.games_v2_audit_log import write_audit_log
            await write_audit_log(
                db, campaign_id=cid, action="reject",
                actor_user_id="user_admin_test",
                reason_code="prize_value_too_low",
                reason_notes="Below threshold")
            row = await db.game_campaign_audit_logs.find_one(
                {"campaign_id": cid, "action": "reject"})
            assert row is not None
            assert row["reason_code"]    == "prize_value_too_low"
            assert row["reason_notes"] == "Below threshold"
            assert row["actor_user_id"] == "user_admin_test"
        finally:
            await _cleanup(db, cid)
    _run(go())


def test_reject_audit_idempotent_within_5min(db):
    async def go():
        cid = await _seed(db)
        try:
            from services.games_v2_audit_log import write_audit_log
            id1 = await write_audit_log(db, campaign_id=cid,
                                                                          action="reject",
                                                                          actor_user_id="u1",
                                                                          reason_code="unsafe_content")
            id2 = await write_audit_log(db, campaign_id=cid,
                                                                          action="reject",
                                                                          actor_user_id="u1",
                                                                          reason_code="unsafe_content")
            assert id1 == id2, "Idempotent within 5-min window"
            rows = await db.game_campaign_audit_logs.count_documents(
                {"campaign_id": cid, "action": "reject"})
            assert rows == 1
        finally:
            await _cleanup(db, cid)
    _run(go())


def test_other_reason_code_requires_notes(db):
    # Validation is at the route layer; here we just confirm the
    # taxonomy entry exists + the route's required-notes guard is
    # documented in REJECT_REASON_CODES.
    from services.games_v2_audit_log import REJECT_REASON_CODES
    assert "other" in REJECT_REASON_CODES
    assert "free-text" in REJECT_REASON_CODES["other"].lower() \
              or "required" in REJECT_REASON_CODES["other"].lower()
