"""Iter 176 — Wave 2: SWITCH CITY + SPONSOR GAME BUILDER backend tests.

Covers:
  * PATCH /api/users/me/market (valid + reject unsupported)
  * GET /api/geo/me shape
  * GET  /api/games/sponsor/{merchant_id}/builder (owner + non-owner 403)
  * POST /api/games/sponsor/{merchant_id}/branded-games (points-only + validation)
  * POST /api/games/sponsor/.../branded-games/{game_id}/toggle
  * Playability: GET /api/games/wheel/config?game_id=<new_id> + list surfacing
"""
import io
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

TEST_EMAIL = "test@bigfm.dubai"
TEST_PASS = "TestUser123!"
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def test_session():
    return _login(TEST_EMAIL, TEST_PASS)


@pytest.fixture(scope="module")
def demo_session():
    return _login(DEMO_EMAIL, DEMO_PASS)


@pytest.fixture(scope="module")
def test_merchant_id(test_session):
    """Find a merchant owned by test@ (business_owner)."""
    r = test_session.get(f"{API}/merchant/mine", timeout=30)
    if r.status_code == 200 and isinstance(r.json(), dict):
        data = r.json()
        # Try common shapes
        items = data.get("businesses") or data.get("items") or []
        if items:
            b = items[0]
            return b.get("business_id") or b.get("id") or b.get("_id")
        if data.get("business_id"):
            return data["business_id"]
    # Fallback: try /api/merchant/me
    r2 = test_session.get(f"{API}/merchant/me", timeout=30)
    if r2.status_code == 200:
        d = r2.json()
        biz = d.get("business") or d
        bid = biz.get("business_id") or biz.get("id") or biz.get("_id")
        if bid:
            return bid
    pytest.skip(f"Could not resolve merchant for {TEST_EMAIL}: {r.status_code}/{r.text[:120]}")


# ─────────── SWITCH CITY ───────────
class TestSwitchCity:
    def test_geo_me_shape(self, test_session):
        r = test_session.get(f"{API}/geo/me", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "market" in data
        assert "city" in data

    def test_patch_market_london(self, test_session):
        r = test_session.patch(f"{API}/users/me/market", json={"market": "london"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("preferred_market") == "london"

        # GET geo/me should now reflect london
        r2 = test_session.get(f"{API}/geo/me", timeout=30)
        assert r2.status_code == 200
        assert r2.json().get("market") == "london"

    def test_patch_market_rejects_unsupported(self, test_session):
        r = test_session.patch(f"{API}/users/me/market", json={"market": "atlantis"}, timeout=30)
        assert r.status_code == 400, r.text

    def test_patch_market_clears_and_back_to_dubai(self, test_session):
        # restore to dubai to avoid polluting other tests
        r = test_session.patch(f"{API}/users/me/market", json={"market": "dubai"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("preferred_market") == "dubai"

    def test_patch_market_all_six_markets(self, test_session):
        for mk in ["dubai", "new_york", "london", "mumbai", "los_angeles", "dfw"]:
            r = test_session.patch(f"{API}/users/me/market", json={"market": mk}, timeout=30)
            assert r.status_code == 200, f"{mk}: {r.text}"
            assert r.json().get("preferred_market") == mk
        # restore
        test_session.patch(f"{API}/users/me/market", json={"market": "dubai"}, timeout=15)


# ─────────── SPONSOR GAME BUILDER ───────────
class TestSponsorBuilder:
    def test_builder_owner_ok(self, test_session, test_merchant_id):
        r = test_session.get(f"{API}/games/sponsor/{test_merchant_id}/builder", timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "business" in data
        assert "offers" in data
        assert "games" in data
        assert "defaults" in data
        assert data["business"].get("merchant_id") == test_merchant_id
        assert isinstance(data["offers"], list)
        assert isinstance(data["defaults"].get("segments"), list)

    def test_builder_non_owner_403(self, demo_session, test_merchant_id):
        r = demo_session.get(f"{API}/games/sponsor/{test_merchant_id}/builder", timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code} {r.text[:200]}"

    def test_create_points_only_wheel(self, test_session, test_merchant_id):
        payload = {
            "game_type": "wheel",
            "sponsor_name": "TEST_ Sponsor Wheel Iter176",
            "daily_spins": 3,
            "segments": [
                {"label": "50 pts", "kind": "points", "value": 50, "weight": 40, "color": "#a855f7"},
                {"label": "100 pts", "kind": "points", "value": 100, "weight": 30, "color": "#ec4899"},
                {"label": "Try again", "kind": "none", "value": 0, "weight": 30, "color": "#334155"},
            ],
            "active": True,
        }
        r = test_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/branded-games",
            json=payload, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        gid = data.get("game_id")
        assert gid and gid.startswith("wheel_spn_")
        pytest.new_wheel_game_id = gid

        # Playability: wheel/config
        r2 = test_session.get(f"{API}/games/wheel/config?game_id={gid}", timeout=30)
        assert r2.status_code == 200, r2.text
        cfg = r2.json()
        assert cfg.get("game_id") == gid
        assert cfg.get("sponsor_name") == payload["sponsor_name"]
        assert isinstance(cfg.get("segments"), list) and len(cfg["segments"]) == 3

        # Surfacing: wheel/list
        r3 = test_session.get(f"{API}/games/wheel/list", timeout=30)
        assert r3.status_code == 200
        ids = [g["game_id"] for g in r3.json().get("items", [])]
        assert gid in ids

    def test_weights_zero_rejected(self, test_session, test_merchant_id):
        payload = {
            "game_type": "wheel",
            "sponsor_name": "TEST_ Zero",
            "segments": [{"label": "x", "kind": "none", "value": 0, "weight": 0, "color": "#000"}],
        }
        r = test_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/branded-games",
            json=payload, timeout=30)
        assert r.status_code == 400
        assert "weights_zero" in r.text

    def test_no_segments_rejected(self, test_session, test_merchant_id):
        payload = {"game_type": "wheel", "sponsor_name": "TEST_ None", "segments": []}
        r = test_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/branded-games",
            json=payload, timeout=30)
        assert r.status_code == 400
        assert "no_segments" in r.text

    def test_bad_game_type_rejected(self, test_session, test_merchant_id):
        payload = {"game_type": "bingo", "sponsor_name": "TEST_ Bad",
                   "segments": [{"label": "x", "kind": "none", "weight": 1, "color": "#000"}]}
        r = test_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/branded-games",
            json=payload, timeout=30)
        assert r.status_code == 400
        assert "bad_game_type" in r.text

    def test_coupon_offer_ownership_validated(self, test_session, test_merchant_id):
        payload = {
            "game_type": "wheel",
            "sponsor_name": "TEST_ Coupon Bad Offer",
            "segments": [
                {"label": "Fake Coupon", "kind": "coupon", "weight": 5,
                 "color": "#ef4444", "coupon_offer_id": "ofr_does_not_exist_xxx"},
                {"label": "50 pts", "kind": "points", "value": 50, "weight": 50, "color": "#a855f7"},
            ],
        }
        r = test_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/branded-games",
            json=payload, timeout=30)
        assert r.status_code == 400
        assert "invalid_coupon_offer" in r.text

    def test_toggle_game_active(self, test_session, test_merchant_id):
        gid = getattr(pytest, "new_wheel_game_id", None)
        if not gid:
            pytest.skip("no game created")
        r = test_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/branded-games/{gid}/toggle",
            timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("active") is False  # was True → False

        # toggle back
        r2 = test_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/branded-games/{gid}/toggle",
            timeout=30)
        assert r2.status_code == 200
        assert r2.json().get("active") is True

    def test_toggle_non_owner_404(self, demo_session, test_merchant_id):
        gid = getattr(pytest, "new_wheel_game_id", None)
        if not gid:
            pytest.skip("no game created")
        r = demo_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/branded-games/{gid}/toggle",
            timeout=30)
        assert r.status_code == 403  # blocked at RBAC before ownership check

    def test_upsert_non_owner_403(self, demo_session, test_merchant_id):
        payload = {"game_type": "wheel", "sponsor_name": "TEST_ NonOwner",
                   "segments": [{"label": "x", "kind": "points", "value": 10, "weight": 1, "color": "#000"}]}
        r = demo_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/branded-games",
            json=payload, timeout=30)
        assert r.status_code == 403

    def test_upload_logo(self, test_session, test_merchant_id):
        # 1x1 PNG bytes
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c6300010000000500010d0a2db40000000049454e44ae426082"
        )
        files = {"file": ("logo.png", io.BytesIO(png), "image/png")}
        r = test_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/game-logo",
            files=files, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert data.get("logo_url", "").startswith("http")

    def test_upload_logo_bad_type_rejected(self, test_session, test_merchant_id):
        files = {"file": ("evil.exe", io.BytesIO(b"MZ"), "application/octet-stream")}
        r = test_session.post(
            f"{API}/games/sponsor/{test_merchant_id}/game-logo",
            files=files, timeout=30)
        assert r.status_code == 400
        assert "unsupported_type" in r.text


# ─────────── REGRESSION: legacy games endpoints still work ───────────
class TestRegression:
    def test_legacy_wheel_house_config(self, test_session):
        r = test_session.get(f"{API}/games/wheel/config", timeout=30)
        assert r.status_code == 200
        assert r.json().get("game_id") == "wheel_house"

    def test_legacy_wheel_list_has_house(self, test_session):
        r = test_session.get(f"{API}/games/wheel/list", timeout=30)
        assert r.status_code == 200
        ids = [g["game_id"] for g in r.json().get("items", [])]
        assert "wheel_house" in ids
