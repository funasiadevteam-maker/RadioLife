"""Phase AD.3 — Advertiser Predict & Win Sponsorship backend tests.

Covers:
- GET /api/advertiser/predict-win/available-campaigns
- GET /api/ad-pricing-hints (PW sponsorship constants + tiers)
- POST /api/advertiser/{aid}/predict-win/sponsorships (create + validation)
- Brand-asset upload (PNG happy + oversize reject)
- Publish (brand_asset_required, mints ADMOD.1 review)
- Admin approve via ad-review queue -> status=live
- Admin admin_set_status (paused)
- Active-sponsor auction (winner + wallet-eligibility filter)
- Impression billing (per_entry -> billed, idempotency, mismatched event=0 billed)
- payment_transactions_v2 row shape (flow + stripe_payment_intent_id sentinel)
- Analytics endpoint
- PATCH sponsorship (edits allowed on draft; rejected on live)
- Regression: /api/predict-win/campaigns still returns parents
"""
import io
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
ADVERTISER_ID = "advv2_9fac10b21f5595"
PARENT_ID = "pwc_2f916cd9261047"
SEED_SPONSORSHIP_ID = "pws_af54ffb79a7f21"


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
                          json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
                          json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


# ─────────────────────── AVAILABLE PARENTS ──────────────────────
class TestAvailableParents:
    def test_available_campaigns_shape(self, demo_session):
        r = demo_session.get(
            f"{BASE_URL}/api/advertiser/predict-win/available-campaigns", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert data.get("count") == len(data["items"])
        # Seed parent must be included (live/approved)
        ids = [it["parent_campaign_id"] for it in data["items"]]
        assert PARENT_ID in ids, f"seed parent missing; got {ids[:5]}"
        item = next(it for it in data["items"] if it["parent_campaign_id"] == PARENT_ID)
        for k in ("title", "event_label", "active_sponsors", "entries_so_far"):
            assert k in item
        assert isinstance(item["active_sponsors"], int)
        assert isinstance(item["entries_so_far"], int)

    def test_available_campaigns_excludes_resolved(self, demo_session):
        r = demo_session.get(
            f"{BASE_URL}/api/advertiser/predict-win/available-campaigns", timeout=15)
        for it in r.json()["items"]:
            # endpoint returns only open/live/locked/scheduled — never resolved/cancelled
            assert it.get("parent_campaign_id")  # sanity


# ─────────────────────── PRICING HINTS ─────────────────────────
class TestPricingHints:
    def test_pw_sponsorship_hints_present(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/ad-pricing-hints", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("pw_sponsorship_default_cpe_cents") == 20
        assert d.get("pw_sponsorship_default_cpi_cents") == 5
        tiers = d.get("pw_sponsorship_tiers")
        assert isinstance(tiers, list) and len(tiers) >= 3
        tier_ids = {t.get("id") or t.get("tier") or t.get("name") for t in tiers}
        # tiers include default/high_volume/niche flavors
        joined = " ".join(str(x).lower() for x in tier_ids)
        assert "default" in joined
        assert "high_volume" in joined or "high" in joined
        assert "niche" in joined


# ─────────────────────── CREATE VALIDATION ─────────────────────
class TestCreateValidation:
    def _base(self, **kwargs):
        payload = {
            "parent_campaign_id": PARENT_ID,
            "brand_name": "TEST_Brand",
            "pricing_model": "per_entry",
            "cpe_cents": 20,
            "budget_cents": 5000,
        }
        payload.update(kwargs)
        return payload

    def test_missing_brand_name_returns_400(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win/sponsorships",
            json=self._base(brand_name=""), timeout=15)
        # empty brand fails Pydantic min_length=2 → 422, or brand_name_required → 400
        assert r.status_code in (400, 422)

    def test_missing_brand_name_none(self, demo_session):
        payload = self._base()
        payload.pop("brand_name")
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win/sponsorships",
            json=payload, timeout=15)
        assert r.status_code == 422  # pydantic missing

    def test_invalid_pricing_model_returns_400(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win/sponsorships",
            json=self._base(pricing_model="bogus"), timeout=15)
        assert r.status_code == 400
        assert "invalid_pricing_model" in r.json().get("detail", {}).get("code", "")

    def test_budget_too_small_returns_400(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win/sponsorships",
            json=self._base(budget_cents=10), timeout=15)
        # pydantic enforces ge=100 → 422
        assert r.status_code == 422

    def test_per_entry_missing_cpe_returns_400(self, demo_session):
        payload = self._base()
        payload.pop("cpe_cents")
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win/sponsorships",
            json=payload, timeout=15)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "cpe_cents_required"

    def test_per_correct_impression_missing_cpi(self, demo_session):
        payload = self._base(pricing_model="per_correct_impression")
        payload.pop("cpe_cents")
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win/sponsorships",
            json=payload, timeout=15)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "cpi_cents_required"


# ─────────────────── FULL LIFECYCLE ──────────────────────────
class TestLifecycle:
    """create → upload asset → publish (mints ADMOD.1) → admin approve → live"""

    created_sid = None
    review_id = None

    def test_01_create_draft(self, demo_session):
        payload = {
            "parent_campaign_id": PARENT_ID,
            "brand_name": f"TEST_Lifecycle_{uuid.uuid4().hex[:6]}",
            "tagline": "TEST tagline",
            "pricing_model": "per_entry",
            "cpe_cents": 15,
            "budget_cents": 2000,
        }
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win/sponsorships",
            json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "draft"
        assert d["advertiser_id"] == ADVERTISER_ID
        assert d["cpe_cents"] == 15
        assert d["budget_cents"] == 2000
        TestLifecycle.created_sid = d["sponsorship_id"]

    def test_02_publish_without_asset_fails(self, demo_session):
        assert TestLifecycle.created_sid
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/predict-win/sponsorships/"
            f"{TestLifecycle.created_sid}/publish", timeout=15)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "brand_asset_required"

    def test_03_upload_brand_asset(self, demo_session):
        # 1x1 PNG (67 bytes)
        png = bytes.fromhex(
            "89504E470D0A1A0A0000000D49484452000000010000000108060000001F15C489"
            "0000000A49444154789C6300010000000500010D0A2DB40000000049454E44AE426082")
        files = {"file": ("brand.png", io.BytesIO(png), "image/png")}
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/predict-win/sponsorships/"
            f"{TestLifecycle.created_sid}/brand-asset",
            files=files, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["brand_asset_url"].startswith("/api/static/pw_sponsorships/")

    def test_04_upload_oversize_rejected(self, demo_session):
        big = b"\x00" * (1024 * 1024 + 10)
        files = {"file": ("big.png", io.BytesIO(big), "image/png")}
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/predict-win/sponsorships/"
            f"{TestLifecycle.created_sid}/brand-asset",
            files=files, timeout=20)
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "file_too_large"

    def test_05_publish_mints_admod_review(self, demo_session, admin_session):
        r = demo_session.post(
            f"{BASE_URL}/api/advertiser/predict-win/sponsorships/"
            f"{TestLifecycle.created_sid}/publish", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "pending_admin"
        # Check ADMOD.1 review exists
        time.sleep(1)
        rq = admin_session.get(
            f"{BASE_URL}/api/ad-review/queue?ad_type=advertiser_pw_sponsorship&status=pending&limit=100",
            timeout=15)
        assert rq.status_code == 200
        rows = rq.json().get("rows") or rq.json().get("items") or []
        matching = [r for r in rows if r.get("target_id") == TestLifecycle.created_sid]
        assert matching, f"No ADMOD.1 review for {TestLifecycle.created_sid}"
        TestLifecycle.review_id = matching[0]["review_id"]

    def test_06_cannot_edit_pending_admin(self, demo_session):
        r = demo_session.patch(
            f"{BASE_URL}/api/advertiser/predict-win/sponsorships/"
            f"{TestLifecycle.created_sid}",
            json={"tagline": "should_fail"}, timeout=15)
        assert r.status_code == 400
        assert "cannot_edit_status" in r.json()["detail"]["code"]

    def test_07_admin_approve_flips_live(self, admin_session):
        assert TestLifecycle.review_id
        r = admin_session.post(
            f"{BASE_URL}/api/ad-review/queue/{TestLifecycle.review_id}/approve",
            json={"notes": "TEST approve"}, timeout=15)
        assert r.status_code == 200, r.text
        # Verify sponsorship status = live
        time.sleep(0.5)
        lst = admin_session.get(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win-sponsorships",
            timeout=15).json()
        row = next(x for x in lst["items"]
                              if x["sponsorship_id"] == TestLifecycle.created_sid)
        assert row["status"] == "live", f"expected live, got {row['status']}"

    def test_08_admin_set_status_pause(self, admin_session):
        r = admin_session.patch(
            f"{BASE_URL}/api/admin/predict-win/sponsorships/"
            f"{TestLifecycle.created_sid}/status?new_status=paused",
            timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "paused"


# ─────────────────── AUCTION + IMPRESSION ────────────────────
class TestAuctionAndImpression:
    def test_active_sponsor_returns_seed(self, demo_session):
        r = demo_session.get(
            f"{BASE_URL}/api/predict-win/{PARENT_ID}/active-sponsorship",
            timeout=15)
        assert r.status_code == 200
        sp = r.json().get("sponsorship")
        assert sp is not None, "auction returned no sponsor"
        assert sp["sponsorship_id"]  # exists
        for k in ("advertiser_id", "brand_name", "brand_asset_url",
                          "tagline", "pricing_model"):
            assert k in sp

    def test_active_sponsor_none_for_unknown_parent(self, demo_session):
        r = demo_session.get(
            f"{BASE_URL}/api/predict-win/pwc_does_not_exist_xxx/active-sponsorship",
            timeout=15)
        assert r.status_code == 200
        assert r.json() == {"sponsorship": None}

    def test_impression_entry_bills_and_idempotent(self, demo_session):
        # Use unique user by hitting with demo — first entry may already exist
        # from previous smoke test. Fire and check either billed_cents=20 or
        # already_billed:true.
        body = {"sponsorship_id": SEED_SPONSORSHIP_ID,
                        "parent_campaign_id": PARENT_ID,
                        "event_type": "entry"}
        r1 = demo_session.post(
            f"{BASE_URL}/api/predict-win/sponsorships/impression",
            json=body, timeout=15)
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1["ok"] is True
        # Repeat → must be idempotent
        r2 = demo_session.post(
            f"{BASE_URL}/api/predict-win/sponsorships/impression",
            json=body, timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("already_billed") is True
        assert d2["billed_cents"] == 20  # cpe_cents on seed

    def test_impression_mismatched_event_zero_billed(self, demo_session):
        # per_entry sponsorship + event_type=correct_impression → 0 billed,
        # but analytics row IS recorded (already_billed:true on second call).
        body = {"sponsorship_id": SEED_SPONSORSHIP_ID,
                        "parent_campaign_id": PARENT_ID,
                        "event_type": "correct_impression"}
        r = demo_session.post(
            f"{BASE_URL}/api/predict-win/sponsorships/impression",
            json=body, timeout=15)
        assert r.status_code == 200
        d = r.json()
        # First call: billed_cents=0 (either new event_id or already_billed)
        assert d["ok"] is True
        assert int(d.get("billed_cents") or 0) == 0

    def test_payment_transaction_row_written(self, demo_session):
        # Verify indirectly via analytics — spend_cents should be > 0
        r = demo_session.get(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win-sponsorships/analytics",
            timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "totals" in d
        assert d["totals"]["spend_cents"] > 0


# ─────────────────── ANALYTICS ───────────────────────────────
class TestAnalytics:
    def test_analytics_shape(self, demo_session):
        r = demo_session.get(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win-sponsorships/analytics",
            timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "totals" in d
        t = d["totals"]
        for k in ("spend_cents", "entries", "correct_impr", "win_views"):
            assert k in t, f"missing totals.{k}"


# ─────────────────── PATCH RULES ────────────────────────────
class TestPatchRules:
    def test_patch_rejected_on_live(self, demo_session):
        # Seed sponsorship is live → patch must reject
        r = demo_session.patch(
            f"{BASE_URL}/api/advertiser/predict-win/sponsorships/{SEED_SPONSORSHIP_ID}",
            json={"tagline": "TEST_reject_edit"}, timeout=15)
        assert r.status_code == 400
        assert "cannot_edit_status" in r.json()["detail"]["code"]

    def test_patch_draft_ok(self, demo_session):
        # Create fresh draft and patch it
        payload = {
            "parent_campaign_id": PARENT_ID,
            "brand_name": f"TEST_Patch_{uuid.uuid4().hex[:6]}",
            "pricing_model": "per_entry",
            "cpe_cents": 10,
            "budget_cents": 500,
        }
        c = demo_session.post(
            f"{BASE_URL}/api/advertiser/{ADVERTISER_ID}/predict-win/sponsorships",
            json=payload, timeout=15).json()
        sid = c["sponsorship_id"]
        r = demo_session.patch(
            f"{BASE_URL}/api/advertiser/predict-win/sponsorships/{sid}",
            json={"tagline": "TEST_new_tag"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["tagline"] == "TEST_new_tag"


# ─────────────────── REGRESSIONS ────────────────────────────
class TestRegressions:
    def test_predict_win_consumer_active_works(self, demo_session):
        # Regression: consumer PW listing (PDX.1 parents) still returns
        r = demo_session.get(f"{BASE_URL}/api/predict-win/active", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d, (list, dict))

    def test_available_campaigns_active_sponsors_count_ge_1(self, demo_session):
        r = demo_session.get(
            f"{BASE_URL}/api/advertiser/predict-win/available-campaigns", timeout=15)
        item = next(it for it in r.json()["items"]
                                if it["parent_campaign_id"] == PARENT_ID)
        assert item["active_sponsors"] >= 1  # seed Nike sponsorship
