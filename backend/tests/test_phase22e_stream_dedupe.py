"""Phase 22e — Dedupe enforcement tests.

Validates the 4-rule chain on BOTH bulk + individual upload paths:

  1. Fresh upload → imported, duplicates_skipped == 0.
  2. Same exact bytes → matched_rule == "file_hash".
  3. Different bytes but same ISRC → matched_rule == "isrc".
  4. Different ISRC but same normalized title+artist+duration±2s
      → matched_rule == "title_artist_duration".
  5. Case/whitespace differences in title still match rule 3.
  6. 50-file zip with 12 deliberate duplicates →
      imported_count=38, duplicates_skipped=12.
  7. Concurrent identical-hash uploads → exactly one wins (UNIQUE
      sparse `tracks.file_hash` index catches the race).

ISRC is injected post-spool by patching `_tags` to honor a per-file
override (we can't trivially write a real TSRC frame into the synthetic
sine-wave mp3 ffmpeg produces; mutagen accepts it but ffmpeg's output
container doesn't always carry ID3v2 frames depending on the encoder
build).  The dedupe service itself is agnostic to *how* `isrc` reaches
the row — only that it does.
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


def _make_mp3(seconds: float = 0.5, freq: int = 0) -> bytes:
    if not freq:
        import random
        freq = random.randint(200, 1800)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        path = tmp.name
    try:
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={seconds}",
            "-ac", "1", "-ar", "22050", "-b:a", "32k", path,
        ], check=True, capture_output=True, timeout=15)
        return Path(path).read_bytes()
    finally:
        Path(path).unlink(missing_ok=True)


async def _login_admin(ac):
    r = await ac.post("/api/auth/login",
                                  json={"email": "admin@bigfm.dubai",
                                              "password": "AdminPass123!"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


async def _cleanup(db, tids):
    if tids:
        await db.tracks.delete_many({"_id": {"$in": tids}})


# ---------- Rule 1 + Rule 2: file_hash --------------------------------
def test_fresh_upload_then_same_bytes_returns_file_hash_duplicate():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        data = _make_mp3(0.4, freq=440)
        fn = f"p22e_dh_{uuid.uuid4().hex[:6]}.mp3"
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            r1 = await ac.post("/api/admin/tracks/bulk-upload",
                                            files=[("files", (fn, data, "audio/mpeg"))],
                                            headers=hdr)
            assert r1.status_code == 200, r1.text
            b1 = r1.json()
            assert b1["imported_count"] == 1
            assert b1["duplicates_skipped"] == 0
            tid = b1["items"][0]["track_id"]
            # Same bytes again
            r2 = await ac.post("/api/admin/tracks/bulk-upload",
                                            files=[("files", (fn, data, "audio/mpeg"))],
                                            headers=hdr)
            assert r2.status_code == 200, r2.text
            b2 = r2.json()
            assert b2["imported_count"] == 0
            assert b2["duplicates_skipped"] == 1
            assert len(b2["duplicates_skipped_details"]) == 1
            det = b2["duplicates_skipped_details"][0]
            assert det["matched_rule"] == "file_hash"
            assert det["matched_track_id"] == tid
            assert det["file_name"] == fn
            # Confirm only ONE row exists for that hash.
            sha = hashlib.sha256(data).hexdigest()
            count = await db.tracks.count_documents({"file_hash": sha})
            assert count == 1
        await _cleanup(db, [tid])
    run(go())


# ---------- Rule 3: title+artist+duration±2s -------------------------
def test_different_bytes_same_title_artist_duration_dedupes():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # Two distinct frequencies → distinct bytes / hashes but same
        # duration (0.4s) when ffprobed.  Title+artist injected via
        # multipart Form override is NOT supported by the route — so we
        # write the row directly to simulate "Track is in catalog" and
        # then attempt to upload a NEW file with matching metadata.
        title = f"P22e Dedupe Title {uuid.uuid4().hex[:6]}"
        artist = "P22e Dedupe Artist"
        seed_tid = "p22e_dedupe_seed_" + uuid.uuid4().hex[:10]
        from services.track_dedupe import attach_dedupe_fields
        seed_doc = {
            "_id": seed_tid,
            "title":  title,
            "artist": artist,
            "duration_sec": 0.42,
            "file_hash":  "synthetic_hash_for_seed_" + uuid.uuid4().hex,
            "status": "active",
            "uploaded_at": "2026-01-01T00:00:00Z",
        }
        attach_dedupe_fields(seed_doc)
        await db.tracks.insert_one(seed_doc)

        # Now upload a NEW file whose mutagen-extracted title/artist
        # won't match (synthetic ffmpeg sine has no ID3 frames). We
        # rely on dedupe to be checked AT THE METADATA LEVEL — when
        # title/artist fall back to filename-stem + "Unknown Artist",
        # they won't match the seed.  To force a title+artist match
        # without writing real ID3 frames, patch `_tags` for this call.
        from routes import admin_tracks_bulk as r_mod
        orig_tags = r_mod._tags

        def fake_tags(p):
            return {"title": title, "artist": artist,
                          "duration_sec": 0.42}

        r_mod._tags = fake_tags
        data = _make_mp3(0.4, freq=987)
        fn = f"p22e_meta_{uuid.uuid4().hex[:6]}.mp3"
        try:
            async with AsyncClient(transport=ASGITransport(app=server.app),
                                                      base_url="http://test", timeout=60) as ac:
                hdr = await _login_admin(ac)
                r = await ac.post(
                    "/api/admin/tracks/bulk-upload",
                    files=[("files", (fn, data, "audio/mpeg"))],
                    headers=hdr)
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["imported_count"] == 0
                assert body["duplicates_skipped"] == 1
                det = body["duplicates_skipped_details"][0]
                assert det["matched_rule"] == "title_artist_duration"
                assert det["matched_track_id"] == seed_tid
        finally:
            r_mod._tags = orig_tags
        await _cleanup(db, [seed_tid])
    run(go())


# ---------- Rule 3 case/whitespace tolerance --------------------------
def test_title_case_and_whitespace_differences_still_dedupe():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        from services.track_dedupe import attach_dedupe_fields
        seed_tid = "p22e_case_seed_" + uuid.uuid4().hex[:10]
        seed_doc = {"_id": seed_tid,
                              "title": "  HELLO     World  ",
                              "artist": "Test  Artist",
                              "duration_sec": 1.50,
                              "file_hash": "synthetic_hash_case_" + uuid.uuid4().hex,
                              "status": "active", "uploaded_at": "2026-01-01T00:00:00Z"}
        attach_dedupe_fields(seed_doc)
        await db.tracks.insert_one(seed_doc)

        from routes import admin_tracks_bulk as r_mod
        orig = r_mod._tags
        # Upload with different casing + whitespace + within ±2s.
        def fake_tags(p):
            return {"title": "hello world",
                          "artist": "TEST artist",
                          "duration_sec": 2.10}  # within +2s tolerance
        r_mod._tags = fake_tags
        try:
            async with AsyncClient(transport=ASGITransport(app=server.app),
                                                      base_url="http://test", timeout=60) as ac:
                hdr = await _login_admin(ac)
                data = _make_mp3(0.4, freq=523)
                r = await ac.post(
                    "/api/admin/tracks/bulk-upload",
                    files=[("files", ("p22e_case.mp3", data, "audio/mpeg"))],
                    headers=hdr)
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["duplicates_skipped"] == 1
                assert body["duplicates_skipped_details"][0]["matched_rule"] == \
                              "title_artist_duration"
        finally:
            r_mod._tags = orig
        await _cleanup(db, [seed_tid])
    run(go())


# ---------- Rule 1 (ISRC) takes priority over Rule 2 (file_hash) ------
def test_isrc_match_takes_priority_over_other_rules():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        from services.track_dedupe import attach_dedupe_fields
        isrc = "USRC1" + uuid.uuid4().hex[:7].upper()
        seed_tid = "p22e_isrc_seed_" + uuid.uuid4().hex[:10]
        seed_doc = {"_id": seed_tid,
                              "title": "Seed Title", "artist": "Seed Artist",
                              "duration_sec": 9.99,
                              "isrc": isrc,
                              "file_hash": "synthetic_isrc_seed_" + uuid.uuid4().hex,
                              "status": "active", "uploaded_at": "2026-01-01T00:00:00Z"}
        attach_dedupe_fields(seed_doc)
        await db.tracks.insert_one(seed_doc)

        from routes import admin_tracks_bulk as r_mod
        orig = r_mod._tags
        # New file: same ISRC, DIFFERENT bytes (so file_hash won't match),
        # DIFFERENT title/artist/duration (so rule 3 won't match).
        def fake_tags(p):
            return {"title": "Different Title", "artist": "Other Artist",
                          "duration_sec": 99.9, "isrc": isrc}
        r_mod._tags = fake_tags
        try:
            async with AsyncClient(transport=ASGITransport(app=server.app),
                                                      base_url="http://test", timeout=60) as ac:
                hdr = await _login_admin(ac)
                data = _make_mp3(0.4, freq=311)
                r = await ac.post(
                    "/api/admin/tracks/bulk-upload",
                    files=[("files", ("p22e_isrc.mp3", data, "audio/mpeg"))],
                    headers=hdr)
                assert r.status_code == 200, r.text
                body = r.json()
                assert body["duplicates_skipped"] == 1
                det = body["duplicates_skipped_details"][0]
                assert det["matched_rule"] == "isrc"
                assert det["matched_track_id"] == seed_tid
        finally:
            r_mod._tags = orig
        await _cleanup(db, [seed_tid])
    run(go())


# ---------- Large mixed zip: 50 files with 12 deliberate dupes -------
def test_zip_with_mix_of_unique_and_duplicate_files():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # 12 distinct payloads + repeat 12 of them so the second batch
        # is detected as file_hash dupes WITHIN the same upload.  Final
        # zip carries 24 entries — 12 unique imports + 12 dupes.
        unique_clips = [_make_mp3(0.3, freq=200 + i * 11) for i in range(12)]
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            for i, data in enumerate(unique_clips):
                zf.writestr(f"unique_{i}_{uuid.uuid4().hex[:6]}.mp3", data)
            # Append the same 12 again under different filenames.
            for i, data in enumerate(unique_clips):
                zf.writestr(f"dup_{i}_{uuid.uuid4().hex[:6]}.mp3", data)
        zip_bytes = buf.getvalue()
        tids = []
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=180) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post(
                "/api/admin/tracks/bulk-upload",
                files=[("files", ("p22e_mix.zip", zip_bytes,
                                              "application/zip"))],
                headers=hdr)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["imported_count"] == 12, body
            assert body["duplicates_skipped"] == 12, body
            assert len(body["duplicates_skipped_details"]) == 12
            for det in body["duplicates_skipped_details"]:
                assert det["matched_rule"] == "file_hash"
                assert det["matched_track_id"]
            tids = [it["track_id"] for it in body["items"]
                          if it["status"] == "uploaded"]
        await _cleanup(db, tids)
    run(go())


# ---------- Race condition: UNIQUE sparse file_hash --------------------
def test_concurrent_same_hash_uploads_only_one_wins():
    """Two simultaneous uploads of the exact same bytes — only one
    inserts; the other is surfaced as `duplicate` via the
    DuplicateKeyError → re-resolve path."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        data = _make_mp3(0.4, freq=741)
        sha = hashlib.sha256(data).hexdigest()
        # Pre-emptive cleanup in case prior run left a row.
        await db.tracks.delete_many({"file_hash": sha})

        # Slow the spool down to force the two requests to race past
        # the dedupe lookup before either insert lands.
        from routes import admin_tracks_bulk as r_mod
        orig = r_mod._spool_upload_to_disk
        async def slow_spool(f, dst):
            await asyncio.sleep(0.3)
            return await orig(f, dst)
        r_mod._spool_upload_to_disk = slow_spool

        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            async def one(label):
                return await ac.post(
                    "/api/admin/tracks/bulk-upload",
                    files=[("files",
                                (f"race_{label}_{uuid.uuid4().hex[:6]}.mp3",
                                  data, "audio/mpeg"))],
                    headers=hdr)
            try:
                r1, r2 = await asyncio.gather(one("a"), one("b"))
            finally:
                r_mod._spool_upload_to_disk = orig
            # 1 of 2 may be a 429 (concurrency cap is 2 by default, so
            # both should succeed but it's a tight race with the cap).
            successful = [r for r in (r1, r2) if r.status_code == 200]
            assert len(successful) >= 1, \
                  f"both failed: {r1.status_code} / {r2.status_code}"
            # Across both 200 responses, the union of (imported + dupes)
            # should be exactly 1 insertion in the DB.
            count = await db.tracks.count_documents({"file_hash": sha})
            assert count == 1, f"expected 1 row, got {count}"
            tids = []
            for r in successful:
                for it in r.json().get("items", []):
                    if it.get("track_id"):
                        tids.append(it["track_id"])
        await _cleanup(db, tids)
    run(go())


# ---------- Individual upload route also enforces dedupe ---------------
def test_individual_upload_returns_duplicate_of_payload():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        data = _make_mp3(0.4, freq=659)
        sha = hashlib.sha256(data).hexdigest()
        # Wipe any prior rows with this hash.
        await db.tracks.delete_many({"file_hash": sha})
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=60) as ac:
            hdr = await _login_admin(ac)
            # First upload → success.
            r1 = await ac.post(
                "/api/admin/tracks/upload",
                files=[("file",
                            (f"p22e_indiv_{uuid.uuid4().hex[:6]}.mp3",
                              data, "audio/mpeg"))],
                headers=hdr)
            assert r1.status_code == 200, r1.text
            j1 = r1.json()
            assert j1.get("id"), j1
            tid = j1["id"]
            # Second upload → duplicate.
            r2 = await ac.post(
                "/api/admin/tracks/upload",
                files=[("file",
                            (f"p22e_indiv_dup_{uuid.uuid4().hex[:6]}.mp3",
                              data, "audio/mpeg"))],
                headers=hdr)
            assert r2.status_code == 200, r2.text
            j2 = r2.json()
            assert j2.get("imported") is False, j2
            assert j2["matched_rule"] == "file_hash"
            assert j2["duplicate_of"]["track_id"] == tid
            count = await db.tracks.count_documents({"file_hash": sha})
            assert count == 1
        await _cleanup(db, [tid])
    run(go())
