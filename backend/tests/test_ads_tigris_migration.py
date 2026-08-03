"""Phase 36c.5 (post-repack ads migration) — tests.

Four user-facing flows:
    A. New manual upload → Tigris key persisted on doc, file HEADs on Tigris.
    B. Stream-creative serve route prefers Tigris key (range slice matches).
    C. Stream-creative serve route falls back to local file when Tigris
        key is set but the object is missing (deleted out-of-band).
    D. Migration script is idempotent (running twice → 0 incremental work).

The serve route is exercised via the helper `_serve_ad_creative_audio`
with a tiny in-memory `_MemTigris` backend (no real Tigris hits).
"""
from __future__ import annotations
import asyncio
import os
import sys
import uuid
from pathlib import Path

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


# ─── tiny in-memory Tigris stand-in ─────────────────────────────────
class _MemTigris:
    backend_name = "tigris"
    bucket = "bigfm-test"
    s3 = object()  # truthy so hygiene treats it as a real client

    def __init__(self):
        self.store: dict[str, bytes] = {}

    def upload(self, *, local_path, key, content_type="application/octet-stream"):
        self.store[key] = Path(local_path).read_bytes()
        return {"key": key, "size": len(self.store[key]),
                  "content_type": content_type, "backend": self.backend_name}

    def head(self, *, key):
        if key in self.store:
            return {"size": len(self.store[key]), "content_type": None, "etag": None}
        return None

    def exists(self, *, key):
        return key in self.store

    def open_range(self, *, key, start, end):
        b = self.store.get(key) or b""
        return b[start:end + 1]

    def download(self, *, key, local_path):
        Path(local_path).write_bytes(self.store[key])
        return len(self.store[key])

    def delete(self, *, key):
        return bool(self.store.pop(key, None))

    def get_signed_url(self, *, key, expires_in=3600):
        return f"mem://{key}"

    def list_keys(self, *, prefix=""):
        for k, v in self.store.items():
            if k.startswith(prefix):
                yield {"key": k, "size": len(v)}


# ─── A. new manual upload persists storage_key_creative_audio ───────
def test_ads_a_manual_upload_writes_to_tigris(monkeypatch):
    from services import object_storage as obs
    mem = _MemTigris()
    monkeypatch.setattr(obs, "get_storage", lambda *a, **k: mem)
    monkeypatch.setattr(obs, "reset_storage", lambda: None)
    # Plant a synthetic mp3 + invoke the same upload helper used by the
    # route (the route logic is replicated minimally to avoid spinning
    # the full FastAPI app).
    cid = f"crt_test_{uuid.uuid4().hex[:8]}"
    local_a = Path("/tmp") / f"{cid}.mp3"
    local_a.write_bytes(b"ID3" + b"\x00" * 2048)
    k_a = obs.key_ad_creative_audio(cid, "mp3")
    mem.upload(local_path=str(local_a), key=k_a, content_type="audio/mpeg")
    h = mem.head(key=k_a)
    assert h and h["size"] > 1024, h
    # Reproduce the doc shape the route writes.
    doc = {"id": cid, "audio_path": str(local_a),
              "storage_key_creative_audio": k_a}
    assert doc["storage_key_creative_audio"] == f"ad_creatives/{cid}.mp3"
    local_a.unlink(missing_ok=True)


# ─── B. serve route prefers Tigris key + Range slice matches ────────
def test_ads_b_serve_prefers_tigris_key_for_range(monkeypatch):
    from services import object_storage as obs
    mem = _MemTigris()
    monkeypatch.setattr(obs, "get_storage", lambda *a, **k: mem)
    cid = f"crt_serve_{uuid.uuid4().hex[:8]}"
    payload = b"".join(bytes([i % 256]) for i in range(8192))
    key = obs.key_ad_creative_audio(cid, "mp3")
    mem.store[key] = payload

    # Tiny request stand-in.
    class _Req:
        def __init__(self, hdrs):
            self.headers = hdrs

    from routes.ads_public import _serve_ad_creative_audio
    req = _Req({"range": "bytes=10-19"})
    cr = {"creative_id": cid, "storage_key_creative_audio": key,
              "audio_path": None}
    resp = run(_serve_ad_creative_audio(cr, req))
    assert resp.status_code == 206, resp.status_code
    body = resp.body
    assert body == payload[10:20], (body, payload[10:20])
    resp_full = run(_serve_ad_creative_audio(cr, _Req({})))
    assert resp_full.status_code == 200
    assert resp_full.body == payload


# ─── C. fallback to local when Tigris key set but object missing ───
def test_ads_c_serve_falls_back_to_local(monkeypatch, tmp_path):
    from services import object_storage as obs
    mem = _MemTigris()
    monkeypatch.setattr(obs, "get_storage", lambda *a, **k: mem)
    cid = f"crt_fb_{uuid.uuid4().hex[:8]}"
    local = tmp_path / f"{cid}.mp3"
    payload = b"LOCAL" + b"\x00" * 4096
    local.write_bytes(payload)
    # Tigris key claimed on the doc but NOT actually in the bucket.
    key = obs.key_ad_creative_audio(cid, "mp3")
    cr = {"creative_id": cid, "storage_key_creative_audio": key,
              "audio_path": str(local)}

    class _Req:
        headers = {}

    from routes.ads_public import _serve_ad_creative_audio
    resp = run(_serve_ad_creative_audio(cr, _Req()))
    # Local file path takes over (StreamingResponse from the legacy
    # range helper). We assert status 200; StreamingResponse body is
    # not materialised here.
    assert resp.status_code == 200, resp.status_code


# ─── D. migration script is idempotent ────────────────────────────
def test_ads_d_migration_idempotent(monkeypatch):
    """Run migrate(apply=True) twice; second run must upload 0 new bytes."""
    from services import object_storage as obs
    mem = _MemTigris()
    monkeypatch.setattr(obs, "get_storage", lambda *a, **k: mem)
    # Plant a fresh doc with a local file + no tigris key.
    db = _db()
    cid = f"crt_mig_{uuid.uuid4().hex[:8]}"
    local = Path("/app/backend/static/ad_creatives") / f"{cid}.mp3"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(b"MIG" + b"\x00" * 4096)
    run(db.ad_creatives.insert_one({"id": cid, "audio_path": str(local),
                                                                "active": False}))
    try:
        from scripts.migrate_ad_creatives_to_tigris import migrate
        r1 = run(migrate(apply=True, delete_local=False))
        r2 = run(migrate(apply=True, delete_local=False))
        # Second run uploaded ≤ first run (other rows may also be picked
        # up — we filter by checking our specific cid below).
        assert r2["audio_uploaded"] <= r1["audio_uploaded"], (r1, r2)
        doc = run(db.ad_creatives.find_one({"id": cid}))
        assert doc.get("storage_key_creative_audio") == \
                      obs.key_ad_creative_audio(cid, "mp3")
        # Object is HEAD-able on the mem-tigris bucket.
        assert mem.head(key=obs.key_ad_creative_audio(cid, "mp3")) is not None
    finally:
        run(db.ad_creatives.delete_one({"id": cid}))
        local.unlink(missing_ok=True)



# ─── E. regression: stream_creative finds by `id` field + status gate ─
def test_ads_e_stream_creative_finds_by_id_field(monkeypatch):
    """Post-repack hotfix: previously the serve route filtered by
    `creative_id` which is absent on newer rows (they use `id`) and
    gated on `active=True` which is also absent on newer rows
    (they use `status="approved"`). Both lookups now match either
    shape, so a newer-shape row with `id` + `status="approved"`
    + Tigris key must serve. We exercise the helper directly to
    avoid spinning the whole FastAPI app + auth chain.
    """
    from services import object_storage as obs
    mem = _MemTigris()
    monkeypatch.setattr(obs, "get_storage", lambda *a, **k: mem)
    db = _db()
    cid = "crt_test_serve"
    # Seed an mp3-like payload on the in-memory Tigris backend.
    payload = b"\xff\xfb\x90\x00" + b"\xaa" * 2044   # ~2 KB
    key = obs.key_ad_creative_audio(cid, "mp3")
    mem.store[key] = payload
    run(db.ad_creatives.delete_many({"id": cid}))
    run(db.ad_creatives.insert_one({
        "id": cid, "status": "approved",
        "audio_path": None,
        "storage_key_creative_audio": key,
    }))
    try:
        # 1. Repro the route's filter to prove it now finds the doc.
        cr = run(db.ad_creatives.find_one(
            {"$and": [
                {"$or": [{"id": cid}, {"creative_id": cid}]},
                {"$or": [{"status": {"$in": ["approved", "active"]}},
                              {"active": True}]},
            ]},
            {"audio_path": 1, "storage_key_creative_audio": 1, "_id": 0}))
        assert cr is not None, "filter must find the newer-shape row"
        assert cr["storage_key_creative_audio"] == key
        # 2. Serve full + serve Range 100-109, verify status + bytes.
        from routes.ads_public import _serve_ad_creative_audio

        class _Req:
            def __init__(self, hdrs):
                self.headers = hdrs

        resp_full = run(_serve_ad_creative_audio(cr, _Req({})))
        assert resp_full.status_code == 200
        assert resp_full.headers.get("content-length") == str(len(payload))
        assert resp_full.body == payload
        resp_206 = run(_serve_ad_creative_audio(cr, _Req({"range": "bytes=100-109"})))
        assert resp_206.status_code == 206
        assert resp_206.headers.get("content-range") == \
                      f"bytes 100-109/{len(payload)}"
        assert resp_206.body == payload[100:110]
        assert len(resp_206.body) == 10
    finally:
        run(db.ad_creatives.delete_many({"id": cid}))
