"""Iter 135 — Reroll Memory (last_pref) + Almost-Gone flags (backend surface).

Verifies:
  1) POST /api/dining-club/selection/start persists dining_prefs; GET /api/dining-club
     returns last_pref.
  2) test@bigfm.dubai has last_pref = {NON_VEG, DINNER} pre-seeded.
  3) demo@bigfm.dubai (via /api/auth/demo) has last_pref = {VEG, LUNCH} pre-seeded.
  4) GET /api/store/adv_fpk exposes the 3-state remaining today used by the UI
     Almost-Gone flag: scratch=~12 (low), spin=sold out, quiz=360 (normal).
"""
import os
import re

import pytest
import requests

def _read_env(path: str, key: str) -> str:
    with open(path) as f:
        for line in f:
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{key} not in {path}")

BASE_URL = _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL").rstrip("/")


def _cookie_login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text}"
    return s


def _demo_bearer() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/demo", json={})
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    tok = r.json().get("session_token") or r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in demo response: {r.text}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ── Reroll Memory ──────────────────────────────────────────────────────
class TestRerollMemory:
    def test_web_test_user_last_pref_non_veg_dinner(self):
        s = _cookie_login("test@bigfm.dubai", "TestUser123!")
        r = s.get(f"{BASE_URL}/api/dining-club")
        assert r.status_code == 200, r.text
        body = r.json()
        assert "last_pref" in body, f"missing last_pref: {body.keys()}"
        lp = body["last_pref"]
        assert lp is not None, "expected pre-seeded last_pref for test@"
        assert lp.get("veg_preference") == "NON_VEG", lp
        assert lp.get("meal_period") == "DINNER", lp

    def test_mobile_demo_user_last_pref_veg_lunch(self):
        s = _demo_bearer()
        r = s.get(f"{BASE_URL}/api/dining-club")
        assert r.status_code == 200, r.text
        lp = r.json().get("last_pref")
        assert lp is not None, "expected pre-seeded last_pref for demo@"
        assert lp.get("veg_preference") == "VEG", lp
        assert lp.get("meal_period") == "LUNCH", lp

    def test_start_persists_last_pref(self):
        """Change the pick and confirm GET reflects it — then restore."""
        s = _cookie_login("test@bigfm.dubai", "TestUser123!")
        r0 = s.get(f"{BASE_URL}/api/dining-club").json()
        orig = r0.get("last_pref") or {"veg_preference": "NON_VEG", "meal_period": "DINNER"}

        # Flip to VEG/LUNCH; ignore no_available_credits — the pref still upserts BEFORE
        # start_session runs (see routes/dining_club.py:selection_start).
        s.post(f"{BASE_URL}/api/dining-club/selection/start",
               json={"veg_preference": "VEG", "meal_period": "LUNCH"})
        lp = s.get(f"{BASE_URL}/api/dining-club").json().get("last_pref") or {}
        # NOTE: pref write is BEFORE the credit check; must persist regardless of outcome.
        assert lp.get("veg_preference") == "VEG", lp
        assert lp.get("meal_period") == "LUNCH", lp

        # Restore original so subsequent tests / UI runs see NON_VEG/DINNER for test@.
        s.post(f"{BASE_URL}/api/dining-club/selection/start",
               json={"veg_preference": orig["veg_preference"],
                     "meal_period": orig["meal_period"]})
        lp2 = s.get(f"{BASE_URL}/api/dining-club").json().get("last_pref") or {}
        assert lp2.get("veg_preference") == orig["veg_preference"]
        assert lp2.get("meal_period") == orig["meal_period"]


# ── Almost-Gone Warning (storefront) ───────────────────────────────────
class TestAlmostGoneStore:
    @pytest.fixture(scope="class")
    def store(self):
        r = requests.get(f"{BASE_URL}/api/store/adv_fpk")
        assert r.status_code == 200, r.text
        return r.json()

    def _game(self, store, cid):
        for g in store.get("games", []):
            if g["campaign_id"] == cid:
                return g
        pytest.fail(f"campaign {cid} missing from /api/store/adv_fpk")

    def test_scratch_is_low(self, store):
        g = self._game(store, "cmp_fpk_scratch")
        rem = g.get("remaining_today")
        cap = g.get("total_cap_today") or 0
        thr = max(10, -(-int(cap * 0.15))) if cap else 20  # ceil
        assert rem is not None and rem > 0, g
        assert rem <= thr, f"scratch remaining {rem} not <= low threshold {thr} (cap={cap})"
        # ~12 per seed doc; allow a small drift if a coupon was consumed
        assert rem <= 20, f"expected ~12 scratch coupons, got {rem}"

    def test_spin_is_sold_out(self, store):
        g = self._game(store, "cmp_fpk_spin")
        assert g.get("remaining_today") == 0, g

    def test_quiz_is_normal(self, store):
        g = self._game(store, "cmp_fpk_quiz")
        rem = g.get("remaining_today")
        cap = g.get("total_cap_today") or 0
        thr = max(10, -(-int(cap * 0.15))) if cap else 20
        assert rem is not None and rem > thr, f"quiz remaining {rem} should exceed low thr {thr}"
