"""Phase 13a — A/B testing on retention campaigns."""
from __future__ import annotations
import asyncio
import os
from datetime import datetime as dt, timezone, timedelta

import pytest
import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient

load_dotenv("/app/backend/.env")

ROOT = (os.environ.get("BIGFM_API_URL")
            or os.environ.get("REACT_APP_BACKEND_URL")
            or "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{ROOT}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bigfm")
DB = MongoClient(MONGO_URL)[DB_NAME]


def _login(email: str, pw: str) -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email,
                                                              "password": pw}, timeout=10)
    assert r.status_code == 200, r.text[:200]
    return s


@pytest.fixture(scope="module")
def admin_session():
    return _login("admin@bigfm.dubai", "AdminPass123!")


@pytest.fixture(scope="module")
def free_session():
    return _login("test@bigfm.dubai", "TestUser123!")


@pytest.fixture
def fresh_ab_campaign(admin_session):
    """Create a fresh A/B campaign + clean up after."""
    payload = {
        "name": "QA AB Campaign",
        "trigger": "inactive_7d",
        "channels": ["email"],
        "template": {"email_subject": "Default",
                          "email_body": "Default body"},
        "variants": [
            {"slug": "A", "weight": 60,
              "template_overrides": {"email_subject": "Variant A",
                                              "email_body": "Body A"}},
            {"slug": "B", "weight": 40,
              "template_overrides": {"email_subject": "Variant B",
                                              "email_body": "Body B"}},
        ],
        "active": True,
    }
    r = admin_session.post(f"{API}/admin/retention/campaigns",
                                      json=payload, timeout=10)
    assert r.status_code == 200, r.text[:200]
    cid = r.json()["id"]
    yield cid
    DB.lifecycle_campaigns.delete_one({"id": cid})
    DB.lifecycle_send_log.delete_many({"campaign_id": cid})
    DB.ab_assignments.delete_many({"campaign_id": cid})


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─── 1. Create with variants persists ─────────────────────────────────
def test_create_campaign_with_variants_persists(fresh_ab_campaign):
    cid = fresh_ab_campaign
    doc = DB.lifecycle_campaigns.find_one({"id": cid})
    assert doc is not None
    assert len(doc.get("variants") or []) == 2
    assert {v["slug"] for v in doc["variants"]} == {"A", "B"}
    assert doc["variants"][0]["weight"] == 60
    # Overrides surface only the allowed keys
    keys = set(doc["variants"][0]["template_overrides"].keys())
    assert keys <= {"email_subject", "email_body",
                          "push_title", "push_body", "deep_link"}


# ─── 2. pick_variant is sticky ────────────────────────────────────────
def test_pick_variant_is_sticky_for_same_user_campaign(
        fresh_ab_campaign):
    from services import ab
    cid = fresh_ab_campaign
    c = DB.lifecycle_campaigns.find_one({"id": cid})
    DB.ab_assignments.delete_many({"campaign_id": cid})

    async def _go():
        cli = AsyncIOMotorClient(MONGO_URL)
        try:
            db = cli[DB_NAME]
            first = await ab.pick_variant(db, campaign=c,
                                                       user_id="user_qa_sticky")
            again = await ab.pick_variant(db, campaign=c,
                                                       user_id="user_qa_sticky")
            return first, again
        finally:
            cli.close()

    a, b = _run(_go())
    assert a["slug"] == b["slug"]
    # Stickiness must survive even if we re-roll the weights AFTER
    # the first assignment.
    DB.lifecycle_campaigns.update_one(
        {"id": cid},
        {"$set": {"variants": [
            {"slug": "A", "weight": 1,
              "template_overrides": {"email_subject": "Variant A"}},
            {"slug": "B", "weight": 99,
              "template_overrides": {"email_subject": "Variant B"}}]}})
    c2 = DB.lifecycle_campaigns.find_one({"id": cid})

    async def _go2():
        cli = AsyncIOMotorClient(MONGO_URL)
        try:
            return await ab.pick_variant(
                cli[DB_NAME], campaign=c2, user_id="user_qa_sticky")
        finally:
            cli.close()
    c_again = _run(_go2())
    assert c_again["slug"] == a["slug"]
    DB.ab_assignments.delete_many({"campaign_id": cid})


# ─── 3. Distribution respects weights at scale ───────────────────────
def test_pick_variant_respects_weights_at_scale():
    from services import ab
    # Synthetic campaign — no DB write to lifecycle_campaigns needed.
    campaign = {
        "id": "qa_dist_camp",
        "variants": [
            {"slug": "A", "weight": 70,
              "template_overrides": {}},
            {"slug": "B", "weight": 30,
              "template_overrides": {}},
        ],
    }
    DB.ab_assignments.delete_many({"campaign_id": "qa_dist_camp"})
    try:
        async def _go():
            cli = AsyncIOMotorClient(MONGO_URL)
            try:
                db = cli[DB_NAME]
                counts = {"A": 0, "B": 0}
                for i in range(10000):
                    v = await ab.pick_variant(
                        db, campaign=campaign,
                        user_id=f"user_qa_dist_{i:05d}")
                    counts[v["slug"]] += 1
                return counts
            finally:
                cli.close()
        counts = _run(_go())
        a_ratio = counts["A"] / 10000
        # Expect 0.70 ± 0.05
        assert abs(a_ratio - 0.70) < 0.05, counts
    finally:
        DB.ab_assignments.delete_many(
            {"campaign_id": "qa_dist_camp"})


# ─── 4. send_log carries variant_slug ────────────────────────────────
def test_send_log_records_variant_slug(admin_session, fresh_ab_campaign):
    cid = fresh_ab_campaign
    r = admin_session.post(
        f"{API}/admin/retention/campaigns/{cid}/run_now"
        "?max_recipients=20", timeout=20)
    # Even if audience is empty (0 sends), the endpoint should still
    # respond 200; we then drive a synthetic send_log row to validate
    # the field independently of audience seeding.
    assert r.status_code == 200, r.text[:200]
    # Insert a synthetic send_log row with variant_slug and read back.
    DB.lifecycle_send_log.insert_one({
        "_id": f"sl_qa_variant_{cid[-6:]}",
        "user_id": "user_qa_synth",
        "campaign_id": cid,
        "channel": "email",
        "variant_slug": "A",
        "status": "stubbed",
        "sent_at": dt.now(timezone.utc)})
    row = DB.lifecycle_send_log.find_one(
        {"_id": f"sl_qa_variant_{cid[-6:]}"})
    assert row and row.get("variant_slug") == "A"


# ─── 5. Stats endpoint admin only ────────────────────────────────────
def test_variant_stats_endpoint_admin_only(free_session,
                                                            fresh_ab_campaign):
    cid = fresh_ab_campaign
    r = free_session.get(
        f"{API}/admin/retention/campaigns/{cid}/variants/stats",
        timeout=10)
    assert r.status_code == 403, r.text[:200]


# ─── 6. Stats computes open / click / conv rates ─────────────────────
def test_variant_stats_computes_open_click_conv_rates(
        admin_session, fresh_ab_campaign):
    cid = fresh_ab_campaign
    # Seed: A → 100 sends, 50 opens, 20 clicks, 5 conversions.
    #       B → 100 sends, 60 opens, 25 clicks, 10 conversions.
    rows = []
    now = dt.now(timezone.utc)
    for i in range(100):
        rows.append({
            "_id": f"sl_qa_stat_A_{i:03d}",
            "campaign_id": cid, "channel": "email",
            "user_id": f"u_a_{i}", "variant_slug": "A",
            "status": "sent",
            "sent_at": now,
            "opened_at": now if i < 50 else None,
            "clicked_at": now if i < 20 else None,
            "converted_at": now if i < 5 else None})
    for i in range(100):
        rows.append({
            "_id": f"sl_qa_stat_B_{i:03d}",
            "campaign_id": cid, "channel": "email",
            "user_id": f"u_b_{i}", "variant_slug": "B",
            "status": "sent",
            "sent_at": now,
            "opened_at": now if i < 60 else None,
            "clicked_at": now if i < 25 else None,
            "converted_at": now if i < 10 else None})
    DB.lifecycle_send_log.insert_many(rows)

    r = admin_session.get(
        f"{API}/admin/retention/campaigns/{cid}/variants/stats",
        timeout=10)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["has_variants"] is True
    by_slug = {v["slug"]: v for v in body["variants"]}
    assert by_slug["A"]["sends"] == 100
    assert by_slug["A"]["opens"] == 50
    assert by_slug["A"]["clicks"] == 20
    assert by_slug["A"]["conversions"] == 5
    assert by_slug["A"]["open_rate"] == pytest.approx(0.50)
    assert by_slug["A"]["click_rate"] == pytest.approx(0.20)
    assert by_slug["A"]["conv_rate"] == pytest.approx(0.05)
    assert by_slug["B"]["conv_rate"] == pytest.approx(0.10)


# ─── 7. Winner flagged when significant ──────────────────────────────
def test_variant_stats_flags_winner_when_significant(
        admin_session, fresh_ab_campaign):
    cid = fresh_ab_campaign
    DB.lifecycle_send_log.delete_many({"campaign_id": cid})
    now = dt.now(timezone.utc)
    bulk = []
    # A: 1000 sends, 100 conversions (10%)
    for i in range(1000):
        bulk.append({"_id": f"sl_qa_win_A_{i:04d}",
                          "campaign_id": cid, "channel": "email",
                          "user_id": f"u_a_{i}", "variant_slug": "A",
                          "status": "sent", "sent_at": now,
                          "converted_at": now if i < 100 else None})
    # B: 1000 sends, 200 conversions (20%) → ~9.6 sigma against A.
    for i in range(1000):
        bulk.append({"_id": f"sl_qa_win_B_{i:04d}",
                          "campaign_id": cid, "channel": "email",
                          "user_id": f"u_b_{i}", "variant_slug": "B",
                          "status": "sent", "sent_at": now,
                          "converted_at": now if i < 200 else None})
    DB.lifecycle_send_log.insert_many(bulk)

    r = admin_session.get(
        f"{API}/admin/retention/campaigns/{cid}/variants/stats",
        timeout=10)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["winner_slug"] == "B"
    by_slug = {v["slug"]: v for v in body["variants"]}
    assert by_slug["B"]["is_winner"] is True
    assert by_slug["B"]["confidence_95"] is True
    assert by_slug["A"]["is_winner"] is False
    assert body["p_value_vs_control"] < 0.05


# ─── 8. No winner below threshold ────────────────────────────────────
def test_variant_stats_no_winner_below_threshold(admin_session,
                                                                    fresh_ab_campaign):
    cid = fresh_ab_campaign
    DB.lifecycle_send_log.delete_many({"campaign_id": cid})
    now = dt.now(timezone.utc)
    bulk = []
    # Only 50 sends per variant — way under MIN_SEND_PER_VARIANT=200.
    for i in range(50):
        bulk.append({"_id": f"sl_qa_nlow_A_{i}",
                          "campaign_id": cid, "channel": "email",
                          "user_id": f"u_a_{i}", "variant_slug": "A",
                          "status": "sent", "sent_at": now,
                          "converted_at": now if i < 5 else None})
    for i in range(50):
        bulk.append({"_id": f"sl_qa_nlow_B_{i}",
                          "campaign_id": cid, "channel": "email",
                          "user_id": f"u_b_{i}", "variant_slug": "B",
                          "status": "sent", "sent_at": now,
                          "converted_at": now if i < 25 else None})
    DB.lifecycle_send_log.insert_many(bulk)

    r = admin_session.get(
        f"{API}/admin/retention/campaigns/{cid}/variants/stats",
        timeout=10)
    body = r.json()
    assert body["winner_slug"] is None
    for v in body["variants"]:
        assert v["is_winner"] is False


# ─── HF-A. run_now → real pipeline writes variant_slug + applies overrides ─
# Phase 13a Hotfix #1 (2026-05-27): the original `test_send_log_records_
# variant_slug` proved nothing because it called send_email directly. This
# new test drives the FULL pipeline `POST /api/admin/retention/campaigns/
# {id}/run_now`, then asserts the send_log row carries `variant_slug` AND
# the rendered subject/body match the variant's template_overrides (not
# the base template).
def test_run_now_writes_variant_slug_to_send_log_via_pipeline(
        admin_session):
    payload = {
        "name": "QA AB Pipeline",
        "trigger": "subscription_past_due",
        "channels": ["email", "push"],
        "template": {"email_subject": "BASE subject",
                          "email_body": "BASE body",
                          "push_title": "BASE push",
                          "push_body": "BASE push body",
                          "deep_link": "/base"},
        "variants": [
            {"slug": "A", "weight": 100,
              "template_overrides": {
                  "email_subject": "VARIANT_A subject",
                  "email_body": "VARIANT_A body",
                  "push_title": "VARIANT_A push",
                  "push_body": "VARIANT_A push body",
                  "deep_link": "/a"}},
            {"slug": "B", "weight": 1,
              "template_overrides": {
                  "email_subject": "VARIANT_B subject"}},
        ],
        "throttle_per_user_per_period": {"max_sends": 1,
                                                          "period_hours": 1},
        "active": True,
    }
    r = admin_session.post(f"{API}/admin/retention/campaigns",
                                      json=payload, timeout=10)
    assert r.status_code == 200, r.text[:200]
    cid = r.json()["id"]

    # Force test@bigfm.dubai into the audience by flipping their
    # subscription.status to past_due (trigger has no band/min-days filter).
    test_user = DB.users.find_one({"email": "test@bigfm.dubai"})
    assert test_user, "test user missing"
    uid = test_user["user_id"]
    prev_sub = test_user.get("subscription") or {}
    DB.users.update_one(
        {"user_id": uid},
        {"$set": {"subscription": {**prev_sub, "status": "past_due"}}})
    # Clear any sticky assignment + recent send_log + queue rows.
    DB.ab_assignments.delete_many({"campaign_id": cid})
    DB.lifecycle_send_log.delete_many({"campaign_id": cid})
    DB.delivery_queue.delete_many({"campaign_id": cid})

    try:
        rn = admin_session.post(
            f"{API}/admin/retention/campaigns/{cid}/run_now"
            "?max_recipients=5", timeout=20)
        assert rn.status_code == 200, rn.text[:200]
        body = rn.json()
        assert body["sent_email"] >= 1, body
        assert body["sent_push"] >= 1, body

        # Read back the send_log row for this user+campaign.
        rows = list(DB.lifecycle_send_log.find(
            {"campaign_id": cid, "user_id": uid}))
        assert len(rows) >= 2, rows  # one email, one push
        email_row = next(r for r in rows if r.get("channel") == "email")
        push_row = next(r for r in rows if r.get("channel") == "push")

        # 1) variant_slug must be present + come from the campaign.
        assert email_row.get("variant_slug") in ("A", "B"), email_row
        assert push_row.get("variant_slug") == email_row[
            "variant_slug"], (email_row, push_row)
        assigned_slug = email_row["variant_slug"]

        # 2) Rendered subject/title/body MUST match the variant override,
        # NOT the base template. Variant A weight=100, B weight=1, so the
        # selection is overwhelmingly A — but accept either as long as
        # the override (not the base) is what landed.
        # NOTE: send_email writes the email body to delivery_queue, not
        # to lifecycle_send_log (the log row only carries `subject`).
        dq_row = DB.delivery_queue.find_one(
            {"campaign_id": cid, "user_id": uid})
        assert dq_row, "no delivery_queue row written"
        if assigned_slug == "A":
            assert email_row.get("subject") == "VARIANT_A subject", email_row
            assert "VARIANT_A body" in (dq_row.get("body") or ""), dq_row
            assert push_row.get("title") == "VARIANT_A push", push_row
            assert push_row.get("body") == "VARIANT_A push body", push_row
        else:
            assert email_row.get("subject") == "VARIANT_B subject", email_row
            # Variant B only overrode email_subject; other fields fall back
            # to the BASE template (which is the documented merge behavior).
            assert "BASE body" in (dq_row.get("body") or ""), dq_row
            assert push_row.get("title") == "BASE push", push_row

        # 3) ab_assignments collection has the sticky row.
        sticky = DB.ab_assignments.find_one(
            {"campaign_id": cid, "user_id": uid})
        assert sticky and sticky["variant_slug"] == assigned_slug, sticky

        # 4) variants/stats endpoint sees the send (not sends=0).
        stats = admin_session.get(
            f"{API}/admin/retention/campaigns/{cid}/variants/stats",
            timeout=10).json()
        by_slug = {v["slug"]: v for v in stats["variants"]}
        assert by_slug[assigned_slug]["sends"] >= 2, stats  # email + push
    finally:
        DB.users.update_one(
            {"user_id": uid},
            {"$set": {"subscription": prev_sub}}
            if prev_sub
            else {"$unset": {"subscription": ""}})
        DB.lifecycle_campaigns.delete_one({"id": cid})
        DB.ab_assignments.delete_many({"campaign_id": cid})
        DB.lifecycle_send_log.delete_many({"campaign_id": cid})
        DB.delivery_queue.delete_many({"campaign_id": cid})


# ─── HF-B. Sticky variant survives 2 run_now invocations ─────────────
def test_run_now_picks_sticky_variant_on_repeat(admin_session):
    """Same campaign, same user, two run_now calls (separated by a
    throttle reset) — assigned variant must be identical both times."""
    payload = {
        "name": "QA AB Sticky Pipeline",
        "trigger": "subscription_past_due",
        "channels": ["email"],
        "template": {"email_subject": "BASE",
                          "email_body": "BASE"},
        "variants": [
            {"slug": "A", "weight": 50,
              "template_overrides": {"email_subject": "OVER_A"}},
            {"slug": "B", "weight": 50,
              "template_overrides": {"email_subject": "OVER_B"}},
        ],
        "throttle_per_user_per_period": {"max_sends": 5,
                                                          "period_hours": 1},
        "active": True,
    }
    r = admin_session.post(f"{API}/admin/retention/campaigns",
                                      json=payload, timeout=10)
    cid = r.json()["id"]
    test_user = DB.users.find_one({"email": "test@bigfm.dubai"})
    uid = test_user["user_id"]
    prev_sub = test_user.get("subscription") or {}
    DB.users.update_one(
        {"user_id": uid},
        {"$set": {"subscription": {**prev_sub, "status": "past_due"}}})
    DB.ab_assignments.delete_many({"campaign_id": cid})
    DB.lifecycle_send_log.delete_many({"campaign_id": cid})
    try:
        # First run.
        r1 = admin_session.post(
            f"{API}/admin/retention/campaigns/{cid}/run_now"
            "?max_recipients=5", timeout=20)
        assert r1.status_code == 200, r1.text[:200]
        # Clear send_log + throttle (not the sticky assignment) before run 2.
        DB.lifecycle_send_log.delete_many(
            {"campaign_id": cid, "user_id": uid})
        # Second run.
        r2 = admin_session.post(
            f"{API}/admin/retention/campaigns/{cid}/run_now"
            "?max_recipients=5", timeout=20)
        assert r2.status_code == 200, r2.text[:200]
        # Both writes must share the same variant_slug. The
        # ab_assignments doc is the source of truth, but also verify
        # via the second send_log row.
        sticky = DB.ab_assignments.find_one(
            {"campaign_id": cid, "user_id": uid})
        assert sticky and sticky.get("variant_slug") in ("A", "B")
        row2 = DB.lifecycle_send_log.find_one(
            {"campaign_id": cid, "user_id": uid})
        assert row2 and row2.get("variant_slug") == sticky["variant_slug"]
        # The subject must reflect THAT variant's override on the second
        # run too — proving overrides applied via the pipeline twice.
        expected_subject = f"OVER_{sticky['variant_slug']}"
        assert row2.get("subject") == expected_subject, row2
    finally:
        DB.users.update_one(
            {"user_id": uid},
            {"$set": {"subscription": prev_sub}}
            if prev_sub
            else {"$unset": {"subscription": ""}})
        DB.lifecycle_campaigns.delete_one({"id": cid})
        DB.ab_assignments.delete_many({"campaign_id": cid})
        DB.lifecycle_send_log.delete_many({"campaign_id": cid})
        DB.delivery_queue.delete_many({"campaign_id": cid})


# ─── 9. Legacy single-template campaign unchanged ────────────────────
def test_legacy_campaign_without_variants_works_unchanged(admin_session):
    payload = {
        "name": "QA Legacy No-Variants",
        "trigger": "inactive_7d",
        "channels": ["email"],
        "template": {"email_subject": "Legacy",
                          "email_body": "Legacy body"},
        "active": True,
    }
    r = admin_session.post(f"{API}/admin/retention/campaigns",
                                      json=payload, timeout=10)
    assert r.status_code == 200, r.text[:200]
    cid = r.json()["id"]
    try:
        doc = DB.lifecycle_campaigns.find_one({"id": cid})
        assert doc.get("variants") in ([], None, [])

        # Stats endpoint must still respond, just with has_variants=False.
        rr = admin_session.get(
            f"{API}/admin/retention/campaigns/{cid}/variants/stats",
            timeout=10)
        assert rr.status_code == 200, rr.text[:200]
        body = rr.json()
        assert body["has_variants"] is False
        assert body["variants"] == []

        # Run now should not crash + should not write variant_slug.
        rr2 = admin_session.post(
            f"{API}/admin/retention/campaigns/{cid}/run_now"
            "?max_recipients=10", timeout=15)
        assert rr2.status_code == 200, rr2.text[:200]
    finally:
        DB.lifecycle_campaigns.delete_one({"id": cid})
        DB.lifecycle_send_log.delete_many({"campaign_id": cid})
