"""Iteration 107 — Clip artwork + Tap-to-claim + Station art + Local Venues.

Covers acceptance criteria for the shell.py clip + venue endpoints,
imported_station_artwork.py owner/ensure endpoints, and live_radio.py
resolved art fields.
"""
import os
import re
import io
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASS = "DemoPass123!"

CODE_RE = re.compile(r"^RL-[A-F0-9]{6}$")


@pytest.fixture(scope="session")
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(email, password):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    if r.status_code != 200:
        pytest.skip(f"auth failed for {email}: {r.status_code} {r.text[:120]}")
    return s


@pytest.fixture(scope="session")
def admin_client():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="session")
def demo_client():
    return _login(DEMO_EMAIL, DEMO_PASS)


# ---------- Clip artwork + claim ----------

class TestClips:
    def test_clips_first_is_sponsored_with_image(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/shell/clips?limit=10")
        assert r.status_code == 200
        data = r.json()
        items = data["items"]
        assert len(items) >= 1
        first = items[0]
        assert first["sponsored"] is True
        assert first.get("campaign_id"), "sponsored clip must expose campaign_id"
        assert first.get("offer"), "must expose offer"
        assert first.get("sponsor"), "must expose sponsor"
        img = first.get("image") or ""
        assert img and img.startswith(("http://", "https://")), f"sponsored clip must have a real https image, got: {img!r}"

    def test_clips_claim_and_idempotency(self, demo_client, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/shell/clips?limit=5")
        campaign_id = r.json()["items"][0]["campaign_id"]

        r1 = demo_client.post(f"{BASE_URL}/api/shell/clips/claim", json={"campaign_id": campaign_id})
        assert r1.status_code == 200, r1.text
        d1 = r1.json()
        assert d1.get("ok") is True
        assert CODE_RE.match(d1.get("code", "")), f"bad code shape: {d1.get('code')!r}"

        r2 = demo_client.post(f"{BASE_URL}/api/shell/clips/claim", json={"campaign_id": campaign_id})
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2.get("ok") is True
        assert d2.get("already") is True
        assert d2.get("code") == d1.get("code"), "idempotent must return same code"

    def test_clips_claim_requires_auth(self, anon_client):
        r = anon_client.post(f"{BASE_URL}/api/shell/clips/claim", json={"campaign_id": "cmp_dr_mehta_appt"})
        assert r.status_code in (401, 403), f"expected auth error, got {r.status_code}"


# ---------- Live Radio stations art resolver ----------

VALID_ART_SOURCES = {"owner", "ai", "logo", "placeholder"}


class TestStationArt:
    def test_stations_list_all_have_art(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/live-radio/stations?limit=10")
        assert r.status_code == 200
        items = r.json().get("stations") or r.json().get("items") or []
        assert items, "no stations returned"
        for s in items:
            assert s.get("art"), f"missing art: {s.get('id')}"
            src = s.get("art_source")
            assert src in VALID_ART_SOURCES, f"bad art_source {src!r} on {s.get('id')}"
            assert "has_custom_art" in s, f"missing has_custom_art on {s.get('id')}"
            if src == "placeholder":
                assert "ui-avatars.com" in s["art"], f"placeholder must be ui-avatars: {s['art']}"

    def test_iran_international_ai_art(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/live-radio/stations/imp_c3357cf1510811eab8")
        assert r.status_code == 200, r.text
        s = r.json()
        assert s.get("art_source") == "ai", f"expected ai, got {s.get('art_source')}"
        assert "viewer_is_owner" in s
        # Anon user -> viewer_is_owner false
        assert s.get("viewer_is_owner") is False
        # has_custom_art is nested inside the station card
        card = s.get("station") or {}
        assert card.get("art_source") == "ai"
        assert card.get("has_custom_art") is True

    def test_iran_international_admin_owner_flag(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/live-radio/stations/imp_c3357cf1510811eab8")
        assert r.status_code == 200
        s = r.json()
        assert s.get("viewer_is_owner") is True, "admin should be viewer_is_owner=true"


# ---------- Imported station artwork ensure / flagship ----------

class TestArtworkEnsure:
    def test_ensure_flagship_art(self, anon_client):
        r = anon_client.post(f"{BASE_URL}/api/imported-stations/ensure-flagship-art")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert "queued" in d and isinstance(d["queued"], int)

    def test_ensure_specific_station_idempotent(self, anon_client):
        # Iran International already has AI art — should return already/complete.
        sid = "imp_c3357cf1510811eab8"
        r = anon_client.post(f"{BASE_URL}/api/imported-stations/{sid}/artwork/ensure")
        assert r.status_code == 200
        d = r.json()
        assert d.get("ok") is True
        assert d.get("status") in {"complete", "queued", "running", "pending", "idle"}


# ---------- Owner artwork auth ----------

class TestArtworkOwnerAuth:
    STATION = "imp_c3357cf1510811eab8"

    def test_generate_requires_owner_403_for_demo(self, demo_client):
        r = demo_client.post(f"{BASE_URL}/api/imported-stations/{self.STATION}/artwork/generate")
        assert r.status_code == 403, f"expected 403 for non-owner, got {r.status_code} {r.text[:120]}"

    def test_clear_requires_owner_403_for_demo(self, demo_client):
        r = demo_client.post(f"{BASE_URL}/api/imported-stations/{self.STATION}/artwork/clear")
        assert r.status_code == 403

    def test_upload_requires_owner_403_for_demo(self, demo_client):
        # multipart upload — non-owner should still 403 before file processing.
        c = requests.Session()
        c.cookies.update(demo_client.cookies)
        # drop json content-type for multipart
        files = {"file": ("x.png", io.BytesIO(b"fakepng"), "image/png")}
        r = c.post(f"{BASE_URL}/api/imported-stations/{self.STATION}/artwork/upload", files=files)
        assert r.status_code == 403

    def test_clear_allowed_for_admin_then_ensure_regen(self, admin_client, anon_client):
        # admin clear -> ensure to re-queue (proves admin bypass works & endpoint contract)
        r = admin_client.post(f"{BASE_URL}/api/imported-stations/{self.STATION}/artwork/clear")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("ok") is True
        assert d.get("cleared") is True

        # Re-ensure so we don't leave the station art-less for the UI phase
        r2 = anon_client.post(f"{BASE_URL}/api/imported-stations/{self.STATION}/artwork/ensure")
        assert r2.status_code == 200

    def test_generate_allowed_for_admin(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/imported-stations/{self.STATION}/artwork/generate")
        # 200 queued, or 429 rate_limited — both are "allowed" (not 403).
        assert r.status_code in (200, 429), f"admin should be allowed, got {r.status_code}: {r.text[:200]}"


# ---------- Local Venues (Dallas + Dubai regression) ----------

DALLAS_EXPECTED = {"Smoke & Oak BBQ", "Bishop Arts Coffee", "Lone Star Hair Lab",
                   "Pulse DFW Fitness", "Trinity Threads"}


class TestVenues:
    def test_dallas_market_venues(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/shell/venues", params={"market": "dfw", "city": "Dallas", "limit": 24})
        assert r.status_code == 200
        items = r.json()["items"]
        names = {v["name"] for v in items}
        missing = DALLAS_EXPECTED - names
        assert not missing, f"missing Dallas venues: {missing}. Got: {names}"
        # sponsored-first
        sponsored_flags = [v["sponsored"] for v in items]
        first_unsponsored = next((i for i, s in enumerate(sponsored_flags) if not s), len(sponsored_flags))
        # after first unsponsored, all must be unsponsored
        assert all(not s for s in sponsored_flags[first_unsponsored:]), \
            f"sponsored not first: {sponsored_flags}"

    def test_dubai_market_regression(self, anon_client):
        r = anon_client.get(f"{BASE_URL}/api/shell/venues", params={"market": "dubai", "limit": 24})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 5, f"expected ~8 Dubai venues, got {len(items)}"
        # Make sure none of the Dallas venues bled in
        names = {v["name"] for v in items}
        assert not (DALLAS_EXPECTED & names), f"Dallas venues leaked into Dubai: {DALLAS_EXPECTED & names}"
