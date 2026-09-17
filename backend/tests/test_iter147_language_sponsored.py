"""Iter147 — RadioLife language chips + admin restore + sponsored slot.

Backend regression for the 3 backend-facing features:
1. GET /api/radio/browse `lang_group` filter (english/hindi/indian/news)
2. Admin hidden-summary / hidden-stations / restore (SAFE NO-OP only) +
   reversible single-station set-active toggle.
3. GET /api/promoted/stations?limit=1 (auto-seed) + impression + click.
"""
from __future__ import annotations

import os
import pytest
import requests
from dotenv import load_dotenv

load_dotenv("/app/frontend/.env")
BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASS = "AdminPass123!"


@pytest.fixture(scope="module")
def anon():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:200]}"
    # Cookie-based auth; requests.Session captures session_token automatically
    return s


# ────────────── 1) Language chip filter on /api/radio/browse ──────────────
class TestBrowseLangGroup:
    def _browse(self, anon, **params):
        r = anon.get(f"{BASE_URL}/api/radio/browse", params=params, timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        return r.json()

    def test_baseline_imported_no_filter(self, anon):
        data = self._browse(anon, source="imported", limit=1)
        assert "total" in data and isinstance(data["total"], int)
        # baseline total captured for delta comparisons below
        self.baseline_imported_total = data["total"]
        assert data["total"] > 0, "imported directory should not be empty"

    @pytest.mark.parametrize("group", ["english", "hindi", "indian", "news"])
    def test_lang_group_imported_filters(self, anon, group):
        data = self._browse(anon, source="imported", lang_group=group, limit=1)
        # filter should return >0 stations (backend already verified counts)
        assert data["total"] > 0, f"{group} filter returned 0"
        # and should be strictly smaller than the baseline all-imported total
        base = self._browse(anon, source="imported", limit=1)["total"]
        assert data["total"] < base, (
            f"{group} filter total={data['total']} not less than baseline={base}"
        )

    def test_lang_group_all_source(self, anon):
        # `source=all` — Hindi should still filter and change total
        base = self._browse(anon, source="all", limit=1)["total"]
        hindi = self._browse(anon, source="all", lang_group="hindi", limit=1)["total"]
        assert hindi > 0
        assert hindi < base

    def test_lang_group_all_value_is_noop(self, anon):
        # `lang_group=all` should behave like no filter
        base = self._browse(anon, source="imported", limit=1)["total"]
        alld = self._browse(anon, source="imported", lang_group="all", limit=1)["total"]
        assert base == alld


# ────────────── 2) Admin restore panel endpoints ──────────────
class TestAdminHiddenAndRestore:
    def test_hidden_summary(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/radio-import/hidden-summary", timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert isinstance(data["total_hidden"], int)
        assert isinstance(data["total_active"], int)
        assert data["total_hidden"] > 0
        assert isinstance(data["by_country"], list) and len(data["by_country"]) > 0
        assert isinstance(data["by_language"], list) and len(data["by_language"]) > 0
        for row in data["by_country"][:3]:
            assert "value" in row and "count" in row

    def test_hidden_stations_country_filter(self, admin):
        r = admin.get(f"{BASE_URL}/api/admin/radio-import/hidden-stations",
                      params={"country": "DE", "limit": 5}, timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data["limit"] == 5
        assert isinstance(data["items"], list)
        for it in data["items"]:
            assert it.get("country_code") == "DE"

    def test_hidden_stations_q_search(self, admin):
        # any q; result may be 0 or many but must return 200
        r = admin.get(f"{BASE_URL}/api/admin/radio-import/hidden-stations",
                      params={"q": "radio", "limit": 3}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "total" in d

    def test_admin_auth_required_on_hidden_summary(self, anon):
        r = anon.get(f"{BASE_URL}/api/admin/radio-import/hidden-summary", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_safe_no_op_restore_scope_country_zz(self, admin):
        # SAFE — country=ZZ can not match any real docs
        r = admin.post(f"{BASE_URL}/api/admin/radio-import/restore",
                       json={"scope": "country", "value": "ZZ"}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        assert d["ok"] is True
        assert d["restored"] == 0
        assert d["scope"] == "country"

    def test_restore_invalid_scope(self, admin):
        r = admin.post(f"{BASE_URL}/api/admin/radio-import/restore",
                       json={"scope": "bogus", "value": "x"}, timeout=30)
        assert r.status_code == 400

    def test_reversible_single_station_toggle(self, admin):
        # Grab ONE hidden station, flip active on, then flip back off.
        r = admin.get(f"{BASE_URL}/api/admin/radio-import/hidden-stations",
                      params={"limit": 1}, timeout=30)
        assert r.status_code == 200
        items = r.json().get("items", [])
        assert items, "no hidden stations available for reversible test"
        sid = items[0]["id"]

        # Enable
        r = admin.post(
            f"{BASE_URL}/api/admin/radio-import/station/{sid}/set-active",
            json={"active": True}, timeout=30)
        assert r.status_code == 200 and r.json()["ok"] is True
        assert r.json()["active"] is True

        # Revert to hidden state — leave data as-found
        r = admin.post(
            f"{BASE_URL}/api/admin/radio-import/station/{sid}/set-active",
            json={"active": False}, timeout=30)
        assert r.status_code == 200 and r.json()["ok"] is True
        assert r.json()["active"] is False


# ────────────── 3) Promoted/sponsored station slot ──────────────
class TestPromotedStations:
    def test_promoted_stations_public_autoseed(self, anon):
        r = anon.get(f"{BASE_URL}/api/promoted/stations",
                     params={"limit": 1}, timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        items = data.get("items") or data.get("stations") or data
        # Accept either {items:[...]} or a raw list
        if isinstance(data, dict) and "items" in data:
            items = data["items"]
        elif isinstance(data, list):
            items = data
        assert isinstance(items, list) and len(items) >= 1, f"no promoted station returned: {data}"
        card = items[0]
        assert card.get("promo_id"), f"missing promo_id in {card}"
        assert card.get("is_sponsored") is True, f"is_sponsored not True: {card}"
        assert card.get("sponsor_name"), f"missing sponsor_name in {card}"
        # stash for the next two tests
        TestPromotedStations.promo_id = card["promo_id"]
        TestPromotedStations.sponsor_name = card["sponsor_name"]

    def test_promoted_impression(self, anon):
        pid = getattr(TestPromotedStations, "promo_id", None)
        assert pid, "no promo_id captured from previous test"
        r = anon.post(f"{BASE_URL}/api/promoted/{pid}/impression", timeout=15)
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("ok") is True

    def test_promoted_click(self, anon):
        pid = getattr(TestPromotedStations, "promo_id", None)
        assert pid, "no promo_id captured from previous test"
        r = anon.post(f"{BASE_URL}/api/promoted/{pid}/click", timeout=15)
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("ok") is True
