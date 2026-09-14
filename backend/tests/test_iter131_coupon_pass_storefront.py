"""P1 — Unified Coupon Passes (QR + in-store redeem) + Store Links.

Covers:
- POST /api/me/coupons/pass          (idempotent mint)
- GET  /api/coupons/pass/{token}     (public preview)
- POST /api/coupons/redeem/{token}   (staff-only)
- GET  /api/sponsors/{advertiser_id}/store
- store key presence on /api/ads/current + /api/banner/serve
"""
import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def demo_session():
    return _login("demo@bigfm.dubai", "DemoPass123!")


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def demo_coupon(demo_session):
    """Grab one of demo@'s owned coupons via the unified wallet endpoint."""
    r = demo_session.get(f"{BASE}/api/me/wallet-coupons", timeout=15)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    items = data.get("items") or []
    assert items, "demo@ has no coupons — seed check failed"
    # Prefer a NON-redeemed one for the redeem test
    non_red = [c for c in items if c.get("status") not in ("redeemed", "used")]
    return (non_red[0] if non_red else items[0]), items


# ─── Sponsor store endpoint ─────────────────────────────────────
class TestSponsorStore:
    def test_known_advertiser_has_store(self):
        r = requests.get(f"{BASE}/api/sponsors/adv_fpk/store", timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("has_store") is True
        assert d.get("store_url") == "/store/adv_fpk"
        assert d.get("name")  # non-empty
        assert d.get("advertiser_id") == "adv_fpk"

    def test_unknown_advertiser_has_no_store(self):
        r = requests.get(f"{BASE}/api/sponsors/adv_nope_zzz_xxx/store", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d.get("has_store") is False
        assert d.get("store_url") is None


# ─── Coupon-pass mint / preview / redeem ────────────────────────
class TestCouponPass:
    def test_mint_pass_idempotent(self, demo_session, demo_coupon):
        coupon, _ = demo_coupon
        body = {"source": coupon["source"], "id": coupon["id"]}
        r1 = demo_session.post(f"{BASE}/api/me/coupons/pass", json=body, timeout=15)
        assert r1.status_code == 200, r1.text[:300]
        d1 = r1.json()
        assert d1["token"].startswith("clp_"), d1
        assert d1["qr_data_uri"].startswith("data:image/png;base64,")
        assert len(d1["qr_data_uri"]) > 200
        assert d1.get("code")
        assert d1.get("title")
        assert d1.get("status") in ("active", "redeemed")

        # idempotent — same token
        r2 = demo_session.post(f"{BASE}/api/me/coupons/pass", json=body, timeout=15)
        assert r2.status_code == 200
        assert r2.json()["token"] == d1["token"], "pass mint must be idempotent"

    def test_public_preview_pass(self, demo_session, demo_coupon):
        coupon, _ = demo_coupon
        r = demo_session.post(f"{BASE}/api/me/coupons/pass",
                              json={"source": coupon["source"], "id": coupon["id"]}, timeout=15)
        token = r.json()["token"]
        # Public preview — no auth
        r2 = requests.get(f"{BASE}/api/coupons/pass/{token}", timeout=15)
        assert r2.status_code == 200, r2.text[:300]
        d = r2.json()
        assert d["token"] == token
        assert "status" in d
        assert "title" in d and "code" in d

    def test_invalid_source_400(self, demo_session):
        r = demo_session.post(f"{BASE}/api/me/coupons/pass",
                              json={"source": "bogus", "id": "x"}, timeout=15)
        assert r.status_code == 400

    def test_unknown_coupon_404(self, demo_session):
        r = demo_session.post(f"{BASE}/api/me/coupons/pass",
                              json={"source": "wallet", "id": "wi_does_not_exist_zzz"}, timeout=15)
        assert r.status_code == 404

    def test_consumer_cannot_redeem(self, demo_session, demo_coupon):
        coupon, _ = demo_coupon
        r = demo_session.post(f"{BASE}/api/me/coupons/pass",
                              json={"source": coupon["source"], "id": coupon["id"]}, timeout=15)
        token = r.json()["token"]
        # Consumer role — 403
        r2 = demo_session.post(f"{BASE}/api/coupons/redeem/{token}", timeout=15)
        assert r2.status_code == 403, f"expected 403 got {r2.status_code}: {r2.text[:200]}"

    def test_admin_can_redeem_and_replay_blocked(self, demo_session, admin_session, demo_coupon):
        # Pick a NON-redeemed coupon to guarantee we can settle it fresh.
        _, items = demo_coupon
        fresh = [c for c in items if c.get("status") not in ("redeemed", "used")]
        assert fresh, "no active coupon available for redeem test"
        c = fresh[0]
        r = demo_session.post(f"{BASE}/api/me/coupons/pass",
                              json={"source": c["source"], "id": c["id"]}, timeout=15)
        assert r.status_code == 200
        token = r.json()["token"]
        assert r.json()["status"] == "active", "picked coupon should be active"

        # Admin redeems — succeed
        r1 = admin_session.post(f"{BASE}/api/coupons/redeem/{token}", timeout=15)
        assert r1.status_code == 200, r1.text[:300]
        d1 = r1.json()
        assert d1.get("ok") is True
        assert d1.get("status") == "redeemed"

        # Second admin call — already_redeemed
        r2 = admin_session.post(f"{BASE}/api/coupons/redeem/{token}", timeout=15)
        assert r2.status_code == 400, r2.text[:200]
        assert "already_redeemed" in r2.text

        # Underlying source should reflect redemption in /me/wallet-coupons
        wr = demo_session.get(f"{BASE}/api/me/wallet-coupons", timeout=15)
        assert wr.status_code == 200
        matches = [x for x in wr.json().get("items") or []
                   if x.get("id") == c["id"] and x.get("source") == c["source"]]
        assert matches, "coupon disappeared after redemption"
        assert matches[0].get("status") in ("redeemed", "used"), \
            f"underlying source not synced: {matches[0].get('status')}"


# ─── Store-key injection on ad + banner endpoints ───────────────
class TestStoreInjection:
    def test_current_ad_has_store_key(self):
        # KEY EXISTS check — the response may say has_ad=false in the test env.
        r = requests.get(f"{BASE}/api/ads/current",
                         params={"session_id": "test_iter131_sid"}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # If has_ad is False we treat store-absence as acceptable (no ad served);
        # otherwise the payload MUST carry the store key (may be None).
        if d.get("has_ad"):
            assert "store" in d, f"store key missing on current_ad: keys={list(d.keys())}"

    def test_banner_serve_has_store_key(self):
        r = requests.get(f"{BASE}/api/banner/serve",
                         params={"zone": "now_playing"}, timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # If no live banner, banner is None — that's fine, endpoint must not 500.
        if d.get("banner"):
            assert "store" in d["banner"], \
                f"store key missing on banner: keys={list(d['banner'].keys())}"
