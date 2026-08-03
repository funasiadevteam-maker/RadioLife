"""Phase 22g — Bulk Upload Job Audit Log tests.

Covers the seven scenarios from the dispatch:

    1. Successful upload creates a `status="completed"` row with counts.
    2. Failed upload creates a `status="failed"` row with `failure_reason`.
    3. `GET /api/admin/tracks/bulk-upload/jobs` is admin-only (403 otherwise).
    4. A user CAN see their own jobs via `GET /api/me/bulk-upload/jobs`.
    5. A user CANNOT see another user's jobs via the same `/api/me` endpoint.
    6. `POST /sweep-stale` flips old `running` rows to `abandoned`.
    7. `per_file_results_json` is capped at 200 entries with a truncated flag.
"""
from __future__ import annotations
import asyncio
import io
import os
import sys
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/app/backend")
os.environ["STRIPE_MODE"] = "mock"
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient

# Reuse the synthetic MP3 + login helpers shipped with 22a so we don't
# diverge from the canonical fixtures.
sys.path.insert(0, str(Path(__file__).parent))
from test_phase22a_bulk_upload import (_make_mp3, _login_admin,
                                                                              _register_user, _cleanup_tracks,
                                                                              _multipart_files)


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)
def _db(): return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ════════════════════════════════════════════════════════════════════════
# 1. Successful upload → completed row with counts.
# ════════════════════════════════════════════════════════════════════════
def test_successful_upload_creates_completed_job_row_with_counts():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        clips = [(f"p22g_ok_{i}_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))
                          for i in range(2)]
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                            files=_multipart_files(clips), headers=hdr)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["uploaded"] == 2
            job_id = body.get("job_id")
            assert job_id, "response must carry job_id"

            row = await db.bulk_upload_jobs.find_one({"_id": job_id})
            assert row is not None, "job row not persisted"
            assert row["status"]                          == "completed"
            assert row["uploaded_count"]            == 2
            assert row["failed_count"]                == 0
            assert row["duplicate_count"]            == 0
            assert row["audio_direct_count"]      == 2
            assert row["total_extracted_from_zip"] == 0
            assert row["total_inputs"]                == 2
            assert row["total_bytes_received"]  > 0
            assert row["completed_at"]                is not None
            assert row["duration_ms"]                  is not None
            assert row["client_ip"]                      is not None
            assert row["client_user_agent"]      is not None
            assert row["failure_reason"]              is None
            assert row["per_file_results_truncated"] is False
            assert len(row["per_file_results_json"]) == 2

            tids = [it["track_id"] for it in body["items"]
                          if it["status"] == "uploaded"]
        await _cleanup_tracks(db, tids)
        await db.bulk_upload_jobs.delete_one({"_id": job_id})
    run(go())


# ════════════════════════════════════════════════════════════════════════
# 2. Failed upload (bad ZIP entry → 400 no_valid_audio) creates a
#    `status="failed"` row with `failure_reason`.
# ════════════════════════════════════════════════════════════════════════
def test_failed_upload_creates_failed_job_row_with_failure_reason():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # A zip with a single zip-slip entry → no candidates → 400.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil_only.mp3", _make_mp3(0.2))
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test", timeout=30) as ac:
            hdr = await _login_admin(ac)
            before = await db.bulk_upload_jobs.count_documents({})
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                            files=[("files", ("evil.zip",
                                                                            buf.getvalue(), "application/zip"))],
                                            headers=hdr)
            assert r.status_code == 400, r.text
            after  = await db.bulk_upload_jobs.count_documents({})
            assert after == before + 1, "fail path must still leave a row"

            # Newest fail row.
            row = await db.bulk_upload_jobs.find_one({"status": "failed"},
                                                                                          sort=[("started_at", -1)])
            assert row is not None
            assert row["status"] == "failed"
            assert row["failure_reason"]
            assert row["completed_at"] is not None
            # The slip item was recorded.
            items = row["per_file_results_json"]
            assert any(it["status"] == "failed" for it in items)

        await db.bulk_upload_jobs.delete_one({"_id": row["_id"]})
    run(go())


# ════════════════════════════════════════════════════════════════════════
# 3. Admin-only history endpoint — non-admin gets 403.
# ════════════════════════════════════════════════════════════════════════
def test_job_history_endpoint_admin_only_403_for_non_admin():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test", timeout=30) as ac:
            hdr = await _register_user(ac)
            r = await ac.get("/api/admin/tracks/bulk-upload/jobs",
                                            headers=hdr)
            assert r.status_code == 403, r.text
    run(go())


# ════════════════════════════════════════════════════════════════════════
# 4 + 5. User can see their own jobs via /api/me; cannot see others'.
# ════════════════════════════════════════════════════════════════════════
def test_user_can_see_own_jobs_via_me_endpoint():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test", timeout=30) as ac:
            hdr = await _login_admin(ac)
            me = await ac.get("/api/auth/me", headers=hdr)
            uid = me.json()["user_id"]
            # Seed two rows directly so we don't depend on a real upload.
            now = datetime.now(timezone.utc)
            jids = [f"job_me_self_{i}_{uuid.uuid4().hex[:6]}" for i in range(2)]
            for jid in jids:
                await db.bulk_upload_jobs.insert_one({
                    "_id": jid, "job_id": jid,
                    "started_by_user_id": uid,
                    "started_at": now,
                    "status": "completed",
                    "total_inputs": 1, "zip_count": 0,
                    "audio_direct_count": 1,
                    "total_extracted_from_zip": 0,
                    "uploaded_count": 1, "duplicate_count": 0,
                    "skipped_non_audio_count": 0, "failed_count": 0,
                    "total_bytes_received": 100,
                    "storage_provider": "local",
                    "per_file_results_json": [],
                    "per_file_results_truncated": False,
                    "created_at": now, "updated_at": now,
                })

            r = await ac.get("/api/me/bulk-upload/jobs?limit=100",
                                            headers=hdr)
            assert r.status_code == 200, r.text
            ids = [j["job_id"] for j in r.json()["items"]]
            assert set(jids).issubset(set(ids))

            # Cleanup
            await db.bulk_upload_jobs.delete_many({"_id": {"$in": jids}})
    run(go())


def test_user_cannot_see_other_users_jobs_via_me_endpoint():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        now = datetime.now(timezone.utc)
        other_jid = f"job_other_{uuid.uuid4().hex[:8]}"
        await db.bulk_upload_jobs.insert_one({
            "_id": other_jid, "job_id": other_jid,
            "started_by_user_id": "user_some_other_id",
            "started_at": now, "status": "completed",
            "total_inputs": 1, "zip_count": 0,
            "audio_direct_count": 1, "total_extracted_from_zip": 0,
            "uploaded_count": 1, "duplicate_count": 0,
            "skipped_non_audio_count": 0, "failed_count": 0,
            "total_bytes_received": 99, "storage_provider": "local",
            "per_file_results_json": [],
            "per_file_results_truncated": False,
            "created_at": now, "updated_at": now,
        })
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test", timeout=30) as ac:
            hdr = await _register_user(ac)
            # `/api/me` is user-scoped.
            r1 = await ac.get("/api/me/bulk-upload/jobs?limit=100",
                                              headers=hdr)
            assert r1.status_code == 200, r1.text
            ids = {j["job_id"] for j in r1.json()["items"]}
            assert other_jid not in ids
            # `/api/me/.../{job_id}` returns 404 (not 200, not 403).
            r2 = await ac.get(f"/api/me/bulk-upload/jobs/{other_jid}",
                                              headers=hdr)
            assert r2.status_code == 404, r2.text

        await db.bulk_upload_jobs.delete_one({"_id": other_jid})
    run(go())


# ════════════════════════════════════════════════════════════════════════
# 6. Sweep-stale flips old running rows to abandoned.
# ════════════════════════════════════════════════════════════════════════
def test_sweep_stale_flips_old_running_jobs_to_abandoned():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # Two stale-running rows + one fresh-running row.  Sweep should
        # only flip the stale pair.
        now = datetime.now(timezone.utc)
        stale_jids = [f"job_stale_{uuid.uuid4().hex[:8]}" for _ in range(2)]
        fresh_jid  = f"job_fresh_{uuid.uuid4().hex[:8]}"
        for jid in stale_jids:
            await db.bulk_upload_jobs.insert_one({
                "_id": jid, "job_id": jid,
                "started_by_user_id": "tester",
                "started_at": now - timedelta(hours=2),
                "status": "running",
                "total_inputs": 0, "zip_count": 0,
                "audio_direct_count": 0,
                "total_extracted_from_zip": 0,
                "uploaded_count": 0, "duplicate_count": 0,
                "skipped_non_audio_count": 0, "failed_count": 0,
                "total_bytes_received": 0,
                "storage_provider": "local",
                "per_file_results_json": [],
                "per_file_results_truncated": False,
                "created_at": now, "updated_at": now,
            })
        await db.bulk_upload_jobs.insert_one({
            "_id": fresh_jid, "job_id": fresh_jid,
            "started_by_user_id": "tester",
            "started_at": now,
            "status": "running",
            "total_inputs": 0, "zip_count": 0,
            "audio_direct_count": 0, "total_extracted_from_zip": 0,
            "uploaded_count": 0, "duplicate_count": 0,
            "skipped_non_audio_count": 0, "failed_count": 0,
            "total_bytes_received": 0, "storage_provider": "local",
            "per_file_results_json": [],
            "per_file_results_truncated": False,
            "created_at": now, "updated_at": now,
        })

        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test", timeout=30) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post(
                "/api/admin/tracks/bulk-upload/jobs/sweep-stale",
                headers=hdr)
            assert r.status_code == 200, r.text
            assert r.json()["abandoned_count"] >= 2

        for jid in stale_jids:
            row = await db.bulk_upload_jobs.find_one({"_id": jid})
            assert row["status"] == "abandoned"
        fresh_row = await db.bulk_upload_jobs.find_one({"_id": fresh_jid})
        assert fresh_row["status"] == "running"

        await db.bulk_upload_jobs.delete_many(
            {"_id": {"$in": [*stale_jids, fresh_jid]}})
    run(go())


# ════════════════════════════════════════════════════════════════════════
# 7. per_file_results_json truncated to 200 entries.
# ════════════════════════════════════════════════════════════════════════
def test_per_file_results_truncated_when_over_200_entries():
    async def go():
        from services.bulk_upload_jobs import complete_job, create_job
        db = _db()
        jid = await create_job(
            db,
            started_by_user_id="tester",
            total_inputs=210,
            total_bytes_received=1024,
            defaults_json={},
            client_ip="127.0.0.1",
            client_user_agent="pytest",
            storage_provider="local",
        )
        items = [{"source": "direct", "filename": f"f{i}.mp3",
                          "status": "uploaded", "track_id": f"t{i}",
                          "title": f"T{i}", "artist": "A",
                          "duration_sec": 1.0}
                          for i in range(210)]
        await complete_job(db, jid, items=items, extra_counts=None)
        row = await db.bulk_upload_jobs.find_one({"_id": jid})
        assert len(row["per_file_results_json"]) == 200
        assert row["per_file_results_truncated"] is True
        assert row["uploaded_count"] == 210
        await db.bulk_upload_jobs.delete_one({"_id": jid})
    run(go())
