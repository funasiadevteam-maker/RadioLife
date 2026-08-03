"""Phase 11.4 — commerce coupons listing must not 500 on legacy rows
missing `coupon_id`."""
from __future__ import annotations
import os
import uuid
from datetime import datetime, timezone, timedelta

import requests
from pymongo import MongoClient

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"
MONGO = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
DB = MONGO[os.environ.get("DB_NAME", "bigfm")]


def _login(email: str, pwd: str):
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                json={"email": email, "password": pwd}, timeout=10)
    assert r.status_code == 200, r.text
    me = s.get(f"{API}/auth/me", timeout=10).json()
    s._user_id = me["user_id"]
    return s


def test_coupons_me_returns_200_with_missing_coupon_id_docs():
    """Insert a legacy-shaped coupon row WITHOUT a `coupon_id` field;
    `GET /api/commerce/coupons/me` must still return 200 and render that
    row with `coupon_id` falling back to `str(_id)`."""
    user = _login("test@bigfm.dubai", "TestUser123!")
    uid = user._user_id
    # Synthetic legacy row — `_id` is set, `coupon_id` field is absent
    legacy_id = f"legacy_no_cid_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    DB.coupons.delete_one({"_id": legacy_id})
    DB.coupons.insert_one({
        "_id": legacy_id,
        # NB: deliberately NOT writing `coupon_id`
        "offer_id": "synthetic_offer",
        "business_id": "synthetic_biz",
        "user_id": uid,
        "claimed_at": now,
        "expires_at": now + timedelta(days=30),
        "status": "claimed",
        "redemption_code": "TEST1234",
    })
    try:
        r = user.get(f"{API}/commerce/coupons/me", timeout=10)
        assert r.status_code == 200, r.text
        items = (r.json() or {}).get("items") or r.json()
        if isinstance(r.json(), dict) and "items" in r.json():
            items = r.json()["items"]
        ids = [it.get("coupon_id") for it in items]
        # Legacy row must be present and render with _id as the coupon_id
        assert legacy_id in ids, (
            f"legacy row not rendered. coupon_ids returned: {ids}")
    finally:
        DB.coupons.delete_one({"_id": legacy_id})


def test_admin_backfill_endpoint_sets_coupon_id(admin_session=None):
    """Admin backfill route writes `coupon_id = str(_id)` for legacy rows."""
    admin = _login("admin@bigfm.dubai", "AdminPass123!")
    legacy_id = f"legacy_backfill_{uuid.uuid4().hex[:10]}"
    DB.coupons.delete_one({"_id": legacy_id})
    DB.coupons.insert_one({
        "_id": legacy_id, "offer_id": "x", "business_id": "y",
        "user_id": "ghost_user", "status": "claimed",
        "claimed_at": datetime.now(timezone.utc),
    })
    try:
        r = admin.post(
            f"{API}/admin/coupons/backfill_missing_ids", timeout=10)
        assert r.status_code == 200, r.text
        assert (r.json() or {}).get("backfilled") >= 1
        row = DB.coupons.find_one({"_id": legacy_id})
        assert row.get("coupon_id") == legacy_id
        # Idempotent — second call should not re-backfill the same row
        r2 = admin.post(
            f"{API}/admin/coupons/backfill_missing_ids", timeout=10)
        assert r2.status_code == 200, r2.text
    finally:
        DB.coupons.delete_one({"_id": legacy_id})


def test_coupons_me_handles_mix_of_valid_and_legacy_rows():
    """Listing endpoint must render the legacy row alongside a normal one."""
    user = _login("test@bigfm.dubai", "TestUser123!")
    uid = user._user_id
    legacy_id = f"mix_legacy_{uuid.uuid4().hex[:10]}"
    proper_id = f"mix_proper_{uuid.uuid4().hex[:10]}"
    now = datetime.now(timezone.utc)
    DB.coupons.delete_one({"_id": legacy_id})
    DB.coupons.delete_one({"_id": proper_id})
    DB.coupons.insert_one({
        "_id": legacy_id, "offer_id": "x", "business_id": "y",
        "user_id": uid, "status": "claimed", "claimed_at": now,
    })
    DB.coupons.insert_one({
        "_id": proper_id, "coupon_id": proper_id, "offer_id": "x",
        "business_id": "y", "user_id": uid, "status": "claimed",
        "claimed_at": now,
    })
    try:
        r = user.get(f"{API}/commerce/coupons/me", timeout=10)
        assert r.status_code == 200, r.text
        items = r.json().get("items") if isinstance(r.json(), dict) else r.json()
        ids = [it.get("coupon_id") for it in items]
        assert legacy_id in ids, ids
        assert proper_id in ids, ids
    finally:
        DB.coupons.delete_one({"_id": legacy_id})
        DB.coupons.delete_one({"_id": proper_id})
