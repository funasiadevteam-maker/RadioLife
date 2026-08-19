"""Iter98 — Partner Ads Console enhancements
- Spend Dashboard: GET /api/partner/commerce/analytics/summary
- Console History: GET /api/partner/commerce/history + refresh growth
- Voice Favourites: POST /api/partner/commerce/voice-favourite + catalog reflect
- Admin Bulk Approve: POST /api/admin/marketplace/promotions/bulk-approve
Regression: existing sandbox purchase (promotion) still works.
"""
import os
import pytest
import requests

def _read_env(path, key):
    try:
        with open(path) as f:
            for line in f:
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip()
    except FileNotFoundError:
        return None
    return None

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")
ADV_EMAIL = "test@bigfm.dubai"
ADV_PASS = "TestUser123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"


@pytest.fixture(scope="module")
def adv_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADV_EMAIL, "password": ADV_PASS}, timeout=15)
    assert r.status_code == 200, f"advertiser login failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    return s


# ── Spend Dashboard ──────────────────────────────────────────────────
SUMMARY_FIELDS = [
    "promotions", "active_promotions", "pending_promotions",
    "impressions", "orders", "revenue_cents",
    "placement_spend_cents", "spotlight_spend_cents", "total_spend_cents",
]


def test_spend_summary_has_all_fields(adv_session):
    r = adv_session.get(f"{BASE_URL}/api/partner/commerce/analytics/summary", timeout=15)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    for k in SUMMARY_FIELDS:
        assert k in data, f"missing field {k} in summary response: {list(data.keys())}"
        assert isinstance(data[k], (int, float)), f"{k} not numeric: {data[k]!r}"
    assert data["promotions"] >= 0
    assert data["total_spend_cents"] >= 0


# ── Console History ──────────────────────────────────────────────────
def test_history_returns_unified_items(adv_session):
    r = adv_session.get(f"{BASE_URL}/api/partner/commerce/history", timeout=15)
    assert r.status_code == 200, r.text[:200]
    data = r.json()
    assert "items" in data and "count" in data
    assert isinstance(data["items"], list)
    assert data["count"] == len(data["items"])
    if data["items"]:
        allowed_kinds = {"promotion", "spotlight", "trivia", "rj_read"}
        for it in data["items"]:
            assert "kind" in it and it["kind"] in allowed_kinds, f"bad kind: {it.get('kind')}"
            assert "id" in it and it["id"]
            assert "status" in it
            # environment is either SANDBOX/LIVE or None-ish
            env = it.get("environment")
            assert env is None or env in ("SANDBOX", "LIVE", "sandbox", "live", "")


def test_history_grows_after_new_sandbox_purchase(adv_session):
    """Regression: create a sandbox promotion and verify history count grows."""
    # snapshot count
    r0 = adv_session.get(f"{BASE_URL}/api/partner/commerce/history", timeout=15)
    assert r0.status_code == 200
    before = r0.json()["count"]

    # need a business + tier from catalog
    cat = adv_session.get(f"{BASE_URL}/api/partner/commerce/catalog", timeout=15).json()
    biz = (cat.get("businesses") or [])
    tiers = (cat.get("tiers") or [])
    if not biz or not tiers:
        pytest.skip("no promotable businesses/tiers seeded")
    tier_key = tiers[0].get("tier") or tiers[0].get("key")
    r = adv_session.post(
        f"{BASE_URL}/api/partner/commerce/promotion/checkout",
        json={"business_id": biz[0]["business_id"], "tier": tier_key,
              "environment": "sandbox"}, timeout=20)
    assert r.status_code == 200, f"sandbox promo checkout failed: {r.text[:200]}"
    assert r.json().get("sandbox") is True or r.json().get("status") in ("active", "credited")

    r1 = adv_session.get(f"{BASE_URL}/api/partner/commerce/history", timeout=15)
    assert r1.status_code == 200
    after = r1.json()["count"]
    assert after >= before + 1, f"history did not grow: before={before} after={after}"


# ── Voice Favourites ─────────────────────────────────────────────────
def test_voice_favourite_persists_and_reflects_in_catalog(adv_session):
    # find any persona
    cat = adv_session.get(f"{BASE_URL}/api/partner/commerce/catalog", timeout=15).json()
    personas = cat.get("personas") or []
    if not personas:
        pytest.skip("no personas seeded")
    pid = personas[0]["id"]

    # set favourite
    r = adv_session.post(f"{BASE_URL}/api/partner/commerce/voice-favourite",
                         json={"persona_id": pid}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    assert r.json().get("favourite_persona_id") == pid

    # catalog reflects
    cat2 = adv_session.get(f"{BASE_URL}/api/partner/commerce/catalog", timeout=15).json()
    assert cat2.get("favourite_persona_id") == pid

    # clear
    r = adv_session.post(f"{BASE_URL}/api/partner/commerce/voice-favourite",
                         json={"persona_id": None}, timeout=15)
    assert r.status_code == 200
    assert r.json().get("favourite_persona_id") is None

    cat3 = adv_session.get(f"{BASE_URL}/api/partner/commerce/catalog", timeout=15).json()
    assert cat3.get("favourite_persona_id") in (None, "")


# ── Admin Bulk Approve ───────────────────────────────────────────────
def test_bulk_approve_response_shape(admin_session):
    """Non-reviewable ids should surface in `failed` with a code; unknown id ->
    promotion_not_found. Empty list returns empty results."""
    r = admin_session.post(
        f"{BASE_URL}/api/admin/marketplace/promotions/bulk-approve",
        json={"promotion_ids": []}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert set(["approved", "approved_count", "failed", "failed_count"]).issubset(d.keys())
    assert d["approved_count"] == 0 and d["failed_count"] == 0

    # unknown id -> failed with promotion_not_found
    r = admin_session.post(
        f"{BASE_URL}/api/admin/marketplace/promotions/bulk-approve",
        json={"promotion_ids": ["promo_does_not_exist_xyz"]}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["approved_count"] == 0
    assert d["failed_count"] == 1
    codes = [f.get("code") for f in d["failed"]]
    assert "promotion_not_found" in codes


def test_bulk_approve_happy_path_with_pending_review(admin_session):
    """If any promotion is in pending_review, bulk-approve must move it to
    active. If none exists, we skip and only assert shape."""
    # find pending_review promotions
    r = admin_session.get(f"{BASE_URL}/api/admin/marketplace/promotions",
                          params={"status": "pending_review", "limit": 5}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    items = r.json().get("items", [])
    if not items:
        pytest.skip("no pending_review promotions to bulk-approve")
    ids = [p["promotion_id"] for p in items[:3]]

    r = admin_session.post(
        f"{BASE_URL}/api/admin/marketplace/promotions/bulk-approve",
        json={"promotion_ids": ids}, timeout=20)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert d["approved_count"] >= 1
    assert set(d["approved"]).issubset(set(ids))

    # verify each approved is now active
    for pid in d["approved"]:
        chk = admin_session.get(
            f"{BASE_URL}/api/admin/marketplace/promotions",
            params={"status": "active", "limit": 200}, timeout=15).json()
        assert any(p["promotion_id"] == pid for p in chk.get("items", [])), \
            f"approved promotion {pid} not found in active list"


def test_bulk_approve_max_100_ids(admin_session):
    """Backend caps at 100 ids; extras should be silently ignored."""
    ids = [f"promo_fake_{i}" for i in range(150)]
    r = admin_session.post(
        f"{BASE_URL}/api/admin/marketplace/promotions/bulk-approve",
        json={"promotion_ids": ids}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    # 100 attempts, all failed
    assert d["approved_count"] + d["failed_count"] <= 100


def test_admin_promotions_includes_via_partner_flag(admin_session):
    """`via_partner` + `partner_name` should appear on partner-purchased rows."""
    r = admin_session.get(f"{BASE_URL}/api/admin/marketplace/promotions",
                          params={"limit": 200}, timeout=15)
    assert r.status_code == 200, r.text[:200]
    items = r.json().get("items", [])
    partner_rows = [p for p in items if p.get("via_partner")]
    # Not strictly required to exist, but if any partner promotions were seeded,
    # we should be able to find at least one.
    if partner_rows:
        p = partner_rows[0]
        assert "partner_name" in p


# ── Bulk-approve permissions ─────────────────────────────────────────
def test_bulk_approve_requires_admin(adv_session):
    r = adv_session.post(
        f"{BASE_URL}/api/admin/marketplace/promotions/bulk-approve",
        json={"promotion_ids": ["x"]}, timeout=15)
    assert r.status_code in (401, 403), f"expected auth error, got {r.status_code}"
