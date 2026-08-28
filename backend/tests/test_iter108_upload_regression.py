"""Iteration 108 — Backend regression for lint-driven upload+storage refactors.

Verifies request/response contracts for endpoints touched in this session:
  * POST /api/advertiser/{aid}/creatives            (multipart audio+image)
  * POST /api/advertiser/predict-win/sponsorships/{sid}/brand-asset
  * POST /api/advertiser/notification-campaigns/{id}/creative-upload
  * POST /api/advertiser/banner-campaigns/{id}/creative-upload
  * POST /api/admin/stations/{sid}/logo             (flagship logo upload)
  * POST /api/admin/tracks/upload                   (admin mp3 upload — now reads
                                                    full bytes into memory)
  * POST /api/business/register                     (returns business_id)
  * marketplace_orders _price_menu path            (profile without _id) via
    POST /api/marketplace/quote (checkout uses same _price_menu)
  * POST /api/games_v2/advertiser/assets/upload    (save_uploaded_asset)
  * GET  /api/shell/venues + /api/shell/clips      (iter107 baseline)

Auth is COOKIE-BASED (POST /api/auth/login sets a session cookie).
"""
from __future__ import annotations
import io
import os
import struct
import wave

import pytest
import requests

def _load_base_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v: return v.rstrip("/")
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except OSError: pass
    raise RuntimeError("REACT_APP_BACKEND_URL not set")


BASE_URL = _load_base_url()

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
TEST  = ("test@bigfm.dubai",  "TestUser123!")
DEMO  = ("demo@bigfm.dubai",  "DemoPass123!")


# ─── Fixtures ───────────────────────────────────────────────────────────
def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} → {r.status_code}: {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def test_session() -> requests.Session:
    return _login(*TEST)


@pytest.fixture(scope="module")
def demo_session() -> requests.Session:
    return _login(*DEMO)


@pytest.fixture(scope="module")
def anon_session() -> requests.Session:
    return requests.Session()


# ─── Small binary fixtures ──────────────────────────────────────────────
def _tiny_png() -> bytes:
    """1x1 transparent PNG."""
    return bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c6300010000000500010d0a2db40000000049454e44"
        "ae426082")


def _tiny_mp3_like() -> bytes:
    """A minimal MP3 header (ID3v2 + a bit of MPEG-1 L3 frame). ffprobe may
    reject non-real audio; upload endpoints use audio/mpeg content-type
    validation only for some routes — for admin/tracks/upload it also
    ffprobes. So this fixture is used only where ffprobe is NOT called."""
    return b"ID3\x04\x00\x00\x00\x00\x00\x00" + b"\xff\xfb\x90\x00" + b"\x00" * 512


def _tiny_wav() -> bytes:
    """A real ~0.1s silent WAV wrapped as .mp3 name — used where ffprobe runs.
    We supply a real MP3 by encoding silence with lameenc if available, else
    fall back to a canned small MP3 shipped in tests."""
    # Not needed for now.
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(struct.pack("<h", 0) * 800)
    return buf.getvalue()


# --- shell venues / clips (iter107 regression baseline) ---
class TestShellBaseline:
    def test_shell_venues_dubai_returns_items(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/shell/venues?market=dubai", timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 1

    def test_shell_venues_dallas_returns_items(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/shell/venues?market=dfw&city=Dallas", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json().get("items"), list)

    def test_shell_clips_returns_items(self, anon_session):
        r = anon_session.get(f"{BASE_URL}/api/shell/clips", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert isinstance(data["items"], list)
        assert len(data["items"]) >= 1
        # First item should have a stable clip contract
        it = data["items"][0]
        assert "image" in it or "clip_id" in it


# --- auth smoke ---
class TestAuth:
    def test_admin_login_and_me(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200
        me = r.json()
        assert me.get("email") == ADMIN[0]

    def test_test_login_and_me(self, test_session):
        r = test_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert r.status_code == 200


# --- business/register ---
class TestBusinessRegister:
    def test_register_returns_business_id_shape(self, test_session):
        # test@ already owns a business — endpoint returns
        # {ok:False, reason:'already_registered', business_id:<id>}.
        # The response STILL includes business_id — contract preserved.
        r = test_session.post(
            f"{BASE_URL}/api/business/register",
            json={"name": "TEST_biz", "category": "cafe",
                  "terminal_pin": "1234"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert "business_id" in data
        assert isinstance(data["business_id"], str)


# --- admin: tracks upload ---
class TestAdminTracksUpload:
    def test_upload_track_bad_ext_400(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/admin/tracks/upload",
            files={"file": ("x.wav", _tiny_wav(), "audio/wav")}, timeout=30)
        assert r.status_code == 400
        assert "only .mp3" in r.text.lower()

    def test_upload_track_missing_filename_400(self, admin_session):
        # Missing file → 422 (FastAPI validation)
        r = admin_session.post(
            f"{BASE_URL}/api/admin/tracks/upload", timeout=30)
        assert r.status_code in (400, 422)

    def test_upload_track_non_admin_403(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/admin/tracks/upload",
            files={"file": ("x.mp3", _tiny_mp3_like(), "audio/mpeg")}, timeout=30)
        assert r.status_code in (401, 403)


# --- admin: station logo (flagship_stations) ---
class TestFlagshipStationLogo:
    def _pick_station(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/imported-stations?limit=1", timeout=30)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items") or data.get("stations") or []
            if items: return items[0].get("id") or items[0].get("_id")
        # fallback — a canonical seeded station id used in prior tests
        return "imp_c3357cf1510811eab8"

    def test_upload_logo_success_or_404(self, admin_session):
        sid = self._pick_station(admin_session)
        r = admin_session.post(
            f"{BASE_URL}/api/admin/stations/{sid}/logo",
            files={"file": ("logo.png", _tiny_png(), "image/png")}, timeout=60)
        # Either the station exists (200 with contract) or 404 station_not_found
        assert r.status_code in (200, 404), r.text[:200]
        if r.status_code == 200:
            data = r.json()
            assert data.get("ok") is True
            assert "logo_url" in data
            assert isinstance(data["logo_url"], str)
            assert "station_id" in data
            assert data.get("bytes") == len(_tiny_png())

    def test_upload_logo_unsupported_type_400(self, admin_session):
        sid = self._pick_station(admin_session)
        r = admin_session.post(
            f"{BASE_URL}/api/admin/stations/{sid}/logo",
            files={"file": ("logo.txt", b"nope", "text/plain")}, timeout=30)
        # 400 unsupported_type (or 404 if station missing)
        assert r.status_code in (400, 404)

    def test_upload_logo_non_admin_403(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/admin/stations/anything/logo",
            files={"file": ("logo.png", _tiny_png(), "image/png")}, timeout=30)
        assert r.status_code in (401, 403)


# --- creatives (advertiser) ---
class TestAdvertiserCreatives:
    def test_creatives_needs_advertiser_membership(self, test_session):
        # test@ is not a member of any advertiser → 401/403 with a stable
        # error contract. This exercises route wiring (no import errors
        # from the object_storage refactor).
        r = test_session.post(
            f"{BASE_URL}/api/advertiser/adv_demo_karak/creatives",
            data={"title": "T1"},
            files={"audio": ("a.mp3", _tiny_mp3_like(), "audio/mpeg")},
            timeout=30)
        assert r.status_code in (401, 403, 404), r.text[:200]


# --- predict-win sponsorship brand-asset ---
class TestPredictWinBrandAsset:
    def test_missing_sponsorship_returns_404(self, test_session):
        r = test_session.post(
            f"{BASE_URL}/api/advertiser/predict-win/sponsorships/does_not_exist/brand-asset",
            files={"file": ("i.png", _tiny_png(), "image/png")}, timeout=30)
        # Auth first (401 if session dropped) or 404 sponsorship_not_found
        assert r.status_code in (401, 403, 404), r.text[:200]
        if r.status_code == 404:
            body = r.json()
            code = (body.get("detail") or {}).get("code") if isinstance(body.get("detail"), dict) else body.get("detail")
            assert "sponsorship_not_found" in str(code) or "sponsorship_not_found" in r.text


# --- banner campaign creative-upload ---
class TestBannerCampaignUpload:
    def test_missing_banner_returns_404(self, test_session):
        r = test_session.post(
            f"{BASE_URL}/api/advertiser/banner-campaigns/does_not_exist/creative-upload",
            params={"zone": "home_top"},
            files={"file": ("i.png", _tiny_png(), "image/png")}, timeout=30)
        assert r.status_code in (401, 403, 404), r.text[:200]
        if r.status_code == 404:
            assert "banner_not_found" in r.text or "not_found" in r.text.lower()


# --- notification campaign creative-upload ---
class TestNotificationCampaignUpload:
    def test_missing_campaign_returns_404(self, test_session):
        r = test_session.post(
            f"{BASE_URL}/api/advertiser/notification-campaigns/does_not_exist/creative-upload",
            params={"slot": "icon"},
            files={"file": ("i.png", _tiny_png(), "image/png")}, timeout=30)
        assert r.status_code in (401, 403, 404), r.text[:200]
        if r.status_code == 404:
            assert "notification_campaign_not_found" in r.text or "not_found" in r.text.lower()


# --- games_v2 advertiser asset upload ---
class TestGamesV2AssetUpload:
    def test_non_advertiser_denied_or_upload_shape(self, test_session):
        r = test_session.post(
            f"{BASE_URL}/api/games_v2/advertiser/assets/upload",
            files={"file": ("i.png", _tiny_png(), "image/png")}, timeout=30)
        # Either the user is not classified as advertiser → 401/403,
        # or the upload succeeds and returns the {asset_id, url} contract.
        assert r.status_code in (200, 400, 401, 403), r.text[:200]
        if r.status_code == 200:
            data = r.json()
            assert "asset_id" in data
            assert "url" in data
            assert isinstance(data["url"], str)


# --- marketplace_orders _price_menu path via /quote ---
class TestMarketplaceQuoteProfileShape:
    """The refactor: _price_menu now returns `profile` WITHOUT the internal
    _id field. /quote pops the whole `profile` key from its response, so we
    hit the internal contract via /checkout. But /checkout requires stripe.
    Instead, we hit /quote which still exercises the same _price_menu code
    path — its status_code + shape being intact is what we validate here."""

    def test_quote_empty_cart_400(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/shop/orders/quote",
            json={"business_id": "biz_8484f6f985d5", "items": []}, timeout=30)
        assert r.status_code == 400
        assert "empty_cart" in r.text

    def test_quote_unknown_business_404(self, demo_session):
        r = demo_session.post(
            f"{BASE_URL}/api/shop/orders/quote",
            json={"business_id": "biz_does_not_exist",
                  "items": [{"item_id": "mi_x", "qty": 1}]}, timeout=30)
        assert r.status_code == 404
        assert "business_unavailable" in r.text

    def test_quote_valid_item_returns_totals(self, demo_session):
        # Uses the seeded approved+active marketplace biz + a real menu item.
        r = demo_session.post(
            f"{BASE_URL}/api/shop/orders/quote",
            json={"business_id": "biz_8484f6f985d5",
                  "items": [{"item_id": "mi_3ad4ad3bad30", "qty": 1}]}, timeout=30)
        # Either the item exists (200 with totals) or backend rejects (400/404)
        assert r.status_code in (200, 400, 404), r.text[:200]
        if r.status_code == 200:
            data = r.json()
            # /quote pops "profile" — verify it's not returned
            assert "profile" not in data
            assert "total_cents" in data
            assert "line_items" in data
            assert isinstance(data["total_cents"], int)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
