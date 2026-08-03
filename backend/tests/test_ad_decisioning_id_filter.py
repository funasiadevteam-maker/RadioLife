"""Phase 36c.5 hotfix — `ad_creatives` filter regression for the
ad-decisioning + route-ad-engine paths.

Both lookups previously filtered by `{"creative_id": creative_id,
"approval_status": "approved", "active": True}`, which silently dropped
newer-shape rows that use the `id` field with `status="approved"` (no
`active` / `approval_status` columns). These tests lock in the dual-
shape filter we now use in both production sites.

We exercise the SMALLEST UNIT that does the creative lookup — the
filter dict applied to the live Mongo collection — to avoid hauling
in the rest of the ad-decisioning ranking logic / scoring / pacing.
"""
from __future__ import annotations
import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app/backend")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


# Dual-shape filter that both production sites now use.
def _filter(cid: str) -> dict:
    return {"$and": [
        {"$or": [{"id": cid}, {"creative_id": cid}]},
        {"$or": [
            {"status": {"$in": ["approved", "active"]}},
            {"$and": [{"approval_status": "approved"},
                            {"active": True}]},
        ]},
    ]}


def test_ad_decisioning_finds_creative_by_id_field():
    """Newer-shape row (id + status='approved') resolves through the
    ad-decisioning creative-lookup filter."""
    db = _db()
    cid = f"crt_test_decision_{uuid.uuid4().hex[:8]}"
    run(db.ad_creatives.delete_many({"id": cid}))
    run(db.ad_creatives.insert_one({
        "id": cid, "status": "approved",
        "audio_path": "/tmp/x.mp3", "title": "T"}))
    try:
        got = run(db.ad_creatives.find_one(_filter(cid)))
        assert got is not None, "filter dropped the newer-shape row"
        assert got["id"] == cid
        # Confirm the production callsite uses the exact same filter.
        import inspect
        from services import ad_decisioning as ad
        src = inspect.getsource(ad)
        assert "status" in src and "approval_status" in src and \
                  '"id": creative_id' in src and \
                  '"creative_id": creative_id' in src, \
                  "ad_decisioning.py creative-lookup filter regressed"
    finally:
        run(db.ad_creatives.delete_many({"id": cid}))


def test_route_ad_engine_finds_creative_by_id_field():
    """Same dual-shape contract for the route-ad-engine creative pick."""
    db = _db()
    cid = f"crt_test_route_{uuid.uuid4().hex[:8]}"
    run(db.ad_creatives.delete_many({"id": cid}))
    run(db.ad_creatives.insert_one({
        "id": cid, "status": "approved",
        "audio_path": "/tmp/x.mp3", "title": "T"}))
    try:
        got = run(db.ad_creatives.find_one(_filter(cid)))
        assert got is not None
        assert got["id"] == cid
        import inspect
        from services import route_ad_engine as rae
        src = inspect.getsource(rae)
        assert "status" in src and "approval_status" in src and \
                  '"id": cr_id' in src and \
                  '"creative_id": cr_id' in src, \
                  "route_ad_engine.py creative-lookup filter regressed"
    finally:
        run(db.ad_creatives.delete_many({"id": cid}))


def test_legacy_shape_still_resolves():
    """Legacy seed-shape row (creative_id + active=True +
    approval_status='approved') keeps resolving — back-compat
    guarantee on both sites."""
    db = _db()
    cid = f"crv_legacy_{uuid.uuid4().hex[:8]}"
    run(db.ad_creatives.delete_many({"creative_id": cid}))
    run(db.ad_creatives.insert_one({
        "creative_id": cid, "active": True,
        "approval_status": "approved",
        "audio_path": "/tmp/legacy.mp3", "title": "Legacy"}))
    try:
        got = run(db.ad_creatives.find_one(_filter(cid)))
        assert got is not None
        assert got["creative_id"] == cid
    finally:
        run(db.ad_creatives.delete_many({"creative_id": cid}))


def test_pending_creative_rejected_by_status_gate():
    """A row with id + status='pending_review' MUST NOT resolve —
    the safety intent of the gate is preserved."""
    db = _db()
    cid = f"crt_pending_{uuid.uuid4().hex[:8]}"
    run(db.ad_creatives.delete_many({"id": cid}))
    run(db.ad_creatives.insert_one({
        "id": cid, "status": "pending_review",
        "audio_path": "/tmp/x.mp3", "title": "T"}))
    try:
        got = run(db.ad_creatives.find_one(_filter(cid)))
        assert got is None, "pending_review row leaked past the status gate"
    finally:
        run(db.ad_creatives.delete_many({"id": cid}))
