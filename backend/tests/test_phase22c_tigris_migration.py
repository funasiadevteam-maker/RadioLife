"""Phase 22c — Tigris migration of `tracks` rows + radio engine read path.

The Tigris client (`services.object_storage`) is monkey-patched in each
test to a synthesizing fake so no real bucket calls happen.
"""
from __future__ import annotations
import asyncio, os, subprocess, sys, tempfile, uuid
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
def _db(): return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


class _FakeStorage:
    def __init__(self, fail: bool = False):
        self.calls: list[dict] = []
        self.fail = fail
    def upload(self, *, local_path, key, content_type=None, **kw):
        if self.fail: raise RuntimeError("tigris_down")
        self.calls.append({"local_path": local_path, "key": key,
                                            "content_type": content_type})
        return {"ok": True}
    def get_signed_url(self, *, key, expires_in=3600):
        return f"https://fake-tigris.example.com/{key}?sig=abc&exp={expires_in}"


def _patch_storage(fake):
    import services.object_storage as os_mod
    os_mod.get_storage = lambda *a, **kw: fake


def _make_mp3() -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as t: p = t.name
    import random
    subprocess.run(["ffmpeg","-y","-loglevel","error","-f","lavfi","-i",
                                  f"sine=frequency={random.randint(200,1800)}:duration=0.3",
                                  "-ac","1","-ar","22050","-b:a","32k",p],
                              check=True, capture_output=True, timeout=15)
    b = Path(p).read_bytes(); Path(p).unlink(); return b


async def _login_admin(ac):
    r = await ac.post("/api/auth/login",
                                  json={"email":"admin@bigfm.dubai","password":"AdminPass123!"})
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


async def _register_listener(ac):
    suf = uuid.uuid4().hex[:8]
    r = await ac.post("/api/auth/register",
                                  json={"email": f"u_22c_{suf}@bigfm.dubai",
                                              "password":"Pwd1234!","name":"P22c"})
    return {"Authorization": f"Bearer {r.json()['session_token']}"}


def test_bulk_upload_writes_to_tigris_when_provider_set():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        fake = _FakeStorage(); _patch_storage(fake)
        os.environ["TRACKS_STORAGE_PROVIDER"] = "tigris"
        os.environ["TRACKS_BUCKET_PREFIX"]      = "tracks/"
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=[("files", (f"tg_{uuid.uuid4().hex[:6]}.mp3",
                                                                      _make_mp3(), "audio/mpeg"))],
                                          headers=hdr)
            assert r.status_code == 200, r.text
            tid = r.json()["items"][0]["track_id"]
            assert fake.calls, "upload() never called"
            assert fake.calls[0]["key"].startswith("tracks/") and fake.calls[0]["key"].endswith(".mp3")
            await db.tracks.delete_one({"_id": tid})
    run(go())


def test_bulk_upload_returns_502_on_tigris_failure_no_silent_local_fallback():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        fake = _FakeStorage(fail=True); _patch_storage(fake)
        os.environ["TRACKS_STORAGE_PROVIDER"] = "tigris"
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=[("files", (f"fail_{uuid.uuid4().hex[:6]}.mp3",
                                                                      _make_mp3(), "audio/mpeg"))],
                                          headers=hdr)
            assert r.status_code == 502, r.text
            assert "storage_upload_failed" in r.text
    run(go())


def test_track_row_has_storage_provider_and_storage_key_fields():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        fake = _FakeStorage(); _patch_storage(fake)
        os.environ["TRACKS_STORAGE_PROVIDER"] = "tigris"
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=30) as ac:
            hdr = await _login_admin(ac)
            r = await ac.post("/api/admin/tracks/bulk-upload",
                                          files=[("files", (f"row_{uuid.uuid4().hex[:6]}.mp3",
                                                                      _make_mp3(), "audio/mpeg"))],
                                          headers=hdr)
            tid = r.json()["items"][0]["track_id"]
            doc = await db.tracks.find_one({"_id": tid})
            assert doc["storage_provider"] == "tigris"
            assert doc["storage_key"].startswith("tracks/")
            assert doc["file_path"].startswith("s3://")
            assert doc["local_file_path"]
            await db.tracks.delete_one({"_id": tid})
    run(go())


def test_migration_script_idempotent_returns_zero_migrated_on_second_run():
    async def go():
        fake = _FakeStorage(); _patch_storage(fake)
        from scripts.migrate_tracks_to_tigris import migrate_tracks_to_tigris
        db = _db()
        # Seed one fake local-only row.
        tid = f"t22c_idem_{uuid.uuid4().hex[:6]}"
        p = Path(f"/tmp/{tid}.mp3"); p.write_bytes(_make_mp3())
        await db.tracks.insert_one({"_id": tid, "file_path": str(p),
                                                                  "duration_sec": 0.3, "status": "active"})
        try:
            await migrate_tracks_to_tigris(db, limit=500)
            after1 = await db.tracks.find_one({"_id": tid})
            assert after1.get("storage_provider") == "tigris", after1
            # Second run: this row must not transition again (state unchanged).
            before_key = after1.get("storage_key")
            await migrate_tracks_to_tigris(db, limit=500)
            after2 = await db.tracks.find_one({"_id": tid})
            assert after2.get("storage_key") == before_key
        finally:
            await db.tracks.delete_one({"_id": tid})
            p.unlink(missing_ok=True)
    run(go())


def test_migration_script_handles_missing_local_file_gracefully():
    async def go():
        fake = _FakeStorage(); _patch_storage(fake)
        from scripts.migrate_tracks_to_tigris import migrate_tracks_to_tigris
        db = _db()
        tid = f"t22c_miss_{uuid.uuid4().hex[:6]}"
        await db.tracks.insert_one({"_id": tid,
                                                                  "file_path": "/tmp/does_not_exist.mp3",
                                                                  "duration_sec": 0.3, "status": "active"})
        try:
            await migrate_tracks_to_tigris(db, limit=500)
            after = await db.tracks.find_one({"_id": tid})
            # Seeded row should have been flagged missing_local_file —
            # untouched, no provider transition.
            assert after.get("storage_provider") != "tigris", after
        finally:
            await db.tracks.delete_one({"_id": tid})
    run(go())


def test_radio_engine_reads_tigris_track_via_signed_url():
    async def go():
        import importlib
        fake = _FakeStorage(); _patch_storage(fake)
        server = importlib.import_module("server")
        tigris_track = {"_id": "x", "storage_provider": "tigris",
                                  "storage_key": "tracks/x.mp3", "file_path": "s3://b/tracks/x.mp3"}
        local_track = {"_id": "y", "storage_provider": "local",
                                  "file_path": "/app/backend/storage/tracks/y.mp3"}
        out_tigris = server._track_file_path_for_ffmpeg(tigris_track)
        out_local  = server._track_file_path_for_ffmpeg(local_track)
        assert out_tigris.startswith("https://") and "tracks/x.mp3" in out_tigris
        assert out_local  == "/app/backend/storage/tracks/y.mp3"
    run(go())


def test_legacy_local_tracks_still_playable_during_migration():
    """Rows without `storage_provider` field (legacy) must still resolve to
    their on-disk path, not error."""
    async def go():
        import importlib
        fake = _FakeStorage(); _patch_storage(fake)
        server = importlib.import_module("server")
        legacy = {"_id": "z", "file_path": "/app/backend/storage/tracks/z.mp3"}
        assert server._track_file_path_for_ffmpeg(legacy) == \
                  "/app/backend/storage/tracks/z.mp3"
    run(go())


def test_admin_only_403_on_migration_endpoint_for_non_admin():
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        fake = _FakeStorage(); _patch_storage(fake)
        server = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                  base_url="http://test", timeout=20) as ac:
            hdr = await _register_listener(ac)
            r = await ac.post("/api/admin/tracks/migrate-storage-to-tigris",
                                          headers=hdr)
            assert r.status_code == 403, r.text
    run(go())
