"""Phase FLAGADMIN.1 — Flagship CRUD + Pre-roll Parity backend tests.

Exercises the full lifecycle:
  1. validate-stream (good + bad URL)
  2. create flagship
  3. slug collision → 409
  4. PATCH with bad URL → warn-only, needs_stream_review=true
  5. PATCH preroll_enabled=false → preroll disabled; re-enable → back
  6. Pre-roll parity on a seeded imp_fun_* flagship
  7. Soft delete → row hidden from admin listing
  8. Hard delete → 404 on next DELETE
  9. Audit log contains 4 entries (create, update, soft_delete, hard_delete)
 10. RBAC: non-admin cannot list flagship admin endpoints
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@bigfm.dubai"
ADMIN_PASSWORD = "AdminPass123!"
DEMO_EMAIL = "demo@bigfm.dubai"
DEMO_PASSWORD = "DemoPass123!"

GOOD_STREAM = "https://stream.radioparadise.com/mp3-192"
BAD_STREAM = "https://this-does-not-exist.example.invalid/x"


# ─── Fixtures ──────────────────────────────────────
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def demo_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, timeout=15)
    assert r.status_code == 200
    return s


@pytest.fixture(scope="module")
def created_station(admin_session):
    """Create a flagship station used across tests; cleanup at end (hard)."""
    payload = {
        "name": f"TEST_FLAGADMIN E2E {int(time.time())}",
        "stream_url": GOOD_STREAM,
        "flagship_region": "AE",
        "country": "United Arab Emirates",
        "country_code": "ae",
        "city": "Dubai",
        "flagship_categories": ["home", "music", "test"],
        "languages": ["english"],
        "flagship_priority": 170,
        "preroll_enabled": True,
    }
    r = admin_session.post(f"{API}/admin/stations/flagship",
                           json=payload, timeout=30)
    assert r.status_code == 200, f"create failed: {r.status_code} {r.text}"
    data = r.json()
    yield data
    # Teardown - best effort hard delete
    try:
        sid = data["station"]["id"]
        admin_session.delete(f"{API}/admin/stations/flagship/{sid}?hard=true",
                             timeout=15)
    except Exception:
        pass


# ─── Tests ─────────────────────────────────────────
class TestStreamValidation:
    def test_validate_good_stream(self, admin_session):
        r = admin_session.post(
            f"{API}/admin/stations/flagship/validate-stream",
            json={"stream_url": GOOD_STREAM}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert 200 <= d["status_code"] < 400

    def test_validate_bad_stream(self, admin_session):
        r = admin_session.post(
            f"{API}/admin/stations/flagship/validate-stream",
            json={"stream_url": BAD_STREAM}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is False
        assert d["status_code"] == 0

    def test_validate_requires_admin(self, demo_session):
        r = demo_session.post(
            f"{API}/admin/stations/flagship/validate-stream",
            json={"stream_url": GOOD_STREAM}, timeout=15)
        assert r.status_code in (401, 403)


class TestCreateFlagship:
    def test_create_response_shape(self, created_station):
        d = created_station
        assert d["ok"] is True
        st = d["station"]
        assert st["id"].startswith("imp_flg_")
        assert st["preroll_enabled"] is True
        assert st["needs_stream_review"] is False
        assert d["stream_probe"]["ok"] is True
        assert d["warnings"] == []

    def test_slug_collision_returns_409(self, admin_session, created_station):
        slug = created_station["station"]["flagship_slug"]
        payload = {
            "name": "Dup",
            "stream_url": GOOD_STREAM,
            "flagship_slug": slug,
        }
        r = admin_session.post(f"{API}/admin/stations/flagship",
                               json=payload, timeout=30)
        assert r.status_code == 409
        assert r.json().get("detail", {}).get("code") == "slug_taken"


class TestUpdateFlagship:
    def test_patch_bad_stream_url_warn_only(self, admin_session, created_station):
        sid = created_station["station"]["id"]
        r = admin_session.patch(f"{API}/admin/stations/flagship/{sid}",
                                json={"stream_url": BAD_STREAM}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert "stream_url_head_check_failed" in d.get("warnings", [])
        assert d["station"]["needs_stream_review"] is True
        assert d["station"]["playable_status"] == "pending"

    def test_patch_other_fields_independent(self, admin_session, created_station):
        sid = created_station["station"]["id"]
        r = admin_session.patch(
            f"{API}/admin/stations/flagship/{sid}",
            json={"frequency": "101.7 FM", "flagship_priority": 175,
                  "flagship_categories": ["home", "test", "updated"]},
            timeout=30)
        assert r.status_code == 200
        st = r.json()["station"]
        assert st["frequency"] == "101.7 FM"
        assert st["flagship_priority"] == 175
        assert "updated" in st["flagship_categories"]

    def test_restore_good_stream(self, admin_session, created_station):
        sid = created_station["station"]["id"]
        r = admin_session.patch(f"{API}/admin/stations/flagship/{sid}",
                                json={"stream_url": GOOD_STREAM}, timeout=30)
        assert r.status_code == 200
        assert r.json()["station"]["needs_stream_review"] is False


class TestPrerollParity:
    def test_preroll_toggle_off_disables(self, admin_session, created_station):
        sid = created_station["station"]["id"]
        r = admin_session.patch(f"{API}/admin/stations/flagship/{sid}",
                                json={"preroll_enabled": False}, timeout=15)
        assert r.status_code == 200
        assert r.json()["station"]["preroll_enabled"] is False

        # Anonymous preroll request
        r2 = requests.post(f"{API}/live-radio/preroll/request",
                           json={"station_id": sid,
                                 "session_id": "parity_off_test"},
                           timeout=15)
        assert r2.status_code == 200
        d = r2.json()
        assert d["has_preroll"] is False
        assert d["reason"] == "preroll_disabled_for_station"

    def test_preroll_toggle_on_reenables(self, admin_session, created_station):
        sid = created_station["station"]["id"]
        r = admin_session.patch(f"{API}/admin/stations/flagship/{sid}",
                                json={"preroll_enabled": True}, timeout=15)
        assert r.status_code == 200
        assert r.json()["station"]["preroll_enabled"] is True

        r2 = requests.post(f"{API}/live-radio/preroll/request",
                           json={"station_id": sid,
                                 "session_id": "parity_on_test"},
                           timeout=15)
        assert r2.status_code == 200
        d = r2.json()
        # has_preroll may be True (with ad) or False (no eligible ad) - the
        # important part is the reason is NOT preroll_disabled_for_station.
        assert d.get("reason") != "preroll_disabled_for_station"

    def test_preroll_parity_seeded_flagship(self):
        """Seeded imp_fun_* flagship shares gate with community stations
        (no is_flagship bypass)."""
        r = requests.post(f"{API}/live-radio/preroll/request",
                          json={"station_id": "imp_fun_big_1062_uae",
                                "session_id": f"parity_seeded_{int(time.time())}"},
                          timeout=15)
        assert r.status_code == 200
        d = r.json()
        # Should either get a preroll or a specific non-disabled reason,
        # but MUST NOT bypass the gate on account of being flagship.
        if not d.get("has_preroll"):
            assert d.get("reason") != "preroll_disabled_for_station"


class TestDeleteFlagship:
    """Delete tests use their own station to avoid cross-fixture pollution."""

    def _create(self, admin_session, suffix):
        r = admin_session.post(
            f"{API}/admin/stations/flagship",
            json={"name": f"TEST_DEL {suffix} {int(time.time()*1000)}",
                  "stream_url": GOOD_STREAM,
                  "flagship_region": "AE",
                  "country_code": "ae",
                  "preroll_enabled": True},
            timeout=30)
        assert r.status_code == 200
        return r.json()["station"]["id"]

    def test_soft_delete(self, admin_session):
        sid = self._create(admin_session, "soft")
        r = admin_session.delete(f"{API}/admin/stations/flagship/{sid}",
                                 timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["hard"] is False

        # Confirm hidden from admin listing (active=false + is_flagship=false)
        r2 = admin_session.get(f"{API}/admin/stations/flagship", timeout=15)
        assert r2.status_code == 200
        ids = [s["id"] for s in r2.json()["items"]]
        assert sid not in ids

        # Cleanup
        admin_session.delete(f"{API}/admin/stations/flagship/{sid}?hard=true",
                             timeout=15)

    def test_hard_delete_and_404_after(self, admin_session):
        sid = self._create(admin_session, "hard")
        r = admin_session.delete(
            f"{API}/admin/stations/flagship/{sid}?hard=true", timeout=15)
        assert r.status_code == 200
        assert r.json() == {"ok": True, "hard": True, "station_id": sid}

        # Second delete → 404
        r2 = admin_session.delete(
            f"{API}/admin/stations/flagship/{sid}?hard=true", timeout=15)
        assert r2.status_code == 404
        assert r2.json().get("detail", {}).get("code") == "station_not_found"


class TestAuditLog:
    def test_full_cycle_audit(self, admin_session):
        # Full lifecycle on a dedicated station
        r = admin_session.post(
            f"{API}/admin/stations/flagship",
            json={"name": f"TEST_AUDIT {int(time.time()*1000)}",
                  "stream_url": GOOD_STREAM,
                  "flagship_region": "AE",
                  "country_code": "ae",
                  "preroll_enabled": True},
            timeout=30)
        assert r.status_code == 200
        sid = r.json()["station"]["id"]

        # update
        r = admin_session.patch(f"{API}/admin/stations/flagship/{sid}",
                                json={"frequency": "99.9"}, timeout=15)
        assert r.status_code == 200
        # soft delete
        r = admin_session.delete(f"{API}/admin/stations/flagship/{sid}",
                                 timeout=15)
        assert r.status_code == 200
        # hard delete
        r = admin_session.delete(
            f"{API}/admin/stations/flagship/{sid}?hard=true", timeout=15)
        assert r.status_code == 200

        # Audit (hard-deleted station id still queryable)
        r = admin_session.get(f"{API}/admin/stations/flagship/{sid}/audit",
                              timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        actions = [it["action"] for it in items]
        # Reverse chronological: hard_delete first
        assert actions[0] == "hard_delete"
        assert "soft_delete" in actions
        assert "update" in actions
        assert "create" in actions
        assert len(items) >= 4


class TestRBAC:
    def test_non_admin_cannot_list_flagship_admin(self, demo_session):
        r = demo_session.get(f"{API}/admin/stations/flagship", timeout=15)
        assert r.status_code in (401, 403)

    def test_non_admin_cannot_create(self, demo_session):
        r = demo_session.post(f"{API}/admin/stations/flagship",
                              json={"name": "x", "stream_url": GOOD_STREAM},
                              timeout=15)
        assert r.status_code in (401, 403)

    def test_anon_cannot_delete(self):
        r = requests.delete(f"{API}/admin/stations/flagship/imp_flg_deadbeef",
                            timeout=15)
        assert r.status_code in (401, 403)
