# iter140 — New Look V2 lock + right-rail buyable ads + theme prefs (web)
# Tests:
#  1) 3 new banner slots (right_rail_mpu_1/2/3) return house 300x250 for non-premium
#  2) Same slots return source=none for premium (ad-free)
#  3) shell prefs theme persists (PUT then GET)
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
PREMIUM = ("premium@bigfm.dubai", "PremiumTest123!")
TEST = ("test@bigfm.dubai", "TestUser123!")
FREE = ("freeuser@bigfm.dubai", "FreePass123!")


def _login(email, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text[:200]}"
    return s


# --- Banner decisions ---
class TestBannerDecisionsV2:
    @pytest.mark.parametrize("slot", ["right_rail_mpu_1", "right_rail_mpu_2", "right_rail_mpu_3"])
    def test_house_for_non_premium(self, slot):
        s = _login(*FREE)
        r = s.get(f"{BASE_URL}/api/ads/banner/decision", params={"slot_key": slot, "page_route": "/home"}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        assert j.get("source") == "house", f"expected house, got {j}"
        assert j.get("size") == "300x250", f"expected 300x250, got {j.get('size')}"

    @pytest.mark.parametrize("slot", ["right_rail_mpu_1", "right_rail_mpu_2", "right_rail_mpu_3"])
    def test_none_for_premium(self, slot):
        s = _login(*PREMIUM)
        r = s.get(f"{BASE_URL}/api/ads/banner/decision", params={"slot_key": slot, "page_route": "/home"}, timeout=15)
        assert r.status_code == 200, r.text[:200]
        j = r.json()
        assert j.get("source") == "none", f"expected none for premium, got {j}"
        # reason should be premium
        reason = (j.get("reason") or "").lower()
        assert "premium" in reason or reason == "premium", f"expected premium reason, got {reason}"


# --- Shell theme prefs ---
class TestShellPrefsTheme:
    def test_theme_persists(self):
        s = _login(*TEST)
        # set to light
        r = s.put(f"{BASE_URL}/api/shell/prefs", json={"theme": "light"}, timeout=15)
        assert r.status_code in (200, 204), r.text[:200]
        r = s.get(f"{BASE_URL}/api/shell/prefs", timeout=15)
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("theme") == "light", r.json()
        # flip back to dark
        r = s.put(f"{BASE_URL}/api/shell/prefs", json={"theme": "dark"}, timeout=15)
        assert r.status_code in (200, 204)
        r = s.get(f"{BASE_URL}/api/shell/prefs", timeout=15)
        assert r.json().get("theme") == "dark"


# --- Admin role for switcher ---
class TestAdminRole:
    def test_admin_me_role(self):
        s = _login(*ADMIN)
        r = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json().get("role") == "admin", r.json()

    def test_premium_me_role(self):
        s = _login(*PREMIUM)
        r = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        assert r.json().get("role") != "admin", r.json()
