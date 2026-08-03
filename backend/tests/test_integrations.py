"""Phase 12d — Live integration switchers + tests."""
from __future__ import annotations
import asyncio
import datetime
import logging
import os
import tempfile
from datetime import datetime as dt, timedelta, timezone
from unittest.mock import patch, AsyncMock

import httpx
import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

# Ensure backend .env is in os.environ (GOOGLE_APPLICATION_CREDENTIALS,
# MONGO_URL, etc.) so creds_present() detects the same paths the live
# server sees.
load_dotenv("/app/backend/.env")


ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")
MONGO = MongoClient(MONGO_URL)
DB = MONGO[DB_NAME]


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, r.text[:200]
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def free_session():
    return _login("test@bigfm.dubai", "TestUser123!")


def _aio() -> AsyncIOMotorClient:
    return AsyncIOMotorClient(MONGO_URL)


def _run(coro_factory):
    """Run an async coroutine in a fresh event loop. Accepts either
    a coroutine or a 0-arg callable that returns a coroutine; the
    callable form lets each call build a Motor client bound to the
    new loop (avoids 'future belongs to a different loop')."""
    loop = asyncio.new_event_loop()
    try:
        coro = coro_factory() if callable(coro_factory) else coro_factory
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _with_db(work):
    """work: async fn(db) -> result. Builds a fresh Motor client per
    call so we never cross event loops."""
    async def _run_in_loop():
        cli = AsyncIOMotorClient(MONGO_URL)
        try:
            return await work(cli[DB_NAME])
        finally:
            cli.close()
    return _run(_run_in_loop)


# ─── 1. Status endpoint admin-only ───────────────────────────────────
def test_integration_status_endpoint_admin_only_403(free_session):
    r = free_session.get(f"{API}/admin/integrations/status", timeout=10)
    assert r.status_code == 403, r.text[:200]


# ─── 2. Maps probe handles 403 gracefully ────────────────────────────
def test_maps_probe_handles_403_gracefully(admin_session):
    """Hits the real probe endpoint. The preview env has Maps APIs
    disabled (403 on Routes / Places / Weather / Geocoding). Endpoint
    must return 200 with an api_health map showing the per-sub-API
    status (some `forbidden`, some `missing_sa_unsupported`), never a
    500."""
    r = admin_session.get(f"{API}/admin/integrations/maps/probe",
                                  timeout=15)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert "api_health" in body
    # Either live mode (4 sub-APIs all 'ok') or any non-ok value;
    # crucially, no crash.
    for k in ("routes", "places", "weather", "geocoding"):
        # Sub-key may be absent if MockMapsClient is active (api_health={}).
        # That's also a valid no-crash outcome.
        assert k in body["api_health"] or body["api_health"] == {}


# ─── 3. Apple PassKit: returns .pkpass bytes when creds set ──────────
@pytest.fixture
def _apple_test_certs():
    """Generate a self-signed cert + key + a fake WWDR cert in a temp
    dir so build_apple_pass can sign without real Apple infra."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import hashes, serialization

    def _gen_cert():
        key = rsa.generate_private_key(public_exponent=65537,
                                                    key_size=2048)
        subj = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "QA"),
        ])
        cert = (x509.CertificateBuilder()
                    .subject_name(subj).issuer_name(subj)
                    .public_key(key.public_key())
                    .serial_number(x509.random_serial_number())
                    .not_valid_before(dt.now(timezone.utc))
                    .not_valid_after(
                        dt.now(timezone.utc) + timedelta(days=365))
                    .sign(key, hashes.SHA256()))
        return key, cert

    key, cert = _gen_cert()
    wwdr_key, wwdr_cert = _gen_cert()

    tmp = tempfile.mkdtemp(prefix="apple_pass_qa_")
    cp = os.path.join(tmp, "pass.pem")
    kp = os.path.join(tmp, "key.pem")
    wp = os.path.join(tmp, "wwdr.pem")
    with open(cp, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(kp, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()))
    with open(wp, "wb") as f:
        f.write(wwdr_cert.public_bytes(serialization.Encoding.PEM))
    yield {"cert": cp, "key": kp, "wwdr": wp}
    import shutil; shutil.rmtree(tmp, ignore_errors=True)


def test_apple_pass_returns_pkpass_bytes_when_creds_set(_apple_test_certs):
    from services import wallet_passes as wp
    env = {
        "APPLE_PASS_TYPE_ID": "pass.qa.bigfm.test",
        "APPLE_TEAM_ID": "QA12345",
        "APPLE_PASS_CERT_PATH": _apple_test_certs["cert"],
        "APPLE_PASS_KEY_PATH": _apple_test_certs["key"],
        "APPLE_WWDR_CERT_PATH": _apple_test_certs["wwdr"],
    }
    with patch.dict(os.environ, env):
        coupon = {"coupon_id": "cpn_qa_apple_1",
                       "qr_token": "qr_qa_apple"}
        business = {"display_name": "Demo Karak"}
        offer = {"title": "5 AED off"}
        cli = _aio()
        db = cli[DB_NAME]
        try:
            out = _run(wp.build_apple_pass(
                db, coupon=coupon, business=business, offer=offer))
        finally:
            cli.close()
    assert out["mode"] == "live", out
    assert "pkpass_bytes" in out
    # .pkpass is a ZIP archive — magic bytes PK\x03\x04
    assert out["pkpass_bytes"][:2] == b"PK", out["pkpass_bytes"][:8]
    assert out["size_bytes"] > 300, out["size_bytes"]


# ─── 4. Apple PassKit: stub when creds missing ───────────────────────
def test_apple_pass_returns_stub_when_creds_missing(caplog):
    from services import wallet_passes as wp
    # Strip any Apple env vars so the path is forced to mock.
    bad = {k: "" for k in wp.APPLE_ENV_KEYS}
    with patch.dict(os.environ, bad, clear=False):
        for k in wp.APPLE_ENV_KEYS:
            os.environ.pop(k, None)
        coupon = {"coupon_id": "cpn_qa_apple_stub"}
        cli = _aio()
        db = cli[DB_NAME]
        try:
            with caplog.at_level(logging.WARNING,
                                          logger="bigfm.wallet_passes"):
                out = _run(wp.build_apple_pass(
                    db, coupon=coupon, business={}, offer={}))
        finally:
            cli.close()
    assert out["mode"] == "mock"
    assert "placeholder.bigfm.dubai/apple-pass/" in out["save_url"]
    assert "HIGHLIGHTED MOCK" in " ".join(
        r.message for r in caplog.records)


# ─── 5. Google Wallet: returns JWT-bearing save URL when creds set ───
def test_google_wallet_pass_returns_jwt_when_creds_set():
    from services import wallet_passes as wp

    class _FakeClient:
        def mint_coupon_pass(self, *, coupon, business, offer):
            return {"save_url": "https://pay.google.com/gp/v/save/abc.def",
                      "jwt": "abc.def.signature",
                      "pass_status": "live",
                      "issuer_id": "3388000000000123456"}

    env = {"GOOGLE_WALLET_ISSUER_ID": "3388000000000123456",
              "GOOGLE_WALLET_SERVICE_ACCOUNT_PATH":
                  "/app/backend/secrets/gcp_service_account.json"}
    with patch.dict(os.environ, env):
        with patch("services.google_wallet.get_wallet_client",
                       return_value=_FakeClient()):
            cli = _aio()
            db = cli[DB_NAME]
            try:
                out = _run(wp.build_google_wallet_pass(
                    db, coupon={"coupon_id": "cpn_qa_google"},
                    business={}, offer={}))
            finally:
                cli.close()
    assert out["mode"] == "live"
    assert "pay.google.com/gp/v/save/" in out["save_url"]
    assert out["jwt"] == "abc.def.signature"


# ─── 6. Google Wallet: stub when creds missing ───────────────────────
def test_google_wallet_pass_returns_stub_when_creds_missing(caplog):
    from services import wallet_passes as wp
    # Strip both wallet envs.
    bad_keys = ("GOOGLE_WALLET_ISSUER_ID",
                    "GOOGLE_WALLET_SERVICE_ACCOUNT_PATH")
    saved = {k: os.environ.pop(k, None) for k in bad_keys}
    try:
        # Also unset GOOGLE_APPLICATION_CREDENTIALS for this test so the
        # fallback path is also missing.
        gac_saved = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        try:
            cli = _aio()
            db = cli[DB_NAME]
            try:
                with caplog.at_level(logging.WARNING,
                                              logger="bigfm.wallet_passes"):
                    out = _run(wp.build_google_wallet_pass(
                        db, coupon={"coupon_id": "cpn_qa_google_stub"},
                        business={}, offer={}))
            finally:
                cli.close()
            assert out["mode"] == "mock"
            assert "stub-" in out["save_url"]
            assert "HIGHLIGHTED MOCK" in " ".join(
                r.message for r in caplog.records)
        finally:
            if gac_saved is not None:
                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = gac_saved
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


# ─── 7. GAM probe: no line items → degraded ─────────────────────────
def test_gam_probe_handles_no_line_items_as_degraded(admin_session):
    """The current preview env has no DELIVERING audio line items.
    Probe should return ok-ish but mark mode degraded with
    `line_items=none_trafficked` and a note. Either way, no crash."""
    r = admin_session.post(f"{API}/admin/integrations/gam/probe",
                                    timeout=15)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    # Either result.ok=false with reason (no SA configured in this
    # env) OR result.ok=true with line_items=none_trafficked → mode is
    # `degraded` or `mock`. Crucially never `live` without line items.
    mode = body.get("mode_after_probe")
    assert mode in ("mock", "degraded"), body


# ─── 8. GAM failure falls through to direct-sold ─────────────────────
def test_gam_failure_falls_through_to_direct_sold():
    """Stub `call_gam_for_backfill` to raise. The ad-decisioning layer
    must not crash and must hand off to the next priority (direct-sold
    is checked BEFORE GAM in ad_decisioning.pick_ad — but if GAM later
    raises, OpenRTB / house also fall through). We assert the
    try/except wrapper catches the exception."""
    from services import ad_decisioning as ad

    async def _boom(*a, **kw):
        raise RuntimeError("gam SOAP exploded")

    cli = _aio()
    db = cli[DB_NAME]
    try:
        user = {"user_id": "user_qa_fallthrough",
                  "preference_vector": {}}
        session = {"_id": "sess_qa", "session_id": "sess_qa"}
        ctx = {"market": "dubai", "daypart": "all",
                "channel_slug": "qa"}
        # Patch gam to raise; the decisioning entry point must not
        # propagate the exception (it logs at debug level + falls
        # through to other sources, returning None or a non-gam pick).
        with patch("services.gam_client.call_gam_for_backfill",
                       side_effect=_boom):
            result = _run(ad.select_ad(
                db, user=user, session=session,
                segment_context=ctx))
        # Either None (no other source had a pick) or a decision dict
        # WITHOUT gam_backfill path. The point: no exception.
        if isinstance(result, dict):
            assert result.get("decision_path") != "gam_backfill"
    finally:
        cli.close()


# ─── 9. SendGrid throttle at soft limit ──────────────────────────────
def test_sendgrid_throttle_at_soft_limit_slows_sends(monkeypatch):
    from services import delivery
    date, hour = delivery._date_hour_keys()
    # Prime via sync client so we never cross loops.
    DB.sendgrid_quota.update_one(
        {"_id": date},
        {"$set": {"_id": date, "date": date,
                    "plan_tier": "free",
                    "daily_sent": 30,
                    f"hourly_sent.{hour}": 30,
                    "throttled_count": 0,
                    "quota_blocked_count": 0,
                    "created_at": dt.now(timezone.utc)}},
        upsert=True)
    try:
        monkeypatch.setenv("SENDGRID_PLAN_TIER", "free")
        delivery.SENDGRID_PLAN_TIER = "free"

        async def _do(db):
            return await delivery._check_quota_and_increment(db)
        out = _with_db(_do)
        assert out["action"] == "throttle", out
        assert out["snapshot"]["soft_limit_hit"] is True
        post = DB.sendgrid_quota.find_one({"_id": date})
        assert post["throttled_count"] >= 1
    finally:
        DB.sendgrid_quota.delete_many(
            {"plan_tier": "free", "_id": date})


# ─── 10. SendGrid throttle at hard limit → queue ─────────────────────
def test_sendgrid_throttle_at_hard_limit_queues_to_delivery_queue(
        monkeypatch):
    from services import delivery
    date, _h = delivery._date_hour_keys()
    DB.sendgrid_quota.update_one(
        {"_id": date},
        {"$set": {"_id": date, "date": date,
                    "plan_tier": "free",
                    "daily_sent": 999,
                    "hourly_sent": {},
                    "throttled_count": 0,
                    "quota_blocked_count": 0,
                    "created_at": dt.now(timezone.utc)}},
        upsert=True)
    try:
        monkeypatch.setenv("SENDGRID_PLAN_TIER", "free")
        monkeypatch.setenv("SENDGRID_API_KEY", "sg.fake.qa")
        delivery.SENDGRID_PLAN_TIER = "free"

        async def _check(db):
            return await delivery._check_quota_and_increment(db)
        chk = _with_db(_check)
        assert chk["action"] == "block", chk

        user = {"user_id": "user_qa_quota_block",
                  "email": "qa+block@bigfm.dubai", "name": "QA"}
        before = DB.delivery_queue.count_documents(
            {"user_id": user["user_id"]})

        async def _send(db):
            return await delivery.send_email(
                db, user=user, campaign_id="qa_test",
                subject="hi", body_template="<p>hi</p>", vars={})
        log = _with_db(_send)
        assert log["status"] == "throttled_quota", log
        after = DB.delivery_queue.count_documents(
            {"user_id": user["user_id"],
              "status": "throttled_quota"})
        assert after == before + 1
    finally:
        DB.sendgrid_quota.delete_many({"_id": date})
        DB.delivery_queue.delete_many(
            {"user_id": "user_qa_quota_block"})
        DB.lifecycle_send_log.delete_many(
            {"user_id": "user_qa_quota_block"})


# ─── 11. Health loop promotes to live after success streak ──────────
def test_integration_health_loop_promotes_to_live_after_success_streak():
    from services import integration_health as ih
    DB.integration_health.delete_one({"integration": "maps"})
    try:
        async def _record_5_ok(db):
            for _ in range(5):
                await ih.record_call(db, "maps", success=True,
                                              detail={"qa": True})
            await ih.record_call(db, "maps", success=False,
                                          error="qa_intentional")
            return await ih.recompute_mode(db, "maps")
        mode = _with_db(_record_5_ok)
        assert mode == "live", mode

        # Flip success counters so failures dominate.
        DB.integration_health.update_one(
            {"integration": "maps"},
            {"$set": {"success_count_1h": 1,
                        "failure_count_1h": 9}})

        async def _recompute(db):
            return await ih.recompute_mode(db, "maps")
        mode2 = _with_db(_recompute)
        assert mode2 == "degraded", mode2
    finally:
        DB.integration_health.delete_one({"integration": "maps"})
