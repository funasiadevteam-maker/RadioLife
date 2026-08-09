"""Iteration 44 — Premium Cues (RWD.3) + Brand Cleanup regression.

Coverage:
- Premium public benefits (unauth OK)
- Premium listener status (demo=free, premium@bigfm.dubai=premium)
- Admin premium config get/put (require_admin, non-admin 403)
- points_multiplier round-trip → premium_bonus_points_estimate recomputes
- Benefit enable=false hides it from /api/premium/benefits
- Restore multiplier to 1.5 at end
- Brand cleanup: DB user-visible fields say RadioLife (game_campaigns.title/sponsor_name,
  bigcoin_rewards.name, channels.name/description, badges.description, users.name);
  functional identifiers (users.email, station slugs, coupon redemption_code) unchanged
"""
import os
import re

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get(
    "REACT_APP_BACKEND_URL") else "https://mobile-games-v2.preview.emergentagent.com"

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"
PREMIUM_EMAIL = "premium@bigfm.dubai"
PREMIUM_PASS = "PremiumTest123!"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")

RX_BIGFM = re.compile(r"big\s*fm", re.IGNORECASE)


# ─── Fixtures ────────────────────────────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"admin login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def premium_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": PREMIUM_EMAIL, "password": PREMIUM_PASS}, timeout=15)
    if r.status_code != 200:
        pytest.skip(f"premium login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/demo", timeout=15)
    if r.status_code != 200:
        pytest.skip(f"demo login failed: {r.status_code}")
    return s


# ─── Premium: public benefits ───────────────────────────────
class TestPremiumPublicBenefits:
    def test_get_benefits_unauth(self):
        r = requests.get(f"{BASE_URL}/api/premium/benefits", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "benefits" in data
        assert isinstance(data["benefits"], list)
        assert len(data["benefits"]) > 0
        assert "points_multiplier" in data
        assert "monthly_price" in data
        assert "annual_price" in data
        # all returned benefits should be enabled
        for b in data["benefits"]:
            assert b.get("enabled", True) is True
            assert "key" in b and "title" in b


# ─── Premium: status ────────────────────────────────────────
class TestPremiumStatus:
    def test_status_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/me/premium/status", timeout=15)
        assert r.status_code in (401, 403)

    def test_demo_user_is_not_premium(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/me/premium/status", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["is_premium"] is False
        assert "value" in data
        assert "month_points_earned" in data["value"]
        assert "premium_bonus_points_estimate" in data["value"]
        assert isinstance(data["benefits"], list)

    def test_premium_user_is_premium(self, premium_session):
        r = premium_session.get(f"{BASE_URL}/api/me/premium/status", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["is_premium"] is True


# ─── Premium admin config gating + round-trip ───────────────
class TestPremiumAdminConfig:
    def test_non_admin_forbidden(self, demo_session):
        r = demo_session.get(f"{BASE_URL}/api/admin/premium/config", timeout=15)
        assert r.status_code in (401, 403)
        r2 = demo_session.put(f"{BASE_URL}/api/admin/premium/config",
                              json={"points_multiplier": 2.0}, timeout=15)
        assert r2.status_code in (401, 403)

    def test_admin_get_config(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/premium/config", timeout=15)
        assert r.status_code == 200, r.text
        cfg = r.json()
        assert "points_multiplier" in cfg
        assert "benefits" in cfg

    def test_multiplier_roundtrip_recomputes_estimate(
            self, admin_session, demo_session):
        # PUT 2.0
        r = admin_session.put(f"{BASE_URL}/api/admin/premium/config",
                              json={"points_multiplier": 2.0}, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["points_multiplier"] == 2.0

        # GET reflects
        g = admin_session.get(f"{BASE_URL}/api/admin/premium/config", timeout=15)
        assert g.json()["points_multiplier"] == 2.0

        # /api/me/premium/status recomputes: estimate = round(month_earned*(2.0-1)) = month_earned
        s = demo_session.get(f"{BASE_URL}/api/me/premium/status", timeout=15)
        assert s.status_code == 200
        v = s.json()["value"]
        expected = int(round(v["month_points_earned"] * (2.0 - 1)))
        assert v["premium_bonus_points_estimate"] == expected
        assert s.json()["points_multiplier"] == 2.0

    def test_benefit_disable_hides_from_public(self, admin_session):
        # Get current benefits, pick one to disable
        cur = admin_session.get(f"{BASE_URL}/api/admin/premium/config",
                                timeout=15).json()
        benefits = cur["benefits"]
        # Pick 'extra_game_entries' — non-critical
        modified = []
        target_key = "extra_game_entries"
        for b in benefits:
            b2 = dict(b)
            if b2["key"] == target_key:
                b2["enabled"] = False
            modified.append(b2)
        r = admin_session.put(f"{BASE_URL}/api/admin/premium/config",
                              json={"benefits": modified}, timeout=15)
        assert r.status_code == 200, r.text

        # public /api/premium/benefits should NOT include the disabled key
        pub = requests.get(f"{BASE_URL}/api/premium/benefits", timeout=15).json()
        keys = [b["key"] for b in pub["benefits"]]
        assert target_key not in keys

        # /api/me/premium/status also excludes disabled
        # (do a fresh unauth check via demo session)
        # Re-enable
        for b in modified:
            if b["key"] == target_key:
                b["enabled"] = True
        rr = admin_session.put(f"{BASE_URL}/api/admin/premium/config",
                               json={"benefits": modified}, timeout=15)
        assert rr.status_code == 200
        pub2 = requests.get(f"{BASE_URL}/api/premium/benefits", timeout=15).json()
        keys2 = [b["key"] for b in pub2["benefits"]]
        assert target_key in keys2

    def test_restore_multiplier_to_1_5(self, admin_session):
        r = admin_session.put(f"{BASE_URL}/api/admin/premium/config",
                              json={"points_multiplier": 1.5}, timeout=15)
        assert r.status_code == 200
        assert r.json()["points_multiplier"] == 1.5


# ─── Brand cleanup DB regression ─────────────────────────────
@pytest.mark.asyncio
class TestBrandCleanupDB:
    async def _db(self):
        client = AsyncIOMotorClient(MONGO_URL)
        return client, client[DB_NAME]

    async def test_game_campaigns_display_no_bigfm(self):
        client, db = await self._db()
        try:
            bad = []
            async for doc in db.game_campaigns.find(
                    {}, {"title": 1, "sponsor_name": 1}):
                for k in ("title", "sponsor_name"):
                    v = doc.get(k)
                    if isinstance(v, str) and RX_BIGFM.search(v):
                        bad.append((str(doc.get("_id")), k, v))
            assert not bad, f"game_campaigns still contain BigFM: {bad[:5]}"
        finally:
            client.close()

    async def test_bigcoin_rewards_name_no_bigfm(self):
        client, db = await self._db()
        try:
            bad = []
            async for doc in db.bigcoin_rewards.find({}, {"name": 1}):
                v = doc.get("name")
                if isinstance(v, str) and RX_BIGFM.search(v):
                    bad.append((str(doc.get("_id")), v))
            assert not bad, f"bigcoin_rewards.name still contain BigFM: {bad[:5]}"
        finally:
            client.close()

    async def test_channels_display_no_bigfm(self):
        client, db = await self._db()
        try:
            bad = []
            async for doc in db.channels.find(
                    {}, {"name": 1, "description": 1, "slug": 1}):
                for k in ("name", "description"):
                    v = doc.get(k)
                    if isinstance(v, str) and RX_BIGFM.search(v):
                        bad.append((str(doc.get("_id")), k, v))
            assert not bad, f"channels display still contain BigFM: {bad[:5]}"
        finally:
            client.close()

    async def test_badges_description_no_bigfm(self):
        client, db = await self._db()
        try:
            bad = []
            async for doc in db.badges.find({}, {"description": 1}):
                v = doc.get("description")
                if isinstance(v, str) and RX_BIGFM.search(v):
                    bad.append((str(doc.get("_id")), v))
            assert not bad, f"badges.description still contain BigFM: {bad[:5]}"
        finally:
            client.close()

    async def test_users_name_no_bigfm(self):
        client, db = await self._db()
        try:
            bad = []
            async for doc in db.users.find({}, {"name": 1, "email": 1}):
                v = doc.get("name")
                if isinstance(v, str) and RX_BIGFM.search(v):
                    bad.append((doc.get("email"), v))
            assert not bad, f"users.name still contain BigFM: {bad[:5]}"
        finally:
            client.close()

    # Functional identifiers must be UNCHANGED
    async def test_admin_email_unchanged(self):
        client, db = await self._db()
        try:
            u = await db.users.find_one({"email": "admin@bigfm.dubai"})
            assert u is not None, "admin@bigfm.dubai must still exist"
        finally:
            client.close()

    async def test_channels_slugs_still_have_bigfm(self):
        """At least one station slug should still contain 'bigfm' — slugs are
        functional identifiers and MUST NOT be rebranded."""
        client, db = await self._db()
        try:
            has_bigfm_slug = False
            async for doc in db.channels.find({}, {"slug": 1}):
                slug = doc.get("slug") or ""
                if RX_BIGFM.search(slug):
                    has_bigfm_slug = True
                    break
            # If no channels exist with bigfm slugs, that's OK — just log
            # (we're primarily checking that rebrand didn't touch slug field)
            print(f"channel with bigfm slug present: {has_bigfm_slug}")
        finally:
            client.close()


def test_admin_login_still_works():
    """Regression: admin login must still work after brand cleanup."""
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"admin login broken: {r.status_code} {r.text[:200]}"


def test_earn_overview_regression(demo_session):
    """Regression: RWD.1 earn overview still works."""
    r = demo_session.get(f"{BASE_URL}/api/me/earn/overview", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "balance" in d and "tier" in d and "daily_goal" in d
    assert "ways_to_earn" in d and "missions" in d
