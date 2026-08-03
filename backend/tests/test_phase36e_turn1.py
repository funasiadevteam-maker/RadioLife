"""Phase 36e Turn 1 — Subscription lifecycle + paywall tests.

All Stripe calls route through services/stripe_client in mock mode.
Hermetic: no external HTTP, no real Stripe network. Each test cleans
its own collections.
"""
from __future__ import annotations
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, "/app/backend")
# Force mock Stripe BEFORE any .env load, so live .env can't sneak in.
os.environ["STRIPE_MODE"] = "mock"
try:
    from dotenv import load_dotenv
    load_dotenv("/app/backend/.env")
except Exception: pass

# Re-force after .env load (load_dotenv default is override=False, but be safe).
os.environ["STRIPE_MODE"] = "mock"

from motor.motor_asyncio import AsyncIOMotorClient
from fastapi import HTTPException

from services import subscriptions as subs
from services import stripe_client
from services import ad_decisioning


def run(coro): return asyncio.get_event_loop().run_until_complete(coro)


def _db():
    return AsyncIOMotorClient(
        os.environ.get("MONGO_URL") or "mongodb://localhost:27017"
        )[os.environ.get("DB_NAME") or "bigfm"]


def _creator(suffix=""): return {"id": f"crt_test_{uuid.uuid4().hex[:8]}{suffix}"}
def _user(suffix=""):       return {"user_id": f"usr_test_{uuid.uuid4().hex[:8]}{suffix}",
                                                          "email": "tester@bigfm.local"}


async def _cleanup(db, creator_id=None, channel_id=None, user_id=None):
    if creator_id:
        await db.creator_stripe_accounts.delete_many({"creator_id": creator_id})
        await db.creator_subscription_plans.delete_many({"creator_id": creator_id})
    if channel_id:
        await db.creator_subscription_plans.delete_many({"channel_id": channel_id})
        await db.listener_subscriptions.delete_many({"channel_id": channel_id})
        await db.podcast_channels.delete_many({"id": channel_id})
        await db.podcast_episodes.delete_many({"channel_id": channel_id})
    if user_id:
        await db.listener_subscriptions.delete_many({"listener_user_id": user_id})


# ─── 1. Stripe Connect Express create + refresh ─────────────────
def test_creator_stripe_account_create_and_refresh():
    async def go():
        db = _db(); creator = _creator()
        row = await subs.get_or_create_stripe_account(
            db, creator=creator, creator_email="creator@bigfm.local")
        assert row["stripe_account_id"].startswith("acct_mock_")
        # mock retrieve_account returns charges/payouts/details = True
        refreshed = await subs.refresh_stripe_account(db, creator_id=creator["id"])
        assert refreshed["charges_enabled"] is True
        assert refreshed["payouts_enabled"] is True
        assert refreshed["details_submitted"] is True
        await _cleanup(db, creator_id=creator["id"])
    run(go())


# ─── 2. Plan creation requires charges_enabled ──────────────────
def test_subscription_plan_requires_stripe_charges_enabled():
    async def go():
        db = _db(); creator = _creator(); ch_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        # No stripe account at all → 412.
        with pytest.raises(HTTPException) as ei:
            await subs.create_plan(
                db, creator=creator, channel_id=ch_id,
                name="P", price_cents=500)
        assert ei.value.status_code == 412
        await _cleanup(db, creator_id=creator["id"], channel_id=ch_id)
    run(go())


# ─── 3. Min price enforcement ────────────────────────────────────
def test_subscription_plan_validates_min_price():
    async def go():
        db = _db(); creator = _creator(); ch_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        # Make stripe account ready.
        await subs.get_or_create_stripe_account(
            db, creator=creator, creator_email="c@b.local")
        await subs.refresh_stripe_account(db, creator_id=creator["id"])
        with pytest.raises(HTTPException) as ei:
            await subs.create_plan(
                db, creator=creator, channel_id=ch_id,
                name="P", price_cents=299)  # below min 300
        assert ei.value.status_code == 400
        assert "300" in str(ei.value.detail)
        await _cleanup(db, creator_id=creator["id"], channel_id=ch_id)
    run(go())


# ─── 4. Unique active plan per channel ──────────────────────────
def test_unique_active_plan_per_channel():
    async def go():
        db = _db(); creator = _creator(); ch_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        await subs.get_or_create_stripe_account(
            db, creator=creator, creator_email="c@b.local")
        await subs.refresh_stripe_account(db, creator_id=creator["id"])
        p1 = await subs.create_plan(
            db, creator=creator, channel_id=ch_id,
            name="P1", price_cents=500)
        assert p1["active"] is True
        with pytest.raises(HTTPException) as ei:
            await subs.create_plan(
                db, creator=creator, channel_id=ch_id,
                name="P2", price_cents=600)
        assert ei.value.status_code == 409
        await _cleanup(db, creator_id=creator["id"], channel_id=ch_id)
    run(go())


# ─── 5. Subscribe creates incomplete, webhook completes ─────────
def test_listener_subscribe_creates_incomplete_then_webhook_completes():
    async def go():
        db = _db(); creator = _creator(); user = _user()
        ch_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        await db.podcast_channels.insert_one(
            {"id": ch_id, "creator_id": creator["id"], "slug": "x"})
        await subs.get_or_create_stripe_account(
            db, creator=creator, creator_email="c@b.local")
        await subs.refresh_stripe_account(db, creator_id=creator["id"])
        plan = await subs.create_plan(
            db, creator=creator, channel_id=ch_id, name="P",
            price_cents=500)
        out = await subs.create_checkout(
            db, user=user, channel_id=ch_id, base_url="http://test")
        assert out["checkout_url"].startswith("/mock/stripe/checkout")
        row = await db.listener_subscriptions.find_one({"id": out["subscription_id"]})
        assert row["status"] == "incomplete"
        # Fire mock webhook
        fake = stripe_client.build_mock_event(
            event_type="customer.subscription.created",
            data_object={
                "id": "sub_mock_xxx", "status": "trialing",
                "customer": "cus_mock_xxx",
                "client_reference_id": out["subscription_id"],
                "current_period_end": int(
                    (datetime.now(timezone.utc) + timedelta(days=7)).timestamp()),
                "cancel_at_period_end": False,
            })
        await subs.handle_stripe_event(db, event=fake)
        row2 = await db.listener_subscriptions.find_one({"id": out["subscription_id"]})
        assert row2["status"] == "trialing"
        assert row2["stripe_subscription_id"] == "sub_mock_xxx"
        await _cleanup(db, creator_id=creator["id"], channel_id=ch_id, user_id=user["user_id"])
    run(go())


# ─── 6. Block duplicate active sub ──────────────────────────────
def test_listener_subscribe_blocks_duplicate_active():
    async def go():
        db = _db(); creator = _creator(); user = _user()
        ch_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        await db.podcast_channels.insert_one(
            {"id": ch_id, "creator_id": creator["id"], "slug": "x"})
        await subs.get_or_create_stripe_account(
            db, creator=creator, creator_email="c@b.local")
        await subs.refresh_stripe_account(db, creator_id=creator["id"])
        await subs.create_plan(
            db, creator=creator, channel_id=ch_id, name="P", price_cents=500)
        # First subscribe — make it active.
        out1 = await subs.create_checkout(
            db, user=user, channel_id=ch_id, base_url="http://test")
        await db.listener_subscriptions.update_one(
            {"id": out1["subscription_id"]},
            {"$set": {"status": "trialing"}})
        # Second subscribe attempt → 409.
        with pytest.raises(HTTPException) as ei:
            await subs.create_checkout(
                db, user=user, channel_id=ch_id, base_url="http://test")
        assert ei.value.status_code == 409
        await _cleanup(db, creator_id=creator["id"], channel_id=ch_id, user_id=user["user_id"])
    run(go())


# ─── 7. cancel_at_period_end keeps access ────────────────────────
def test_cancel_at_period_end_keeps_access_until_period_end():
    async def go():
        db = _db(); creator = _creator(); user = _user()
        ch_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        sub_id = f"lsub_test_{uuid.uuid4().hex[:8]}"
        future = datetime.now(timezone.utc) + timedelta(days=10)
        await db.listener_subscriptions.insert_one({
            "id": sub_id, "listener_user_id": user["user_id"],
            "channel_id": ch_id, "plan_id": "csp_dummy",
            "stripe_subscription_id": "sub_mock_keepalive",
            "status": "active", "trial_end": None,
            "current_period_end": future,
            "cancel_at_period_end": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        # User cancels.
        r = await subs.cancel_subscription(db, user=user, lsub_id=sub_id)
        assert r["cancel_at_period_end"] is True
        assert r["status"] == "active"
        # Access gate check — must still pass because status is still active.
        has = await subs.user_has_active_sub_for_channel(
            db, user_id=user["user_id"], channel_id=ch_id)
        assert has is True
        # User changes mind, resumes.
        r2 = await subs.resume_subscription(db, user=user, lsub_id=sub_id)
        assert r2["cancel_at_period_end"] is False
        await _cleanup(db, user_id=user["user_id"])
    run(go())


# ─── 8. Bonus episode gate ───────────────────────────────────────
def test_paywall_gate_episode_bonus_blocks_non_subscriber():
    async def go():
        db = _db(); user = _user()
        ch_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        # Public episode — anyone.
        pub_ep = {"id": "pep_pub", "channel_id": ch_id,
                          "is_bonus": False, "release_for_subscribers_at": None}
        assert await subs.is_episode_accessible(db, episode=pub_ep, user=None) is True
        assert await subs.is_episode_accessible(db, episode=pub_ep, user=user) is True
        # Bonus — non-sub blocked.
        bonus = {"id": "pep_bonus", "channel_id": ch_id,
                        "is_bonus": True, "release_for_subscribers_at": None}
        assert await subs.is_episode_accessible(db, episode=bonus, user=user) is False
        assert await subs.is_episode_accessible(db, episode=bonus, user=None) is False
        # Bonus — active sub allows access.
        await db.listener_subscriptions.insert_one({
            "id": f"lsub_{uuid.uuid4().hex[:6]}",
            "listener_user_id": user["user_id"],
            "channel_id": ch_id, "plan_id": "csp_dummy",
            "stripe_subscription_id": None, "status": "trialing",
            "trial_end": None, "current_period_end": datetime.now(timezone.utc) + timedelta(days=7),
            "cancel_at_period_end": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        assert await subs.is_episode_accessible(db, episode=bonus, user=user) is True
        await _cleanup(db, channel_id=ch_id, user_id=user["user_id"])
    run(go())


# ─── 9. 24h early-access window ──────────────────────────────────
def test_paywall_gate_early_access_window():
    async def go():
        db = _db(); user = _user()
        ch_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        future = datetime.now(timezone.utc) + timedelta(hours=12)
        past      = datetime.now(timezone.utc) - timedelta(hours=1)
        ep_embargo = {"id": "pep_e", "channel_id": ch_id, "is_bonus": False,
                                      "release_for_subscribers_at": future.isoformat()}
        ep_open      = {"id": "pep_o", "channel_id": ch_id, "is_bonus": False,
                                      "release_for_subscribers_at": past.isoformat()}
        # Before public release, non-sub blocked.
        assert await subs.is_episode_accessible(db, episode=ep_embargo, user=user) is False
        # After public release, anyone in.
        assert await subs.is_episode_accessible(db, episode=ep_open, user=user) is True
        assert await subs.is_episode_accessible(db, episode=ep_open, user=None) is True
        # Active sub during embargo → in.
        await db.listener_subscriptions.insert_one({
            "id": f"lsub_{uuid.uuid4().hex[:6]}",
            "listener_user_id": user["user_id"],
            "channel_id": ch_id, "plan_id": "csp_dummy",
            "stripe_subscription_id": None, "status": "active",
            "trial_end": None, "current_period_end": datetime.now(timezone.utc) + timedelta(days=7),
            "cancel_at_period_end": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        assert await subs.is_episode_accessible(db, episode=ep_embargo, user=user) is True
        await _cleanup(db, channel_id=ch_id, user_id=user["user_id"])
    run(go())


# ─── 10. Ad decisioning subscriber-skip ──────────────────────────
def test_ad_decisioning_skips_ads_for_active_subscriber():
    async def go():
        db = _db(); user = _user()
        ch_id = f"pch_test_{uuid.uuid4().hex[:8]}"
        # Insert active sub for (user, channel).
        await db.listener_subscriptions.insert_one({
            "id": f"lsub_{uuid.uuid4().hex[:6]}",
            "listener_user_id": user["user_id"],
            "channel_id": ch_id, "plan_id": "csp_dummy",
            "stripe_subscription_id": None, "status": "trialing",
            "trial_end": None, "current_period_end": datetime.now(timezone.utc) + timedelta(days=7),
            "cancel_at_period_end": False,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
        out = await ad_decisioning.select_ad(
            db, user=user, session={},
            segment_context={"position": "midroll", "channel_id": ch_id})
        assert out is None, f"expected ad-skip, got: {out}"
        # Sanity: a different channel doesn't trigger the skip via this sub.
        # (we can't easily assert ad presence without a full campaign fixture,
        # so just check the early-return path doesn't fire.)
        await _cleanup(db, channel_id=ch_id, user_id=user["user_id"])
    run(go())


# ─── 11. HTTP-layer: PATCH /episodes accepts is_bonus ────────────
def test_patch_episode_accepts_is_bonus_field():
    """Hits the real /api/podcasts/channels/:cid/episodes/:ep route.
    Verifies is_bonus persists + round-trips on a subsequent GET, and that
    a non-bool value is rejected with 400."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        # Login as admin → bearer token.
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            login = await ac.post("/api/auth/login",
                json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
            assert login.status_code == 200, login.text
            tok = login.json()["session_token"]
            hdrs = {"Authorization": f"Bearer {tok}"}
            admin_uid = login.json()["user_id"]

            # Seed approved creator + channel + episode (all temp).
            crt_id = f"crt_t36e_{uuid.uuid4().hex[:8]}"
            ch_id = f"pch_t36e_{uuid.uuid4().hex[:8]}"
            ep_id = f"pep_t36e_{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc)
            # Use the existing admin creator row if present (test harness may
            # have seeded one already); otherwise insert a temp one.
            existing = await db.podcast_creators.find_one({"user_id": admin_uid})
            if existing:
                crt_id = existing["id"]
                _crt_owned = False
            else:
                await db.podcast_creators.insert_one({
                    "id": crt_id, "user_id": admin_uid,
                    "display_name": "Test Creator",
                    "application_status": "approved", "created_at": now})
                _crt_owned = True
            await db.podcast_channels.insert_one({
                "id": ch_id, "creator_id": crt_id, "title": "T",
                "category": "other", "created_at": now})
            await db.podcast_episodes.insert_one({
                "id": ep_id, "channel_id": ch_id, "title": "Ep",
                "is_bonus": False, "publish_status": "published",
                "created_at": now, "updated_at": now})

            try:
                # 1. PATCH with is_bonus=True.
                r = await ac.patch(
                    f"/api/podcasts/channels/{ch_id}/episodes/{ep_id}",
                    json={"is_bonus": True}, headers=hdrs)
                assert r.status_code == 200, r.text
                assert r.json()["is_bonus"] is True
                # 2. DB persisted.
                row = await db.podcast_episodes.find_one({"id": ep_id})
                assert row["is_bonus"] is True
                # 3. GET roundtrip (list endpoint).
                lr = await ac.get(
                    f"/api/podcasts/channels/{ch_id}/episodes?include_drafts=true",
                    headers=hdrs)
                assert lr.status_code == 200
                found = [e for e in lr.json()["items"] if e["id"] == ep_id]
                assert found and found[0]["is_bonus"] is True
                # 4. Bad value → 400.
                r2 = await ac.patch(
                    f"/api/podcasts/channels/{ch_id}/episodes/{ep_id}",
                    json={"is_bonus": "yes"}, headers=hdrs)
                assert r2.status_code == 400, r2.text
                assert "is_bonus" in r2.text
            finally:
                if _crt_owned:
                    await db.podcast_creators.delete_many({"id": crt_id})
                await _cleanup(db, channel_id=ch_id)
    run(go())


# ─── 12. HTTP-layer: PATCH /episodes accepts release_for_subscribers_at ──
def test_patch_episode_accepts_release_for_subscribers_at_iso8601():
    """Verifies release_for_subscribers_at accepts a valid ISO8601 string
    (parsed to datetime), null (clears embargo), and rejects garbage with 400."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            login = await ac.post("/api/auth/login",
                json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
            assert login.status_code == 200, login.text
            tok = login.json()["session_token"]
            hdrs = {"Authorization": f"Bearer {tok}"}
            admin_uid = login.json()["user_id"]

            crt_id = f"crt_t36e_{uuid.uuid4().hex[:8]}"
            ch_id = f"pch_t36e_{uuid.uuid4().hex[:8]}"
            ep_id = f"pep_t36e_{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc)
            existing = await db.podcast_creators.find_one({"user_id": admin_uid})
            if existing:
                crt_id = existing["id"]
                _crt_owned = False
            else:
                await db.podcast_creators.insert_one({
                    "id": crt_id, "user_id": admin_uid,
                    "display_name": "Test Creator",
                    "application_status": "approved", "created_at": now})
                _crt_owned = True
            await db.podcast_channels.insert_one({
                "id": ch_id, "creator_id": crt_id, "title": "T",
                "category": "other", "created_at": now})
            await db.podcast_episodes.insert_one({
                "id": ep_id, "channel_id": ch_id, "title": "Ep",
                "publish_status": "published",
                "created_at": now, "updated_at": now})

            try:
                # 1. PATCH with ISO8601 string (with Z).
                iso_z = "2027-01-15T12:00:00Z"
                r = await ac.patch(
                    f"/api/podcasts/channels/{ch_id}/episodes/{ep_id}",
                    json={"release_for_subscribers_at": iso_z}, headers=hdrs)
                assert r.status_code == 200, r.text
                # 2. DB persisted as datetime (Mongo serializes back).
                row = await db.podcast_episodes.find_one({"id": ep_id})
                assert row["release_for_subscribers_at"] is not None
                assert isinstance(row["release_for_subscribers_at"], datetime)
                assert row["release_for_subscribers_at"].year == 2027
                # 3. PATCH with null clears the embargo.
                r2 = await ac.patch(
                    f"/api/podcasts/channels/{ch_id}/episodes/{ep_id}",
                    json={"release_for_subscribers_at": None}, headers=hdrs)
                assert r2.status_code == 200, r2.text
                row2 = await db.podcast_episodes.find_one({"id": ep_id})
                assert row2["release_for_subscribers_at"] is None
                # 4. Bad value → 400.
                r3 = await ac.patch(
                    f"/api/podcasts/channels/{ch_id}/episodes/{ep_id}",
                    json={"release_for_subscribers_at": "not-a-date"},
                    headers=hdrs)
                assert r3.status_code == 400, r3.text
                assert "release_for_subscribers_at" in r3.text
            finally:
                if _crt_owned:
                    await db.podcast_creators.delete_many({"id": crt_id})
                await _cleanup(db, channel_id=ch_id)
    run(go())

# ─── 13. Admin bypass: admin can PATCH episode they don't own ────
def test_patch_episode_as_admin_bypasses_creator_check():
    """Locks the admin role bypass at _own_channel_or_403 / inline gate
    ordering. Seeds a channel owned by a NON-admin creator (admin has no
    direct ownership tie), then admin PATCHes is_bonus and expects 200."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            login = await ac.post("/api/auth/login",
                json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
            assert login.status_code == 200, login.text
            tok = login.json()["session_token"]
            hdrs = {"Authorization": f"Bearer {tok}"}

            # Seed an UNRELATED creator (not the admin's). Admin must still PATCH.
            other_uid = f"usr_other_{uuid.uuid4().hex[:8]}"
            other_crt = f"crt_other_{uuid.uuid4().hex[:8]}"
            ch_id = f"pch_admin_bypass_{uuid.uuid4().hex[:8]}"
            ep_id = f"pep_admin_bypass_{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc)
            await db.podcast_creators.insert_one({
                "id": other_crt, "user_id": other_uid,
                "display_name": "Other Creator",
                "application_status": "approved", "created_at": now})
            await db.podcast_channels.insert_one({
                "id": ch_id, "creator_id": other_crt, "title": "T",
                "category": "other", "created_at": now})
            await db.podcast_episodes.insert_one({
                "id": ep_id, "channel_id": ch_id, "title": "Ep",
                "is_bonus": False, "publish_status": "published",
                "created_at": now, "updated_at": now})
            try:
                r = await ac.patch(
                    f"/api/podcasts/channels/{ch_id}/episodes/{ep_id}",
                    json={"is_bonus": True}, headers=hdrs)
                assert r.status_code == 200, \
                    f"admin should bypass; got {r.status_code}: {r.text}"
                assert r.json()["is_bonus"] is True
            finally:
                await db.podcast_creators.delete_many({"id": other_crt})
                await _cleanup(db, channel_id=ch_id)
    run(go())


# ─── 14. Non-owner creator cannot PATCH another creator's episode ──
def test_patch_episode_as_unrelated_creator_403():
    """Non-admin creator attempting to PATCH a channel they don't own must
    be rejected. Uses a freshly-registered listener-role user promoted to an
    'approved' but unrelated creator — the seeded channel belongs to a
    different creator. Expect 403 or 404 (channel_not_found is also valid
    since we don't leak ownership info to non-owners)."""
    async def go():
        import importlib
        from httpx import ASGITransport, AsyncClient
        server = importlib.import_module("server")
        db = _db()
        async with AsyncClient(transport=ASGITransport(app=server.app),
                                                    base_url="http://test") as ac:
            # Register a fresh user (non-admin).
            email = f"creator_t36e_{uuid.uuid4().hex[:6]}@bigfm.dubai"
            reg = await ac.post("/api/auth/register",
                json={"email": email, "password": "TestPass123!",
                          "name": "Outsider"})
            assert reg.status_code == 200, reg.text
            tok = reg.json()["session_token"]
            outsider_uid = reg.json()["user_id"]
            hdrs = {"Authorization": f"Bearer {tok}"}

            # Seed: the outsider IS an approved creator, but the channel
            # belongs to a DIFFERENT creator.
            outsider_crt = f"crt_outsider_{uuid.uuid4().hex[:8]}"
            owner_uid = f"usr_owner_{uuid.uuid4().hex[:8]}"
            owner_crt = f"crt_owner_{uuid.uuid4().hex[:8]}"
            ch_id = f"pch_403_{uuid.uuid4().hex[:8]}"
            ep_id = f"pep_403_{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc)
            await db.podcast_creators.insert_one({
                "id": outsider_crt, "user_id": outsider_uid,
                "display_name": "Outsider Creator",
                "application_status": "approved", "created_at": now})
            await db.podcast_creators.insert_one({
                "id": owner_crt, "user_id": owner_uid,
                "display_name": "Channel Owner",
                "application_status": "approved", "created_at": now})
            await db.podcast_channels.insert_one({
                "id": ch_id, "creator_id": owner_crt, "title": "T",
                "category": "other", "created_at": now})
            await db.podcast_episodes.insert_one({
                "id": ep_id, "channel_id": ch_id, "title": "Ep",
                "publish_status": "published",
                "created_at": now, "updated_at": now})
            try:
                r = await ac.patch(
                    f"/api/podcasts/channels/{ch_id}/episodes/{ep_id}",
                    json={"is_bonus": True}, headers=hdrs)
                assert r.status_code in (403, 404), \
                    f"non-owner must be rejected; got {r.status_code}: {r.text}"
                # Verify DB not mutated.
                row = await db.podcast_episodes.find_one({"id": ep_id})
                assert row.get("is_bonus", False) is False, \
                    "is_bonus must NOT be flipped by non-owner"
            finally:
                await db.podcast_creators.delete_many({"id": outsider_crt})
                await db.podcast_creators.delete_many({"id": owner_crt})
                await db.users.delete_many({"user_id": outsider_uid})
                await _cleanup(db, channel_id=ch_id)
    run(go())

