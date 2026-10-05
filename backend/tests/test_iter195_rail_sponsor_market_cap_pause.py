"""Iteration 195 — Rail Sponsor NEW surface:
  1) GET /api/social/rail/sponsor/market  (per-area competition snapshot)
  2) POST /api/social/rail/sponsor  with optional daily_cap_cents (persisted,
     exposed on list)
  3) POST /api/social/rail/sponsor/{sid}/bid  with optional daily_cap_cents
  4) POST /api/social/rail/sponsor/{sid}/pause  (active->paused, reason=manual;
     404 not_found_or_not_active otherwise)
  5) POST /api/social/rail/sponsor/{sid}/resume (paused->active; errors
     not_found / not_paused / campaign_ended)
  6) GET /api/social/rail/sponsor/list exposes daily_cap_cents, paused_reason,
     and status can be 'paused'.
"""
import os, requests, pytest


def _env(path, key):
    try:
        with open(path) as f:
            for ln in f:
                if ln.startswith(f"{key}="):
                    return ln.split("=", 1)[1].strip().strip('"')
    except FileNotFoundError:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or _env("/app/frontend/.env", "REACT_APP_BACKEND_URL")).rstrip("/")

TEST_EMAIL = "test@bigfm.dubai"; TEST_PASSWORD = "TestUser123!"
FREE_EMAIL = "freeuser@bigfm.dubai"; FREE_PASSWORD = "FreePass123!"
MERCHANT_ID = "biz_karak_cafe_karama"
FLOOR = 500


def _login(email, pw):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, f"login {email} -> {r.status_code} {r.text}"
    return s


def _code(resp):
    try:
        d = resp.json().get("detail")
        return d.get("code") if isinstance(d, dict) else d
    except Exception:
        return None


@pytest.fixture(scope="session")
def merchant_client():
    return _login(TEST_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="session")
def free_client():
    return _login(FREE_EMAIL, FREE_PASSWORD)


# ── 1) Market snapshot ────────────────────────────────────────────────
class TestMarket:
    def test_market_shape(self, merchant_client):
        r = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/market",
                                params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("daily_floor_cents") == FLOOR
        assert d.get("increment_cents", 0) >= 1
        areas = d.get("areas") or {}
        for a in ("social", "shop", "listen"):
            assert a in areas, f"missing area {a}: {areas}"
            blk = areas[a]
            assert "active_total" in blk and isinstance(blk["active_total"], int)
            assert "top_other_cents" in blk  # may be 0
            assert "suggested_cents" in blk and blk["suggested_cents"] >= FLOOR

    def test_market_exclude_sid(self, merchant_client):
        # Exclude the biggest seeded bidder from SOCIAL and verify
        # the suggested bid for social does not grow (it should drop or stay same).
        base = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/market",
                                   params={"merchant_id": MERCHANT_ID}, timeout=30).json()
        excl = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/market",
                                   params={"merchant_id": MERCHANT_ID,
                                           "exclude_sid": "rsp_seed_hi"}, timeout=30).json()
        base_social = base["areas"]["social"]["suggested_cents"]
        excl_social = excl["areas"]["social"]["suggested_cents"]
        assert excl_social <= base_social, (base_social, excl_social)

    def test_market_non_owner_403(self, free_client):
        r = free_client.get(f"{BASE_URL}/api/social/rail/sponsor/market",
                            params={"merchant_id": MERCHANT_ID}, timeout=30)
        assert r.status_code == 403, r.text


# ── 2) Create with daily_cap_cents ────────────────────────────────────
class TestCreateWithCap:
    def test_create_persists_cap(self, merchant_client):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                                 json={"merchant_id": MERCHANT_ID,
                                       "target_id": "lsw_sponsor_evt",
                                       "duration_tier": "1d",
                                       "daily_bid_cents": 700,
                                       "target_pages": ["shop"],
                                       "daily_cap_cents": 1500}, timeout=30)
        assert r.status_code == 200, r.text
        sid = r.json()["sponsorship_id"]
        # verify list exposes it
        lst = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                  params={"merchant_id": MERCHANT_ID}, timeout=30).json()
        found = next((it for it in lst["sponsorships"] if it["id"] == sid), None)
        assert found, f"sponsorship {sid} not in list"
        assert found.get("daily_cap_cents") == 1500, found
        # cleanup
        merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor/{sid}/cancel",
                             json={}, timeout=30)


# ── 3) Adjust bid updates cap ─────────────────────────────────────────
@pytest.fixture(scope="class")
def sid_for_cap(merchant_client):
    r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                             json={"merchant_id": MERCHANT_ID,
                                   "target_id": "lsw_sponsor_evt",
                                   "duration_tier": "1d",
                                   "daily_bid_cents": 700,
                                   "target_pages": ["shop"]}, timeout=30)
    assert r.status_code == 200, r.text
    sid = r.json()["sponsorship_id"]
    yield sid
    merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor/{sid}/cancel",
                         json={}, timeout=30)


class TestAdjustBidWithCap:
    def test_bid_route_updates_cap(self, merchant_client, sid_for_cap):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor/{sid_for_cap}/bid",
                                 json={"daily_bid_cents": 900,
                                       "daily_cap_cents": 2500}, timeout=30)
        assert r.status_code == 200, r.text
        # verify
        lst = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                  params={"merchant_id": MERCHANT_ID}, timeout=30).json()
        found = next(it for it in lst["sponsorships"] if it["id"] == sid_for_cap)
        assert found.get("daily_bid_cents") == 900
        assert found.get("daily_cap_cents") == 2500


# ── 4+5) Pause/Resume + list exposes paused_reason ────────────────────
@pytest.fixture(scope="class")
def sid_for_pause(merchant_client):
    r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor",
                             json={"merchant_id": MERCHANT_ID,
                                   "target_id": "lsw_sponsor_evt",
                                   "duration_tier": "1d",
                                   "daily_bid_cents": 600,
                                   "target_pages": ["shop"]}, timeout=30)
    assert r.status_code == 200, r.text
    sid = r.json()["sponsorship_id"]
    yield sid
    merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor/{sid}/cancel",
                         json={}, timeout=30)


class TestPauseResume:
    def test_pause_unknown_404(self, merchant_client):
        r = merchant_client.post(f"{BASE_URL}/api/social/rail/sponsor/rsp_missing/pause",
                                 json={}, timeout=30)
        assert r.status_code == 404, r.text
        assert "not_found_or_not_active" in str(_code(r)), r.text

    def test_pause_active_ok(self, merchant_client, sid_for_pause):
        r = merchant_client.post(
            f"{BASE_URL}/api/social/rail/sponsor/{sid_for_pause}/pause",
            json={}, timeout=30)
        assert r.status_code == 200, r.text
        # list reflects paused + manual reason
        lst = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                  params={"merchant_id": MERCHANT_ID}, timeout=30).json()
        found = next(it for it in lst["sponsorships"] if it["id"] == sid_for_pause)
        assert found["status"] == "paused", found
        assert found.get("paused_reason") == "manual", found

    def test_pause_already_paused_404(self, merchant_client, sid_for_pause):
        r = merchant_client.post(
            f"{BASE_URL}/api/social/rail/sponsor/{sid_for_pause}/pause",
            json={}, timeout=30)
        assert r.status_code == 404, r.text

    def test_resume_ok(self, merchant_client, sid_for_pause):
        r = merchant_client.post(
            f"{BASE_URL}/api/social/rail/sponsor/{sid_for_pause}/resume",
            json={}, timeout=30)
        assert r.status_code == 200, r.text
        lst = merchant_client.get(f"{BASE_URL}/api/social/rail/sponsor/list",
                                  params={"merchant_id": MERCHANT_ID}, timeout=30).json()
        found = next(it for it in lst["sponsorships"] if it["id"] == sid_for_pause)
        assert found["status"] == "active", found

    def test_resume_not_paused_errors(self, merchant_client, sid_for_pause):
        # It's active now → resume should fail with not_paused
        r = merchant_client.post(
            f"{BASE_URL}/api/social/rail/sponsor/{sid_for_pause}/resume",
            json={}, timeout=30)
        assert r.status_code in (400, 404), r.text
        assert "not_paused" in str(_code(r)) or "not_found" in str(_code(r)), r.text

    def test_resume_unknown(self, merchant_client):
        r = merchant_client.post(
            f"{BASE_URL}/api/social/rail/sponsor/rsp_missing/resume",
            json={}, timeout=30)
        assert r.status_code in (400, 404), r.text
