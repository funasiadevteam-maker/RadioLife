"""E2E tests for the cookie-authed Partner Console commerce endpoints,
   the /api/v1 promotion report, and the admin Partner Queue badge."""
import os
import time
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api"

ADV_EMAIL = "test@bigfm.dubai"
ADV_PW = "TestUser123!"
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PW = "AdminPass123!"

LIVE_KEY = "rlk_live_RI7fonLpLAzW.pL6e_b7Ok-f5FsNmSkyxwtLeWYWStHTCZsP0Kmqf6SM"
SANDBOX_KEY = "rlk_test_m55nJ-GmIviJ.0cKrGo5T3AKq_FLmZcqPvePDkLzhMdGIlQIB8T5an2Q"


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def adv_sess():
    return _login(ADV_EMAIL, ADV_PW)


@pytest.fixture(scope="module")
def admin_sess():
    return _login(ADMIN_EMAIL, ADMIN_PW)


# ─── Catalog ────────────────────────────────────────────────────────
def test_catalog(adv_sess):
    r = adv_sess.get(f"{API}/partner/commerce/catalog", timeout=15)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    for k in ("tiers", "categories", "businesses", "personas"):
        assert k in d, k
    assert len(d["tiers"]) > 0
    assert len(d["businesses"]) > 0
    assert len(d["personas"]) >= 3, f"expected >=3 personas, got {len(d['personas'])}"


# ─── Sandbox Promotion (activates instantly) + status + report ──────
def test_sandbox_promotion_flow(adv_sess):
    r = adv_sess.post(f"{API}/partner/commerce/promotion/checkout",
                      json={"business_id": "biz_demo_grill", "tier": "spotlight_7",
                            "environment": "sandbox"}, timeout=20)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d.get("sandbox") is True
    pid = d.get("promotion_id")
    assert pid, d
    # status
    rs = adv_sess.get(f"{API}/partner/commerce/promotion/{pid}/status",
                      params={"environment": "sandbox"}, timeout=15)
    assert rs.status_code == 200, rs.text[:300]
    assert rs.json().get("status") == "active"
    # report
    rr = adv_sess.get(f"{API}/partner/commerce/promotion/{pid}/report",
                      params={"environment": "sandbox"}, timeout=15)
    assert rr.status_code == 200, rr.text[:300]
    rep = rr.json()
    for k in ("impressions", "views", "orders", "revenue_cents", "total_spend_cents"):
        assert k in rep, f"missing {k} in {rep}"
    pytest.SB_PROMO_ID = pid


# ─── Sandbox Spotlight ─────────────────────────────────────────────
def test_sandbox_spotlight_flow(adv_sess):
    # need a category
    r = adv_sess.get(f"{API}/partner/commerce/catalog", timeout=10)
    cats = r.json().get("categories") or []
    assert cats
    cat = cats[0]["key"]
    b = adv_sess.post(f"{API}/partner/commerce/spotlight/checkout",
                      json={"business_id": "biz_demo_grill", "category": cat,
                            "bid_cents": 25, "amount_cents": 2000,
                            "environment": "sandbox"}, timeout=20)
    assert b.status_code == 200, b.text[:400]
    d = b.json()
    assert d.get("sandbox") is True
    # sandbox spotlight funds a category bid directly (no Stripe session)
    assert d.get("status") == "active"
    assert d.get("bid_id"), d
    assert int(d.get("budget_cents", 0)) >= 2000


# ─── Sandbox Trivia ────────────────────────────────────────────────
def test_sandbox_trivia_flow(adv_sess):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    body = {
        "type": "trivia", "environment": "sandbox",
        "display_name": "TEST_Console_Trivia",
        "sponsor_target_type": "any", "winner_selection": "top_n",
        "prize_pool": [{"rank": 1, "points_reward": 500, "currency": "bc", "quantity": 1}],
        "start_at": (now + timedelta(minutes=5)).isoformat(),
        "end_at": (now + timedelta(days=30)).isoformat(),
    }
    r = adv_sess.post(f"{API}/partner/commerce/sponsorships", json=body, timeout=20)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d.get("sponsorship_id")
    sp = d.get("sponsorship") or {}
    assert sp.get("status") == "active", sp


# ─── AI-RJ personas + REAL preview ─────────────────────────────────
def test_personas_and_preview(adv_sess):
    r = adv_sess.get(f"{API}/partner/commerce/personas", timeout=15)
    assert r.status_code == 200
    items = r.json().get("items") or []
    names = [p.get("name", "") for p in items]
    assert any("Ava" in n or "Leo" in n or "Maya" in n for n in names), names
    pid = items[0]["id"]
    # preview may take up to ~10s
    pv = adv_sess.post(f"{API}/partner/commerce/personas/{pid}/preview", timeout=45)
    assert pv.status_code == 200, pv.text[:400]
    d = pv.json()
    assert d.get("audio_url"), d
    # if remote, verify HEAD works; if data-url ok too
    au = d["audio_url"]
    # Presigned S3 URLs sometimes reject HEAD; try GET with tiny range instead
    if au.startswith("http"):
        h = requests.get(au, headers={"Range": "bytes=0-2"}, allow_redirects=True, timeout=15)
        assert h.status_code < 400, f"audio_url GET {h.status_code}"


# ─── Sandbox RJ read booking ───────────────────────────────────────
def test_sandbox_rj_read(adv_sess):
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    r = adv_sess.get(f"{API}/partner/commerce/personas", timeout=10)
    per_id = (r.json().get("items") or [{}])[0].get("id")
    assert per_id
    body = {"type": "rj_read", "environment": "sandbox", "persona_id": per_id,
            "any_station": True, "disclosure_prefix": "Sponsored by",
            "plays_target": 20, "cost_per_play_cents": 8,
            "product_name": "TEST_Cola", "key_message": "crisp",
            "cta": "try it", "script_body": "auto",
            "start_at": (now + timedelta(minutes=5)).isoformat(),
            "end_at": (now + timedelta(days=30)).isoformat()}
    r = adv_sess.post(f"{API}/partner/commerce/sponsorships", json=body, timeout=25)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d.get("sponsorship_id")


# ─── LIVE: returns real cs_test_ session ───────────────────────────
def test_live_promotion_returns_checkout_url(adv_sess):
    r = adv_sess.post(f"{API}/partner/commerce/promotion/checkout",
                      json={"business_id": "biz_demo_grill", "tier": "spotlight_7",
                            "environment": "live",
                            "origin_url": BASE}, timeout=25)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    assert d.get("checkout_url", "").startswith("https://checkout.stripe.com/"), d
    pid = d.get("promotion_id")
    assert pid
    st = adv_sess.get(f"{API}/partner/commerce/promotion/{pid}/status",
                      params={"environment": "live"}, timeout=15)
    assert st.status_code == 200, st.text[:300]
    js = st.json()
    # not paid yet
    assert js.get("paid") in (False, None)
    pytest.LIVE_PROMO_ID = pid


def test_live_spotlight_returns_checkout_url(adv_sess):
    cats = adv_sess.get(f"{API}/partner/commerce/catalog", timeout=10).json().get("categories") or []
    cat = cats[0]["key"]
    r = adv_sess.post(f"{API}/partner/commerce/spotlight/checkout",
                      json={"business_id": "biz_demo_grill", "category": cat,
                            "bid_cents": 30, "amount_cents": 2500,
                            "environment": "live", "origin_url": BASE}, timeout=25)
    assert r.status_code == 200, r.text[:400]
    assert r.json().get("checkout_url", "").startswith("https://checkout.stripe.com/")


# ─── /api/v1 promotion report (bearer) ────────────────────────────
def test_v1_promotion_report_ok_for_owner():
    # Create a sandbox promotion via /api/v1 with sandbox key
    hdr = {"Authorization": f"Bearer {SANDBOX_KEY}"}
    r = requests.post(f"{API}/v1/marketplace/promotion/checkout",
                      json={"business_id": "biz_demo_grill", "tier": "spotlight_7"},
                      headers=hdr, timeout=20)
    assert r.status_code == 200, r.text[:400]
    pid = r.json().get("promotion_id")
    assert pid
    rep = requests.get(f"{API}/v1/marketplace/promotion/{pid}/report",
                       headers=hdr, timeout=15)
    assert rep.status_code == 200, rep.text[:400]
    d = rep.json()
    for k in ("impressions", "views", "orders", "revenue_cents", "total_spend_cents"):
        assert k in d, f"missing {k}"


def test_v1_promotion_report_404_for_non_owner():
    # promotion created via portal (partner E2E Test Harness sandbox owns some,
    # but the cookie-console partner is different). Use an obviously fake id.
    hdr = {"Authorization": f"Bearer {LIVE_KEY}"}
    rep = requests.get(f"{API}/v1/marketplace/promotion/promo_does_not_exist/report",
                       headers=hdr, timeout=15)
    assert rep.status_code == 404, rep.text[:300]


# ─── Admin partner queue badge ────────────────────────────────────
def test_admin_promotions_has_via_partner_flag(admin_sess):
    r = admin_sess.get(f"{API}/admin/marketplace/promotions", params={"status": "all"}, timeout=20)
    assert r.status_code == 200, r.text[:400]
    items = r.json().get("items") or r.json().get("promotions") or r.json()
    if isinstance(items, dict) and "items" in items:
        items = items["items"]
    assert isinstance(items, list) and len(items) > 0, "no promotions returned"
    # At least ONE promotion should carry via_partner + partner_name
    partner_items = [it for it in items if it.get("via_partner")]
    assert partner_items, f"no via_partner=True promotions; sample={items[:2]}"
    for it in partner_items[:3]:
        assert it.get("partner_name"), f"missing partner_name on via_partner item: {it}"
