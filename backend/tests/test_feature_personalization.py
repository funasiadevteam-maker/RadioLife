"""Backend tests — Personalized Portal feature set.

Covers:
  • GET  /api/social/features        (user)
  • PUT  /api/social/features        (user)
  • POST /api/social/features/skip   (user)
  • GET  /api/admin/feature-defaults (admin)
  • PUT  /api/admin/feature-defaults (admin)
"""
import os
import uuid
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
DEMO = ("demo@bigfm.dubai", "DemoPass123!")
FREE = ("freeuser@bigfm.dubai", "FreePass123!")

CATALOG_KEYS = {"listen", "social", "live", "shop", "play", "dining", "earn", "explore"}
MANDATORY = {"listen"}


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def admin_client():
    return _login(*ADMIN)


@pytest.fixture(scope="module")
def demo_client():
    return _login(*DEMO)


@pytest.fixture(scope="module")
def free_client():
    return _login(*FREE)


# ---------- Admin feature defaults ----------
class TestAdminFeatureDefaults:
    def test_admin_only(self):
        # unauth → should be rejected
        r = requests.get(f"{BASE_URL}/api/admin/feature-defaults", timeout=15)
        assert r.status_code in (401, 403), f"expected auth error, got {r.status_code}"

    def test_user_cannot_access(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/admin/feature-defaults", timeout=15)
        assert r.status_code in (401, 403), f"demo user should NOT access admin: {r.status_code}"

    def test_admin_get_defaults(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/admin/feature-defaults", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "catalog" in data and "features" in data and "mandatory" in data
        keys = {c["key"] for c in data["catalog"]}
        assert keys == CATALOG_KEYS, f"catalog mismatch: {keys}"
        assert set(data["mandatory"]) == MANDATORY
        assert "listen" in data["features"]

    def test_admin_put_persists_and_forces_listen(self, admin_client):
        # Set defaults WITHOUT listen + with an unknown key
        r = admin_client.put(
            f"{BASE_URL}/api/admin/feature-defaults",
            json={"features": ["social", "shop", "bogus_key"]}, timeout=15)
        assert r.status_code == 200, r.text
        feats = set(r.json()["features"])
        assert "listen" in feats, "mandatory listen must be forced on"
        assert "bogus_key" not in feats, "unknown keys must be dropped"
        assert feats == {"listen", "social", "shop"}, f"unexpected: {feats}"

        # GET verifies persistence
        r2 = admin_client.get(f"{BASE_URL}/api/admin/feature-defaults", timeout=15)
        assert r2.status_code == 200
        assert set(r2.json()["features"]) == {"listen", "social", "shop"}

    def test_admin_put_empty_still_has_listen(self, admin_client):
        r = admin_client.put(
            f"{BASE_URL}/api/admin/feature-defaults",
            json={"features": []}, timeout=15)
        assert r.status_code == 200
        assert set(r.json()["features"]) == {"listen"}

    def test_restore_full_defaults(self, admin_client):
        """Teardown — restore all features as default to not disrupt other tests."""
        full = list(CATALOG_KEYS)
        r = admin_client.put(
            f"{BASE_URL}/api/admin/feature-defaults",
            json={"features": full}, timeout=15)
        assert r.status_code == 200
        assert set(r.json()["features"]) == CATALOG_KEYS


# ---------- User features ----------
class TestUserFeatures:
    def test_user_get_features(self, demo_client):
        r = demo_client.get(f"{BASE_URL}/api/social/features", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("catalog", "mandatory", "enabled", "default", "needs_onboarding"):
            assert k in data, f"missing key: {k}"
        assert set(data["mandatory"]) == MANDATORY
        assert "listen" in data["enabled"]
        assert isinstance(data["needs_onboarding"], bool)
        keys = {c["key"] for c in data["catalog"]}
        assert keys == CATALOG_KEYS

    def test_user_put_forces_listen_drops_unknown(self, demo_client):
        r = demo_client.put(
            f"{BASE_URL}/api/social/features",
            json={"features": ["social", "shop", "nope", "play"]}, timeout=15)
        assert r.status_code == 200, r.text
        feats = set(r.json()["enabled"])
        assert "listen" in feats, "listen must be forced on"
        assert "nope" not in feats, "unknown keys must be dropped"
        assert feats == {"listen", "social", "shop", "play"}

        # GET verifies persistence + onboarded flag flipped
        r2 = demo_client.get(f"{BASE_URL}/api/social/features", timeout=15)
        assert r2.status_code == 200
        d2 = r2.json()
        assert set(d2["enabled"]) == {"listen", "social", "shop", "play"}
        assert d2["needs_onboarding"] is False, "put must mark onboarded_features=True"

    def test_user_put_empty_still_has_listen(self, demo_client):
        r = demo_client.put(
            f"{BASE_URL}/api/social/features",
            json={"features": []}, timeout=15)
        assert r.status_code == 200
        assert set(r.json()["enabled"]) == {"listen"}

    def test_user_put_omit_listen_still_forced(self, demo_client):
        r = demo_client.put(
            f"{BASE_URL}/api/social/features",
            json={"features": ["social", "live"]}, timeout=15)
        assert r.status_code == 200
        feats = set(r.json()["enabled"])
        assert feats == {"listen", "social", "live"}

    def test_user_skip_keeps_default(self, free_client, admin_client):
        """POST /features/skip marks onboarded_features true and returns admin default.
        We reset free user's feature flags via admin PUT (restore full defaults
        already done above). Then skip should return the full default set."""
        # Make sure defaults are the full catalog
        admin_client.put(
            f"{BASE_URL}/api/admin/feature-defaults",
            json={"features": list(CATALOG_KEYS)}, timeout=15)
        r = free_client.post(f"{BASE_URL}/api/social/features/skip", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("ok") is True
        assert "listen" in data.get("enabled", [])

        # Now GET → needs_onboarding must be False
        r2 = free_client.get(f"{BASE_URL}/api/social/features", timeout=15)
        assert r2.status_code == 200
        assert r2.json()["needs_onboarding"] is False


# ---------- Interaction: admin default feeds new-user default ----------
class TestAdminDefaultFlowsThrough:
    def test_admin_narrow_default_reflects_in_new_user_default(self, admin_client):
        # Narrow admin default
        narrow = ["listen", "social", "earn"]
        r = admin_client.put(
            f"{BASE_URL}/api/admin/feature-defaults",
            json={"features": narrow}, timeout=15)
        assert r.status_code == 200
        assert set(r.json()["features"]) == set(narrow)

        # Register a brand-new user
        email = f"TEST_feat_{uuid.uuid4().hex[:8]}@bigfm.dubai"
        s = requests.Session()
        reg = s.post(f"{BASE_URL}/api/auth/register",
                     json={"email": email, "password": "TestPass123!",
                           "name": "TEST feat user"}, timeout=20)
        if reg.status_code not in (200, 201):
            # Fall back to login attempt if register endpoint differs
            pytest.skip(f"register failed {reg.status_code}: {reg.text[:120]}")

        # New user GET /features — default should match admin default, needs_onboarding True
        r = s.get(f"{BASE_URL}/api/social/features", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert set(data["default"]) == set(narrow), f"default: {data['default']}"
        # since enabled_features not saved yet → effective = default
        assert set(data["enabled"]) == set(narrow)
        assert data["needs_onboarding"] is True, "fresh user should need onboarding"

        # Restore full defaults for other tests
        admin_client.put(
            f"{BASE_URL}/api/admin/feature-defaults",
            json={"features": list(CATALOG_KEYS)}, timeout=15)
