"""Phase 23 Session 2 — wizard backend tests.

Covers:
  - Payload extension: create + patch accept the 4 new fields
  - Persistence + view round-trip
  - creator_type defaulting + admin-bypass
  - Admin-creator endpoint: 200 + status=active when complete, draft when not
  - Non-admin → 403 on /admin/campaigns
  - validate_for_submit: missing prize / missing terms / end_at past / start≥end
  - /sessions/{id}/play alias delegates to /submit
  - Backfill idempotency
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone


sys.path.insert(0, "/app/backend")
os.environ["STRIPE_MODE"] = "mock"
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def _now():
    return datetime.now(timezone.utc)


def _nid(prefix: str, n: int = 12) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:n]}"


async def _login(ac, email: str, password: str):
    r = await ac.post("/api/auth/login",
        json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


async def _login_admin(ac):
    j = await _login(ac, "admin@bigfm.dubai", "AdminPass123!")
    return {"Authorization": f"Bearer {j['session_token']}"}, j["user_id"]


async def _ensure_advertiser_login(ac):
    """Phase 8a tests already create this advertiser fixture.  Reuse it."""
    # First try login
    r = await ac.post("/api/auth/login",
        json={"email": "advertiser@bigfm.dubai",
                  "password": "AdvertiserP8!23"})
    if r.status_code == 200:
        return ({"Authorization": f"Bearer {r.json()['session_token']}"},
                  r.json()["user_id"])
    # Otherwise create via DB
    from auth import hash_password
    db = _db()
    uid = f"user_{uuid.uuid4().hex[:14]}"
    await db.users.insert_one({
        "_id": uid, "user_id": uid,
        "email": "advertiser@bigfm.dubai",
        "name": "P23 S2 Advertiser",
        "password_hash": hash_password("AdvertiserP8!23"),
        "role": "advertiser", "is_advertiser": True,
        "is_premium": False, "billing_status": "active",
        "reward_multiplier": 1.0, "preference_vector": {"city": "Dubai"},
        "language": "en", "market": "dubai",
        "created_at": _now(),
    })
    await db.advertisers.insert_one({
        "_id": "adv_phase23_s2",
        "advertiser_id": "adv_phase23_s2", "user_id": uid,
        "display_name": "P23 S2 Test Co", "approval_status": "approved",
        "market": "dubai",
    })
    r = await ac.post("/api/auth/login",
        json={"email": "advertiser@bigfm.dubai",
                  "password": "AdvertiserP8!23"})
    assert r.status_code == 200, r.text
    return ({"Authorization": f"Bearer {r.json()['session_token']}"},
              r.json()["user_id"])


def _minimal_campaign_payload(*, with_wizard_cols: bool = True) -> dict:
    end = (_now() + timedelta(days=7)).isoformat()
    body = {
        "template_id": "tpl_spin_wheel",
        "title": "P23 S2 Test Campaign",
        "end_at": end,
        "prizes": [{
            "prize_type": "coupon", "title": "Free chai",
            "value_amount": 10, "value_currency": "AED",
            "probability_weight": 100, "inventory_total": 5,
            "max_per_user": 1, "redemption_method": "qr_code",
            "requires_staff_validation": True,
        }],
        "compliance": {
            "terms_text": "Promotional game terms — no purchase necessary.",
            "odds_disclosure": "Odds vary; see terms.",
            "age_restriction": 13,
        },
    }
    if with_wizard_cols:
        body["placement_rules_json"] = {"surfaces": ["play_and_win_tab"]}
        body["eligibility_rules_json"] = {"min_listening_minutes": 0}
        body["win_rules_json"] = {"mode": "random_per_play"}
        body["creator_type"] = "advertiser"
    return body


async def _cleanup_campaign(db, cid: str):
    await db.game_campaigns.delete_one({"campaign_id": cid})
    await db.game_prizes.delete_many({"campaign_id": cid})
    await db.game_compliance_settings.delete_one({"campaign_id": cid})
    await db.game_redemption_rules.delete_one({"campaign_id": cid})


# =====================================================================
# Payload extension on existing advertiser create / patch
# =====================================================================
def test_advertiser_create_accepts_4_new_wizard_columns():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            ahdr, _ = await _ensure_advertiser_login(ac)
            r = await ac.post("/api/games_v2/advertiser/campaigns",
                                      json=_minimal_campaign_payload(),
                                      headers=ahdr)
            assert r.status_code == 200, r.text
            body = r.json()
            cid = body["campaign_id"]
            try:
                # Persisted
                doc = await db.game_campaigns.find_one({"campaign_id": cid})
                assert doc["placement_rules_json"] == {"surfaces": ["play_and_win_tab"]}
                assert doc["eligibility_rules_json"] == {"min_listening_minutes": 0}
                assert doc["win_rules_json"] == {"mode": "random_per_play"}
                assert doc["creator_type"] == "advertiser"
                # Round-tripped in view
                view = body["campaign"]
                assert view["placement_rules_json"]["surfaces"] == ["play_and_win_tab"]
                assert view["win_rules_json"]["mode"] == "random_per_play"
                assert view["creator_type"] == "advertiser"
            finally:
                await _cleanup_campaign(db, cid)
    run(go())


def test_advertiser_patch_updates_wizard_columns():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            ahdr, _ = await _ensure_advertiser_login(ac)
            r = await ac.post("/api/games_v2/advertiser/campaigns",
                                      json=_minimal_campaign_payload(with_wizard_cols=False),
                                      headers=ahdr)
            assert r.status_code == 200
            cid = r.json()["campaign_id"]
            try:
                r2 = await ac.patch(
                    f"/api/games_v2/advertiser/campaigns/{cid}",
                    headers=ahdr,
                    json={"placement_rules_json": {"surfaces": ["during_ad"]},
                              "win_rules_json": {"mode": "everyone_wins"}})
                assert r2.status_code == 200, r2.text
                doc = await db.game_campaigns.find_one({"campaign_id": cid})
                assert doc["placement_rules_json"] == {"surfaces": ["during_ad"]}
                assert doc["win_rules_json"] == {"mode": "everyone_wins"}
                # eligibility was not patched — stays default
                assert doc["eligibility_rules_json"] == {}
            finally:
                await _cleanup_campaign(db, cid)
    run(go())


def test_advertiser_create_unknown_field_still_rejected():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=15) as ac:
            ahdr, _ = await _ensure_advertiser_login(ac)
            body = _minimal_campaign_payload()
            body["totally_made_up_field"] = "boom"
            r = await ac.post("/api/games_v2/advertiser/campaigns",
                                      json=body, headers=ahdr)
            assert r.status_code == 400
            assert "unknown_fields" in r.text
    run(go())


def test_campaign_view_defaults_creator_type_from_platform_funded():
    async def go():
        db = _db()
        cid = _nid("cmp_p23s2", 14)
        await db.game_campaigns.insert_one({
            "_id": cid, "campaign_id": cid,
            "template_id": "tpl_spin_wheel",
            "title": "Pre-Phase23 row",
            "status": "active",
            "is_platform_funded": True,
            "start_at": _now() - timedelta(days=1),
            "end_at": _now() + timedelta(days=7),
            "created_at": _now(),
        })
        try:
            from routes.games_v2 import _campaign_view
            v = _campaign_view(await db.game_campaigns.find_one({"campaign_id": cid}))
            assert v["creator_type"] == "admin", \
                "platform-funded row should view as creator_type=admin"
        finally:
            await db.game_campaigns.delete_one({"campaign_id": cid})
    run(go())


# =====================================================================
# Admin-creator endpoint
# =====================================================================
def test_admin_create_campaign_auto_activates_when_complete():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            ahdr, _ = await _login_admin(ac)
            r = await ac.post("/api/games_v2/admin/campaigns",
                                      json=_minimal_campaign_payload(),
                                      headers=ahdr)
            assert r.status_code == 200, r.text
            body = r.json()
            cid = body["campaign_id"]
            try:
                assert body["creator_type"] == "admin"
                assert body["auto_activated"] is True
                assert body["status"] == "active"
                doc = await db.game_campaigns.find_one({"campaign_id": cid})
                assert doc["is_platform_funded"] is True
                assert doc["creator_type"] == "admin"
                assert doc["status"] == "active"
                # Compliance auto-approved
                comp = await db.game_compliance_settings.find_one(
                    {"campaign_id": cid})
                assert comp["approval_status"] == "approved"
            finally:
                await _cleanup_campaign(db, cid)
    run(go())


def test_admin_create_campaign_stays_draft_when_missing_terms():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=30) as ac:
            ahdr, _ = await _login_admin(ac)
            body = _minimal_campaign_payload()
            body["compliance"] = {"terms_text": ""}
            r = await ac.post("/api/games_v2/admin/campaigns",
                                      json=body, headers=ahdr)
            assert r.status_code == 200, r.text
            data = r.json()
            cid = data["campaign_id"]
            try:
                assert data["auto_activated"] is False
                assert data["status"] == "draft"
            finally:
                await _cleanup_campaign(db, cid)
    run(go())


def test_admin_create_campaign_non_admin_403():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=15) as ac:
            ahdr, _ = await _ensure_advertiser_login(ac)
            r = await ac.post("/api/games_v2/admin/campaigns",
                                      json=_minimal_campaign_payload(),
                                      headers=ahdr)
            assert r.status_code == 403, r.text
    run(go())


def test_admin_create_campaign_template_required():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=15) as ac:
            ahdr, _ = await _login_admin(ac)
            r = await ac.post("/api/games_v2/admin/campaigns",
                                      json={"title": "no template"}, headers=ahdr)
            assert r.status_code == 400
            assert "template_id" in r.text
    run(go())


# =====================================================================
# validate_for_submit harness
# =====================================================================
def test_validate_for_submit_catches_missing_terms_and_dates():
    async def go():
        from routes.games_v2_admin_campaigns import validate_for_submit
        db = _db()
        cid = _nid("cmp_p23s2_val", 14)
        # baseline: complete + valid
        await db.game_campaigns.insert_one({
            "_id": cid, "campaign_id": cid,
            "template_id": "tpl_spin_wheel", "title": "val test",
            "status": "draft",
            "start_at": _now() + timedelta(hours=1),
            "end_at": _now() + timedelta(days=7),
            "created_at": _now(),
        })
        pid = _nid("prz")
        await db.game_prizes.insert_one({
            "_id": pid, "prize_id": pid, "campaign_id": cid,
            "active": True, "probability_weight": 100,
            "inventory_total": 1, "inventory_remaining": 1,
        })
        await db.game_compliance_settings.insert_one({
            "_id": cid, "campaign_id": cid,
            "terms_text": "Real terms",
        })
        try:
            # Happy path
            await validate_for_submit(db, cid)

            # Missing terms
            await db.game_compliance_settings.update_one(
                {"campaign_id": cid}, {"$set": {"terms_text": ""}})
            try:
                await validate_for_submit(db, cid)
                assert False, "expected terms_text_required"
            except ValueError as e:
                assert str(e) == "terms_text_required"
            await db.game_compliance_settings.update_one(
                {"campaign_id": cid}, {"$set": {"terms_text": "Real terms"}})

            # end_at in the past — null start_at first so we hit the
            # end_at_in_past branch (not start_must_precede_end)
            await db.game_campaigns.update_one(
                {"campaign_id": cid},
                {"$set": {"start_at": None,
                              "end_at": _now() - timedelta(days=1)}})
            try:
                await validate_for_submit(db, cid)
                assert False, "expected end_at_in_past"
            except ValueError as e:
                assert str(e) == "end_at_in_past"

            # start >= end
            await db.game_campaigns.update_one(
                {"campaign_id": cid},
                {"$set": {"start_at": _now() + timedelta(days=5),
                              "end_at": _now() + timedelta(days=2)}})
            try:
                await validate_for_submit(db, cid)
                assert False, "expected start_must_precede_end"
            except ValueError as e:
                assert str(e) == "start_must_precede_end"

            # Missing prizes
            await db.game_prizes.delete_many({"campaign_id": cid})
            await db.game_campaigns.update_one(
                {"campaign_id": cid},
                {"$set": {"start_at": _now() + timedelta(hours=1),
                              "end_at": _now() + timedelta(days=7)}})
            try:
                await validate_for_submit(db, cid)
                assert False, "expected at_least_one_prize_required"
            except ValueError as e:
                assert str(e) == "at_least_one_prize_required"
        finally:
            await _cleanup_campaign(db, cid)
    run(go())


def test_validate_for_submit_campaign_not_found():
    async def go():
        from routes.games_v2_admin_campaigns import validate_for_submit
        try:
            await validate_for_submit(_db(), "cmp_does_not_exist")
            assert False, "expected campaign_not_found"
        except ValueError as e:
            assert str(e) == "campaign_not_found"
    run(go())


# =====================================================================
# /sessions/{id}/play alias
# =====================================================================
def test_play_alias_route_is_mounted():
    async def go():
        from httpx import ASGITransport, AsyncClient
        srv = importlib.import_module("server")
        # We don't have a live session at hand — verify the route exists
        # in openapi and that calling it without a session returns the
        # SAME error shape as /submit (400 or 404 invariant).
        spec = srv.app.openapi()
        play_path = "/api/games_v2/sessions/{session_id}/play"
        submit_path = "/api/games_v2/sessions/{session_id}/submit"
        assert play_path in spec["paths"], "play alias not mounted"
        assert submit_path in spec["paths"], "submit canonical not present"
        # Same method
        assert "post" in spec["paths"][play_path]
        assert "post" in spec["paths"][submit_path]
        # Hit the alias with bogus id — should match submit's behavior
        async with AsyncClient(transport=ASGITransport(app=srv.app),
                                          base_url="http://test", timeout=15) as ac:
            ahdr, _ = await _login_admin(ac)
            r_play = await ac.post(
                "/api/games_v2/sessions/gs_nonexistent_p23/play",
                headers=ahdr, json={})
            r_sub = await ac.post(
                "/api/games_v2/sessions/gs_nonexistent_p23/submit",
                headers=ahdr, json={})
            # Both should report an invariant error (same status code)
            assert r_play.status_code == r_sub.status_code, \
                f"play={r_play.status_code} submit={r_sub.status_code}"
    run(go())


# =====================================================================
# Backfill
# =====================================================================
def test_backfill_session2_columns_idempotent():
    async def go():
        from scripts.backfill_phase23_session2_columns import backfill
        db = _db()
        s1 = await backfill(db)
        s2 = await backfill(db)
        # Second run modifies nothing
        for k in s2:
            assert s2[k] == 0, f"{k} should be 0 on second run, got {s2}"
    run(go())


def test_backfill_session2_creator_type_inference():
    async def go():
        from scripts.backfill_phase23_session2_columns import backfill
        db = _db()
        # Seed 3 rows with no creator_type
        cids = []
        try:
            for spec in [
                {"is_platform_funded": True, "advertiser_id": None},
                {"is_platform_funded": False,
                  "advertiser_id": "adv_phase8a_tester"},
                {"is_platform_funded": False, "advertiser_id": None},
            ]:
                cid = _nid("cmp_p23s2_bf", 14)
                cids.append(cid)
                await db.game_campaigns.insert_one({
                    "_id": cid, "campaign_id": cid,
                    "template_id": "tpl_spin_wheel", "title": "bf test",
                    "status": "draft", "created_at": _now(),
                    **spec})
            await backfill(db)
            rows = {r["campaign_id"]: r async for r in
                          db.game_campaigns.find({"campaign_id": {"$in": cids}})}
            assert rows[cids[0]]["creator_type"] == "admin"
            assert rows[cids[1]]["creator_type"] == "advertiser"
            assert rows[cids[2]]["creator_type"] == "business"
            for cid in cids:
                assert rows[cid].get("placement_rules_json") == {}
        finally:
            for cid in cids:
                await db.game_campaigns.delete_one({"campaign_id": cid})
    run(go())
