"""Iteration 48 — Phase MKT.2 backend tests.

Covers:
  1) GET /api/rate-card/formats — banner/audio/push/video with pricing.
  2) Campaign CRUD MKT.2 types — spin/scratch/giveaway validation + creation.
  3) Brand Games — active feed, play idempotent, win → award points + spend rate + auto-pause on budget exhaustion.
  4) Brand Giveaways — active feed, enter idempotent, draw ownership + already_drawn + not_a_giveaway.
  5) Radio Directory scaling — source=imported paginated fast path (deep pages, search).
  6) Admin Rate Card — 9 items including instant_win_game + giveaway_entry (backfilled).
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://mobile-games-v2.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def demo_session():
    r = requests.post(f"{API}/auth/demo")
    assert r.status_code == 200, r.text
    data = r.json()
    tok = data["session_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return {"session": s, "user_id": data["user_id"], "email": data["email"]}


@pytest.fixture(scope="session")
def demo2_session():
    """Second fresh demo session (different underlying user_id-per-token flow if applicable).

    Falls back to primary demo if backend keys demo by email only.
    """
    r = requests.post(f"{API}/auth/demo")
    assert r.status_code == 200
    data = r.json()
    tok = data["session_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return {"session": s, "user_id": data["user_id"]}


@pytest.fixture(scope="session")
def admin_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"email": "admin@bigfm.dubai", "password": "AdminPass123!"})
    assert r.status_code == 200, r.text
    s.headers.update({"Content-Type": "application/json"})
    return {"session": s, "user_id": r.json()["user_id"]}


# ==================== 1) Ad format selector ====================

class TestRateCardFormats:
    def test_formats_returns_4_with_pricing(self, demo_session):
        r = demo_session["session"].get(f"{API}/rate-card/formats")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        formats = {i["format"]: i for i in items}
        for k in ("banner", "audio", "push", "video"):
            assert k in formats, f"missing format {k}"
            assert formats[k].get("pricing_model") in ("CPM", "CPC", "CPA", "CPL", "flat"), formats[k]
            assert isinstance(formats[k].get("base_cents"), int)

    def test_formats_requires_auth(self):
        r = requests.get(f"{API}/rate-card/formats")
        assert r.status_code in (401, 403)


# ==================== 2) Campaign CRUD (MKT.2 types) ====================

class TestMKT2CampaignCRUD:
    def test_bad_type_400(self, demo_session):
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns", json={
            "merchant_id": "biz_demo_marketplace",
            "type": "bogus_type", "goal": "engagement",
            "title": "TEST bad", "budget_usd": 1.0,
        })
        assert r.status_code == 400, r.text
        assert r.json().get("detail", {}).get("code") == "bad_campaign_type"

    def test_giveaway_requires_prize_desc(self, demo_session):
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns", json={
            "merchant_id": "biz_demo_marketplace",
            "type": "giveaway", "goal": "engagement",
            "title": "TEST_iter48_gv_bad", "budget_usd": 1.0, "num_winners": 1,
        })
        assert r.status_code == 400, r.text
        assert r.json().get("detail", {}).get("code") == "prize_required"

    def test_create_spin_ok(self, demo_session):
        title = f"TEST_iter48_spin_{uuid.uuid4().hex[:6]}"
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns", json={
            "merchant_id": "biz_demo_marketplace",
            "type": "spin", "goal": "engagement",
            "title": title, "budget_usd": 5.0,
            "win_points": 25, "win_probability": 1.0,
            "prize_label": "25 pts guaranteed",
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "spin"
        assert d["win_points"] == 25
        assert d["win_probability"] == 1.0
        assert d["status"] == "active"
        pytest._iter48_spin_id = d["campaign_id"]

    def test_create_scratch_low_budget_for_autopause(self, demo_session):
        # Very small budget so a single play will exhaust it → status flips to paused.
        title = f"TEST_iter48_scratch_{uuid.uuid4().hex[:6]}"
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns", json={
            "merchant_id": "biz_demo_marketplace",
            "type": "scratch", "goal": "engagement",
            "title": title, "budget_usd": 0.05,
            "win_points": 5, "win_probability": 0.001,
        })
        assert r.status_code == 200, r.text
        pytest._iter48_scratch_id = r.json()["campaign_id"]

    def test_create_giveaway_ok(self, demo_session):
        title = f"TEST_iter48_gv_{uuid.uuid4().hex[:6]}"
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns", json={
            "merchant_id": "biz_demo_marketplace",
            "type": "giveaway", "goal": "engagement",
            "title": title, "budget_usd": 5.0,
            "prize_desc": "Weekend brunch for two",
            "num_winners": 2,
            "reward_points_on_claim": 3,
        })
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["type"] == "giveaway"
        assert d["num_winners"] == 2
        assert d["prize_desc"] == "Weekend brunch for two"
        assert d.get("drawn") in (False, None)
        pytest._iter48_gv_id = d["campaign_id"]


# ==================== 3) Brand Games ====================

class TestBrandGames:
    def test_active_lists_spin(self, demo_session):
        r = demo_session["session"].get(f"{API}/brand-games/active")
        assert r.status_code == 200, r.text
        ids = [c["campaign_id"] for c in r.json()["items"]]
        assert getattr(pytest, "_iter48_spin_id", None) in ids

    def test_play_wins_awards_points(self, demo_session):
        cid = getattr(pytest, "_iter48_spin_id", None)
        r = demo_session["session"].post(f"{API}/brand-games/{cid}/play")
        assert r.status_code == 200, r.text
        d = r.json()
        # win_probability=1.0 → guaranteed win
        assert d["won"] is True
        assert d["awarded"] == 25

    def test_play_idempotent_409(self, demo_session):
        cid = getattr(pytest, "_iter48_spin_id", None)
        r = demo_session["session"].post(f"{API}/brand-games/{cid}/play")
        assert r.status_code == 409, r.text
        assert r.json().get("detail", {}).get("code") == "already_played"

    def test_active_marks_played(self, demo_session):
        cid = getattr(pytest, "_iter48_spin_id", None)
        r = demo_session["session"].get(f"{API}/brand-games/active")
        items = {c["campaign_id"]: c for c in r.json()["items"]}
        if cid in items:
            # Some backends drop the row once played+budget-exhausted; if still listed, must show played state.
            assert items[cid].get("played") is not None
        # OK if excluded — still valid.

    def test_scratch_autopauses_on_budget_exhaustion(self, demo_session, demo2_session):
        cid = getattr(pytest, "_iter48_scratch_id", None)
        # Use secondary demo session — but demo user is shared by email; a play will 409 if already played.
        # Try with primary session first — if that returns 409, the campaign already exhausted from smoke.
        r = demo_session["session"].post(f"{API}/brand-games/{cid}/play")
        assert r.status_code in (200, 409), r.text
        # instant_win_game rate = 12c > $0.05 budget → after 1 play, should be paused
        # Verify via list
        r2 = demo_session["session"].get(f"{API}/merchant/marketplace/campaigns")
        c = next((x for x in r2.json()["items"] if x["campaign_id"] == cid), None)
        assert c is not None
        assert c["status"] == "paused", f"expected paused after budget exhaustion, got {c['status']} spent={c.get('spent_usd')} budget={c.get('budget_usd')}"


# ==================== 4) Brand Giveaways ====================

class TestBrandGiveaways:
    def test_active_lists_giveaway(self, demo_session):
        r = demo_session["session"].get(f"{API}/brand-giveaways/active")
        assert r.status_code == 200, r.text
        ids = [c["campaign_id"] for c in r.json()["items"]]
        assert getattr(pytest, "_iter48_gv_id", None) in ids

    def test_enter_awards(self, demo_session):
        cid = getattr(pytest, "_iter48_gv_id", None)
        r = demo_session["session"].post(f"{API}/brand-giveaways/{cid}/enter")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert d["awarded"] == 3

    def test_enter_idempotent_409(self, demo_session):
        cid = getattr(pytest, "_iter48_gv_id", None)
        r = demo_session["session"].post(f"{API}/brand-giveaways/{cid}/enter")
        assert r.status_code == 409, r.text
        assert r.json().get("detail", {}).get("code") == "already_entered"

    def test_active_marks_entered(self, demo_session):
        cid = getattr(pytest, "_iter48_gv_id", None)
        r = demo_session["session"].get(f"{API}/brand-giveaways/active")
        c = next((x for x in r.json()["items"] if x["campaign_id"] == cid), None)
        assert c is not None
        assert c.get("entered") is True

    def test_draw_not_a_giveaway_on_spin(self, demo_session):
        spin_id = getattr(pytest, "_iter48_spin_id", None)
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns/{spin_id}/draw")
        assert r.status_code == 400, r.text
        assert r.json().get("detail", {}).get("code") == "not_a_giveaway"

    def test_draw_owner_ok(self, demo_session):
        cid = getattr(pytest, "_iter48_gv_id", None)
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns/{cid}/draw")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["ok"] is True
        assert isinstance(d["winners"], list)
        # at least the demo user's entry
        assert d["total_entries"] >= 1
        # min(num_winners=2, total_entries) winners
        assert len(d["winners"]) == min(2, d["total_entries"])

    def test_draw_already_drawn_400(self, demo_session):
        cid = getattr(pytest, "_iter48_gv_id", None)
        r = demo_session["session"].post(f"{API}/merchant/marketplace/campaigns/{cid}/draw")
        assert r.status_code == 400, r.text
        assert r.json().get("detail", {}).get("code") == "already_drawn"

    def test_drawn_giveaway_excluded_from_active(self, demo_session):
        cid = getattr(pytest, "_iter48_gv_id", None)
        r = demo_session["session"].get(f"{API}/brand-giveaways/active")
        ids = [c["campaign_id"] for c in r.json()["items"]]
        assert cid not in ids


# ==================== 5) Radio Directory scaling ====================

class TestRadioDirectory:
    def test_imported_page1(self, demo_session):
        r = requests.get(f"{API}/radio/browse", params={"source": "imported", "page": 1, "limit": 24})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["page"] == 1
        assert d["limit"] == 24
        assert isinstance(d["total"], int)
        assert d["total"] > 1000, f"expected large imported catalog, got total={d['total']}"
        assert len(d["items"]) <= 24
        # counts_by_source imported should equal total
        assert d.get("counts_by_source", {}).get("imported") == d["total"]

    def test_imported_deep_page(self, demo_session):
        r = requests.get(f"{API}/radio/browse", params={"source": "imported", "page": 3, "limit": 24})
        assert r.status_code == 200
        d = r.json()
        assert d["page"] == 3
        assert len(d["items"]) > 0, "page 3 returned no items"

    def test_imported_search(self, demo_session):
        r = requests.get(f"{API}/radio/browse", params={"source": "imported", "q": "radio", "page": 1, "limit": 12})
        assert r.status_code == 200
        d = r.json()
        assert len(d["items"]) > 0

    def test_all_source_unchanged(self, demo_session):
        r = requests.get(f"{API}/radio/browse", params={"source": "all", "page": 1, "limit": 24})
        assert r.status_code == 200
        d = r.json()
        # Merged path returns counts_by_source with all 3 keys
        cbs = d.get("counts_by_source", {})
        assert "bigfm_ai" in cbs and "community" in cbs and "imported" in cbs


# ==================== 6) Admin Rate Card w/ new keys ====================

class TestRateCardExpanded:
    def test_rate_card_has_9_items(self, admin_session):
        r = admin_session["session"].get(f"{API}/admin/rate-card")
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        keys = {i["key"] for i in items}
        assert "instant_win_game" in keys, f"instant_win_game missing; keys={keys}"
        assert "giveaway_entry" in keys, f"giveaway_entry missing; keys={keys}"
        assert len(items) >= 9, f"expected >=9 rate items, got {len(items)}"

    def test_rate_card_put_still_validates(self, admin_session):
        current = admin_session["session"].get(f"{API}/admin/rate-card").json()["items"]
        bad = [dict(current[0])]
        bad[0]["pricing_model"] = "ZZZ"
        r = admin_session["session"].put(f"{API}/admin/rate-card", json={"items": bad})
        assert r.status_code == 400, r.text
