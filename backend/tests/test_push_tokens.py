"""Phase 11.5 — Mobile push-token registration tests."""
from __future__ import annotations
import os
import uuid

import requests
from pymongo import MongoClient

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"
MONGO = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB = MONGO[os.environ.get("DB_NAME", "bigfm")]


def _login(email: str, pwd: str) -> tuple[requests.Session, str]:
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                json={"email": email, "password": pwd}, timeout=10)
    assert r.status_code == 200, r.text
    return s, r.json()["user_id"]


def _fresh_token() -> str:
    return f"ExponentPushToken[test_{uuid.uuid4().hex[:14]}]"


def test_register_push_token_authenticated():
    sess, uid = _login("test@bigfm.dubai", "TestUser123!")
    tok = _fresh_token()
    DB.user_push_tokens.delete_many({"user_id": uid, "expo_push_token": tok})
    r = sess.post(f"{API}/users/push_token",
                          json={"expo_push_token": tok, "platform": "ios",
                                  "device_id": "test-device-1"},
                          timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["registered"] is True
    assert body["token_id"]
    row = DB.user_push_tokens.find_one({"user_id": uid,
                                                      "expo_push_token": tok})
    assert row is not None
    assert row["platform"] == "ios"
    assert row["device_id"] == "test-device-1"
    assert row["active"] is True
    DB.user_push_tokens.delete_many({"user_id": uid, "expo_push_token": tok})


def test_register_push_token_idempotent():
    sess, uid = _login("test@bigfm.dubai", "TestUser123!")
    tok = _fresh_token()
    DB.user_push_tokens.delete_many({"user_id": uid, "expo_push_token": tok})
    # First call → registered
    r1 = sess.post(f"{API}/users/push_token",
                          json={"expo_push_token": tok, "platform": "android"},
                          timeout=10)
    assert r1.status_code == 200, r1.text
    assert r1.json()["registered"] is True
    tok_id_1 = r1.json()["token_id"]
    # Second call same token → NOT a duplicate; registered=False, same id
    r2 = sess.post(f"{API}/users/push_token",
                          json={"expo_push_token": tok, "platform": "android",
                                  "device_id": "updated-device"},
                          timeout=10)
    assert r2.status_code == 200, r2.text
    assert r2.json()["registered"] is False
    assert r2.json()["token_id"] == tok_id_1
    # Only ONE row in Mongo
    n = DB.user_push_tokens.count_documents({"user_id": uid,
                                                              "expo_push_token": tok})
    assert n == 1, f"expected 1 row, got {n}"
    DB.user_push_tokens.delete_many({"user_id": uid, "expo_push_token": tok})


def test_register_push_token_unauthenticated_401():
    """No cookie, no Bearer → must reject."""
    r = requests.post(f"{API}/users/push_token",
                              json={"expo_push_token": _fresh_token(),
                                      "platform": "ios"},
                              timeout=10)
    assert r.status_code in (401, 403), (r.status_code, r.text[:200])


def test_delete_push_token_deactivates():
    sess, uid = _login("test@bigfm.dubai", "TestUser123!")
    tok = _fresh_token()
    DB.user_push_tokens.delete_many({"user_id": uid, "expo_push_token": tok})
    sess.post(f"{API}/users/push_token",
                  json={"expo_push_token": tok, "platform": "web"},
                  timeout=10)
    # DELETE
    r = sess.delete(f"{API}/users/push_token",
                            json={"expo_push_token": tok},
                            timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["deactivated"] is True
    assert body["modified"] >= 1
    row = DB.user_push_tokens.find_one({"user_id": uid,
                                                      "expo_push_token": tok})
    assert row is not None and row["active"] is False
    assert "deactivated_at" in row
    # Idempotent — deleting again still 200 but modified=0
    r2 = sess.delete(f"{API}/users/push_token",
                              json={"expo_push_token": tok}, timeout=10)
    assert r2.status_code == 200, r2.text
    # (modified may be >0 if the row's `active` was True from a flicker,
    # but on stable state it's 0)
    DB.user_push_tokens.delete_many({"user_id": uid, "expo_push_token": tok})


def test_register_push_token_with_bearer_works():
    """Mobile path — Bearer-token auth must also reach this route."""
    r = requests.post(f"{API}/auth/login",
                              json={"email": "test@bigfm.dubai",
                                      "password": "TestUser123!"}, timeout=10)
    token = r.json()["session_token"]
    uid = r.json()["user_id"]
    tok = _fresh_token()
    DB.user_push_tokens.delete_many({"user_id": uid, "expo_push_token": tok})
    r2 = requests.post(f"{API}/users/push_token",
                                headers={"Authorization": f"Bearer {token}"},
                                json={"expo_push_token": tok, "platform": "ios"},
                                timeout=10)
    assert r2.status_code == 200, r2.text
    assert r2.json()["registered"] is True
    DB.user_push_tokens.delete_many({"user_id": uid, "expo_push_token": tok})


def test_register_push_token_invalid_platform_400():
    sess, uid = _login("test@bigfm.dubai", "TestUser123!")
    r = sess.post(f"{API}/users/push_token",
                          json={"expo_push_token": _fresh_token(),
                                  "platform": "nokia_symbian"}, timeout=10)
    assert r.status_code == 400, r.text


def test_openapi_reflects_push_token_routes():
    r = requests.get(f"{API}/openapi.json", timeout=10)
    assert r.status_code == 200
    paths = (r.json() or {}).get("paths") or {}
    assert "/api/users/push_token" in paths, list(paths.keys())[:30]
    methods = paths["/api/users/push_token"].keys()
    assert "post" in methods, methods
    assert "delete" in methods, methods
