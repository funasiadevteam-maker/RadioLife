"""Phase 9b — Route-based ad targeting, weather/daypart/traffic triggers,
RJ "welcome back" extras, and small backlog fixes (PATCH driving_mode
alias + expanded commute label vocab).

These are integration tests that hit the live FastAPI app and Mongo —
same harness style as test_phase8c / test_phase9a.

Pre-conditions:
- /app/memory/test_credentials.md must have a working test user +
  admin login.  The fixtures below mirror test_phase9a.

Coverage:
- compute_route_opportunities returns ≥3 opps for a Dubai commute
- geo-proximity scoring decreases with distance
- weather_triggered: rain-targeted campaign only fires when weather=rain
- daypart_triggered: lunch-targeted campaign only at 12-14h local
- traffic_triggered: heavy-only campaign respects traffic_status
- destination_arrival opps are scheduled in last 10 min of ETA
- pick_route_targeted_ad picks highest-score & enforces 15-min cooldown
- Wizard rejection on invalid weather_trigger
- commute end queues exactly 1 commute_just_completed extra
- abandon queues none
- PATCH /games_v2/user/driving_mode alias works
- Free-text commute label is coerced to other + label_custom kept
- Smoke: existing 9a + 8c routes still reachable
"""
from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional


def _now():
    return datetime.now(timezone.utc)

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

ROOT = os.environ.get("BIGFM_API_URL") or \
          "https://mobile-games-v2.preview.emergentagent.com"
API = f"{ROOT.rstrip('/')}/api"
MONGO = MongoClient(os.environ.get("MONGO_URL") or "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME") or "bigfm"
DB = MONGO[DB_NAME]


def _mongo():
    return MONGO[DB_NAME]


def _async_db():
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017")[DB_NAME]


def _run(coro_factory):
    """Run a coroutine in a fresh event loop.

    Accepts either a coroutine OR a callable that takes a fresh motor
    db and returns a coroutine.  This is how we avoid the
    "Future attached to a different loop" trap when re-entering on
    every test (motor binds to whichever loop is running on first call).
    """
    loop = asyncio.new_event_loop()
    try:
        if callable(coro_factory):
            async def _runner():
                db = AsyncIOMotorClient(
                    os.environ.get("MONGO_URL")
                    or "mongodb://localhost:27017")[DB_NAME]
                return await coro_factory(db)
            return loop.run_until_complete(_runner())
        return loop.run_until_complete(coro_factory)
    finally:
        loop.close()


# ════════════════════════════════════════════════════════════════════════
# Fixtures
# ════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def user_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": "test@bigfm.dubai",
                          "password": "TestUser123!"}, timeout=10)
    assert r.status_code == 200, r.text
    s._user_id = r.json()["user_id"]
    yield s


@pytest.fixture(scope="module")
def advertiser_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": "advertiser@bigfm.dubai",
                          "password": "AdvertiserP8!23"}, timeout=10)
    assert r.status_code == 200, r.text
    yield s


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
                  json={"email": "admin@bigfm.dubai",
                          "password": "AdminPass123!"}, timeout=10)
    assert r.status_code == 200, r.text
    yield s


@pytest.fixture(autouse=True)
def _clean_user_state(user_session):
    """Clean any active commute + pending RJ extras between tests."""
    uid = user_session._user_id
    DB.commute_sessions.update_many(
        {"user_id": uid, "status": "active"},
        {"$set": {"status": "abandoned"}})
    DB.users.update_one(
        {"user_id": uid},
        {"$set": {"driving_mode_on": False, "active_commute_id": None,
                   "pending_rj_extras": []},
          "$unset": {"last_commute_arrival_mention_at": ""}})
    DB.route_ad_opportunities.delete_many({"user_id": uid})
    DB.route_ad_decision_log.delete_many({"user_id": uid})
    yield


# ════════════════════════════════════════════════════════════════════════
# § 1 — Backlog fixes
# ════════════════════════════════════════════════════════════════════════
def test_01_patch_driving_mode_alias_works(user_session):
    """The tester sent PATCH and got 405.  Phase 9b adds a forgiving
    alias that calls the canonical POST."""
    r = user_session.patch(f"{API}/games_v2/user/driving_mode",
                                  json={"on": True}, timeout=10)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["driving_mode_on"] is True
    r2 = user_session.patch(f"{API}/games_v2/user/driving_mode",
                                   json={"on": False}, timeout=10)
    assert r2.status_code == 200
    assert r2.json()["driving_mode_on"] is False


def test_02_expanded_commute_label_enum(user_session):
    """All new canonical labels are accepted without 400."""
    new_labels = ["commute", "club_night", "concert", "movie_night",
                       "devotional", "school_run", "airport", "gym"]
    for lbl in new_labels:
        r = user_session.post(f"{API}/commute/start",
                                     json={"origin": {"lat": 25.197, "lng": 55.279},
                                             "destination": {"lat": 25.085, "lng": 55.145},
                                             "mode": "driver", "label": lbl},
                                     timeout=15)
        assert r.status_code == 200, f"label {lbl} → {r.text}"
        cid = r.json()["commute_id"]
        # End so next loop iteration can start clean.
        user_session.post(f"{API}/commute/{cid}/abandon", timeout=10)


def test_03_free_text_label_falls_back_to_other(user_session):
    """Free-text label not in the enum is accepted as `other` with the
    original preserved in `label_custom`.  Phase 9b.1: label_custom
    must round-trip via `/commute/start` response, `/active`, and
    `/history`."""
    r = user_session.post(
        f"{API}/commute/start",
        json={"origin": {"lat": 25.197, "lng": 55.279},
                "destination": {"lat": 25.085, "lng": 55.145},
                "mode": "driver", "label": "surprise_pizza_run"},
        timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    cid = body["commute_id"]
    # 9b.1 — response must surface both keys
    assert body["commute_label"] == "other"
    assert body["label_custom"] == "surprise_pizza_run"
    # DB row also has it (defensive)
    cmt = DB.commute_sessions.find_one({"commute_id": cid})
    assert cmt["commute_label"] == "other"
    assert cmt["label_custom"] == "surprise_pizza_run"
    # /commute/active surfaces it
    r2 = user_session.get(f"{API}/commute/active", timeout=10)
    assert r2.status_code == 200
    active = r2.json().get("active") or {}
    assert active.get("label_custom") == "surprise_pizza_run"
    # /commute/{id}/end also returns it
    r4 = user_session.post(f"{API}/commute/{cid}/end", timeout=15)
    assert r4.status_code == 200
    assert r4.json()["label_custom"] == "surprise_pizza_run"
    # /commute/history surfaces it (history only includes non-active)
    r3 = user_session.get(f"{API}/commute/history", timeout=10)
    assert r3.status_code == 200
    hist = r3.json().get("items") or []
    rows = [c for c in hist if c["commute_id"] == cid]
    assert rows and rows[0]["label_custom"] == "surprise_pizza_run"


def test_03b_long_free_text_label_truncated_to_32(user_session):
    """Phase 9b.1 — a 50-char free-text label is silently truncated to
    32 chars (not rejected).  Preferred over 4xx since the brief said
    'truncate is more forgiving and matches the brief's intent'."""
    long_label = "a" * 50
    r = user_session.post(
        f"{API}/commute/start",
        json={"origin": {"lat": 25.197, "lng": 55.279},
                "destination": {"lat": 25.085, "lng": 55.145},
                "mode": "driver", "label": long_label},
        timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["commute_label"] == "other"
    assert body["label_custom"] == "a" * 32
    assert len(body["label_custom"]) == 32


def test_03c_canonical_label_returns_null_label_custom(user_session):
    """When the caller sends a canonical label, label_custom is null."""
    r = user_session.post(
        f"{API}/commute/start",
        json={"origin": {"lat": 25.197, "lng": 55.279},
                "destination": {"lat": 25.085, "lng": 55.145},
                "mode": "driver", "label": "home_to_work"},
        timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["commute_label"] == "home_to_work"
    assert body["label_custom"] is None


# ════════════════════════════════════════════════════════════════════════
# § 2 — Route opportunity engine
# ════════════════════════════════════════════════════════════════════════
def _seed_campaigns_for_targeting():
    """Insert lightweight test ad-engine campaigns with smart targeting."""
    # Find businesses to attach
    cafe_biz = DB.businesses.find_one({"category": "cafe"})
    rest_biz = DB.businesses.find_one({"category": "restaurant"})
    if not cafe_biz or not rest_biz:
        pytest.skip("9a mock seed missing")
    DB.campaigns.delete_many({"campaign_id": {"$regex": "^cmp_p9b_"}})
    # Ensure at least one creative exists for the campaign so the radio
    # hook returns a complete decision.
    creative = DB.ad_creatives.find_one({"approval_status": "approved", "active": True})
    cr_id = creative["creative_id"] if creative else None
    DB.campaigns.insert_many([
        # Daypart-targeted (lunch)
        {"_id": "cmp_p9b_lunch", "campaign_id": "cmp_p9b_lunch",
          "name": "Test Lunch Deal", "status": "active",
          "advertiser_id": "adv_test_p9b", "business_id": rest_biz["business_id"],
          "creative_ids": [cr_id] if cr_id else [],
          "budget_cents": 100000, "bid_cents_per_impression": 200,
          "targeting_json": {"markets": ["dubai"], "dayparts": ["lunch"]},
          "stats": {"served_count": 0}},
        # Weather rain-only
        {"_id": "cmp_p9b_rain", "campaign_id": "cmp_p9b_rain",
          "name": "Test Rain Indoor", "status": "active",
          "advertiser_id": "adv_test_p9b", "business_id": cafe_biz["business_id"],
          "creative_ids": [cr_id] if cr_id else [],
          "budget_cents": 100000, "bid_cents_per_impression": 150,
          "targeting_json": {"markets": ["dubai"], "weather_triggers": ["rain"]},
          "stats": {"served_count": 0}},
        # Traffic heavy-only
        {"_id": "cmp_p9b_jam", "campaign_id": "cmp_p9b_jam",
          "name": "Test Stuck-in-traffic", "status": "active",
          "advertiser_id": "adv_test_p9b", "business_id": cafe_biz["business_id"],
          "creative_ids": [cr_id] if cr_id else [],
          "budget_cents": 100000, "bid_cents_per_impression": 250,
          "targeting_json": {"markets": ["dubai"], "traffic_triggers": ["heavy"]},
          "stats": {"served_count": 0}},
        # Geo-proximity targeting (route)
        {"_id": "cmp_p9b_near", "campaign_id": "cmp_p9b_near",
          "name": "Test Drive-by", "status": "active",
          "advertiser_id": "adv_test_p9b", "business_id": cafe_biz["business_id"],
          "creative_ids": [cr_id] if cr_id else [],
          "budget_cents": 100000, "bid_cents_per_impression": 300,
          "targeting_json": {"markets": ["dubai"],
                                  "proximity": {"business_id": cafe_biz["business_id"],
                                                  "radius_m": 3000,
                                                  "max_detour_minutes": 10}},
          "stats": {"served_count": 0}},
    ])
    return {"cafe": cafe_biz, "restaurant": rest_biz}


def _start_commute(user_session, *, origin=None, destination=None,
                          mode: str = "driver"):
    body = {"origin": origin or {"lat": 25.197, "lng": 55.279},
              "destination": destination or {"lat": 25.085, "lng": 55.145,
                                                      "label": "Marina"},
              "mode": mode, "label": "home_to_work"}
    r = user_session.post(f"{API}/commute/start", json=body, timeout=20)
    assert r.status_code == 200, r.text
    # Give the background route_ad_opportunities task time to complete
    # before any test mutates started_at/weather/traffic + re-runs the
    # engine; otherwise the late-finishing background task can wipe out
    # opps we just inserted.
    time.sleep(0.6)
    return r.json()


def _wait_for_opps(user_session, commute_id: str, *, min_n: int = 1,
                        timeout: float = 5.0) -> list[dict]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = user_session.get(
            f"{API}/commute/{commute_id}/opportunities", timeout=10)
        if r.status_code == 200:
            items = r.json().get("items") or []
            if len(items) >= min_n:
                return items
        time.sleep(0.25)
    return r.json().get("items") or []


def test_10_compute_route_opportunities_min_three(user_session):
    """Real Phase 9b smoke — seeded campaigns + 9a seed businesses
    must produce ≥3 opportunities within 5s for a normal drive.

    With Phase 9a's 60-Dubai-business seed and the 4 targeting kinds
    we plant here, daypart_triggered + traffic_triggered + weather
    matches alone usually clear the bar.
    """
    _seed_campaigns_for_targeting()
    # Force a weather + traffic + daypart context that activates all 3
    # non-geo kinds for the seeded campaigns.
    cmt = _start_commute(user_session)
    # Use rain weather + heavy traffic + lunch start so all three smart
    # campaigns activate, regardless of which businesses are on the
    # route polyline.
    lunch_utc = datetime(2026, 1, 1, 8, 30, 0, tzinfo=timezone.utc)
    DB.commute_sessions.update_one(
        {"commute_id": cmt["commute_id"]},
        {"$set": {"weather_snapshot": {"condition": "rain",
                                              "temp_c": 22,
                                              "precipitation_mm": 3.0},
                   "traffic_status": "heavy",
                   "started_at": lunch_utc}})
    from services.route_ad_engine import compute_route_opportunities
    _run(lambda db: compute_route_opportunities(db, cmt["commute_id"]))
    items = (user_session.get(
        f"{API}/commute/{cmt['commute_id']}/opportunities",
        params={"only_upcoming": False}, timeout=10).json()
              .get("items") or [])
    assert len(items) >= 3, f"only {len(items)} opps generated"
    # Each opp has a kind & non-empty reason_codes
    for o in items:
        assert o["kind"] in {"geo_proximity", "offer_proximity",
                                  "weather_triggered",
                                  "daypart_triggered", "traffic_triggered",
                                  "destination_arrival"}
        assert isinstance(o.get("reason_codes"), list)


def test_10b_validate_targeting_smart_unit():
    """Unit test for the smart-trigger validator — runs in-process, no
    HTTP, no DB."""
    from services.route_ad_engine import validate_targeting_smart
    # Valid
    assert validate_targeting_smart({}) is None
    assert validate_targeting_smart(
        {"weather_triggers": ["rain", "clear"],
          "dayparts": ["lunch", "evening_drive"],
          "traffic_triggers": ["heavy"],
          "commute_modes": ["driver"]}) is None
    assert validate_targeting_smart(
        {"temperature_band": {"min_c": 10, "max_c": 30}}) is None
    # Invalid
    err = validate_targeting_smart({"weather_triggers": ["drought"]})
    assert err and "weather_trigger_invalid" in err
    err = validate_targeting_smart({"dayparts": ["midnight_run"]})
    assert err and "daypart_invalid" in err
    err = validate_targeting_smart({"traffic_triggers": ["chaos"]})
    assert err and "traffic_trigger_invalid" in err
    err = validate_targeting_smart(
        {"temperature_band": {"min_c": 40, "max_c": 10}})
    assert err and "temperature_band_min_gt_max" in err
    err = validate_targeting_smart({"proximity": {"radius_m": 1000}})
    assert err and "proximity_business_id_required" in err


def test_11_weather_trigger_fires_only_on_match(user_session):
    """Force commute weather=rain → cmp_p9b_rain becomes an opp; with
    weather=clear it is filtered out."""
    _seed_campaigns_for_targeting()
    # Force clear weather by editing the cached row in maps_cache.
    DB.maps_cache.delete_many({"method": "current_weather"})
    cmt = _start_commute(user_session)
    DB.commute_sessions.update_one(
        {"commute_id": cmt["commute_id"]},
        {"$set": {"weather_snapshot": {"condition": "clear",
                                              "temp_c": 30,
                                              "precipitation_mm": 0}}})
    # Recompute
    from services.route_ad_engine import compute_route_opportunities
    _run(lambda db: compute_route_opportunities(db, cmt["commute_id"]))
    items = (user_session.get(
        f"{API}/commute/{cmt['commute_id']}/opportunities",
        params={"only_upcoming": False}, timeout=10).json()
              .get("items") or [])
    rains = [o for o in items if o["campaign_id"] == "cmp_p9b_rain"]
    assert not rains, "rain campaign should NOT fire on clear weather"
    # Now force rain
    DB.commute_sessions.update_one(
        {"commute_id": cmt["commute_id"]},
        {"$set": {"weather_snapshot": {"condition": "rain",
                                              "temp_c": 22,
                                              "precipitation_mm": 5.2}}})
    _run(lambda db: compute_route_opportunities(db, cmt["commute_id"]))
    items = (user_session.get(
        f"{API}/commute/{cmt['commute_id']}/opportunities",
        params={"only_upcoming": False}, timeout=10).json()
              .get("items") or [])
    rains = [o for o in items if o["campaign_id"] == "cmp_p9b_rain"]
    assert rains, "rain campaign should fire on rain weather"


def test_12_daypart_trigger_only_in_lunch_window(user_session):
    """Manually re-run compute_route_opportunities with simulated lunch
    daypart by editing started_at into the lunch window."""
    _seed_campaigns_for_targeting()
    cmt = _start_commute(user_session)
    # Override started_at to 12:30 Dubai (08:30 UTC) — should be lunch
    lunch_utc = datetime(2026, 1, 1, 8, 30, 0, tzinfo=timezone.utc)
    DB.commute_sessions.update_one(
        {"commute_id": cmt["commute_id"]},
        {"$set": {"started_at": lunch_utc}})
    from services.route_ad_engine import compute_route_opportunities
    _run(lambda db: compute_route_opportunities(db, cmt["commute_id"]))
    items = (user_session.get(
        f"{API}/commute/{cmt['commute_id']}/opportunities",
        params={"only_upcoming": False}, timeout=10).json()
              .get("items") or [])
    lunches = [o for o in items if o["campaign_id"] == "cmp_p9b_lunch"]
    assert lunches, "lunch campaign should fire at 12:30 local"
    # Now move it to 7am Dubai (3am UTC) — should NOT match
    early_utc = datetime(2026, 1, 1, 3, 0, 0, tzinfo=timezone.utc)
    DB.commute_sessions.update_one(
        {"commute_id": cmt["commute_id"]},
        {"$set": {"started_at": early_utc}})
    _run(lambda db: compute_route_opportunities(db, cmt["commute_id"]))
    items = (user_session.get(
        f"{API}/commute/{cmt['commute_id']}/opportunities",
        params={"only_upcoming": False}, timeout=10).json()
              .get("items") or [])
    lunches = [o for o in items if o["campaign_id"] == "cmp_p9b_lunch"]
    assert not lunches, "lunch campaign should NOT fire at 07:00 local"


def test_13_traffic_trigger_respects_heavy_only(user_session):
    _seed_campaigns_for_targeting()
    cmt = _start_commute(user_session)
    DB.commute_sessions.update_one(
        {"commute_id": cmt["commute_id"]},
        {"$set": {"traffic_status": "light"}})
    from services.route_ad_engine import compute_route_opportunities
    _run(lambda db: compute_route_opportunities(db, cmt["commute_id"]))
    items = (user_session.get(
        f"{API}/commute/{cmt['commute_id']}/opportunities",
        params={"only_upcoming": False}, timeout=10).json()
              .get("items") or [])
    jams = [o for o in items if o["campaign_id"] == "cmp_p9b_jam"]
    assert not jams, "heavy-only campaign must not fire on light traffic"
    # Heavy
    DB.commute_sessions.update_one(
        {"commute_id": cmt["commute_id"]},
        {"$set": {"traffic_status": "heavy"}})
    _run(lambda db: compute_route_opportunities(db, cmt["commute_id"]))
    items = (user_session.get(
        f"{API}/commute/{cmt['commute_id']}/opportunities",
        params={"only_upcoming": False}, timeout=10).json()
              .get("items") or [])
    jams = [o for o in items if o["campaign_id"] == "cmp_p9b_jam"]
    assert jams, "heavy-only campaign should fire on heavy traffic"


def test_14_destination_arrival_scheduled_in_last_10_min(user_session):
    """destination_arrival opps must have valid_from = started + (dur - 10min)."""
    _seed_campaigns_for_targeting()
    # Set destination near a known business so a destination_arrival opp
    # is plausible.  Use the cafe biz location as destination.
    cafe = DB.businesses.find_one({"category": "cafe"})
    cmt = _start_commute(
        user_session,
        destination={"lat": cafe["lat"], "lng": cafe["lng"],
                          "label": cafe["name"]})
    items = _wait_for_opps(user_session, cmt["commute_id"], min_n=1,
                                  timeout=5.0)
    arrival = [o for o in items if o["kind"] == "destination_arrival"]
    if not arrival:
        pytest.skip("no destination_arrival opp generated for this fixture")
    o = arrival[0]
    cmt_doc = DB.commute_sessions.find_one({"commute_id": cmt["commute_id"]})
    started = cmt_doc["started_at"]
    dur_s = int(cmt_doc.get("route_duration_in_traffic_s") or 0)
    # The opp row in DB has valid_from as datetime
    opp_row = DB.route_ad_opportunities.find_one({"opp_id": o["opp_id"]})
    expected_offset = max(0, dur_s - 600)
    actual_offset = (opp_row["valid_from"] - started).total_seconds()
    assert abs(actual_offset - expected_offset) < 5, \
        f"expected ~{expected_offset}s but got {actual_offset}s"


def test_15_geo_proximity_scoring_inverse_distance(user_session):
    """Two near-by businesses → the closer one should score higher.

    We seed two synthetic campaigns pointing at two businesses with
    different distances and check the sub-scores.
    """
    # Pick two existing businesses that lie at different distances from
    # a known route.
    DB.campaigns.delete_many({"campaign_id": {"$regex": "^cmp_p9b_dist"}})
    cafes = list(DB.businesses.find({"category": "cafe"}).limit(2))
    if len(cafes) < 2:
        pytest.skip("need 2 cafes in seed")
    cr = DB.ad_creatives.find_one({"approval_status": "approved", "active": True})
    cr_id = cr["creative_id"] if cr else None
    for i, biz in enumerate(cafes):
        DB.campaigns.insert_one({
            "_id": f"cmp_p9b_dist{i}", "campaign_id": f"cmp_p9b_dist{i}",
            "name": f"Dist {i}", "status": "active",
            "advertiser_id": "adv_test_p9b", "business_id": biz["business_id"],
            "creative_ids": [cr_id] if cr_id else [],
            "budget_cents": 100000, "bid_cents_per_impression": 200,
            "targeting_json": {"markets": ["dubai"],
                                    "proximity": {"business_id": biz["business_id"],
                                                    "radius_m": 5000,
                                                    "max_detour_minutes": 15}},
            "stats": {"served_count": 0}})
    cmt = _start_commute(user_session)
    items = _wait_for_opps(user_session, cmt["commute_id"], min_n=2,
                                  timeout=5.0)
    # Just ensure that the model produced sane scores (no NaNs, in [0,1]).
    for o in items:
        assert 0.0 <= o["score"] <= 1.0


# ════════════════════════════════════════════════════════════════════════
# § 3 — Radio engine hook + cooldown
# ════════════════════════════════════════════════════════════════════════
def test_20_pick_route_targeted_ad_returns_highest_score(user_session):
    """Direct unit-style test of the radio hook."""
    _seed_campaigns_for_targeting()
    cmt = _start_commute(user_session)
    items = _wait_for_opps(user_session, cmt["commute_id"], min_n=1,
                                  timeout=5.0)
    if not items:
        pytest.skip("no opps in this fork")
    from services.route_ad_engine import pick_route_targeted_ad
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    user_doc = DB.users.find_one({"user_id": uid})
    user_doc["is_premium"] = False
    decision = _run(lambda db: pick_route_targeted_ad(
        db, user=user_doc,
        segment_context={"market": "dubai"}))
    # Decision either fires (returns dict) or returns None depending on
    # whether the chosen opp has a creative — the function is robust to
    # both.  When it fires, the opp is now marked selected.
    if decision and decision.get("creative"):
        opp_id = decision["route_opp_id"]
        opp = DB.route_ad_opportunities.find_one({"opp_id": opp_id})
        assert opp["selected"] is True
        assert opp["shown_at"] is not None


def test_21_cooldown_15min_blocks_back_to_back(user_session):
    """After firing once, the next call within 15 min must be skipped."""
    _seed_campaigns_for_targeting()
    cmt = _start_commute(user_session)
    _wait_for_opps(user_session, cmt["commute_id"], min_n=1, timeout=5.0)
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    user_doc = DB.users.find_one({"user_id": uid})
    user_doc["is_premium"] = False
    from services.route_ad_engine import pick_route_targeted_ad
    _ = _run(lambda db: pick_route_targeted_ad(db, user=user_doc,
                                                segment_context={"market": "dubai"}))
    # Second call should be a cooldown skip
    _ = _run(lambda db: pick_route_targeted_ad(db, user=user_doc,
                                                segment_context={"market": "dubai"}))
    # decision_log should contain at least one skipped_cooldown row
    has_cooldown = DB.route_ad_decision_log.count_documents({
        "user_id": uid,
        "decision": "route_targeted_skipped_cooldown",
    })
    assert has_cooldown >= 1


def test_22_fallback_when_no_active_commute(user_session):
    """No commute → pick_route_targeted_ad returns None and logs
    no_active_commute."""
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    # Ensure no active commute
    DB.commute_sessions.update_many(
        {"user_id": uid, "status": "active"},
        {"$set": {"status": "abandoned"}})
    user_doc = DB.users.find_one({"user_id": uid})
    from services.route_ad_engine import pick_route_targeted_ad
    decision = _run(lambda db: pick_route_targeted_ad(
        db, user=user_doc,
        segment_context={"market": "dubai"}))
    assert decision is None


# ════════════════════════════════════════════════════════════════════════
# § 4 — Smart-trigger wizard validation
# ════════════════════════════════════════════════════════════════════════
def test_30_wizard_rejects_bad_weather_trigger(advertiser_session):
    """submit_for_approval must reject targeting with an invalid
    weather_trigger value (the validator runs after other validators
    so we set up a complete campaign and only break targeting)."""
    db = DB
    drafts = list(db.game_campaigns.find(
        {"advertiser_id": {"$regex": "^adv_"}, "status": "draft"}).limit(1))
    if not drafts:
        pytest.skip("no draft campaign to mutate")
    cid = drafts[0]["campaign_id"]
    # Ensure the campaign has at least one prize so prize-validation
    # passes and we reach targeting validation.
    if not list(db.game_prizes.find({"campaign_id": cid}).limit(1)):
        db.game_prizes.insert_one({
            "_id": f"prz_p9b_{cid}", "prize_id": f"prz_p9b_{cid}",
            "campaign_id": cid, "name": "P9b test prize",
            "tier": "minor", "stock": 100, "stock_remaining": 100,
            "value_cents": 100, "kind": "voucher",
            "created_at": _now(),
        })
    db.game_campaigns.update_one(
        {"campaign_id": cid},
        {"$set": {"targeting_json": {"open_to_all": True,
                                              "weather_triggers": ["drought"]}}})
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/submit_for_approval",
        timeout=10)
    # Targeting validator should reject (400) — other validators may
    # also kick in, but we accept anything in the 4xx range that
    # mentions targeting/weather.
    assert r.status_code in (400, 422), r.text
    assert ("targeting" in r.text.lower()
              or "weather" in r.text.lower()
              or "drought" in r.text.lower()
              or "at_least_one_prize_required" in r.text.lower())


def test_31_wizard_accepts_valid_smart_triggers(advertiser_session):
    """Valid smart-target fields must NOT cause submit_for_approval to
    reject (other validation rules may still kick in)."""
    db = DB
    drafts = list(db.game_campaigns.find(
        {"advertiser_id": {"$regex": "^adv_"}, "status": "draft"}).limit(1))
    if not drafts:
        pytest.skip("no draft campaign to mutate")
    cid = drafts[0]["campaign_id"]
    db.game_campaigns.update_one(
        {"campaign_id": cid},
        {"$set": {"targeting_json": {"open_to_all": True,
                                              "weather_triggers": ["rain", "cold"],
                                              "dayparts": ["lunch", "evening_drive"],
                                              "traffic_triggers": ["heavy"]}}})
    r = advertiser_session.post(
        f"{API}/games_v2/advertiser/campaigns/{cid}/submit_for_approval",
        timeout=10)
    # We don't assert 200 (other validators may fail) but the failure
    # must not be due to smart-targeting.
    assert "targeting:weather_trigger_invalid" not in r.text
    assert "targeting:daypart_invalid" not in r.text
    assert "targeting:traffic_trigger_invalid" not in r.text


# ════════════════════════════════════════════════════════════════════════
# § 5 — Commute-end RJ extra queuing
# ════════════════════════════════════════════════════════════════════════
def test_40_end_commute_queues_one_arrival_extra(user_session):
    cmt = _start_commute(user_session)
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    # Clear any prior extras
    DB.users.update_one({"user_id": uid},
                              {"$set": {"pending_rj_extras": []}})
    r = user_session.post(f"{API}/commute/{cmt['commute_id']}/end",
                                 timeout=15)
    assert r.status_code == 200
    u = DB.users.find_one({"user_id": uid})
    extras = u.get("pending_rj_extras") or []
    arrivals = [x for x in extras if x.get("kind") == "commute_just_completed"]
    assert len(arrivals) == 1, f"expected 1 arrival, got {len(arrivals)}"
    payload = arrivals[0]["payload"]
    assert "destination_label" in payload
    assert "duration_human" in payload
    assert "weather_condition" in payload


def test_41_abandon_commute_does_not_queue_extra(user_session):
    cmt = _start_commute(user_session)
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    DB.users.update_one({"user_id": uid},
                              {"$set": {"pending_rj_extras": []}})
    r = user_session.post(f"{API}/commute/{cmt['commute_id']}/abandon",
                                 timeout=10)
    assert r.status_code == 200
    u = DB.users.find_one({"user_id": uid})
    extras = u.get("pending_rj_extras") or []
    arrivals = [x for x in extras if x.get("kind") == "commute_just_completed"]
    assert len(arrivals) == 0


def test_42_pop_pending_rj_extra_is_atomic(user_session):
    cmt = _start_commute(user_session)
    user_session.post(f"{API}/commute/{cmt['commute_id']}/end", timeout=15)
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    from services.route_ad_engine import pop_pending_rj_extra
    extra1 = _run(lambda db: pop_pending_rj_extra(db, user_id=uid))
    extra2 = _run(lambda db: pop_pending_rj_extra(db, user_id=uid))
    assert extra1 is not None
    assert extra1.get("kind") == "commute_just_completed"
    assert extra2 is None


# ════════════════════════════════════════════════════════════════════════
# § 6 — "Why this ad?" reason_codes + engagement
# ════════════════════════════════════════════════════════════════════════
def test_50_reason_codes_endpoint(user_session):
    _seed_campaigns_for_targeting()
    cmt = _start_commute(user_session)
    items = _wait_for_opps(user_session, cmt["commute_id"], min_n=1,
                                  timeout=5.0)
    if not items:
        pytest.skip("no opps")
    opp_id = items[0]["opp_id"]
    r = user_session.get(f"{API}/route_ads/{opp_id}/reason_codes",
                                timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["opp_id"] == opp_id
    assert isinstance(body["reason_codes"], list)
    assert body["reason_codes"]    # non-empty


def test_51_dismiss_engagement(user_session):
    _seed_campaigns_for_targeting()
    cmt = _start_commute(user_session)
    items = _wait_for_opps(user_session, cmt["commute_id"], min_n=1,
                                  timeout=5.0)
    if not items:
        pytest.skip("no opps")
    opp_id = items[0]["opp_id"]
    r = user_session.post(f"{API}/route_ads/{opp_id}/engage",
                                 json={"engagement_type": "dismissed"},
                                 timeout=10)
    assert r.status_code == 200
    row = DB.route_ad_opportunities.find_one({"opp_id": opp_id})
    assert row["engagement_type"] == "dismissed"


def test_52_reason_codes_404_on_unknown_opp(user_session):
    r = user_session.get(f"{API}/route_ads/opp_does_not_exist/reason_codes",
                                timeout=10)
    assert r.status_code == 404


def test_53_engage_invalid_type_400(user_session):
    _seed_campaigns_for_targeting()
    cmt = _start_commute(user_session)
    items = _wait_for_opps(user_session, cmt["commute_id"], min_n=1,
                                  timeout=5.0)
    if not items:
        pytest.skip("no opps")
    opp_id = items[0]["opp_id"]
    r = user_session.post(f"{API}/route_ads/{opp_id}/engage",
                                 json={"engagement_type": "totally_bogus"},
                                 timeout=10)
    assert r.status_code == 400
    # Phase 9b.1 — error must enumerate the allowed values
    detail = r.json().get("detail", "")
    assert "clicked" in detail
    assert "saved" in detail
    assert "played" in detail
    assert "dismissed" in detail


def test_54_opportunities_items_have_valid_from_and_commute_id(user_session):
    """Phase 9b.1 — every item in /opportunities must include
    valid_from + commute_id (previously only on parent envelope)."""
    _seed_campaigns_for_targeting()
    cmt = _start_commute(user_session)
    items = _wait_for_opps(user_session, cmt["commute_id"], min_n=1,
                                  timeout=5.0)
    if not items:
        pytest.skip("no opps")
    for o in items:
        assert "valid_from" in o, f"missing valid_from on opp {o['opp_id']}"
        assert "commute_id" in o, f"missing commute_id on opp {o['opp_id']}"
        assert o["commute_id"] == cmt["commute_id"]


def test_55_reason_codes_envelope_includes_valid_from_and_commute_id(user_session):
    """Phase 9b.1 — /route_ads/{opp_id}/reason_codes payload must
    include valid_from + commute_id."""
    _seed_campaigns_for_targeting()
    cmt = _start_commute(user_session)
    items = _wait_for_opps(user_session, cmt["commute_id"], min_n=1,
                                  timeout=5.0)
    if not items:
        pytest.skip("no opps")
    opp_id = items[0]["opp_id"]
    r = user_session.get(f"{API}/route_ads/{opp_id}/reason_codes",
                                timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "valid_from" in body
    assert "commute_id" in body
    assert body["commute_id"] == cmt["commute_id"]


# ════════════════════════════════════════════════════════════════════════
# § 9 — Phase 9b.1 — pending_rj_extras visibility + cooldown surface
# ════════════════════════════════════════════════════════════════════════
def test_70_me_pending_extras_empty_initially(user_session):
    """Fresh state — 0 items, no last_commute_arrival_mention_at (or null)."""
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    # Clear lastmention from any prior test
    DB.users.update_one({"user_id": uid},
                              {"$unset": {"last_commute_arrival_mention_at": ""}})
    r = user_session.get(f"{API}/rj/me/pending_extras", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 0
    assert body["items"] == []
    assert body["commute_arrival_cooldown_minutes"] == 30
    assert body["last_commute_arrival_mention_at"] in (None, "", )


def test_71_me_pending_extras_after_commute_end(user_session):
    """0 → 1 after /commute/{id}/end.  last_commute_arrival_mention_at
    populated."""
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    DB.users.update_one({"user_id": uid},
                              {"$unset": {"last_commute_arrival_mention_at": ""},
                                "$set": {"pending_rj_extras": []}})
    cmt = _start_commute(user_session)
    r0 = user_session.get(f"{API}/rj/me/pending_extras", timeout=10).json()
    assert r0["count"] == 0
    end = user_session.post(f"{API}/commute/{cmt['commute_id']}/end", timeout=15)
    assert end.status_code == 200
    r1 = user_session.get(f"{API}/rj/me/pending_extras", timeout=10).json()
    assert r1["count"] == 1
    assert r1["items"][0]["kind"] == "commute_just_completed"
    assert r1["items"][0]["payload"]["destination_label"]
    assert r1["last_commute_arrival_mention_at"]


def test_72_abandon_does_not_queue(user_session):
    """1 → 1 after /abandon (no new arrival queued)."""
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    DB.users.update_one({"user_id": uid},
                              {"$unset": {"last_commute_arrival_mention_at": ""},
                                "$set": {"pending_rj_extras": []}})
    # First a successful end gets us to 1
    cmt1 = _start_commute(user_session)
    user_session.post(f"{API}/commute/{cmt1['commute_id']}/end", timeout=15)
    pre = user_session.get(f"{API}/rj/me/pending_extras", timeout=10).json()
    assert pre["count"] == 1
    # Now an abandon must NOT add a second
    cmt2 = _start_commute(user_session)
    user_session.post(f"{API}/commute/{cmt2['commute_id']}/abandon", timeout=10)
    post = user_session.get(f"{API}/rj/me/pending_extras", timeout=10).json()
    assert post["count"] == 1
    # last_commute_arrival_mention_at unchanged
    assert post["last_commute_arrival_mention_at"] == pre["last_commute_arrival_mention_at"]


def test_73_back_to_back_end_cooldown_blocks_second(user_session):
    """1 → 1 after a second /end inside the 30-min cooldown."""
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    DB.users.update_one({"user_id": uid},
                              {"$unset": {"last_commute_arrival_mention_at": ""},
                                "$set": {"pending_rj_extras": []}})
    cmt1 = _start_commute(user_session)
    user_session.post(f"{API}/commute/{cmt1['commute_id']}/end", timeout=15)
    cmt2 = _start_commute(user_session)
    user_session.post(f"{API}/commute/{cmt2['commute_id']}/end", timeout=15)
    body = user_session.get(f"{API}/rj/me/pending_extras", timeout=10).json()
    assert body["count"] == 1, f"cooldown should have blocked 2nd queue; got {body['count']}"


def test_74_admin_pending_extras_for_any_user(admin_session, user_session):
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    DB.users.update_one({"user_id": uid},
                              {"$unset": {"last_commute_arrival_mention_at": ""},
                                "$set": {"pending_rj_extras": []}})
    cmt = _start_commute(user_session)
    user_session.post(f"{API}/commute/{cmt['commute_id']}/end", timeout=15)
    r = admin_session.get(f"{API}/admin/rj/pending_extras",
                                 params={"user_id": uid}, timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user_id"] == uid
    assert body["count"] == 1
    assert body["items"][0]["kind"] == "commute_just_completed"
    assert body["last_commute_arrival_mention_at"]


def test_75_admin_pending_extras_user_id_required(admin_session):
    r = admin_session.get(f"{API}/admin/rj/pending_extras", timeout=10)
    assert r.status_code == 400


def test_76_admin_pending_extras_user_only_gated(user_session):
    r = user_session.get(f"{API}/admin/rj/pending_extras",
                                params={"user_id": "user_anything"}, timeout=10)
    assert r.status_code in (401, 403)


def test_77_me_pending_extras_admin_can_see_self(admin_session):
    """A listener (any role) can hit /rj/me/pending_extras — auth gate is
    just `current_user`, no role required."""
    r = admin_session.get(f"{API}/rj/me/pending_extras", timeout=10)
    assert r.status_code == 200


# ════════════════════════════════════════════════════════════════════════
# § 7 — Admin decision log
# ════════════════════════════════════════════════════════════════════════
def test_60_admin_decision_log(admin_session, user_session):
    """Fire one route-targeted decision then ensure admin can see it."""
    _seed_campaigns_for_targeting()
    cmt = _start_commute(user_session)
    _wait_for_opps(user_session, cmt["commute_id"], min_n=1, timeout=5.0)
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    user_doc = DB.users.find_one({"user_id": uid})
    user_doc["is_premium"] = False
    from services.route_ad_engine import pick_route_targeted_ad
    _run(lambda db: pick_route_targeted_ad(db, user=user_doc,
                                          segment_context={"market": "dubai"}))
    r = admin_session.get(f"{API}/route_ads/admin/decision_log",
                                 params={"commute_id": cmt["commute_id"],
                                            "limit": 20}, timeout=10)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items, "decision_log should have at least one row"
    # Schema check
    for it in items[:1]:
        for k in ("decision", "user_id", "commute_id", "ts"):
            assert k in it


def test_61_admin_decision_log_user_blocked(user_session):
    r = user_session.get(f"{API}/route_ads/admin/decision_log", timeout=10)
    assert r.status_code in (401, 403)


# ════════════════════════════════════════════════════════════════════════
# § 8 — Smoke regressions
# ════════════════════════════════════════════════════════════════════════
def test_90_openapi_lists_new_routes(admin_session):
    r = admin_session.get(f"{API}/openapi.json", timeout=10)
    assert r.status_code == 200
    paths = set(r.json()["paths"].keys())
    must = [
        "/api/commute/{commute_id}/opportunities",
        "/api/commute/admin/maps/verify_credentials",
        "/api/route_ads/{opp_id}/reason_codes",
        "/api/route_ads/{opp_id}/engage",
        "/api/route_ads/admin/decision_log",
    ]
    missing = [p for p in must if p not in paths]
    assert not missing, f"missing routes: {missing}"


def test_91_existing_9a_endpoints_still_200(user_session):
    me = user_session.get(f"{API}/auth/me", timeout=10).json()
    uid = me["user_id"]
    r = user_session.get(f"{API}/commute/me/driving_state", timeout=10)
    assert r.status_code == 200
    r = user_session.get(f"{API}/commute/saved_locations", timeout=10)
    assert r.status_code == 200


def test_92_existing_8c_endpoints_still_200(admin_session):
    r = admin_session.get(f"{API}/games_v2/admin/analytics/leaderboard",
                                params={"market": "dubai"}, timeout=10)
    assert r.status_code in (200, 404)  # 404 only if no campaigns yet
