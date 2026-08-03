"""Phase 9a — Maps plumbing + commute lifecycle + driving-mode hardening.

Covers:
  - Maps factory selects Mock vs Google by env key
  - Mock determinism + per-method behaviour
  - Cache TTL hit-rate
  - geocode/reverse_geocode fixtures
  - Compute_route returns polyline + traffic varies by time-of-day
  - Places along route returns ≥1 result for a Dubai polyline
  - Commute lifecycle: save → preview → start → heartbeat → end
  - Commute milestone unlock fires on end; not on abandon; idempotent
  - 423 driving_mode_active body carries commute_id when commute active
  - /api/system/integrations admin view
  - Webhook event-name back-compat alias
  - Smoke regressions on radio/billing/lobbies/games_v2
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient


API = os.environ.get("PHASE7_API",
                       "https://mobile-games-v2.preview.emergentagent.com").rstrip("/") + "/api"
MONGO = os.environ.get("PHASE7_MONGO", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")


def _mongo():
    return AsyncIOMotorClient(MONGO)[DB_NAME]


def _run(coro):
    return asyncio.run(coro)


def _login(email: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email} failed: {r.text}"
    s._user_id = r.json()["user_id"]
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def user_session():
    s = _login("test@bigfm.dubai", "TestUser123!")
    # Reset any leftover driving_mode + commutes from prior runs
    async def reset():
        db = _mongo()
        await db.users.update_one(
            {"user_id": s._user_id},
            {"$set": {"driving_mode_on": False,
                       "active_commute_id": None}})
        await db.commute_sessions.update_many(
            {"user_id": s._user_id, "status": "active"},
            {"$set": {"status": "abandoned"}})
    _run(reset())
    return s


@pytest.fixture(scope="module")
def advertiser_session():
    return _login("advertiser@bigfm.dubai", "AdvertiserP8!23")


# ════════════════════════════════════════════════════════════════════════
# § 1 — Maps client factory + Mock behaviour
# ════════════════════════════════════════════════════════════════════════
def test_01_factory_returns_mock_without_key(monkeypatch):
    # Force re-init by clearing the singleton.  Hide the service-account
    # env so the factory falls back to Mock.
    from services import maps_client as mc
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    mc._singleton = None
    db = _mongo()
    cli = mc.get_maps_client(db)
    assert cli.name == "MockMapsClient"
    mc._singleton = None


def test_02_factory_returns_google_with_key(monkeypatch):
    from services import maps_client as mc
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "fake-test-key")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    mc._singleton = None
    cli = mc.get_maps_client(_mongo())
    assert cli.name == "GoogleMapsClient"
    assert cli.auth_mode == "api_key"
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    mc._singleton = None


def test_02b_factory_returns_google_with_service_account(monkeypatch):
    """Phase 9a Addendum — SA path resolves when GAC env points at a
    real JSON file (downloaded to /app/backend/secrets/)."""
    from services import maps_client as mc
    import os
    sa_path = "/app/backend/secrets/gcp_service_account.json"
    if not os.path.exists(sa_path):
        pytest.skip("service account file not staged in this fork")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", sa_path)
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    mc._singleton = None
    cli = mc.get_maps_client(_mongo())
    assert cli.name == "GoogleMapsClient"
    assert cli.auth_mode == "service_account"
    assert cli.auth_email and "iam.gserviceaccount.com" in cli.auth_email
    mc._singleton = None


def test_03_seeded_places_count():
    async def check():
        db = _mongo()
        return await db.businesses.count_documents({"source": "mock_seed"})
    assert _run(check()) >= 80


def test_04_geocode_known_fixture():
    async def go():
        from services.maps_client import MockMapsClient
        db = _mongo()
        cli = MockMapsClient(db)
        r = await cli.geocode("Dubai Mall")
        return r
    out = _run(go())
    assert 25.0 < out["lat"] < 25.5
    assert 55.0 < out["lng"] < 56.0
    assert "Dubai Mall" in out["formatted_address"] or "Mall" in out["formatted_address"]


def test_05_reverse_geocode_dubai_band():
    async def go():
        from services.maps_client import MockMapsClient
        return await MockMapsClient(_mongo()).reverse_geocode(25.20, 55.27)
    out = _run(go())
    assert out["country_code"] == "AE"
    assert out["city"] == "Dubai"


def test_06_compute_route_polyline_and_traffic():
    async def go():
        from services.maps_client import MockMapsClient
        return await MockMapsClient(_mongo()).compute_route(
            {"lat": 25.1972, "lng": 55.2790},
            {"lat": 25.0800, "lng": 55.1400})
    r = _run(go())
    assert r["polyline_encoded"]
    assert r["distance_meters"] > 5000
    assert r["duration_seconds"] > 0
    assert r["traffic_status"] in {"light", "moderate", "heavy", "unknown"}
    assert r["duration_in_traffic_seconds"] >= r["duration_seconds"]


def test_07_places_along_route_returns_results():
    async def go():
        from services.maps_client import MockMapsClient
        cli = MockMapsClient(_mongo())
        r = await cli.compute_route(
            {"lat": 25.1972, "lng": 55.2790},
            {"lat": 25.0800, "lng": 55.1400})
        return await cli.places_along_route(
            r["polyline_encoded"], 3000,
            ["restaurant", "cafe", "fast_food", "mall"], 10)
    out = _run(go())
    assert len(out) >= 5, f"expected ≥5 places along Dubai route, got {len(out)}"
    for p in out[:3]:
        for k in ("place_id", "name", "lat", "lng",
                    "distance_from_route_m", "extra_drive_time_seconds"):
            assert k in p


def test_08_weather_deterministic_per_band():
    async def go():
        from services.maps_client import MockMapsClient
        cli = MockMapsClient(_mongo())
        w_dub = await cli.current_weather(25.20, 55.27)
        w_dfw = await cli.current_weather(32.78, -96.80)
        return w_dub, w_dfw
    dub, dfw = _run(go())
    assert dub["condition"] in {"clear", "haze", "hot", "cloudy", "thunderstorm"}
    assert dfw["condition"] in {"clear", "cloudy", "thunderstorm",
                                        "cold", "hot", "rain"}


def test_09_cache_hits_within_ttl():
    async def go():
        from services.maps_client import MockMapsClient
        # Use a fresh client so counters are clean
        cli = MockMapsClient(_mongo())
        await _mongo().maps_cache.delete_many({"method": "geocode"})
        await cli.geocode("Burj Khalifa")
        n1 = cli._real_calls
        await cli.geocode("Burj Khalifa")
        n2 = cli._real_calls
        return n1, n2, cli._cache_hits
    n1, n2, hits = _run(go())
    assert n2 == n1, "second geocode should hit cache (no real call)"
    assert hits >= 1


# ════════════════════════════════════════════════════════════════════════
# § 2 — Commute lifecycle
# ════════════════════════════════════════════════════════════════════════
def test_20_saved_location_crud(user_session):
    # Create by address
    r = user_session.post(f"{API}/commute/saved_locations",
                                 json={"label": "Home", "address": "Home"},
                                 timeout=10)
    assert r.status_code == 200, r.text
    home = r.json()
    assert home["loc_id"]
    assert home["label"] == "Home"
    # Create by lat/lng
    r = user_session.post(f"{API}/commute/saved_locations",
                                 json={"label": "Work",
                                         "lat": 25.0800, "lng": 55.1400}, timeout=10)
    assert r.status_code == 200
    # List
    r = user_session.get(f"{API}/commute/saved_locations", timeout=10)
    labels = {it["label"] for it in r.json()["items"]}
    assert "Home" in labels and "Work" in labels
    # Patch label
    r = user_session.patch(
        f"{API}/commute/saved_locations/{home['loc_id']}",
        json={"label": "Home (updated)"}, timeout=10)
    assert r.status_code == 200
    assert r.json()["label"] == "Home (updated)"
    # Delete
    r = user_session.delete(
        f"{API}/commute/saved_locations/{home['loc_id']}", timeout=10)
    assert r.status_code == 200


def test_21_route_preview(user_session):
    r = user_session.post(f"{API}/commute/route_preview",
                                 json={"origin": {"lat": 25.1972, "lng": 55.2790},
                                         "destination": {"lat": 25.0800, "lng": 55.1400}},
                                 timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["route"]["polyline_encoded"]
    assert body["weather"]["condition"]


def test_22_start_heartbeat_end_lifecycle(user_session):
    # Start as driver
    r = user_session.post(f"{API}/commute/start",
                                 json={"origin": {"lat": 25.1972, "lng": 55.2790},
                                         "destination": {"lat": 25.0800, "lng": 55.1400},
                                         "mode": "driver",
                                         "label": "work_to_home"},
                                 timeout=15)
    assert r.status_code == 200, r.text
    cmt = r.json()
    cid = cmt["commute_id"]
    assert cmt["status"] == "active"
    assert cmt["route_polyline"]
    # Driving mode auto-toggled on
    r = user_session.get(f"{API}/commute/me/driving_state", timeout=10)
    state = r.json()
    assert state["driving_mode_on"] is True
    assert state["commute_id"] == cid
    assert state["mode"] == "driver"
    # Heartbeat
    r = user_session.post(f"{API}/commute/{cid}/heartbeat",
                                 json={"eta_remaining_s": 600}, timeout=10)
    assert r.status_code == 200
    # End → milestone fires
    r = user_session.post(f"{API}/commute/{cid}/end", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["milestone"] is not None, "commute_completed milestone should fire"
    # Driving mode restored (was off before)
    r = user_session.get(f"{API}/commute/me/driving_state", timeout=10)
    assert r.json()["driving_mode_on"] is False
    # Idempotent re-end
    r = user_session.post(f"{API}/commute/{cid}/end", timeout=10)
    assert r.status_code == 200
    assert r.json()["status"] == "completed"


def test_23_abandon_does_not_fire_milestone(user_session):
    r = user_session.post(f"{API}/commute/start",
                                 json={"origin": {"lat": 25.20, "lng": 55.27},
                                         "destination": {"lat": 25.08, "lng": 55.14},
                                         "mode": "passenger",
                                         "label": "errand"},
                                 timeout=15).json()
    cid = r["commute_id"]
    r = user_session.post(f"{API}/commute/{cid}/abandon", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "abandoned"
    assert body.get("milestone") is None


def test_24_driving_mode_auto_toggle_restoration(user_session):
    # Manually turn driving_mode_on=True, then start a driver commute,
    # end → driving_mode should be RESTORED to True (the user's prior choice).
    uid = user_session._user_id
    async def set_on():
        await _mongo().users.update_one(
            {"user_id": uid}, {"$set": {"driving_mode_on": True}})
    _run(set_on())
    r = user_session.post(f"{API}/commute/start",
                                 json={"origin": {"lat": 25.20, "lng": 55.27},
                                         "destination": {"lat": 25.08, "lng": 55.14},
                                         "mode": "driver", "label": "home_to_work"},
                                 timeout=15).json()
    cid = r["commute_id"]
    user_session.post(f"{API}/commute/{cid}/end", timeout=10)
    async def check():
        u = await _mongo().users.find_one({"user_id": uid})
        return u.get("driving_mode_on")
    assert _run(check()) is True   # restored to prior


def test_25_active_endpoint(user_session):
    r = user_session.post(f"{API}/commute/start",
                                 json={"origin": {"lat": 25.20, "lng": 55.27},
                                         "destination": {"lat": 25.08, "lng": 55.14},
                                         "mode": "passenger", "label": "lunch_run"},
                                 timeout=15).json()
    cid = r["commute_id"]
    r = user_session.get(f"{API}/commute/active", timeout=10)
    assert r.status_code == 200
    assert r.json()["active"]["commute_id"] == cid
    user_session.post(f"{API}/commute/{cid}/abandon", timeout=10)
    r = user_session.get(f"{API}/commute/active", timeout=10)
    assert r.json()["active"] is None


def test_26_nearby_places(user_session):
    r = user_session.get(f"{API}/commute/nearby_places",
                                params={"lat": 25.1972, "lng": 55.2790,
                                          "radius": 3000,
                                          "categories": "restaurant,cafe"},
                                timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 3
    for it in items[:3]:
        assert it["category"] in {"restaurant", "cafe"}


def test_27_places_along_route(user_session):
    r = user_session.post(f"{API}/commute/start",
                                 json={"origin": {"lat": 25.1972, "lng": 55.2790},
                                         "destination": {"lat": 25.0800, "lng": 55.1400},
                                         "mode": "passenger", "label": "errand"},
                                 timeout=15).json()
    cid = r["commute_id"]
    r = user_session.get(
        f"{API}/commute/{cid}/places_along_route",
        params={"radius": 3000, "max_detour_minutes": 10}, timeout=15)
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) >= 1
    user_session.post(f"{API}/commute/{cid}/abandon", timeout=10)


# ════════════════════════════════════════════════════════════════════════
# § 3 — Driving-mode 423 enrichment
# ════════════════════════════════════════════════════════════════════════
def test_30_driving_mode_423_carries_commute_id(user_session, admin_session):
    # Start a driver commute → driving_mode auto-on
    r = user_session.post(f"{API}/commute/start",
                                 json={"origin": {"lat": 25.20, "lng": 55.27},
                                         "destination": {"lat": 25.08, "lng": 55.14},
                                         "mode": "driver", "label": "home_to_work"},
                                 timeout=15).json()
    cid = r["commute_id"]
    # Try to start a game → 423 with commute context
    r = user_session.post(f"{API}/games_v2/campaigns/cmp_house_spin/start",
                                 json={}, timeout=10)
    assert r.status_code == 423
    detail = r.json()["detail"]
    # detail is now a dict with commute context
    assert isinstance(detail, dict)
    assert detail["error"] == "driving_mode_active"
    assert detail["commute_id"] == cid
    assert detail["mode"] == "driver"
    # Cleanup
    user_session.post(f"{API}/commute/{cid}/abandon", timeout=10)


# ════════════════════════════════════════════════════════════════════════
# § 4 — System integrations admin view + Phase 9a Addendum (GCP SA)
# ════════════════════════════════════════════════════════════════════════
def test_40_system_integrations(admin_session):
    r = admin_session.get(f"{API}/system/integrations", timeout=10)
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    maps = [it for it in items if it["name"] == "MapsClient"][0]
    # Implementation can be Mock or Google depending on env at boot.
    # When SA file is staged on /app/backend/secrets/ it resolves to
    # GoogleMapsClient (with mock fallback at runtime when the APIs
    # haven't been enabled at the GCP project).  Either way the schema
    # should be stable.
    assert maps["implementation"] in ("MockMapsClient", "GoogleMapsClient")
    assert maps["env_key"] == "GOOGLE_MAPS_API_KEY"
    assert maps["mode"] in ("mock", "live", "mock_fallback")
    # Addendum surface
    assert "auth_mode" in maps
    assert "auth_email" in maps
    assert "api_health" in maps


def test_41_admin_maps_verify_credentials(admin_session):
    """Phase 9a Addendum — admin re-probe returns the fresh client
    snapshot."""
    r = admin_session.post(
        f"{API}/commute/admin/maps/verify_credentials", timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["client"] in ("MockMapsClient", "GoogleMapsClient")
    assert body["mode"] in ("mock", "live", "mock_fallback")
    assert "auth_mode" in body
    assert "api_health" in body


def test_42_verify_credentials_admin_gated(user_session):
    """Verify_credentials must be admin-only."""
    r = user_session.post(
        f"{API}/commute/admin/maps/verify_credentials", timeout=10)
    assert r.status_code in (401, 403)


def test_43_service_account_emails_safe_to_surface(admin_session):
    """When GAC is configured, the SA email must surface in
    /system/integrations.  Never the private key (verified by absence
    of `private_key` substring in the response body)."""
    r = admin_session.get(f"{API}/system/integrations", timeout=10)
    assert r.status_code == 200
    body_text = r.text
    assert "private_key" not in body_text
    assert "BEGIN PRIVATE KEY" not in body_text


# ════════════════════════════════════════════════════════════════════════
# § 5 — Webhook event-name back-compat
# ════════════════════════════════════════════════════════════════════════
def test_50_webhook_event_alias_play_win(advertiser_session):
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks",
        json={"url": "https://example.test/alias-check",
                "events_subscribed": ["play_win", "test_ping"]},
        timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    # Alias should have been rewritten + deprecation warning surfaced
    assert "prize_won" in body["endpoint"]["events_subscribed"]
    assert "play_win" not in body["endpoint"]["events_subscribed"]
    assert "deprecation_warnings" in body
    assert any("play_win" in w for w in body["deprecation_warnings"])


def test_51_webhook_event_canonical_prize_won(advertiser_session):
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/webhooks",
        json={"url": "https://example.test/canonical",
                "events_subscribed": ["prize_won", "test_ping"]},
        timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "prize_won" in body["endpoint"]["events_subscribed"]
    assert "deprecation_warnings" not in body


# ════════════════════════════════════════════════════════════════════════
# § 6 — Smoke regressions
# ════════════════════════════════════════════════════════════════════════
def test_90_smoke_lobbies_still_ok():
    r = requests.get(f"{API}/lobbies/list", timeout=10)
    assert r.status_code == 200


def test_91_smoke_play_and_win(user_session):
    r = user_session.get(f"{API}/games_v2/play_and_win", timeout=10)
    assert r.status_code == 200


def test_92_smoke_billing_status(user_session):
    r = user_session.get(f"{API}/billing/status", timeout=10)
    assert r.status_code == 200


def test_93_smoke_openapi_lists_9a_routes():
    r = requests.get(f"{API}/openapi.json", timeout=10)
    paths = list(r.json()["paths"].keys())
    must = [
        "/api/commute/saved_locations",
        "/api/commute/route_preview",
        "/api/commute/start",
        "/api/commute/{commute_id}/heartbeat",
        "/api/commute/{commute_id}/end",
        "/api/commute/{commute_id}/abandon",
        "/api/commute/active",
        "/api/commute/me/driving_state",
        "/api/commute/nearby_places",
        "/api/commute/{commute_id}/places_along_route",
        "/api/commute/admin/maps/verify_credentials",
        "/api/system/integrations",
    ]
    missing = [m for m in must if m not in paths]
    assert not missing, f"missing 9a routes: {missing}"
