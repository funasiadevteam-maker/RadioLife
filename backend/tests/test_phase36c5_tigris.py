"""Phase 36c.5 — ObjectStorage abstraction + Tigris migration tests.

Mix of unit tests (pure local) and live Tigris tests (against the configured
bucket). Live tests are skipped if STORAGE_BACKEND != 'tigris'.
"""
from __future__ import annotations
import asyncio, io, os, shutil, sys, time, uuid
from pathlib import Path

import pytest

sys.path.insert(0, "/app/backend")

# Ensure backend .env values are loaded for the live tests.
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception: pass

from services import object_storage as obs    # noqa: E402

TIGRIS_LIVE = (os.environ.get("STORAGE_BACKEND") or "").lower() == "tigris"


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


# ─── 1. LocalDiskStorage round-trip ─────────────────────────
def test_36c5_01_local_disk_round_trip(tmp_path):
    s = obs.LocalDiskStorage(root=str(tmp_path / "store"))
    src = tmp_path / "src.bin"; src.write_bytes(b"local-disk-payload")
    meta = s.upload(local_path=str(src), key="x/y.bin", content_type="application/octet-stream")
    assert meta["backend"] == "local"
    assert s.exists(key="x/y.bin")
    h = s.head(key="x/y.bin"); assert h["size"] == 18
    out = tmp_path / "out.bin"
    s.download(key="x/y.bin", local_path=str(out))
    assert out.read_bytes() == b"local-disk-payload"
    # Range read
    buf = s.open_range(key="x/y.bin", start=0, end=4)
    assert buf == b"local"
    assert s.delete(key="x/y.bin") is True
    assert not s.exists(key="x/y.bin")


# ─── 2. Tigris round-trip (live) ────────────────────────────
@pytest.mark.skipif(not TIGRIS_LIVE, reason="STORAGE_BACKEND!=tigris")
def test_36c5_02_tigris_round_trip(tmp_path):
    s = obs.TigrisStorage()
    src = tmp_path / "src.bin"; src.write_bytes(b"tigris-live-payload")
    k = f"_test/{uuid.uuid4().hex}.bin"
    s.upload(local_path=str(src), key=k, content_type="application/octet-stream")
    try:
        assert s.exists(key=k)
        h = s.head(key=k); assert h["size"] == 19
        out = tmp_path / "out.bin"; s.download(key=k, local_path=str(out))
        assert out.read_bytes() == b"tigris-live-payload"
        buf = s.open_range(key=k, start=0, end=5)
        assert buf == b"tigris"
    finally:
        s.delete(key=k)
    assert not s.exists(key=k)


# ─── 3. Signed URL respects expiry + serves content (live) ─
@pytest.mark.skipif(not TIGRIS_LIVE, reason="STORAGE_BACKEND!=tigris")
def test_36c5_03_signed_url_get_works(tmp_path):
    import urllib.request
    s = obs.TigrisStorage()
    src = tmp_path / "u.txt"; src.write_text("signed-url-content")
    k = f"_test/{uuid.uuid4().hex}.txt"
    s.upload(local_path=str(src), key=k, content_type="text/plain")
    try:
        url = s.get_signed_url(key=k, expires_in=60)
        assert url.startswith("https://"), url
        assert "X-Amz-Signature" in url or "Signature=" in url
        with urllib.request.urlopen(url, timeout=15) as r:
            body = r.read()
        assert body == b"signed-url-content"
    finally:
        s.delete(key=k)


# ─── 4. HEAD + Range on signed URL preserves S3 contract (live) ─
@pytest.mark.skipif(not TIGRIS_LIVE, reason="STORAGE_BACKEND!=tigris")
def test_36c5_04_range_get_returns_partial(tmp_path):
    import urllib.request
    s = obs.TigrisStorage()
    payload = b"ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    src = tmp_path / "r.bin"; src.write_bytes(payload)
    k = f"_test/{uuid.uuid4().hex}.bin"
    s.upload(local_path=str(src), key=k, content_type="application/octet-stream")
    try:
        url = s.get_signed_url(key=k, expires_in=60)
        req = urllib.request.Request(url, headers={"Range": "bytes=2-7"})
        with urllib.request.urlopen(req, timeout=15) as r:
            assert r.status == 206
            assert r.read() == b"CDEFGH"
            assert r.headers.get("Content-Range") == f"bytes 2-7/{len(payload)}"
    finally:
        s.delete(key=k)


# ─── 5. Factory respects STORAGE_BACKEND env var ──────────
def test_36c5_05_factory_dispatch():
    obs.reset_storage()
    saved = os.environ.get("STORAGE_BACKEND")
    try:
        os.environ["STORAGE_BACKEND"] = "local"; obs.reset_storage()
        assert obs.get_storage().backend_name == "local"
        if TIGRIS_LIVE:
            os.environ["STORAGE_BACKEND"] = "tigris"; obs.reset_storage()
            assert obs.get_storage().backend_name == "tigris"
    finally:
        if saved is None: os.environ.pop("STORAGE_BACKEND", None)
        else: os.environ["STORAGE_BACKEND"] = saved
        obs.reset_storage()


# ─── 6. Key builders are deterministic + collision-free ────
def test_36c5_06_key_builders_canonical():
    assert obs.key_episode_audio("ch_1", "pep_x") == "podcasts/channels/ch_1/pep_x/audio.mp3"
    assert obs.key_episode_video("ch_1", "pep_x") == "podcasts/channels/ch_1/pep_x/video.mp4"
    assert obs.key_recording_mixed_audio("prs_y") == "podcasts/recordings/prs_y/mixed.mp3"
    assert obs.key_recording_mixed_video("prs_y") == "podcasts/recordings/prs_y/mixed.mp4"
    assert obs.key_recording_participant_audio("prs_y", "prp_a") == "podcasts/recordings/prs_y/prp_a/audio.mp3"
    assert obs.key_music_track("tr_z") == "music/tracks/tr_z.mp3"
    assert obs.key_rj("rj_1") == "rj/rj_1.mp3"
    assert obs.key_ad_creative_audio("ac_1") == "ad_creatives/ac_1.mp3"
    assert obs.key_ad_creative_image("ac_1", "webp") == "ad_creatives/ac_1.webp"
    assert obs.key_chapters_json("pep_x") == "chapters/pep_x.json"
    assert obs.key_transcript_srt("pep_x") == "transcripts/pep_x.srt"


# ─── 7. Path traversal protection on local backend ──────
def test_36c5_07_local_blocks_path_traversal(tmp_path):
    s = obs.LocalDiskStorage(root=str(tmp_path / "store"))
    src = tmp_path / "src.bin"; src.write_bytes(b"x")
    with pytest.raises(ValueError):
        s.upload(local_path=str(src), key="../../etc/passwd",
                          content_type="text/plain")


# ─── 8. Migration script: dry-run does not mutate ──────
def test_36c5_08_migrate_dry_run_no_mutation(tmp_path):
    """Use a temp local root so we can prove the dry-run path doesn't
    delete files or upload to Tigris."""
    import subprocess
    fake_root = tmp_path / "store"
    (fake_root / "tracks").mkdir(parents=True)
    sample = fake_root / "tracks" / "tr_dry.mp3"
    sample.write_bytes(b"\xff\xfb" + b"\x00" * 1000)
    env = os.environ.copy()
    env["STORAGE_LOCAL_ROOT"] = str(fake_root)
    r = subprocess.run(
        ["python3", "/app/scripts/migrate_local_to_tigris.py", "--dry-run"],
        env=env, capture_output=True, timeout=60)
    out = r.stdout.decode()
    assert r.returncode == 0, r.stderr.decode()
    assert "DRY-RUN" in out
    assert "tracks/tr_dry.mp3" in out
    assert "music/tracks/tr_dry.mp3" in out    # canonical key in report
    # The file must NOT have been deleted (dry-run is read-only).
    assert sample.exists()


# ─── 9. Tigris admin status endpoint shape (no live backend roundtrip) ─
def test_36c5_09_admin_status_endpoint_shape():
    """Verify the admin endpoint is registered and returns the expected
    envelope under live Tigris. (Auth bypassed via dependency override.)"""
    if not TIGRIS_LIVE: pytest.skip("STORAGE_BACKEND!=tigris")
    import server, auth as au
    from fastapi.testclient import TestClient
    server.app.dependency_overrides[au.require_admin] = lambda: {
        "user_id": "u_test", "role": "admin"}
    try:
        with TestClient(server.app) as cli:
            r = cli.get("/api/admin/podcasts/integrations/tigris/status")
    finally:
        server.app.dependency_overrides.pop(au.require_admin, None)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["backend"] == "tigris"
    assert d["is_live"] is True
    assert d["bucket"] == "bigfm-storage"
    assert d["endpoint"]
    assert "total_objects" in d and "total_size_bytes" in d
    assert "last_check_at" in d


# ─── 10. Tigris fallback on the audio.mp3 proxy route ─────
@pytest.mark.skipif(not TIGRIS_LIVE, reason="STORAGE_BACKEND!=tigris")
def test_36c5_10_audio_proxy_route_streams_from_tigris(tmp_path):
    """Upload a small mp3 to Tigris under the canonical episode key, insert
    a podcast_episodes row WITHOUT a local file present, and hit the public
    audio.mp3 proxy route on the live backend (port 8001) — should stream
    from Tigris and honor Range. (TestClient hits an asyncio loop-mismatch
    with Motor when server.app is imported; the live backend has no such
    issue.)"""
    import httpx, subprocess as sp
    from motor.motor_asyncio import AsyncIOMotorClient
    db_name = os.environ.get("DB_NAME") or "bigfm"
    db = AsyncIOMotorClient(os.environ.get("MONGO_URL") or
                                                  "mongodb://localhost:27017")[db_name]
    s = obs.TigrisStorage()
    src = tmp_path / "a.mp3"
    sp.run(["ffmpeg", "-y", "-f", "lavfi",
                  "-i", "sine=frequency=440:duration=1",
                  "-codec:a", "libmp3lame", "-b:a", "64k", str(src)],
                  check=True, capture_output=True, timeout=15)
    payload_size = src.stat().st_size
    ep_id = f"pep_tig_{uuid.uuid4().hex[:10]}"
    ch_id = f"ch_tig_{uuid.uuid4().hex[:6]}"
    key    = obs.key_episode_audio(ch_id, ep_id)
    s.upload(local_path=str(src), key=key, content_type="audio/mpeg")
    try:
        run(db.podcast_episodes.insert_one({
            "id": ep_id, "channel_id": ch_id,
            "storage_path": "/nonexistent/path",
            "title": "Tigris proxy probe",
            "audio_url": f"/api/podcasts/episodes/{ep_id}/audio.mp3",
            "publish_status": "draft",
            "created_at": "2026-06-04T00:00:00Z"}))
        with httpx.Client(base_url="http://localhost:8001", timeout=15) as cli:
            r1 = cli.head(f"/api/podcasts/episodes/{ep_id}/audio.mp3")
            r2 = cli.get(f"/api/podcasts/episodes/{ep_id}/audio.mp3",
                                  headers={"Range": "bytes=0-127"})
        assert r1.status_code == 200, r1.text
        assert r1.headers.get("content-length") == str(payload_size)
        assert r1.headers.get("accept-ranges") == "bytes"
        assert r2.status_code == 206, r2.text
        assert r2.headers.get("content-range") == f"bytes 0-127/{payload_size}"
        assert len(r2.content) == 128
    finally:
        run(db.podcast_episodes.delete_one({"id": ep_id}))
        s.delete(key=key)


# ─── 11. List_keys works (used by hygiene + status endpoint) ─
@pytest.mark.skipif(not TIGRIS_LIVE, reason="STORAGE_BACKEND!=tigris")
def test_36c5_11_list_keys_paginates_and_filters_by_prefix(tmp_path):
    s = obs.TigrisStorage()
    base = tmp_path / "lk.bin"; base.write_bytes(b"x")
    pfx = f"_list_{uuid.uuid4().hex[:8]}"
    keys = [f"{pfx}/a.bin", f"{pfx}/b.bin", f"{pfx}/sub/c.bin"]
    for k in keys: s.upload(local_path=str(base), key=k, content_type="application/octet-stream")
    try:
        found = [it["key"] for it in s.list_keys(prefix=pfx + "/")]
        assert set(keys).issubset(set(found))
        # Sub-prefix narrows correctly.
        sub_found = [it["key"] for it in s.list_keys(prefix=f"{pfx}/sub/")]
        assert sub_found == [f"{pfx}/sub/c.bin"]
    finally:
        for k in keys: s.delete(key=k)


# ─── 12. Migration mapper recognizes canonical local paths ──
def test_36c5_12_migration_mapper_recognition():
    """Spot-check the path → canonical-key mapping in the migration script."""
    sys.path.insert(0, "/app")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_mig", "/app/scripts/migrate_local_to_tigris.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    cases = [
        (Path("tracks/tr_x.mp3"),                                                                            "music/tracks/tr_x.mp3"),
        (Path("rj/rj_1.mp3"),                                                                                      "rj/rj_1.mp3"),
        (Path("chapters/pep_z.json"),                                                                "chapters/pep_z.json"),
        (Path("transcripts/pep_z.srt"),                                                              "transcripts/pep_z.srt"),
        (Path("podcasts/recordings/prs_x/host.mp3"),                                "podcasts/recordings/prs_x/host/audio.mp3"),
        (Path("podcasts/recordings/prs_x/host_video.mp4"),                        "podcasts/recordings/prs_x/host/video.mp4"),
        (Path("podcasts/recordings/prs_x/mixed.mp3"),                                "podcasts/recordings/prs_x/mixed.mp3"),
        (Path("podcasts/recordings/prs_x/mixed.mp4"),                                "podcasts/recordings/prs_x/mixed.mp4"),
        (Path("podcasts/recordings/prs_x/prp_aaaa.mp3"),                          "podcasts/recordings/prs_x/prp_aaaa/audio.mp3"),
        (Path("podcasts/recordings/prs_x/prp_aaaa_video.mp4"),              "podcasts/recordings/prs_x/prp_aaaa/video.mp4"),
        (Path("ad_creatives/ac_q.mp3"),                                                              "ad_creatives/ac_q.mp3"),
        (Path("ad_creatives/ac_q.webp"),                                                          "ad_creatives/ac_q.webp"),
        (Path("podcasts/recordings/prs_x/host_video_raw.webm"),              None),    # transcode intermediate
        (Path("station_ids/whatever.mp3"),                                                      None),    # unmapped
    ]
    for rel, expected in cases:
        k, _ = m._key_for(rel)
        assert k == expected, f"{rel} → expected {expected!r} got {k!r}"



# ─── 13. Hygiene Tigris orphan pruner is dry-run safe + correct shape ──
@pytest.mark.skipif(not TIGRIS_LIVE, reason="STORAGE_BACKEND!=tigris")
def test_36c5_13_hygiene_tigris_orphan_dry_run(tmp_path):
    """Upload an unreferenced object under _test/ prefix (transient, 1-hour
    TTL) — but mtime is just-now, so it must NOT be marked deleted even
    in dry-run. Then verify the returned envelope shape is correct."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import hygiene18c
    s = obs.TigrisStorage()
    src = tmp_path / "o.bin"; src.write_bytes(b"orphan-payload")
    k = f"_test/{uuid.uuid4().hex}.bin"
    s.upload(local_path=str(src), key=k, content_type="application/octet-stream")
    try:
        db = AsyncIOMotorClient(os.environ.get("MONGO_URL") or
                                                      "mongodb://localhost:27017")[
            os.environ.get("DB_NAME") or "bigfm"]
        r = run(hygiene18c.tick_tigris_orphans(db, dry_run=True, ttl_hours=168))
        assert r.get("kind") == "tigris_orphans"
        assert r.get("dry_run") is True
        assert "scanned" in r and r["scanned"] >= 1
        assert "deleted_count" in r and "freed_bytes" in r
        assert "ttl_hours" in r
        # Just-uploaded objects must NOT be deleted yet (transient 1h cutoff).
        assert s.exists(key=k)
    finally:
        s.delete(key=k)


# ─── 14. Hygiene Tigris orphan pruner skips non-tigris backends ─────
def test_36c5_14_hygiene_orphan_skips_local_backend():
    """When STORAGE_BACKEND != tigris, the pruner must early-return with
    {skipped: True} and not crash importing boto3."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import hygiene18c
    saved = os.environ.get("STORAGE_BACKEND")
    try:
        os.environ["STORAGE_BACKEND"] = "local"; obs.reset_storage()
        db = AsyncIOMotorClient(os.environ.get("MONGO_URL") or
                                                      "mongodb://localhost:27017")[
            os.environ.get("DB_NAME") or "bigfm"]
        r = run(hygiene18c.tick_tigris_orphans(db, dry_run=True))
        assert r.get("skipped") is True
        assert "STORAGE_BACKEND" in (r.get("reason") or "")
    finally:
        if saved is None: os.environ.pop("STORAGE_BACKEND", None)
        else: os.environ["STORAGE_BACKEND"] = saved
        obs.reset_storage()
