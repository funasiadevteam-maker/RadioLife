"""Phase 22a — Bulk Music Upload (admin) tests.

End-to-end exercise of `POST /api/admin/tracks/bulk-upload` and its
auxiliary `GET .../limits` endpoint. Synthetic MP3s are generated on
the fly via ffmpeg so tests don't depend on any seeded asset.
"""
from __future__ import annotations
import asyncio
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

sys.path.insert(0, "/app/backend")
os.environ["STRIPE_MODE"] = "mock"
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# ---------- helpers ---------------------------------------------------

def _make_mp3(seconds: float = 0.5, freq: int = 0) -> bytes:
    """Generate a tiny synthetic MP3 via ffmpeg → bytes.

    Default `freq=0` picks a random frequency per call so successive test
    invocations don't collide with previously-uploaded SHA hashes left in
    the DB from a prior run that aborted mid-flight before cleanup.
    """
    if not freq:
        import random
        freq = random.randint(200, 1800)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        path = tmp.name
    try:
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
            "-ac", "1", "-ar", "22050", "-b:a", "32k",
            path,
        ], check=True, capture_output=True, timeout=15)
        return Path(path).read_bytes()
    finally:
        Path(path).unlink(missing_ok=True)


async def _login(ac, email: str, password: str):
    r = await ac.post("/api/auth/login",
                                  json={"email": email, "password": password})
    assert r.status_code == 200, f"login failed: {r.text}"
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


async def _login_admin(ac):
    return await _login(ac, "admin@bigfm.dubai", "AdminPass123!")


async def _register_user(ac):
    suf = uuid.uuid4().hex[:8]
    r = await ac.post("/api/auth/register",
        json={"email": f"u_p22a_{suf}@bigfm.dubai",
                  "password": "Pwd1234!", "name": "Bulk Test User"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


async def _cleanup_tracks(db, track_ids: list[str]):
    if track_ids:
        await db.tracks.delete_many({"_id": {"$in": track_ids}})


def _multipart_files(payloads: list[tuple[str, bytes]],
                                            field: str = "files"):
    """httpx multipart shape for repeated form-data parts."""
    return [(field, (name, data, "audio/mpeg")) for name, data in payloads]


# ---------- tests ----------------------------------------------------

def test_admin_can_bulk_upload_multiple_mp3s_returns_per_file_report():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        clips = [(f"track_{i}_{uuid.uuid4().hex[:6]}.mp3",
                          _make_mp3(0.4))
                          for i in range(3)]
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=_multipart_files(clips),
                                          headers=hdr)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["ok"] is True
            assert body["total_received"] == 3
            assert body["uploaded"] == 3
            assert body["duplicates"] == 0
            assert body["failed"] == 0
            assert len(body["items"]) == 3
            tids = []
            for item in body["items"]:
                assert item["status"] == "uploaded"
                assert item["track_id"]
                assert item["title"]
                assert item["duration_sec"] > 0
                tids.append(item["track_id"])
        await _cleanup_tracks(db, tids)
    run(go())


def test_non_admin_user_gets_403_on_bulk_upload():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            hdr = await _register_user(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=_multipart_files([("a.mp3", _make_mp3(0.2))]),
                                          headers=hdr)
            assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    run(go())


def test_zip_archive_extracts_and_persists_each_audio_entry():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # Build a small in-memory ZIP with 2 mp3s.
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"zip_a_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))
            zf.writestr(f"zip_b_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=[("files",
                                                      ("bundle.zip", buf.getvalue(), "application/zip"))],
                                          headers=hdr)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["uploaded"] == 2
            # Phase 22b: `total_received` is the count of top-level inputs
            # (1 ZIP here), not the extracted-entry count. The actual extract
            # count surfaces in `audio_files_extracted_from_zip`.
            assert body["total_received"] == 1
            assert body["audio_files_extracted_from_zip"] == 2
            tids = [it["track_id"] for it in body["items"]
                          if it["status"] == "uploaded"]
            assert len(tids) == 2
        await _cleanup_tracks(db, tids)
    run(go())


def test_zip_slip_attempt_is_rejected_with_400():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../escape_attempt.mp3", _make_mp3(0.2))
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=[("files",
                                                      ("evil.zip", buf.getvalue(), "application/zip"))],
                                          headers=hdr)
            assert r.status_code == 400
            assert "zip_slip_attempt" in r.text
    run(go())


def test_duplicate_file_hash_returns_duplicate_status_without_re_persisting():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        data = _make_mp3(0.4)
        sha = hashlib.sha256(data).hexdigest()
        fn = f"dup_{uuid.uuid4().hex[:6]}.mp3"
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            # First upload — should be `uploaded`.
            r1 = await ac.post("/api/admin/tracks/bulk-upload",
                                            files=_multipart_files([(fn, data)]),
                                            headers=hdr)
            assert r1.status_code == 200, r1.text
            tid = r1.json()["items"][0]["track_id"]
            # Same bytes → `duplicate` referencing the original.
            r2 = await ac.post("/api/admin/tracks/bulk-upload",
                                            files=_multipart_files([(fn, data)]),
                                            headers=hdr)
            assert r2.status_code == 200, r2.text
            body = r2.json()
            assert body["uploaded"] == 0
            assert body["duplicates"] == 1
            assert body["items"][0]["status"] == "duplicate"
            assert body["items"][0]["existing_track_id"] == tid
            # Confirm only ONE row exists for that hash.
            count = await db.tracks.count_documents({"file_hash": sha})
            assert count == 1
        await _cleanup_tracks(db, [tid])
    run(go())


def test_non_audio_files_inside_zip_are_skipped_not_failed():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(f"good_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))
            zf.writestr("readme.txt",          b"hi this is not audio")
            zf.writestr("art.jpg",                b"\xff\xd8\xff\xe0fake-jpeg")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=[("files",
                                                      ("mixed.zip", buf.getvalue(), "application/zip"))],
                                          headers=hdr)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["uploaded"] == 1
            assert body["skipped_non_audio"] == 2
            assert body["failed"] == 0
            tid = next(it["track_id"] for it in body["items"]
                              if it["status"] == "uploaded")
        await _cleanup_tracks(db, [tid])
    run(go())


def test_request_exceeding_max_files_returns_413():
    """101 tiny top-level inputs exceeds BULK_UPLOAD_MAX_FILES=100 → 413.

    Phase 22b: the cap is on TOP-LEVEL inputs (loose files OR ZIPs), not on
    ZIP-extracted entries — those have their own per-ZIP/global caps tested
    separately below.
    """
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        from routes.admin_tracks_bulk import BULK_UPLOAD_MAX_FILES
        payloads = [(f"f{i:03d}.mp3", b"x")
                              for i in range(BULK_UPLOAD_MAX_FILES + 1)]
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=_multipart_files(payloads),
                                          headers=hdr)
            assert r.status_code == 413, r.text
            assert "too_many_files" in r.text
    run(go())


def test_uploaded_track_is_immediately_queryable_via_existing_tracks_endpoint():
    """After bulk-upload, the new track row shows up in GET /admin/tracks."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        clip_name = f"queryable_{uuid.uuid4().hex[:6]}.mp3"
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=_multipart_files([(clip_name, _make_mp3(0.4))]),
                                          headers=hdr)
            assert r.status_code == 200, r.text
            tid = r.json()["items"][0]["track_id"]
            # GET /admin/tracks should include the new row in `id` field.
            lr = await ac.get("/api/admin/tracks", headers=hdr)
            assert lr.status_code == 200, lr.text
            ids = {t["id"] for t in lr.json()}
            assert tid in ids, f"newly-uploaded track missing from /admin/tracks"
        await _cleanup_tracks(db, [tid])
    run(go())


def test_limits_endpoint_reports_configured_caps():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=15) as ac:
            hdr = await _login_admin(ac)
            r = await ac.get("/api/admin/tracks/bulk-upload/limits", headers=hdr)
            assert r.status_code == 200, r.text
            body = r.json()
            # Phase 22e — raised caps; assertions read config constants so
            # future env-driven raises don't re-break tests.
            from routes.admin_tracks_bulk import (
                BULK_UPLOAD_MAX_FILES, BULK_UPLOAD_MAX_BYTES,
                BULK_UPLOAD_MAX_EXTRACTED_FILES, BULK_UPLOAD_MAX_ZIP_ENTRIES)
            assert body["max_files"]              == BULK_UPLOAD_MAX_FILES                  == 200
            assert body["max_bytes"]              == BULK_UPLOAD_MAX_BYTES                  == 5 * 1024 * 1024 * 1024
            assert body["max_extracted_files"] == BULK_UPLOAD_MAX_EXTRACTED_FILES == 5000
            assert body["max_zip_entries"]    == BULK_UPLOAD_MAX_ZIP_ENTRIES      == 2000
            assert ".mp3" in body["accepted_ext"]
            assert ".wav" in body["accepted_ext"]
    run(go())


# ─────────────────────────────────────────────────────────────────
# Phase 22b — multi-ZIP + mixed selection extension
# ─────────────────────────────────────────────────────────────────

def _make_zip(entries: list[tuple[str, bytes]]) -> bytes:
    """Build an in-memory ZIP from (filename, bytes) tuples."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n, d in entries:
            zf.writestr(n, d)
    return buf.getvalue()


def test_can_upload_multiple_zips_in_single_request():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        z1 = _make_zip([(f"a_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3)),
                                (f"b_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))])
        z2 = _make_zip([(f"c_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))])
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=[("files", ("lib1.zip", z1, "application/zip")),
                                                      ("files", ("lib2.zip", z2, "application/zip"))],
                                          headers=hdr)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total_received"]                              == 2
            assert body["zip_archives_processed"]              == 2
            assert body["audio_files_extracted_from_zip"] == 3
            assert body["audio_files_direct"]                          == 0
            assert body["uploaded"]                                          == 3
            tids = [it["track_id"] for it in body["items"]
                          if it["status"] == "uploaded"]
            await _cleanup_tracks(db, tids)
    run(go())


def test_can_mix_zips_and_loose_audio_in_single_request():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        loose1 = (f"loose_a_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))
        loose2 = (f"loose_b_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))
        zb = _make_zip([(f"zip_x_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3)),
                                (f"zip_y_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))])
        files = _multipart_files([loose1, loose2]) + \
                      [("files", ("lib.zip", zb, "application/zip"))]
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=files, headers=hdr)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total_received"]                              == 3
            assert body["zip_archives_processed"]              == 1
            assert body["audio_files_extracted_from_zip"] == 2
            assert body["audio_files_direct"]                          == 2
            assert body["uploaded"]                                          == 4
            tids = [it["track_id"] for it in body["items"]
                          if it["status"] == "uploaded"]
            await _cleanup_tracks(db, tids)
    run(go())


def test_legacy_archive_field_returns_400_after_phase_19_part_c_removal():
    """Phase 19 Part C — `archive=<single .zip>` field removed. Callers
    sending it get a hard 400 directing them to `files[]` (which has
    accepted ZIPs since Phase 22b)."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        zb = _make_zip([(f"legacy_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))])
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=[("archive",
                                                      ("legacy.zip", zb, "application/zip"))],
                                          headers=hdr)
            assert r.status_code == 400, r.text
            assert "archive_field_removed_use_files" in r.text
            # Deprecation header is gone — alias is fully removed.
            assert "X-Deprecated" not in r.headers
    run(go())


def test_total_extracted_count_cap_returns_413_too_many_extracted_files():
    """When the running extracted-from-ZIP count crosses 1000, the request
    is hard-413 (no partial commit allowed). The detail payload identifies
    which archive tipped the count over."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        from routes.admin_tracks_bulk import (BULK_UPLOAD_MAX_EXTRACTED_FILES,
                                                                            BULK_UPLOAD_MAX_ZIP_ENTRIES)
        server = importlib.import_module("server")
        # Phase 22e — per_zip stays at the per-zip cap; 3 ZIPs of that size
        # push the running total past `BULK_UPLOAD_MAX_EXTRACTED_FILES`.
        per_zip = BULK_UPLOAD_MAX_ZIP_ENTRIES
        zips = [_make_zip([(f"z{idx}_e{i:04d}.mp3", b"x")
                                          for i in range(per_zip)])
                      for idx in range(3)]
        files = [("files", (f"big{i}.zip", b, "application/zip"))
                      for i, b in enumerate(zips)]
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=files, headers=hdr)
            assert r.status_code == 413, r.text
            detail = r.json().get("detail") or {}
            assert detail.get("code")    == "too_many_extracted_files"
            assert detail.get("limit") == BULK_UPLOAD_MAX_EXTRACTED_FILES
            assert detail.get("archive", "").startswith("big")
    run(go())


def test_per_zip_entry_cap_marks_that_zip_failed_but_other_inputs_still_process():
    """A ZIP with > 500 entries is marked `failed: zip_too_many_entries`;
    other inputs in the same request continue to process normally."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        from routes.admin_tracks_bulk import BULK_UPLOAD_MAX_ZIP_ENTRIES
        server = importlib.import_module("server")
        db = _db()
        oversized = _make_zip([(f"o_{i:03d}.mp3", b"x")
                                              for i in range(BULK_UPLOAD_MAX_ZIP_ENTRIES + 1)])
        loose_name = f"survives_{uuid.uuid4().hex[:6]}.mp3"
        loose = (loose_name, _make_mp3(0.3))
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=[("files", ("oversize.zip", oversized,
                                                                    "application/zip")),
                                                      ("files", (loose[0], loose[1], "audio/mpeg"))],
                                          headers=hdr)
            assert r.status_code == 200, r.text
            body = r.json()
            oversize_rows = [it for it in body["items"]
                                              if it.get("reason") == "zip_too_many_entries"]
            assert len(oversize_rows) == 1
            assert oversize_rows[0]["status"]      == "failed"
            assert oversize_rows[0]["filename"] == "oversize.zip"
            assert body["audio_files_direct"] == 1
            assert body["uploaded"]                == 1
            uploaded_row = next(it for it in body["items"]
                                              if it["status"] == "uploaded")
            assert uploaded_row["filename"]  == loose_name
            assert uploaded_row["source"]      == "direct"
            await _cleanup_tracks(db, [uploaded_row["track_id"]])
    run(go())


def test_response_items_carry_source_and_archive_fields():
    """Spot-check the per-item shape: direct items have `source="direct"`,
    zip items have `source="zip"` AND `archive=<filename>` of the parent
    ZIP."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        zb = _make_zip([(f"inside_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))])
        loose = (f"plain_{uuid.uuid4().hex[:6]}.mp3", _make_mp3(0.3))
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=[("files", (loose[0], loose[1], "audio/mpeg")),
                                                      ("files", ("shape.zip", zb, "application/zip"))],
                                          headers=hdr)
            assert r.status_code == 200, r.text
            body = r.json()
            direct = [it for it in body["items"] if it.get("source") == "direct"]
            zips    = [it for it in body["items"] if it.get("source") == "zip"]
            assert len(direct) == 1
            assert direct[0]["filename"] == loose[0]
            assert "archive" not in direct[0]
            assert len(zips)        == 1
            assert zips[0]["archive"]  == "shape.zip"
            assert zips[0]["status"]    == "uploaded"
            tids = [it["track_id"] for it in body["items"]
                          if it["status"] == "uploaded"]
            await _cleanup_tracks(db, tids)
    run(go())

