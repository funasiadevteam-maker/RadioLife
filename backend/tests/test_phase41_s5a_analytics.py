"""Phase 41 Session 5.A — Creator Analytics Dashboard backend tests.

Covers:
  - GET /api/stations/{slug}/analytics (owner, business + personal)
  - Window param normalization (invalid -> 7d)
  - Non-owner -> 403, anon -> 401/403, missing slug -> 404
  - Admin can view any station
  - 15-min cache: fast 2nd call w/ identical window_starts_at
  - Daily series density (no gaps, capped at 90 for 'all')
  - top_posts engagement_score weighted (reactions + 3*comments) sort
  - business_metrics tv_display_polls consistent
  - CSV export headers, content-type, content-disposition, gating
  - openapi.json lists both endpoints
"""
from __future__ import annotations
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                break
API = f"{BASE_URL}/api"

ADMIN = ("admin@bigfm.dubai", "AdminPass123!")
OWNER = ("test@bigfm.dubai",  "TestUser123!")
DEMO  = ("demo@bigfm.dubai",  "DemoPass123!")

BIZ_SLUG = "s3a-smoke-karak"
PER_SLUG = "p41-audit-test"


def _login(email: str, pw: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=15)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def owner():
    return _login(*OWNER)

@pytest.fixture(scope="module")
def admin():
    return _login(*ADMIN)

@pytest.fixture(scope="module")
def demo():
    return _login(*DEMO)


# --- core owner GET on business station ---------------------------
def test_owner_business_7d(owner):
    r = owner.get(f"{API}/stations/{BIZ_SLUG}/analytics", params={"window": "7d"}, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["window"] == "7d"
    h = j["headline_metrics"]
    for k in ("total_listen_minutes", "unique_listeners", "session_count",
              "peak_concurrent_listeners", "followers_total", "followers_delta",
              "post_count", "reactions_total", "comments_total"):
        assert k in h, f"missing headline key {k}"
    assert "prev_window_metrics" in j and isinstance(j["prev_window_metrics"], dict)
    assert isinstance(j["daily_series"], list) and len(j["daily_series"]) == 7
    assert isinstance(j["top_posts"], list)
    assert isinstance(j["top_listeners_by_city"], list) and len(j["top_listeners_by_city"]) <= 5
    biz = j["business_only"]
    assert biz is not None, "business_only must be populated for business station"
    assert "announcement_count" in biz and "tv_display_polls" in biz


# --- personal station: business_only is null + top_posts present --
def test_owner_personal_30d(owner):
    r = owner.get(f"{API}/stations/{PER_SLUG}/analytics", params={"window": "30d"}, timeout=20)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["window"] == "30d"
    assert j["business_only"] is None, "personal station business_only must be null"
    assert len(j["daily_series"]) == 30
    posts = j["top_posts"]
    assert len(posts) == 5, f"expected 5 top posts for personal, got {len(posts)}"
    # engagement_score weighted sort verification
    scores = [p["engagement_score"] for p in posts]
    assert scores == sorted(scores, reverse=True), "top_posts not sorted by engagement_score desc"
    for p in posts:
        expected = (p["reaction_total"] or 0) + 3 * (p["comment_count"] or 0)
        assert p["engagement_score"] == expected, \
            f"engagement_score weighting wrong for {p['post_id']}: got {p['engagement_score']} expected {expected}"


# --- invalid window param falls back to 7d ------------------------
def test_invalid_window_falls_back(owner):
    r = owner.get(f"{API}/stations/{BIZ_SLUG}/analytics", params={"window": "foo"}, timeout=20)
    assert r.status_code == 200
    assert r.json()["window"] == "7d"


# --- non-owner returns 403 ---------------------------------------
def test_non_owner_forbidden(demo):
    r = demo.get(f"{API}/stations/{BIZ_SLUG}/analytics", timeout=15)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text}"
    body = r.json()
    detail = body.get("detail", body)
    code = detail.get("code") if isinstance(detail, dict) else None
    assert code == "permission_denied", f"expected code permission_denied, got {body}"


# --- anonymous: auth dep should reject ----------------------------
def test_anon_rejected():
    r = requests.get(f"{API}/stations/{BIZ_SLUG}/analytics", timeout=15)
    assert r.status_code in (401, 403), f"expected 401/403, got {r.status_code}"


# --- missing slug returns 404 ------------------------------------
def test_missing_slug_404(owner):
    r = owner.get(f"{API}/stations/missing-slug-zzz-xyz/analytics", timeout=15)
    assert r.status_code == 404
    body = r.json()
    detail = body.get("detail", body)
    code = detail.get("code") if isinstance(detail, dict) else None
    assert code == "not_found", f"expected not_found, got {body}"


# --- admin can view any station's analytics ----------------------
def test_admin_can_view_any(admin):
    r = admin.get(f"{API}/stations/{BIZ_SLUG}/analytics", timeout=20)
    assert r.status_code == 200


# --- 15-min cache: 2nd call same window_starts_at ---------------
def test_cache_hit(owner):
    r1 = owner.get(f"{API}/stations/{BIZ_SLUG}/analytics", params={"window": "90d"}, timeout=20)
    t0 = time.time()
    r2 = owner.get(f"{API}/stations/{BIZ_SLUG}/analytics", params={"window": "90d"}, timeout=20)
    elapsed = time.time() - t0
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["window_starts_at"] == r2.json()["window_starts_at"], \
        "window_starts_at should match between cached calls"
    assert r1.json()["window_ends_at"] == r2.json()["window_ends_at"], \
        "cache should return identical window_ends_at"
    # cache should be fast
    assert elapsed < 2.0, f"2nd call took {elapsed:.2f}s — cache may not be hitting"


# --- daily series capped at 90 for all-window --------------------
def test_all_window_series_capped(owner):
    r = owner.get(f"{API}/stations/{PER_SLUG}/analytics", params={"window": "all"}, timeout=30)
    assert r.status_code == 200
    j = r.json()
    assert j["window"] == "all"
    assert j["window_starts_at"] is None
    series = j["daily_series"]
    # daily_series only computed when start is not None — for 'all', empty per code
    assert isinstance(series, list)
    assert len(series) <= 90


# --- 90d series exactly 90 entries -------------------------------
def test_90d_series_len(owner):
    r = owner.get(f"{API}/stations/{BIZ_SLUG}/analytics", params={"window": "90d"}, timeout=30)
    assert r.status_code == 200
    assert len(r.json()["daily_series"]) == 90


# --- tv_display_polls is an integer (sum of tv_poll_daily counts) -
def test_tv_polls_int(owner):
    r = owner.get(f"{API}/stations/{BIZ_SLUG}/analytics", params={"window": "7d"}, timeout=20)
    assert r.status_code == 200
    tv = r.json()["business_only"]["tv_display_polls"]
    assert isinstance(tv, int) and tv >= 0


# --- CSV export: 200, headers, body ------------------------------
def test_csv_export_personal(owner):
    r = owner.get(f"{API}/stations/{PER_SLUG}/analytics.csv", params={"window": "7d"}, timeout=20)
    assert r.status_code == 200, r.text
    ctype = r.headers.get("content-type", "")
    assert ctype.startswith("text/csv"), f"content-type was {ctype}"
    cd = r.headers.get("content-disposition", "")
    assert "attachment" in cd
    # filename should contain the slug + window (main agent's spec mentions p41-audit-test_analytics_7d)
    assert f"{PER_SLUG}_analytics_7d" in cd, f"content-disposition was: {cd}"
    body = r.text.strip().splitlines()
    assert body[0] == "date,listen_minutes,unique_listeners,new_followers,posts,reactions,comments"
    assert len(body) == 8, f"expected 1 header + 7 data rows, got {len(body)}"


# --- CSV non-owner forbidden -------------------------------------
def test_csv_non_owner(demo):
    r = demo.get(f"{API}/stations/{BIZ_SLUG}/analytics.csv", params={"window": "7d"}, timeout=15)
    assert r.status_code == 403


# --- openapi lists both routes -----------------------------------
def test_openapi_lists_routes():
    r = requests.get(f"{API}/openapi.json", timeout=15)
    if r.status_code == 404:
        r = requests.get(f"{BASE_URL}/openapi.json", timeout=15)
    assert r.status_code == 200, f"openapi fetch failed: {r.status_code}"
    paths = r.json().get("paths", {})
    assert "/api/stations/{slug}/analytics" in paths, "GET analytics route missing in openapi"
    assert "/api/stations/{slug}/analytics.csv" in paths, "CSV analytics route missing in openapi"
