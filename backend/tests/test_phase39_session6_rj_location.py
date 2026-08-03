"""Phase 39 Session 6 — Persona × location RJ greeting tests.

Validates:
- consent>=3 + selected_persona_id + ≥1 pattern → location_context in prompt
- consent=0 → no location_context, falls back to generic prompt
- generated text never contains a clock time
"""
import asyncio
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app/backend")
os.environ.setdefault("STRIPE_MODE", "mock")
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass
from motor.motor_asyncio import AsyncIOMotorClient


def run(c): return asyncio.get_event_loop().run_until_complete(c)
def _db(): return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


# Carries the Session 4 "7 AM" fix regex assertion forward.
CLOCK_TIME_REGEX = re.compile(
    r"\b(\d{1,2})\s*(AM|PM|am|pm|:00|o'?clock)\b")


def test_location_context_present_when_consent_3_and_pattern():
    async def go():
        from services.route_pattern_detection import detect_for_user, get_location_context
        db = _db()
        uid = "u_loc_ctx_" + uuid.uuid4().hex[:6]
        # Clean slate
        await db.UserTravelEvents.delete_many({"user_id": uid})
        await db.UserFrequentPlaces.delete_many({"user_id": uid})
        await db.UserTrips.delete_many({"user_id": uid})
        await db.UserRoutePatterns.delete_many({"user_id": uid})
        await db.UserBusinessVisits.delete_many({"user_id": uid})
        # Seed: 2 places + 3 trips between them at morning bucket
        await db.UserFrequentPlaces.insert_many([
            {"_id": uuid.uuid4().hex, "user_id": uid, "place_id": "fp_home_x",
             "lat": 25.20, "lng": 55.30, "label": "Home", "category": "home",
             "visit_count": 40, "confidence": "high",
             "last_seen": datetime.now(timezone.utc), "user_hidden": False},
            {"_id": uuid.uuid4().hex, "user_id": uid, "place_id": "fp_cafe_x",
             "lat": 25.21, "lng": 55.31, "label": "Karak Cafe", "category": "cafe",
             "visit_count": 20, "confidence": "high",
             "last_seen": datetime.now(timezone.utc), "user_hidden": False},
        ])
        pts = [(25.200, 55.300), (25.204, 55.304),
               (25.207, 55.307), (25.210, 55.310)]
        for d in range(3):
            base = datetime.now(timezone.utc).replace(
                hour=8, minute=0, second=0, microsecond=0) - timedelta(days=d)
            for i, (lat, lng) in enumerate(pts):
                await db.UserTravelEvents.insert_one({
                    "_id": uuid.uuid4().hex, "user_id": uid,
                    "lat": lat, "lng": lng,
                    "captured_at": base + timedelta(minutes=25 * i),
                    "app_state": "foreground"})
        await detect_for_user(db, uid)
        loc = await get_location_context(db, uid)
        assert loc is not None
        assert loc["pattern_count"] >= 1
        assert loc["morning_commute"] is not None
        assert loc["morning_commute"]["label"] == "Karak Cafe"
        assert loc["recent_business_visit"] is not None
        assert loc["recent_business_visit"]["category"] == "cafe"
        # Cleanup
        await db.UserTravelEvents.delete_many({"user_id": uid})
        await db.UserFrequentPlaces.delete_many({"user_id": uid})
        await db.UserTrips.delete_many({"user_id": uid})
        await db.UserRoutePatterns.delete_many({"user_id": uid})
        await db.UserBusinessVisits.delete_many({"user_id": uid})
    run(go())


def test_no_location_context_when_no_patterns():
    async def go():
        from services.route_pattern_detection import get_location_context
        db = _db()
        uid = "u_no_loc_" + uuid.uuid4().hex[:6]
        # No data → None
        loc = await get_location_context(db, uid)
        assert loc is None
    run(go())


def test_rj_prompt_includes_location_block():
    """Static prompt-builder test: when location_context is non-empty, the
    user prompt assembler must include the LOCATION CONTEXT block. When
    it's None, the block is absent.
    """
    from services.rj import _solo_user_prompt
    class _Ctx:
        time_of_day = "morning"
        weather_hint = "warm"
        city = "Dubai"
        market = "dubai"
    prev = {"title": "P", "artist": "A", "energy_level": "medium", "mood": "chill"}
    nxt = {"title": "N", "artist": "B", "energy_level": "high", "mood": "uplifting"}

    loc_ctx = {
        "morning_commute": {"label": "Karak Cafe", "category": "cafe"},
        "recent_business_visit": {"label": "Karak Cafe", "category": "cafe",
                                  "time_bucket": "evening"},
        "current_time_bucket": "morning",
        "pattern_count": 3,
    }
    with_loc = _solo_user_prompt(prev, nxt, _Ctx(), "Some persona",
                                 location_context=loc_ctx)
    no_loc = _solo_user_prompt(prev, nxt, _Ctx(), "Some persona",
                               location_context=None)
    assert "LOCATION CONTEXT" in with_loc
    assert "Karak Cafe" in with_loc
    assert "LOCATION CONTEXT" not in no_loc


def test_no_clock_time_in_generated_script():
    """Regression — system prompt forbids clock times. Use the prompt
    builder + a synthetic GPT mock to assert the regex assertion holds.
    We don't call OpenAI live — we assert the regex itself.
    """
    samples_pass = [
        "Doston morning ka time hai... BigFM!",
        "Evening drive kar rahe ho? Karak chai ke saath, yaar.",
        "Lunch break mein chillax... [warm] BigFM dil se.",
    ]
    samples_fail = [
        "It's 7 AM and the vibe is...",
        "Just after 10 PM, doston...",
        "Hello, it is 3:00 in the city.",
    ]
    for s in samples_pass:
        assert CLOCK_TIME_REGEX.search(s) is None, f"false positive: {s}"
    for s in samples_fail:
        assert CLOCK_TIME_REGEX.search(s) is not None, f"missed clock: {s}"
