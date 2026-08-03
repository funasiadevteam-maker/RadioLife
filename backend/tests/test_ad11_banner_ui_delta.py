"""AD.11 Phase — delta tests: /api/banner/serve, impression dedup + frequency cap,
admin nav-counts, openapi.

Uses direct mongo insertion to spin up 4 live banners for the freq-cap test
because the seed set only has one live banner (bnr_079349a719cbde)."""
import os
import time
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASSWORD = "AdminPass123!"
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASSWORD = "DemoPass123!"


@pytest.fixture(scope="module")
def db():
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


# ─── /api/banner/serve ──────────────────────────────────────────
def test_serve_landing_hero_returns_seed():
    r = requests.get(f"{BASE_URL}/api/banner/serve", params={"zone": "landing_hero", "session_id": "sess_srv_probe"})
    assert r.status_code == 200
    d = r.json()
    assert d["zone"] == "landing_hero"
    # Seed banner should be served (or null if no auction match)
    if d.get("banner"):
        b = d["banner"]
        for k in ("banner_id", "creative_url", "target_url", "cta_text"):
            assert k in b, f"missing key {k}"


def test_serve_invalid_zone_returns_400():
    r = requests.get(f"{BASE_URL}/api/banner/serve", params={"zone": "not_a_zone"})
    assert r.status_code == 400


# ─── Dedup: same (session, banner, zone) within 5min → already_billed ───
def test_impression_dedup_returns_already_billed():
    sid = f"sess_dedup_{uuid.uuid4().hex[:10]}"
    payload = {"banner_id": "bnr_079349a719cbde", "zone": "landing_hero", "session_id": sid}
    r1 = requests.post(f"{BASE_URL}/api/banner/impression", json=payload)
    assert r1.status_code == 200, f"first impression 5xx (known bug): {r1.status_code} {r1.text}"
    d1 = r1.json()
    assert d1.get("ok") is True, f"first impression not ok: {d1}"
    assert not d1.get("already_billed"), f"first call unexpectedly already_billed: {d1}"

    r2 = requests.post(f"{BASE_URL}/api/banner/impression", json=payload)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("already_billed") is True, f"dedup failed: {d2}"
    assert d2.get("impression_id") == d1.get("impression_id")


# ─── Fresh impression response shape + ledger row (AD.11 fix delta) ───
def test_fresh_impression_returns_full_billing_shape_and_ledger(db):
    sid = f"sess_fresh_{uuid.uuid4().hex[:10]}"
    payload = {"banner_id": "bnr_079349a719cbde", "zone": "landing_hero", "session_id": sid}
    try:
        r = requests.post(f"{BASE_URL}/api/banner/impression", json=payload)
        assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
        d = r.json()
        assert d.get("ok") is True, f"ok not true: {d}"
        assert not d.get("already_billed"), f"unexpected already_billed on fresh: {d}"
        assert isinstance(d.get("impression_id"), str) and d["impression_id"].startswith("bimp_"), f"bad impression_id: {d}"
        for k in ("cost_cents", "app_fee_cents", "merchant_net_cents"):
            assert k in d, f"missing key {k} in response: {d}"
            assert isinstance(d[k], int), f"{k} not int: {type(d[k])}"

        # verify ledger row: find the most recent ad11 ledger row for this banner
        # and assert stripe_payment_intent_id == transaction_id (sentinel per fix)
        ledger = db.payment_transactions_v2.find_one(
            {"flow": "ad11_banner_impression", "banner_id": payload["banner_id"]},
            sort=[("created_at", -1)])
        assert ledger, "no ad11_banner_impression ledger row found"
        tx_id = ledger.get("transaction_id")
        assert tx_id and tx_id.startswith("tx_bnr"), f"bad tx_id: {tx_id}"
        assert ledger.get("stripe_payment_intent_id") == tx_id, (
            f"stripe_payment_intent_id sentinel mismatch: pi={ledger.get('stripe_payment_intent_id')} tx={tx_id}"
        )
        assert ledger.get("amount_cents") == d["cost_cents"]
    finally:
        db.banner_impressions.delete_many({"session_id": sid})


# ─── AD.11 frequency cap ────────────────────────────────────────
def _ensure_extra_live_banners(db, count=3):
    """Create N extra live banners tied to the same seed advertiser so we
    can test cap with unique banner_ids in the same session+zone."""
    seed = db.banner_campaigns.find_one({"banner_id": "bnr_079349a719cbde"})
    assert seed, "seed banner missing"
    created = []
    for i in range(count):
        bid = f"bnr_test_cap_{uuid.uuid4().hex[:10]}"
        doc = {k: v for k, v in seed.items() if k != "_id"}
        doc["banner_id"] = bid
        doc["placement_zones"] = ["landing_hero"]
        doc["per_zone_cpm_cents"] = {"landing_hero": 800}
        doc["status"] = "live"
        db.banner_campaigns.insert_one(doc)
        created.append(bid)
    return created


def test_frequency_cap_session_zone_3_per_zone(db):
    """With 4 unique banner_ids sharing (session, zone), the 4th call is capped."""
    extra_ids = _ensure_extra_live_banners(db, 3)
    all_ids = ["bnr_079349a719cbde"] + extra_ids
    sid = f"sess_cap_{uuid.uuid4().hex[:10]}"
    try:
        results = []
        for bid in all_ids:
            r = requests.post(f"{BASE_URL}/api/banner/impression",
                              json={"banner_id": bid, "zone": "landing_hero", "session_id": sid})
            results.append((r.status_code, r.text))

        # First 3 must now return 200 (fix delta)
        for i in range(3):
            assert results[i][0] == 200, f"call {i+1} not 200 after fix: {results[i]}"

        code4, body4 = results[3]
        assert code4 == 200, f"4th call not 200: {code4} {body4}"
        import json as _json
        r4 = _json.loads(body4)
        assert r4.get("ok") is True
        assert r4.get("capped") is True, f"4th call not capped: {r4}"
        assert r4.get("reason") == "session_zone_cap_reached"
        assert r4.get("cap") == 3
        assert r4.get("current") == 3
    finally:
        db.banner_campaigns.delete_many({"banner_id": {"$in": extra_ids}})
        db.banner_impressions.delete_many({"session_id": sid})


# ─── /api/admin/nav-counts ──────────────────────────────────────
def test_admin_nav_counts_requires_auth():
    r = requests.get(f"{BASE_URL}/api/admin/nav-counts")
    assert r.status_code in (401, 403)


def test_admin_nav_counts_shape(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/admin/nav-counts")
    assert r.status_code == 200, r.text
    d = r.json()
    expected_keys = [
        "ad_review_pending",
        "banner_reviews_pending",
        "merchant_applications_pending",
        "refunds_pending",
        "station_claims_pending",
        "podcast_apps_pending",
    ]
    for k in expected_keys:
        assert k in d, f"missing key {k} in {list(d.keys())}"
        assert isinstance(d[k], int), f"{k} not int: {type(d[k])}"


# ─── OpenAPI routes present ─────────────────────────────────────
def test_openapi_contains_ad11_routes():
    r = requests.get(f"{BASE_URL}/api/openapi.json")
    assert r.status_code == 200
    d = r.json()
    paths = set(d["paths"].keys())
    required = [
        "/api/advertiser/{advertiser_id}/banner-campaigns",
        "/api/banner/serve",
        "/api/banner/impression",
        "/api/admin/nav-counts",
    ]
    for p in required:
        assert p in paths, f"missing openapi path {p}"
