"""iter142 — Backend tests for PUBLIC V2 landing + Rail Analytics + Admin Approve Ads + Genre-personalized hero."""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
PREMIUM = ("premium@bigfm.dubai", "PremiumTest123!")
ADVERTISER = ("test@bigfm.dubai", "TestUser123!")


def _login(email: str, pw: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


# ─── (A) PUBLIC/anonymous landing endpoints ──────────────────────────
class TestPublicLanding:
    def test_stations_public_no_auth(self):
        r = requests.get(f"{BASE_URL}/api/live-radio/stations", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        assert len(data["items"]) >= 1

    def test_shell_home_anonymous_no_crash(self):
        r = requests.get(f"{BASE_URL}/api/shell/home", timeout=15)
        # anonymous shell/home should not 500 (may or may not require auth)
        assert r.status_code < 500


# ─── (B) Rail Analytics (advertiser) ─────────────────────────────────
class TestRailAnalytics:
    @pytest.fixture(scope="class")
    def adv_session(self):
        return _login(*ADVERTISER)

    def test_advertiser_rail_analytics_shape(self, adv_session):
        r = adv_session.get(f"{BASE_URL}/api/ads/advertiser/rail-analytics", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(["cpm", "campaigns", "slots", "totals"]).issubset(data.keys())
        assert data["cpm"] == 8.0
        # 3 slots: right_rail_mpu_1/2/3
        slot_keys = [s["slot_key"] for s in data["slots"]]
        assert slot_keys == ["right_rail_mpu_1", "right_rail_mpu_2", "right_rail_mpu_3"]
        for s in data["slots"]:
            for k in ["impressions", "clicks", "ctr", "spend"]:
                assert k in s
        for k in ["impressions", "clicks", "ctr", "spend"]:
            assert k in data["totals"]


# ─── (C) Admin approve/reject rail-ads ───────────────────────────────
class TestAdminApprove:
    @pytest.fixture(scope="class")
    def admin_session(self):
        return _login(*ADMIN)

    @pytest.fixture(scope="class")
    def adv_session(self):
        return _login(*ADVERTISER)

    def _create_and_checkout(self, adv):
        payload = {
            "slot_keys": ["right_rail_mpu_1"],
            "creative_image_url": "https://images.unsplash.com/photo-1540039155733-5bb30b53aa14?w=300",
            "click_url": f"https://example.com/test-{uuid.uuid4().hex[:6]}",
            "total_budget": 50.0,
            "daily_budget": 0.0,
            "start_date": "2026-09-15T00:00:00Z",
            "end_date": "2026-12-31T23:59:59Z",
        }
        r = adv.post(f"{BASE_URL}/api/ads/advertiser/banner-campaigns", json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        cid = r.json().get("campaign_id") or r.json().get("id") or r.json().get("_id")
        assert cid, r.text
        r2 = adv.post(f"{BASE_URL}/api/ads/advertiser/banner-campaigns/{cid}/checkout", json={}, timeout=15)
        assert r2.status_code == 200, r2.text
        return cid

    def test_admin_list_pending(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/ads/admin/banner-campaigns?status=pending", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and "count" in d

    def test_admin_approve_flow(self, admin_session, adv_session):
        cid = self._create_and_checkout(adv_session)
        # confirm it shows up in pending
        r = admin_session.get(f"{BASE_URL}/api/ads/admin/banner-campaigns?status=pending", timeout=15)
        assert r.status_code == 200
        ids = [it.get("campaign_id") for it in r.json()["items"]]
        assert cid in ids, f"created campaign {cid} not in pending list"

        # approve
        r2 = admin_session.post(f"{BASE_URL}/api/ads/admin/banner-campaigns/{cid}/approve", timeout=15)
        assert r2.status_code == 200, r2.text
        assert r2.json().get("new_status") == "active"

        # no longer pending
        r3 = admin_session.get(f"{BASE_URL}/api/ads/admin/banner-campaigns?status=pending", timeout=15)
        ids3 = [it.get("campaign_id") for it in r3.json()["items"]]
        assert cid not in ids3

        # visible in active
        r4 = admin_session.get(f"{BASE_URL}/api/ads/admin/banner-campaigns?status=active", timeout=15)
        ids4 = [it.get("campaign_id") for it in r4.json()["items"]]
        assert cid in ids4

    def test_admin_reject_flow(self, admin_session, adv_session):
        cid = self._create_and_checkout(adv_session)
        r = admin_session.post(f"{BASE_URL}/api/ads/admin/banner-campaigns/{cid}/reject",
                               json={"reason": "test reject"}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json().get("new_status") == "rejected"

    def test_non_admin_forbidden(self, adv_session):
        r = adv_session.get(f"{BASE_URL}/api/ads/admin/banner-campaigns?status=pending", timeout=15)
        assert r.status_code == 403


# ─── (D) Genre-personalized hero (preference_vector.genres) ──────────
class TestGenreHero:
    def test_admin_top_genre_from_genres(self):
        s = _login(*ADMIN)
        r = s.get(f"{BASE_URL}/api/shell/home", timeout=15)
        assert r.status_code == 200
        d = r.json()
        # admin seeded with preference_vector.genres=[bollywood,...]
        assert d.get("top_genre") == "Bollywood", f"got {d.get('top_genre')}"

    def test_premium_top_genre_from_favorite_genres_fallback(self):
        s = _login(*PREMIUM)
        r = s.get(f"{BASE_URL}/api/shell/home", timeout=15)
        assert r.status_code == 200
        d = r.json()
        # premium seeded with favorite_genres=[Bollywood,Dance] per review spec
        assert d.get("top_genre") in ("Bollywood", "Dance"), f"got {d.get('top_genre')}"
        assert d.get("is_premium") is True

    def test_anonymous_top_genre_no_crash(self):
        r = requests.get(f"{BASE_URL}/api/shell/home", timeout=15)
        # must not 500 with null user
        assert r.status_code < 500
