"""Phase 13e — Apple SIWA + APNs integration tests."""
from __future__ import annotations
import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
import jwt

load_dotenv("/app/backend/.env")

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"
LOCAL_API = "http://localhost:8001/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")
DB = MongoClient(MONGO_URL)[DB_NAME]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _login_admin() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": "admin@bigfm.dubai",
                                                              "password": "AdminPass123!"},
                    timeout=10)
    assert r.status_code == 200, r.text[:200]
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login_admin()


# ─── ES256 keypair fixture (for SIWA client_secret tests) ───────────────
@pytest.fixture(scope="module")
def es256_p8(tmp_path_factory):
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    p8_path = tmp_path_factory.mktemp("apple") / "AuthKey_TEST.p8"
    p8_path.write_bytes(pem)
    return str(p8_path)


# ─── RSA keypair for fake JWKS (Apple uses RS256 for id_tokens) ─────────
@pytest.fixture(scope="module")
def fake_jwks():
    """Generate an RSA keypair + matching JWK dict for jwt verification."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    pub_numbers = key.public_key().public_numbers()
    import base64
    def b64(n: int) -> str:
        bts = n.to_bytes((n.bit_length() + 7) // 8, "big")
        return base64.urlsafe_b64encode(bts).rstrip(b"=").decode()
    jwk = {
        "kty": "RSA", "alg": "RS256", "use": "sig",
        "kid": "qa-apple-kid",
        "n": b64(pub_numbers.n), "e": b64(pub_numbers.e),
    }
    return {"private_pem": private_pem, "jwk": jwk, "kid": "qa-apple-kid"}


def _sign_id_token(fake_jwks, *, aud, iss="https://appleid.apple.com",
                            sub=None, email=None, email_verified=True,
                            exp_offset_sec=600):
    now = int(time.time())
    payload = {"iss": iss, "iat": now, "exp": now + exp_offset_sec,
                  "aud": aud, "sub": sub or f"apple_qa_{uuid.uuid4().hex[:8]}",
                  "email": email,
                  "email_verified": email_verified}
    return jwt.encode(payload, fake_jwks["private_pem"], algorithm="RS256",
                              headers={"kid": fake_jwks["kid"]})


# ════════════════════════════════════════════════════════════════════
# 1. client_secret JWT generates when creds set
# ════════════════════════════════════════════════════════════════════
def test_siwa_client_secret_jwt_generation_when_creds_set(es256_p8):
    from services import apple_siwa
    env_keys = ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_KEY_PATH",
                  "APPLE_SIWA_SERVICE_ID", "APPLE_SIWA_REDIRECT_URI")
    prev = {k: os.environ.get(k) for k in env_keys}
    os.environ.update({
        "APPLE_TEAM_ID": "TEAMTEST01",
        "APPLE_KEY_ID":  "KEYIDTEST1",
        "APPLE_KEY_PATH": es256_p8,
        "APPLE_SIWA_SERVICE_ID": "com.bigfm.qa.siwa",
        "APPLE_SIWA_REDIRECT_URI": "https://bigfm.test/api/auth/apple/callback",
    })
    try:
        tok = apple_siwa.make_client_secret()
        # decode without verification to inspect claims.
        claims = jwt.decode(tok, options={"verify_signature": False})
        assert claims["iss"] == "TEAMTEST01"
        assert claims["aud"] == "https://appleid.apple.com"
        assert claims["sub"] == "com.bigfm.qa.siwa"
        header = jwt.get_unverified_header(tok)
        assert header["alg"] == "ES256"
        assert header["kid"] == "KEYIDTEST1"
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# ════════════════════════════════════════════════════════════════════
# 2. clean error when SIWA creds missing
# ════════════════════════════════════════════════════════════════════
def test_siwa_client_secret_jwt_missing_creds_raises_clean_error():
    from services import apple_siwa
    env_keys = ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_KEY_PATH",
                  "APPLE_SIWA_SERVICE_ID", "APPLE_SIWA_REDIRECT_URI")
    prev = {k: os.environ.pop(k, None) for k in env_keys}
    try:
        with pytest.raises(apple_siwa.SIWANotConfigured):
            apple_siwa.make_client_secret()
    finally:
        for k, v in prev.items():
            if v is not None:
                os.environ[k] = v


# ─── helper to install fake JWKS + creds for verify_identity_token tests
def _setup_siwa_for_verify(fake_jwks, es256_p8, *, service_id):
    os.environ.update({
        "APPLE_TEAM_ID": "TEAMTEST01",
        "APPLE_KEY_ID":  "KEYIDTEST1",
        "APPLE_KEY_PATH": es256_p8,
        "APPLE_SIWA_SERVICE_ID": service_id,
        "APPLE_SIWA_REDIRECT_URI": "https://bigfm.test/cb",
    })
    DB.apple_jwks_cache.update_one(
        {"_id": "apple"},
        {"$set": {"keys": [fake_jwks["jwk"]],
                      "fetched_at": datetime.now(timezone.utc)}},
        upsert=True)


def _teardown_siwa():
    for k in ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_KEY_PATH",
                  "APPLE_SIWA_SERVICE_ID", "APPLE_SIWA_REDIRECT_URI"):
        os.environ.pop(k, None)
    DB.apple_jwks_cache.delete_one({"_id": "apple"})


# ════════════════════════════════════════════════════════════════════
# 3. verify_identity_token — valid
# ════════════════════════════════════════════════════════════════════
def test_siwa_verify_identity_token_valid(fake_jwks, es256_p8):
    from services import apple_siwa
    svc = "com.bigfm.qa.siwa"
    _setup_siwa_for_verify(fake_jwks, es256_p8, service_id=svc)
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        cli = AsyncIOMotorClient(MONGO_URL)
        try:
            tok = _sign_id_token(fake_jwks, aud=svc,
                                          email="qa+valid@bigfm.test")
            claims = _run(apple_siwa.verify_identity_token(
                cli[DB_NAME], tok))
            assert claims["aud"] == svc
            assert claims["iss"] == "https://appleid.apple.com"
            assert claims["email"] == "qa+valid@bigfm.test"
        finally:
            cli.close()
    finally:
        _teardown_siwa()


# ════════════════════════════════════════════════════════════════════
# 4. verify_identity_token — expired rejected
# ════════════════════════════════════════════════════════════════════
def test_siwa_verify_identity_token_expired_rejected(fake_jwks, es256_p8):
    from services import apple_siwa
    svc = "com.bigfm.qa.siwa"
    _setup_siwa_for_verify(fake_jwks, es256_p8, service_id=svc)
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        cli = AsyncIOMotorClient(MONGO_URL)
        try:
            tok = _sign_id_token(fake_jwks, aud=svc,
                                          exp_offset_sec=-60)
            with pytest.raises(jwt.ExpiredSignatureError):
                _run(apple_siwa.verify_identity_token(
                    cli[DB_NAME], tok))
        finally:
            cli.close()
    finally:
        _teardown_siwa()


# ════════════════════════════════════════════════════════════════════
# 5. verify_identity_token — wrong aud rejected
# ════════════════════════════════════════════════════════════════════
def test_siwa_verify_identity_token_wrong_aud_rejected(fake_jwks, es256_p8):
    from services import apple_siwa
    _setup_siwa_for_verify(fake_jwks, es256_p8,
                                          service_id="com.bigfm.qa.siwa")
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        cli = AsyncIOMotorClient(MONGO_URL)
        try:
            tok = _sign_id_token(fake_jwks, aud="com.evil.other")
            with pytest.raises(jwt.InvalidAudienceError):
                _run(apple_siwa.verify_identity_token(
                    cli[DB_NAME], tok))
        finally:
            cli.close()
    finally:
        _teardown_siwa()


# ════════════════════════════════════════════════════════════════════
# 6. apple_user_from_claims — creates new when no existing email
# ════════════════════════════════════════════════════════════════════
def test_apple_user_creates_new_when_no_existing_email():
    from services import apple_siwa
    from motor.motor_asyncio import AsyncIOMotorClient
    apple_sub = f"apple_qa_{uuid.uuid4().hex[:10]}"
    email = f"qa+new+{uuid.uuid4().hex[:6]}@bigfm.test"
    claims = {"sub": apple_sub, "email": email, "email_verified": True}
    cli = AsyncIOMotorClient(MONGO_URL)
    try:
        user = _run(apple_siwa.apple_user_from_claims(cli[DB_NAME], claims))
        assert user["apple_sub"] == apple_sub
        assert user["email"] == email
        assert user.get("email_verified") is True
        assert user.get("auth_provider") == "apple"
    finally:
        cli.close()
        DB.users.delete_one({"apple_sub": apple_sub})


# ════════════════════════════════════════════════════════════════════
# 7. apple_user_from_claims — links when email already present
# ════════════════════════════════════════════════════════════════════
def test_apple_user_links_when_email_already_present():
    from services import apple_siwa
    from motor.motor_asyncio import AsyncIOMotorClient
    email = f"qa+link+{uuid.uuid4().hex[:6]}@bigfm.test"
    existing_uid = f"user_qa_{uuid.uuid4().hex[:10]}"
    DB.users.insert_one({"_id": existing_uid, "user_id": existing_uid,
                                    "email": email, "email_verified": False})
    apple_sub = f"apple_qa_{uuid.uuid4().hex[:10]}"
    claims = {"sub": apple_sub, "email": email, "email_verified": True}
    cli = AsyncIOMotorClient(MONGO_URL)
    try:
        linked = _run(apple_siwa.apple_user_from_claims(
            cli[DB_NAME], claims))
        assert linked["user_id"] == existing_uid
        assert linked["apple_sub"] == apple_sub
        row = DB.users.find_one({"_id": existing_uid})
        assert row["apple_sub"] == apple_sub
        assert row["email_verified"] is True
    finally:
        cli.close()
        DB.users.delete_one({"_id": existing_uid})


@pytest.fixture(scope="module")
def app_client():
    """Module-scoped TestClient so all SIWA tests share one event loop.
    The backend's app.state.db is bound to the loop the TestClient
    creates — reusing avoids 'Event loop is closed' errors."""
    import sys
    sys.path.insert(0, "/app/backend")
    from fastapi.testclient import TestClient
    import server  # noqa: F401
    with TestClient(server.app) as cli:
        yield cli


def _testclient():
    """Deprecated — kept for legacy call sites. Use the `app_client`
    fixture instead."""
    import sys
    sys.path.insert(0, "/app/backend")
    from fastapi.testclient import TestClient
    import server  # noqa: F401
    return TestClient(server.app)


# ════════════════════════════════════════════════════════════════════
# 8. Web SIWA callback — full flow
# ════════════════════════════════════════════════════════════════════
def test_web_siwa_callback_full_flow(fake_jwks, es256_p8, app_client,
                                                        monkeypatch):
    """Use FastAPI TestClient so env vars set in-process apply."""
    svc = "com.bigfm.qa.siwa"
    _setup_siwa_for_verify(fake_jwks, es256_p8, service_id=svc)
    try:
        state = f"qa_state_{uuid.uuid4().hex[:8]}"
        DB.apple_oauth_states.insert_one({
            "_id": state, "state": state,
            "created_at": datetime.now(timezone.utc),
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5)})
        id_tok = _sign_id_token(
            fake_jwks, aud=svc,
            email=f"qa+web+{uuid.uuid4().hex[:6]}@bigfm.dubai",
            sub=f"apple_qa_{uuid.uuid4().hex[:10]}")
        r = app_client.post("/api/auth/apple/callback",
                                    data={"id_token": id_tok, "state": state,
                                            "code": "qa_code"},
                                    follow_redirects=False)
        assert r.status_code == 302, r.text[:200]
        loc = r.headers.get("location", "")
        assert "/auth/apple/return?session_token=sess_" in loc
        assert "user_id=user_" in loc
        assert "bigfm_session=sess_" in r.headers.get("set-cookie", "")
        claims = jwt.decode(id_tok, options={"verify_signature": False})
        DB.users.delete_one({"apple_sub": claims["sub"]})
    finally:
        _teardown_siwa()


# ════════════════════════════════════════════════════════════════════
# 9. Mobile SIWA — returns session_token in body
# ════════════════════════════════════════════════════════════════════
def test_mobile_siwa_endpoint_returns_session_token_in_body(
        fake_jwks, es256_p8, app_client):
    svc = "com.bigfm.qa.siwa"
    _setup_siwa_for_verify(fake_jwks, es256_p8, service_id=svc)
    try:
        id_tok = _sign_id_token(
            fake_jwks, aud=svc,
            email=f"qa+mobile+{uuid.uuid4().hex[:6]}@bigfm.dubai",
            sub=f"apple_qa_{uuid.uuid4().hex[:10]}")
        r = app_client.post("/api/auth/apple/mobile",
                                    json={"identity_token": id_tok,
                                            "profile_name": {"firstName": "QA",
                                                                      "lastName": "Tester"}})
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        assert body["session_token"].startswith("sess_")
        assert body["user_id"].startswith("user_")
        claims = jwt.decode(id_tok, options={"verify_signature": False})
        DB.users.delete_one({"apple_sub": claims["sub"]})
        DB.sessions.delete_one({"token": body["session_token"]})
    finally:
        _teardown_siwa()


# ════════════════════════════════════════════════════════════════════
# 10. APNs JWT generation when creds set
# ════════════════════════════════════════════════════════════════════
def test_apns_jwt_generation_when_creds_set(es256_p8):
    from services import apns
    env_keys = ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_KEY_PATH",
                  "APPLE_BUNDLE_ID")
    prev = {k: os.environ.get(k) for k in env_keys}
    os.environ.update({
        "APPLE_TEAM_ID": "TEAMTEST01",
        "APPLE_KEY_ID":  "KEYIDTEST1",
        "APPLE_KEY_PATH": es256_p8,
        "APPLE_BUNDLE_ID": "com.bigfm.qa",
    })
    # Reset module cache to force a fresh mint.
    apns._jwt_cache["token"] = None
    try:
        tok = apns.make_apns_jwt(force_refresh=True)
        header = jwt.get_unverified_header(tok)
        payload = jwt.decode(tok, options={"verify_signature": False})
        assert header["alg"] == "ES256"
        assert header["kid"] == "KEYIDTEST1"
        assert payload["iss"] == "TEAMTEST01"
        assert "iat" in payload
    finally:
        for k, v in prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        apns._jwt_cache["token"] = None


# ════════════════════════════════════════════════════════════════════
# 11. APNs uses sandbox URL in sandbox env
# ════════════════════════════════════════════════════════════════════
def test_apns_send_uses_sandbox_url_in_sandbox_env(es256_p8, monkeypatch):
    from services import apns
    env_prev = {k: os.environ.get(k) for k in
                       ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_KEY_PATH",
                        "APPLE_BUNDLE_ID", "APNS_ENV")}
    os.environ.update({
        "APPLE_TEAM_ID": "T1", "APPLE_KEY_ID": "K1",
        "APPLE_KEY_PATH": es256_p8, "APPLE_BUNDLE_ID": "com.bigfm.qa",
        "APNS_ENV": "sandbox",
    })
    apns._jwt_cache["token"] = None
    try:
        assert apns.apns_env() == "sandbox"
        assert "sandbox.push.apple.com" in apns.apns_host()
        os.environ["APNS_ENV"] = "production"
        assert apns.apns_env() == "production"
        assert apns.apns_host() == "https://api.push.apple.com"
    finally:
        for k, v in env_prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        apns._jwt_cache["token"] = None


# ════════════════════════════════════════════════════════════════════
# 12. APNs fallback to Expo when MOCK
# ════════════════════════════════════════════════════════════════════
def test_apns_send_falls_back_to_expo_when_apple_in_mock_mode(monkeypatch):
    from services import delivery as delivery_svc
    from services import apns
    # No env vars → MOCK.
    assert apns.is_configured() is False
    # Stub the live Expo HTTP call so the test doesn't hit the network.

    async def _fake_expo_send(messages):
        return [{"status": "ok", "id": f"rcpt_qa_{i}"}
                  for i, _ in enumerate(messages)]
    monkeypatch.setattr(delivery_svc, "_expo_send", _fake_expo_send)
    uid = f"user_qa_{uuid.uuid4().hex[:8]}"
    DB.users.insert_one({"_id": uid, "user_id": uid,
                                    "email": f"qa+{uid}@bigfm.test"})
    DB.user_push_tokens.insert_one({
        "_id": f"pt_qa_{uuid.uuid4().hex[:8]}",
        "user_id": uid,
        "expo_push_token": "ExponentPushToken[QA_FAKE_xxxxxx]",
        "device_type": "expo", "active": True})
    from motor.motor_asyncio import AsyncIOMotorClient
    cli = AsyncIOMotorClient(MONGO_URL)
    try:
        _run(delivery_svc.send_push(
            cli[DB_NAME], user={"user_id": uid},
            campaign_id="cmp_qa_test",
            title="QA Test", body_template="hello {name}",
            vars={"name": "world"}, deep_link="/qa"))
        rows = list(DB.push_deliveries.find({"user_id": uid}))
        assert len(rows) >= 1
        assert all(r["delivery_provider"] == "expo_proxy" for r in rows)
    finally:
        cli.close()
        DB.users.delete_one({"_id": uid})
        DB.user_push_tokens.delete_many({"user_id": uid})
        DB.push_deliveries.delete_many({"user_id": uid})
        DB.lifecycle_send_log.delete_many({"user_id": uid})


# ════════════════════════════════════════════════════════════════════
# 13. push_token registration accepts apns_native device_type
# ════════════════════════════════════════════════════════════════════
def test_push_token_registration_accepts_apns_native_device_type():
    # Use a user account we can log in as.
    email = f"qa+pt+{uuid.uuid4().hex[:6]}@bigfm.dubai"
    pw    = "QApass!23xyz"
    r = requests.post(f"{LOCAL_API}/auth/register",
                              json={"email": email, "password": pw,
                                      "name": "QA Tester",
                                      "market": "AE"}, timeout=10)
    assert r.status_code == 200, r.text[:200]
    tok = r.json().get("session_token") or r.json().get("token")
    assert tok
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    # Raw APNs hex token (64 hex chars).
    raw = "a1b2" * 16
    rr = s.post(f"{LOCAL_API}/users/push_token",
                      json={"expo_push_token": raw,
                              "platform": "ios",
                              "device_type": "apns_native",
                              "apns_environment": "sandbox"},
                      timeout=10)
    assert rr.status_code == 200, rr.text[:200]
    body = rr.json()
    assert body["device_type"] == "apns_native"
    # Spot-check the row.
    row = DB.user_push_tokens.find_one({"expo_push_token": raw})
    assert row["device_type"] == "apns_native"
    assert row["apns_environment"] == "sandbox"
    # Cleanup.
    DB.user_push_tokens.delete_many({"expo_push_token": raw})
    user = DB.users.find_one({"email": email})
    if user:
        DB.users.delete_one({"_id": user["_id"]})
    DB.sessions.delete_many({"_id": tok})


# ════════════════════════════════════════════════════════════════════
# 14. push_deliveries record provider field
# ════════════════════════════════════════════════════════════════════
def test_push_deliveries_record_provider_field(monkeypatch):
    # Reuses the previous test's logic minus the token-type check.
    from services import delivery as delivery_svc
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _fake_expo_send(messages):
        return [{"status": "ok", "id": f"rcpt_qa2_{i}"}
                  for i, _ in enumerate(messages)]
    monkeypatch.setattr(delivery_svc, "_expo_send", _fake_expo_send)
    uid = f"user_qa_{uuid.uuid4().hex[:8]}"
    DB.users.insert_one({"_id": uid, "user_id": uid,
                                    "email": f"qa+{uid}@bigfm.test"})
    DB.user_push_tokens.insert_one({
        "_id": f"pt_qa_{uuid.uuid4().hex[:8]}",
        "user_id": uid,
        "expo_push_token": "ExponentPushToken[QA_PROV]",
        "device_type": "expo", "active": True})
    cli = AsyncIOMotorClient(MONGO_URL)
    try:
        _run(delivery_svc.send_push(
            cli[DB_NAME], user={"user_id": uid},
            campaign_id="cmp_qa_prov",
            title="t", body_template="b", deep_link="/"))
        rows = list(DB.push_deliveries.find({"user_id": uid}))
        assert len(rows) >= 1
        assert all("delivery_provider" in r for r in rows), rows
        assert any(r["delivery_provider"] == "expo_proxy" for r in rows)
    finally:
        cli.close()
        DB.users.delete_one({"_id": uid})
        DB.user_push_tokens.delete_many({"user_id": uid})
        DB.push_deliveries.delete_many({"user_id": uid})
        DB.lifecycle_send_log.delete_many({"user_id": uid})


# ════════════════════════════════════════════════════════════════════
# 15. Integration health promotes apple_apns when env vars present
# ════════════════════════════════════════════════════════════════════
def test_integration_health_promotes_apple_apns_when_env_vars_present(
        admin_session, es256_p8):
    # Probe with creds missing → expect mock.
    r1 = admin_session.post(f"{API}/admin/integrations/apple_apns/probe",
                                          timeout=10)
    assert r1.status_code == 200, r1.text[:200]
    body1 = r1.json()
    assert body1["mode_after_probe"] == "mock"
    assert body1["result"]["ok"] is False

    # The full live flip requires backend-process env vars, which a test
    # process can't inject across processes. We assert the contract: when
    # creds are set in the backend's env at boot, the integration_health
    # `_apple_apns_creds_present()` returns True. Simulate that
    # by reading the creds() function directly.
    from services.integration_health import _apple_apns_creds_present
    env_prev = {k: os.environ.get(k) for k in
                       ("APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_KEY_PATH",
                        "APPLE_BUNDLE_ID")}
    os.environ.update({"APPLE_TEAM_ID": "T",
                                  "APPLE_KEY_ID": "K",
                                  "APPLE_KEY_PATH": es256_p8,
                                  "APPLE_BUNDLE_ID": "com.bigfm.qa"})
    try:
        assert _apple_apns_creds_present() is True
    finally:
        for k, v in env_prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
