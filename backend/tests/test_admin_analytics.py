"""Phase 12a — Admin Analytics Dashboard tests.

Hits the live backend like test_phase10c.py. Validates auth gating,
KPI shape, range filtering, ad aggregation, GAM-missing flag, and
health snapshot.
"""
from __future__ import annotations
import os

import pytest
import requests

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": email, "password": password}, timeout=10)
    assert r.status_code == 200, f"login failed: {r.text[:200]}"
    return s


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def free_session() -> requests.Session:
    return _login("test@bigfm.dubai", "TestUser123!")


# ─── Tests ─────────────────────────────────────────────────────────────
def test_overview_admin_only_403(free_session):
    """Non-admin user must be 403 on every analytics endpoint."""
    for ep in ("overview", "songs", "ads", "commute", "games",
                  "revenue", "health"):
        r = free_session.get(f"{API}/admin/analytics/{ep}", timeout=10)
        assert r.status_code == 403, (ep, r.status_code, r.text[:200])
    # And fully unauthenticated → 401
    r = requests.get(f"{API}/admin/analytics/overview", timeout=10)
    assert r.status_code == 401


def test_overview_returns_kpi_shape(admin_session):
    r = admin_session.get(f"{API}/admin/analytics/overview?range=7d",
                                  timeout=15)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    # Envelope
    for k in ("range", "generated_at", "data", "missing_data_flags"):
        assert k in body, body
    assert body["range"] == "7d"
    assert isinstance(body["missing_data_flags"], list)
    data = body["data"]
    # Required KPI keys
    expected = {"dau", "wau", "mau", "listening_hours_total",
                  "top_channels", "skip_rate", "ai_rj_engagement",
                  "premium_conversion_rate", "rewards_liability_bigcoin",
                  "revenue_by_channel", "revenue_total_cents"}
    missing = expected - set(data.keys())
    assert not missing, f"missing keys: {missing}"
    # premium_conversion_rate must be a number between 0 and 1
    pcr = data["premium_conversion_rate"]
    assert pcr is None or 0.0 <= pcr <= 1.0, pcr


def test_songs_top_played_respects_range(admin_session):
    """7d window must yield <= 30d window play counts."""
    r7 = admin_session.get(f"{API}/admin/analytics/songs?range=7d&limit=50",
                                  timeout=15)
    r30 = admin_session.get(f"{API}/admin/analytics/songs?range=30d&limit=50",
                                  timeout=15)
    assert r7.status_code == 200 and r30.status_code == 200
    d7 = r7.json()["data"]
    d30 = r30.json()["data"]
    # Required keys
    for d in (d7, d30):
        for k in ("top_played", "most_skipped", "top_liked"):
            assert k in d
    # 7d aggregate plays must be <= 30d aggregate plays for the same set
    total7 = sum(t["plays"] for t in d7["top_played"])
    total30 = sum(t["plays"] for t in d30["top_played"])
    assert total7 <= total30, (total7, total30)
    # invalid range → 400
    rbad = admin_session.get(f"{API}/admin/analytics/songs?range=year",
                                       timeout=10)
    assert rbad.status_code == 400, rbad.text


def test_ads_metrics_aggregate_correctly(admin_session):
    r = admin_session.get(f"{API}/admin/analytics/ads?range=30d", timeout=15)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    data = body["data"]
    for k in ("impressions", "completed_listens", "coupon_saves",
                "direction_clicks", "check_ins", "redemptions",
                "by_campaign", "by_advertiser", "eCPM", "fill_rate"):
        assert k in data, f"missing {k}"
    # eCPM + fill_rate must be NULL with the flag set (GAM not live)
    assert data["eCPM"] is None
    assert data["fill_rate"] is None
    assert "eCPM" in body["missing_data_flags"]
    assert "fill_rate" in body["missing_data_flags"]
    # Completed listens cannot exceed total impressions when both present
    if (isinstance(data["impressions"], int)
              and isinstance(data["completed_listens"], int)):
        assert data["completed_listens"] <= data["impressions"]
    # by_campaign rows sum impressions consistently
    if isinstance(data["impressions"], int) and data["by_campaign"]:
        per_campaign_total = sum(c["impressions"] for c in data["by_campaign"])
        # by_campaign is top-10 only; per_campaign_total ≤ impressions
        assert per_campaign_total <= data["impressions"]


def test_revenue_handles_missing_gam_gracefully(admin_session):
    """GAM not live → eCPM + programmatic_fill_rate must be NULL and
    flagged, never a 500."""
    r = admin_session.get(f"{API}/admin/analytics/revenue?range=7d",
                                  timeout=15)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    flags = body["missing_data_flags"]
    data = body["data"]
    assert "eCPM" in flags
    assert "programmatic_fill_rate" in flags
    assert data["eCPM"] is None
    assert data["programmatic_fill_rate"] is None
    # MRR is always a non-negative int even with zero subscribers
    assert isinstance(data["subscription_mrr_cents"], int)
    assert data["subscription_mrr_cents"] >= 0


def test_health_returns_snapshot(admin_session):
    r = admin_session.get(f"{API}/admin/analytics/health", timeout=10)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    data = body["data"]
    for k in ("cold_start_segment_latency_p50_ms",
                "cold_start_segment_latency_p95_ms",
                "ai_rj_generation_failure_rate",
                "ffmpeg_concat_failure_rate",
                "active_lobbies",
                "ws_disconnect_rate",
                "process_started_at"):
        assert k in data, f"missing {k}"
    # active_lobbies is always an int (even 0)
    assert isinstance(data["active_lobbies"], int)
    # On a fresh process all rates should be None and flagged
    if data["ai_rj_generation_failure_rate"] is None:
        assert "ai_rj_generation_failure_rate" in body["missing_data_flags"]
    if data["ffmpeg_concat_failure_rate"] is None:
        assert "ffmpeg_concat_failure_rate" in body["missing_data_flags"]


def test_openapi_lists_admin_analytics_routes(admin_session):
    """Acceptance: /api/openapi.json must reflect the new routes."""
    r = requests.get(f"{API}/openapi.json", timeout=10)
    assert r.status_code == 200
    paths = set(r.json().get("paths", {}).keys())
    for p in ("/api/admin/analytics/overview",
                "/api/admin/analytics/songs",
                "/api/admin/analytics/ads",
                "/api/admin/analytics/commute",
                "/api/admin/analytics/games",
                "/api/admin/analytics/revenue",
                "/api/admin/analytics/health"):
        assert p in paths, f"openapi missing {p}"
