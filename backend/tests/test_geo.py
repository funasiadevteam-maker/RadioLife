"""
Phase 15d — geo + market lexicon + AI prompt hardening + migrations.

12 tests covering the brief's acceptance points.
"""
from __future__ import annotations
import os, sys
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ─── 1. geo.resolve_for_user ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_geo_me_returns_default_market_when_ip_unresolvable():
    from services import geo
    fake_req = MagicMock()
    fake_req.headers = {}
    fake_req.client.host = ""
    fake_db = MagicMock()
    fake_db.geo_cache.find_one = AsyncMock(return_value=None)
    fake_db.geo_cache.update_one = AsyncMock()
    out = await geo.resolve_geo_from_ip(fake_req, fake_db)
    assert out["market"] == "dubai"
    assert out["country"] == "AE"
    assert out["source"].startswith("mock")


@pytest.mark.asyncio
async def test_geo_me_respects_preferred_market_override():
    from services import geo
    fake_req = MagicMock(); fake_req.headers = {}; fake_req.client.host = ""
    fake_db = MagicMock()
    fake_db.geo_cache.find_one = AsyncMock(return_value=None)
    fake_db.geo_cache.update_one = AsyncMock()
    user = {"id": "u1", "preferred_market": "new_york"}
    out = await geo.resolve_for_user(fake_req, user, fake_db)
    assert out["market"] == "new_york"
    assert out["source"] == "override"


# ─── 2. /api/geo/gps writes last_known_location ───────────────────────────
@pytest.mark.asyncio
async def test_geo_gps_updates_last_known_location():
    from routes.geo_routes import _make_router
    fake_db = MagicMock()
    fake_db.users.update_one = AsyncMock()
    router = _make_router(fake_db, lambda: None, lambda: {"id": "u1"})
    # Call the underlying coroutine the route registers.
    route_fn = [r for r in router.routes if r.path == "/api/geo/gps"][0].endpoint
    from routes.geo_routes import GpsBody
    class _Body:
        latitude = 25.2
        longitude = 55.27
        accuracy_meters = 12.0
    body = GpsBody(latitude=25.2, longitude=55.27, accuracy_meters=12.0)
    out = await route_fn(body, user={"id": "u1", "user_id": "u1"})
    assert out["ok"] is True
    fake_db.users.update_one.assert_awaited_once()
    args, _ = fake_db.users.update_one.call_args
    assert args[0] == {"user_id": "u1"}
    assert "last_known_location" in args[1]["$set"]


# ─── 3. PATCH /users/me/market persists ────────────────────────────────────
@pytest.mark.asyncio
async def test_patch_market_persists_to_user_doc():
    from routes.geo_routes import _make_router, MarketBody
    fake_db = MagicMock()
    fake_db.users.update_one = AsyncMock()
    router = _make_router(fake_db, lambda: None, lambda: {"id": "u1"})
    route_fn = [r for r in router.routes if r.path == "/api/users/me/market"][0].endpoint
    out = await route_fn(MarketBody(market="London"), user={"id": "u1"})
    assert out["preferred_market"] == "london"
    fake_db.users.update_one.assert_awaited_once()


# ─── 4. news fetch (mock + cache TTL) ─────────────────────────────────────
@pytest.mark.asyncio
async def test_news_fetch_returns_stubs_in_mock_mode():
    from services import news
    fake_db = MagicMock()
    fake_db.news_cache.find_one = AsyncMock(return_value=None)
    fake_db.news_cache.update_one = AsyncMock()
    payload = await news.fetch_local_news("new_york", fake_db, limit=3)
    assert payload["market"] == "new_york"
    assert len(payload["items"]) == 3
    assert payload["source"] in ("mock", "mock_fallback")
    titles = " ".join(i["title"] for i in payload["items"])
    assert "Dubai" not in titles


@pytest.mark.asyncio
async def test_news_fetch_caches_per_market_30min():
    from services import news
    cached_doc = {
        "_id": "mumbai",
        "items": [{"title": "cached-1", "source": "BigFM mock"}],
        "source": "cache",
        "cached_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=20),
    }
    fake_db = MagicMock()
    fake_db.news_cache.find_one = AsyncMock(return_value=cached_doc)
    payload = await news.fetch_local_news("mumbai", fake_db, limit=5)
    assert payload["items"][0]["title"] == "cached-1"


# ─── 5. AI RJ prompt — market context injection ────────────────────────────
def test_ai_rj_prompt_injects_market_context():
    from services.market_context import build_market_clause
    clause = build_market_clause("dubai")
    assert "Dubai" in clause
    assert "Karak" in clause or "karak" in clause


def test_rj_prompt_excludes_other_markets():
    """market='new_york' → prompt does NOT contain Dubai/Karak/Dubai Marina."""
    from services.market_context import build_market_clause
    clause = build_market_clause("new_york")
    for forbidden in ("Dubai", "Karak", "Dubai Marina", "Lulu", "Burj"):
        assert forbidden not in clause, f"leaked '{forbidden}' into NY prompt"
    assert "New York" in clause


# ─── 6. Integration status cards include geo + news ────────────────────────
def test_integration_status_includes_geo_and_news_cards():
    from services.integration_health import INTEGRATIONS, HUMAN_STEPS
    assert "geo" in INTEGRATIONS
    assert "news" in INTEGRATIONS
    assert len(INTEGRATIONS) >= 8
    assert "geo" in HUMAN_STEPS and len(HUMAN_STEPS["geo"]) >= 3
    assert "news" in HUMAN_STEPS and len(HUMAN_STEPS["news"]) >= 3


# ─── 7. Badge templating respects granted_in_market ───────────────────────
def test_badge_displays_with_user_current_market_when_template():
    from services.phase15d_migrations import render_with_city
    # Template renders with current market.
    out = render_with_city("{city} Bollywood Insider", None, "mumbai")
    assert out == "Mumbai Bollywood Insider"
    # No template → fallback verbatim.
    out2 = render_with_city(None, "Bollywood Insider", "new_york")
    assert out2 == "Bollywood Insider"
    # Unknown market → generic fallback ("your city").
    out3 = render_with_city("{city} Foodie", None, "atlantis")
    assert "your city" in out3.lower()


# ─── 8. Channel rename migration is idempotent ─────────────────────────────
@pytest.mark.asyncio
async def test_channel_rename_migration_idempotent():
    from services import phase15d_migrations as p15d
    fake_db = MagicMock()
    # First run finds 2 unrenamed docs.
    docs_first = [
        {"_id": "1", "name": "Party Dubai"},
        {"_id": "2", "name": "VIP Lounge Dubai"},
    ]
    fake_db.channels.find = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=docs_first)))
    fake_db.channels.update_one = AsyncMock()
    fake_db.channels.count_documents = AsyncMock(return_value=0)
    r1 = await p15d.run_channel_rename(fake_db)
    assert r1["renamed"] == 2 and r1["already_done"] == 0
    # Second run — once names are updated they no longer match the old-name
    # query, so find() returns []. Self-healing also means: if a doc IS still
    # found with an old name (because a seeder re-overwrote it), the rename
    # is force-reapplied regardless of the sentinel flag.
    fake_db.channels.find = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=[])))
    r2 = await p15d.run_channel_rename(fake_db)
    assert r2["renamed"] == 0 and r2["already_done"] == 0
    assert r2["before"] == 0


# ─── 9. Market lexicon has all 6 required markets (Phase 15d.1 adds DFW) ───
def test_market_lexicon_has_required_markets():
    from services.market_lexicon import MARKET_LEXICON, supported_markets
    required = {"dubai", "new_york", "london", "mumbai", "los_angeles", "dfw"}
    assert required.issubset(set(MARKET_LEXICON.keys()))
    assert required.issubset(set(supported_markets()))
    for k in required:
        m = MARKET_LEXICON[k]
        assert m["brands"]   and len(m["brands"])   >= 4
        assert m["landmarks"] and len(m["landmarks"]) >= 4
        assert m["food"]     and len(m["food"])     >= 4
    # DFW-specific assertions for Phase 15d.1.
    dfw = MARKET_LEXICON["dfw"]
    assert dfw["display_name"] == "Dallas"
    assert dfw["timezone"]      == "America/Chicago"
    assert dfw.get("language")   == "english"
    assert dfw.get("centroid")   and len(dfw["centroid"]) == 2


# ─── 10. Market clause is structurally complete + language-aware ───────────
def test_market_clause_has_required_sections():
    from services.market_context import build_market_clause
    for m in ("dubai", "new_york", "london", "mumbai", "los_angeles", "dfw"):
        c = build_market_clause(m)
        assert "ONLY mention" in c
        assert "DO NOT mention" in c
        assert "brands:" in c.lower() or "Brands:" in c or "brands —" in c.lower()
        assert "landmarks" in c.lower()


# ─── 11. Phase 15d.1 — English markets must forbid Hinglish sign-offs ─────
def test_market_clause_strips_hinglish_for_english_markets():
    from services.market_context import build_market_clause
    for english_market in ("dfw", "new_york", "london", "los_angeles"):
        cl = build_market_clause(english_market).lower()
        assert "english only" in cl, f"{english_market}: missing English-only guard"
        # Discourage Hinglish vocabulary explicitly.
        assert "do not use hindi" in cl
        for banned in ("dil se", "yaar", "doston"):
            assert banned in cl  # the clause should TELL the model not to use these


# ─── 12. Phase 15d.1 — Hinglish markets must still allow 'dil se' style ──
def test_market_clause_allows_hinglish_for_hinglish_markets():
    from services.market_context import build_market_clause
    for hinglish_market in ("dubai", "mumbai"):
        cl = build_market_clause(hinglish_market).lower()
        assert "hinglish" in cl
        assert "dil se" in cl
        assert "english only" not in cl


# ─── 13. Phase 15d.1 — timezone fallback resolves America/Chicago → dfw ──
def test_geo_resolves_dfw_for_dallas_timezone():
    from services.geo import _resolve_from_tz
    out = _resolve_from_tz("America/Chicago")
    assert out is not None
    assert out["market"] == "dfw"
    assert out["city"]   == "Dallas"
    assert out["source"] == "tz"


# ─── 14. Phase 15d.1 — closest-market resolver maps known lat/lng pairs ──
def test_geo_closest_market_picks_correct_centroid():
    from services.geo import _closest_market
    assert _closest_market(32.7767, -96.7970)   == "dfw"
    assert _closest_market(40.7128, -74.0060)   == "new_york"
    assert _closest_market(34.0522, -118.2437)  == "los_angeles"
    assert _closest_market(51.5074, -0.1278)    == "london"
    assert _closest_market(19.0760, 72.8777)    == "mumbai"
    assert _closest_market(25.2048, 55.2708)    == "dubai"


# ─── 15. Phase 15d.1 — RJ purge migration idempotency ────────────────────
@pytest.mark.asyncio
async def test_rj_purge_migration_idempotent_and_logs_counts():
    from unittest.mock import AsyncMock, MagicMock
    from services import phase15d_migrations as p15d

    fake_db = MagicMock()
    fake_db.migration_flags.find_one = AsyncMock(return_value=None)
    fake_db.segments.delete_many = AsyncMock(side_effect=[
        MagicMock(deleted_count=12),
    ])
    fake_db.rj_audio_qa.delete_many = AsyncMock(side_effect=[
        MagicMock(deleted_count=3),
    ])
    fake_db.migration_flags.update_one = AsyncMock()

    r = await p15d.run_rj_script_purge(fake_db)
    assert r["deleted"] == 15
    assert r["already_done"] is False
    fake_db.migration_flags.update_one.assert_awaited_once()
    # Second run — flag already done.
    fake_db.migration_flags.find_one = AsyncMock(return_value={"done": True})
    fake_db.segments.delete_many.reset_mock()
    fake_db.rj_audio_qa.delete_many.reset_mock()
    r2 = await p15d.run_rj_script_purge(fake_db)
    assert r2["already_done"] is True
    assert r2["deleted"] == 0
    fake_db.segments.delete_many.assert_not_called()
    fake_db.rj_audio_qa.delete_many.assert_not_called()


# ─── 16. Phase 15d.1 — v2 purge MUST kill dfw-tagged docs with Dubai content ──
@pytest.mark.asyncio
async def test_purge_kills_dfw_tagged_segments_with_dubai_content():
    """Reproduces the tester's bug A: docs with `script_market='dfw'` but
       script_text containing Dubai/Karama/yaar must be deleted."""
    from unittest.mock import AsyncMock, MagicMock
    from services import phase15d_migrations as p15d

    fake_db = MagicMock()
    fake_db.migration_flags.find_one = AsyncMock(return_value=None)
    # Stage 1: segments — 5 dfw-tagged with dubai content should be wiped.
    fake_db.segments.delete_many = AsyncMock(
        return_value=MagicMock(deleted_count=5))
    fake_db.rj_audio_qa.delete_many = AsyncMock(
        return_value=MagicMock(deleted_count=0))
    fake_db.migration_flags.update_one = AsyncMock()

    r = await p15d.run_rj_script_purge(fake_db)
    assert r["already_done"] is False
    assert r["segments_deleted"] == 5
    # Confirm the segments delete_many query targets non-dubai content.
    call_args = fake_db.segments.delete_many.await_args_list[0].args[0]
    assert "rj_script" in call_args
    pattern = call_args["rj_script"]["$regex"]
    import re as _re
    cre = _re.compile(pattern, _re.IGNORECASE)
    assert cre.search("We had a great time in Dubai yaar")
    assert cre.search("Yo Karama hosts!")
    assert cre.search("dil se doston")


# ─── 17. Phase 15d.1 — post-redactor regenerates once on leak ────────────
def test_post_redactor_builds_explicit_addendum_on_leak():
    """When the first generation leaks, the redaction addendum lists every
       banned token explicitly and tells the model how to handle song titles."""
    from services.market_context import (
        banned_tokens_for_market, build_redaction_addendum)
    leaked = "Aap sun rahe ho BigFM Dubai, dil se dosto. Sharjah Sunrise was MAST yaar."
    hits = banned_tokens_for_market(leaked, "dfw")
    # Must catch BOTH dubai-place tokens AND hinglish tokens for english market.
    assert any(h.lower() == "dubai"   for h in hits)
    assert any(h.lower() == "sharjah" for h in hits)
    assert any("dil" in h.lower()      for h in hits)
    assert any(h.lower() == "yaar"    for h in hits)
    addendum = build_redaction_addendum("dfw", hits)
    assert "REDACTION RULES" in addendum
    assert "DO NOT use these words" in addendum
    assert "the previous track" in addendum
    # Banned tokens must be listed in the addendum verbatim.
    for tok in ("dubai", "sharjah", "yaar"):
        assert tok in addendum.lower()


# ─── 18. Phase 15d.1 — post-redactor must NOT regenerate for dubai market ──
def test_post_redactor_passes_through_dubai_market_unchanged():
    """Dubai is the only market allowed to use Dubai tokens / Hinglish — the
       checker must return zero hits for any script when market=dubai."""
    from services.market_context import banned_tokens_for_market
    leaked = "BigFM Dubai, dil se doston! Karak chai aur Sharjah breeze!"
    assert banned_tokens_for_market(leaked, "dubai") == []


# ─── 19. Phase 15d.1 — track-title audit flags "Sharjah Sunrise" → dubai ──
@pytest.mark.asyncio
async def test_track_audit_locks_sharjah_to_dubai_market():
    """Backfill must auto-set markets_allowed=['dubai'] for tracks whose
       title contains a market-restrictive city token."""
    from unittest.mock import AsyncMock, MagicMock
    from services import phase15d_migrations as p15d
    fake_db = MagicMock()
    docs = [
        {"_id": "t1", "title": "Sharjah Sunrise",   "artist": "Ananya R"},
        {"_id": "t2", "title": "Manhattan Mornings", "artist": "X"},
        {"_id": "t3", "title": "Generic Beat",       "artist": "Y"},  # no token
        {"_id": "t4", "title": "Dallas Drive",       "artist": "Z"},
    ]
    fake_db.tracks.find = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=docs)))
    fake_db.tracks.update_one = AsyncMock()
    out = await p15d.run_track_market_audit(fake_db)
    assert out["restricted"] == 3   # sharjah → dubai, manhattan → new_york, dallas → dfw
    assert out["free"]        == 1
    # Verify the update_one calls set the right markets_allowed.
    by_id = {}
    for call in fake_db.tracks.update_one.await_args_list:
        f, u = call.args
        by_id[f["_id"]] = u["$set"].get("markets_allowed")
    assert by_id["t1"] == ["dubai"]
    assert by_id["t2"] == ["new_york"]
    assert by_id["t3"] is None        # untouched
    assert by_id["t4"] == ["dfw"]


# ─── 20. Phase 15d.1 — channel globalisation flips dubai → global ────────
@pytest.mark.asyncio
async def test_channel_globalisation_flips_default_to_global():
    from unittest.mock import AsyncMock, MagicMock
    from services import phase15d_migrations as p15d
    fake_db = MagicMock()
    docs = [
        {"_id": "party_dubai",          "market": "dubai"},
        {"_id": "vip_lounge",           "market": "dubai"},
        {"_id": "dfw_bollywood_drive", "market": "dfw"},      # regional — keep
        {"_id": "morning_masala",       "market": "global",
          "_phase15d_market_globalised": True},                 # already done — skip
    ]
    fake_db.channels.find = MagicMock(return_value=MagicMock(
        to_list=AsyncMock(return_value=docs)))
    fake_db.channels.update_one = AsyncMock()
    out = await p15d.run_channel_market_globalisation(fake_db)
    assert out["flipped"] == 2          # party_dubai + vip_lounge
    assert out["skipped"] == 2          # dfw_* (prefix) + morning_masala (sentinel)
    flipped_ids = [c.args[0]["_id"]
                          for c in fake_db.channels.update_one.await_args_list]
    assert set(flipped_ids) == {"party_dubai", "vip_lounge"}