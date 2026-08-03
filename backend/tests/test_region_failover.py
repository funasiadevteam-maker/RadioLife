"""Phase 13d — region awareness + db routing + circuit breaker + cache."""
from __future__ import annotations
import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"
# Cache-Control headers can be rewritten by upstream proxies (K8s ingress,
# Cloudflare) — for the local middleware tests we hit the backend
# directly. The Cloudflare rewrite is a HUMAN-step in
# integration_setup.md.
LOCAL_API = "http://localhost:8001/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")
DB = MongoClient(MONGO_URL)[DB_NAME]


def _login(email: str, pw: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email,
                                                              "password": pw}, timeout=10)
    assert r.status_code == 200, r.text[:200]
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ════════════════════════════════════════════════════════════════════
# 1. middleware emits X-BigFM-Region on every response
# ════════════════════════════════════════════════════════════════════
def test_region_middleware_adds_response_header():
    r = requests.get(f"{API}/channels", timeout=10)
    assert r.status_code == 200
    assert "x-bigfm-region" in {k.lower() for k in r.headers}
    assert r.headers.get("X-BigFM-Region") in {"ae-uae", "us-east",
                                                                  "eu-west", "sg-asia"}
    assert r.headers.get("X-BigFM-Region-Role") in {"primary", "replica"}


# ════════════════════════════════════════════════════════════════════
# 2. db_routing chooses secondary_preferred for analytics collections
# ════════════════════════════════════════════════════════════════════
def test_db_routing_secondary_preferred_for_analytics_route():
    from services.db_routing import (get_collection,
                                                  SECONDARY_PREFERRED_COLLECTIONS)
    # Pick one of the well-known analytics collections.
    name = "admin_analytics_overview"
    assert name in SECONDARY_PREFERRED_COLLECTIONS
    coll = get_collection(name)
    rp = coll.read_preference
    # pymongo names the enum 'SecondaryPreferred' / 'Primary' (PascalCase).
    assert rp.name == "SecondaryPreferred", rp.name


# ════════════════════════════════════════════════════════════════════
# 3. db_routing keeps `primary` for write routes
# ════════════════════════════════════════════════════════════════════
def test_db_routing_primary_for_write_routes():
    from services.db_routing import get_collection
    coll = get_collection("users")
    assert coll.read_preference.name == "Primary"


# ════════════════════════════════════════════════════════════════════
# 4. /admin/region/status requires admin auth
# ════════════════════════════════════════════════════════════════════
def test_region_health_endpoint_admin_only():
    r = requests.get(f"{API}/admin/region/status", timeout=10)
    assert r.status_code in (401, 403)


# ════════════════════════════════════════════════════════════════════
# 5. /admin/region/status returns the expected status shape
# ════════════════════════════════════════════════════════════════════
def test_region_health_returns_status_shape(admin_session):
    # Probe first so a row exists.
    admin_session.post(f"{API}/admin/region/probe", timeout=10)
    r = admin_session.get(f"{API}/admin/region/status", timeout=10)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    for k in ("region", "role", "mongo_primary_ok",
                  "active_cluster", "failover_count_24h", "history"):
        assert k in body, f"missing key {k} in {body}"
    assert body["region"]
    assert body["role"] in ("primary", "replica")
    assert isinstance(body["history"], list)


# ════════════════════════════════════════════════════════════════════
# 6. circuit breaker flips active cluster to 'replica' when primary down
# ════════════════════════════════════════════════════════════════════
def test_circuit_breaker_routes_to_replica_when_primary_down(monkeypatch):
    """Simulate primary write failure → breaker flips to replica.

    Strategy: seed the region_status row with an already-old
    primary_first_fail_at so the failure threshold (30s) is already
    exceeded, then run probe_once against a wrapped DB where ONLY
    the heartbeat insert raises.
    """
    from datetime import timedelta
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import db_routing, region_health

    region = "ae-uae"
    # Seed: pretend primary has been failing for > 30s.
    DB.region_status.update_one(
        {"region": region},
        {"$set": {"primary_first_fail_at":
                      datetime.now(timezone.utc) - timedelta(seconds=60),
                      "primary_down": False,
                      "region": region, "role": "primary"}},
        upsert=True)

    # Provide a fake replica list so set_active_cluster('replica') works.
    class _FakeRep:
        def get_default_database(self):
            class _D:
                def __getitem__(self_, n):
                    class _C:
                        async def find_one(self, *a, **kw):
                            return None
                    return _C()
            return _D()
    monkeypatch.setattr(db_routing, "replica_clients", lambda: [_FakeRep()])
    db_routing.set_active_cluster("primary")

    # Wrap the real motor DB so ONLY heartbeat insert blows up.
    cli = AsyncIOMotorClient(MONGO_URL)

    class _BoomHB:
        async def insert_one(self, doc):
            raise RuntimeError("primary unreachable (simulated)")

    class _Wrap:
        def __init__(self, real):
            self.real = real

        def __getitem__(self, name):
            if name == region_health._HEARTBEAT_COLL:
                return _BoomHB()
            return self.real[name]

    try:
        _run(region_health.probe_once(_Wrap(cli[DB_NAME])))
        assert db_routing.active_cluster() == "replica"
    finally:
        DB.region_status.delete_one({"region": region})
        DB.region_failover_log.delete_many({"region": region})
        db_routing.set_active_cluster("primary")
        cli.close()


# ════════════════════════════════════════════════════════════════════
# 7. breaker recovers — flip back to 'primary' when probe ok
# ════════════════════════════════════════════════════════════════════
def test_circuit_breaker_recovers_when_primary_returns(monkeypatch):
    from services import db_routing, region_health

    # Pre-mark breaker open.
    region = "ae-uae"
    DB.region_status.update_one(
        {"region": region},
        {"$set": {"primary_down": True,
                      "primary_first_fail_at":
                          datetime.now(timezone.utc)}},
        upsert=True)
    # Make replica list non-empty so set_active_cluster('replica') had effect.

    class _FakeRep:
        def get_default_database(self):
            class _D:
                def __getitem__(self_, n):
                    class _C:
                        async def find_one(self, *a, **kw):
                            return None
                    return _C()
            return _D()
    monkeypatch.setattr(db_routing, "replica_clients", lambda: [_FakeRep()])
    db_routing.set_active_cluster("replica")
    assert db_routing.active_cluster() == "replica"
    # Probe against the real local DB → primary insert succeeds → breaker
    # closes.
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(MONGO_URL)
    try:
        _run(region_health.probe_once(cli[DB_NAME]))
    finally:
        cli.close()
    assert db_routing.active_cluster() == "primary"
    DB.region_status.delete_one({"region": region})


# ════════════════════════════════════════════════════════════════════
# 8. pending writes queue + replay
# ════════════════════════════════════════════════════════════════════
def test_pending_writes_queue_on_primary_outage(monkeypatch):
    from services import db_routing, region_health

    class _FakeRep:
        def __init__(self):
            self._coll = MongoClient(MONGO_URL)[DB_NAME]["pending_writes"]

        def get_default_database(self):
            client = self
            class _D:
                def __getitem__(self_, n):
                    if n != "pending_writes":
                        raise KeyError(n)
                    # Wrap pymongo coll as async-ish.
                    class _AC:
                        async def update_one(self, q, upd, upsert=False):
                            return client._coll.update_one(q, upd,
                                                                          upsert=upsert)
                        def find(self, *a, **kw):
                            async def _gen():
                                for d in client._coll.find(*a, **kw):
                                    yield d
                            return _gen()
                    return _AC()
            return _D()

    fake = _FakeRep()
    monkeypatch.setattr(db_routing, "replica_clients", lambda: [fake])
    # Queue one pending write.
    key = _run(region_health.queue_pending_write(
        DB, surface="test_surface",
        payload={"hello": "world"},
        idempotency_key=f"pw_qa_{uuid.uuid4().hex[:6]}"))
    row = DB.pending_writes.find_one({"_id": key})
    assert row is not None and row["surface"] == "test_surface"
    assert row["replayed"] is False
    # Replay.
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(MONGO_URL)
    try:
        out = _run(region_health.replay_pending_writes(cli[DB_NAME]))
    finally:
        cli.close()
    assert out["replayed"] >= 1
    row2 = DB.pending_writes.find_one({"_id": key})
    assert row2["replayed"] is True
    DB.pending_writes.delete_one({"_id": key})


# ════════════════════════════════════════════════════════════════════
# 9. critical write routes are flagged for 503 (no queueing)
# ════════════════════════════════════════════════════════════════════
def test_pending_writes_critical_routes_return_503():
    from services.region_health import critical_write_blocked
    assert critical_write_blocked("/api/auth/login") is True
    assert critical_write_blocked("/api/billing/checkout") is True
    assert critical_write_blocked("/api/channels") is False
    assert critical_write_blocked("/api/admin/retention/cohorts") is False


# ════════════════════════════════════════════════════════════════════
# 10. SWR header on public routes
# ════════════════════════════════════════════════════════════════════
def test_cache_control_public_routes_carry_swr_header():
    r = requests.get(f"{LOCAL_API}/channels", timeout=10)
    cc = r.headers.get("Cache-Control", "")
    assert "stale-while-revalidate" in cc, cc
    assert "max-age=60" in cc
    assert "s-maxage=300" in cc


# ════════════════════════════════════════════════════════════════════
# 11. no-store header on private routes
# ════════════════════════════════════════════════════════════════════
def test_cache_control_private_routes_carry_no_store():
    r = requests.get(f"{LOCAL_API}/admin/region/status", timeout=10)
    assert r.status_code in (401, 403)
    cc = r.headers.get("Cache-Control", "")
    assert "no-store" in cc, cc


# ════════════════════════════════════════════════════════════════════
# 12. ETag emitted + 304 on If-None-Match match
# ════════════════════════════════════════════════════════════════════
def test_etag_emitted_on_cacheable_routes_and_304_on_match():
    r = requests.get(f"{LOCAL_API}/channels", timeout=10)
    etag = r.headers.get("ETag")
    assert etag and etag.startswith('W/"'), f"missing/invalid etag: {etag}"
    r2 = requests.get(f"{LOCAL_API}/channels",
                              headers={"If-None-Match": etag}, timeout=10)
    assert r2.status_code == 304, r2.status_code
    assert r2.headers.get("X-BigFM-Region")


# ════════════════════════════════════════════════════════════════════
# 13. (13c tidy-up #1) Cohort filter by `city` resolves correctly
# ════════════════════════════════════════════════════════════════════
def test_cohort_filter_by_city_resolves(admin_session):
    tag = uuid.uuid4().hex[:6]
    uid = f"u_p13d_city_{tag}"
    DB.users.insert_one({"user_id": uid,
                                    "preference_vector": {"city": "Sharjah"}})
    try:
        r = admin_session.post(f"{API}/admin/retention/cohorts", json={
            "name": f"QA City {tag}",
            "filter_dsl": {"op": "and", "conditions": [
                {"field": "city", "op": "eq", "value": "Sharjah"}]}},
            timeout=10)
        assert r.status_code == 200, r.text[:200]
        cid = r.json()["id"]
        try:
            aud = admin_session.get(
                f"{API}/admin/retention/cohorts/{cid}/audience?limit=200",
                timeout=10)
            assert aud.status_code == 200, aud.text[:200]
            sample = aud.json()["sample_user_ids"]
            assert uid in sample or aud.json()["audience_size"] >= 1
        finally:
            DB.audience_cohorts.delete_one({"id": cid})
    finally:
        DB.users.delete_one({"user_id": uid})


# ════════════════════════════════════════════════════════════════════
# 14. (13c tidy-up #2) played_artist_x_times accepts both `count` and `x`
# ════════════════════════════════════════════════════════════════════
def test_played_artist_trigger_accepts_x_alias(admin_session):
    from datetime import timedelta
    artist = f"art_alias_{uuid.uuid4().hex[:6]}"
    uid = f"u_p13d_alias_{uuid.uuid4().hex[:6]}"
    DB.users.insert_one({"user_id": uid})
    now = datetime.now(timezone.utc)
    DB.playback_logs.insert_many([
        {"user_id": uid, "event": "play_start", "artist_id": artist,
          "timestamp": now - timedelta(hours=k)} for k in range(4)])
    try:
        # Use the `x` alias (not `count`).
        r = admin_session.post(
            f"{API}/admin/retention/triggers/dry_run",
            json={"trigger": "played_artist_x_times",
                    "params": {"artist_id": artist, "x": 3, "days": 14}},
            timeout=10)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert uid in body["sample_user_ids"]
        # Reasoning text should still mention the count threshold.
        assert "3" in body["reasoning"]
    finally:
        DB.users.delete_one({"user_id": uid})
        DB.playback_logs.delete_many({"artist_id": artist})
