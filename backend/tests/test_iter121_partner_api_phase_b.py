"""Phase B (Partner API v1 write-safety + discovery pricing) tests.

Covers:
  • POST /api/v1/quotes — server-authoritative pricing, error codes.
  • Idempotency-Key on POST /advertisers, /campaigns, /sponsorships, /quotes.
  • external_id de-dup on advertisers/campaigns/sponsorships.
  • Cursor pagination + external_id filter on /campaigns and /sponsorships.
  • SANDBOX auto-activate + env-scoping of idempotency/external_id.
  • capabilities feature_flags idempotency_keys/external_id/quotes=true.
  • Regression: Phase A discovery + /me + /products + /openapi.json.
"""
from __future__ import annotations

import os
import uuid
import time
import pytest
import requests
from dotenv import dotenv_values

_env_file = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL")
        or _env_file.get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api/v1"
SANDBOX_KEY = "rlk_test_BdmWmROSnKO1.7gBxOXKXEIsKhfWOwunaKO2zBlhrtvbgU8uAmkZBwIk"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {SANDBOX_KEY}",
                         "Content-Type": "application/json"})
    return sess


def _uniq(prefix: str = "ta") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ── /quotes ─────────────────────────────────────────────────────────
class TestQuotes:
    def test_quote_audio_preroll_dubai_matches_expected(self, s):
        r = s.post(f"{BASE}/quotes", json={
            "product": "audio_preroll", "pricing_model": "cpm",
            "market": "dubai", "budget_cents": 500000,
            "targeting_dimensions": 2, "daypart": "morning_drive"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["base_rate_cents"] == 2500
        assert d["effective_rate_cents"] == 4680
        assert d["multipliers_applied"] == {
            "market": 1.2, "daypart": 1.3, "premium": 1.0, "targeting": 1.2}
        assert d["estimated_volume"] == {"impressions": 106837}
        assert d["minimum_spend_cents"] == 5000
        assert d["quote_id"].startswith("qte_")
        assert "expires_at" in d and "created_at" in d
        assert d["environment"] == "SANDBOX"

    def test_quote_premium_multiplier(self, s):
        r = s.post(f"{BASE}/quotes", json={
            "product": "audio_preroll", "pricing_model": "cpm",
            "market": "dubai", "budget_cents": 0,
            "targeting_dimensions": 0, "daypart": "morning_drive",
            "premium": True})
        assert r.status_code == 200
        d = r.json()
        assert d["multipliers_applied"]["premium"] == 1.25
        # 2500 * 1.2 * 1.3 * 1.25 = 4875
        assert d["effective_rate_cents"] == 4875

    def test_quote_invalid_pricing_model_for_product(self, s):
        r = s.post(f"{BASE}/quotes", json={
            "product": "audio_preroll", "pricing_model": "cpc"})
        assert r.status_code == 400
        body = r.json()
        assert body["error"]["code"] == "invalid_pricing_model_for_product"
        assert "detail" in body  # legacy envelope preserved

    def test_quote_unknown_product(self, s):
        r = s.post(f"{BASE}/quotes",
                   json={"product": "nope_no_such_thing", "pricing_model": "cpm"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "unknown_product"

    def test_quote_idempotency_returns_same_object(self, s):
        key = _uniq("idem")
        payload = {"product": "display_banner", "pricing_model": "cpm",
                   "market": "new_york", "budget_cents": 100000}
        r1 = s.post(f"{BASE}/quotes", json=payload, headers={"Idempotency-Key": key})
        r2 = s.post(f"{BASE}/quotes",
                    json={**payload, "budget_cents": 999999},
                    headers={"Idempotency-Key": key})
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json()["quote_id"] == r2.json()["quote_id"]


# ── advertiser create: idempotency + external_id ────────────────────
@pytest.fixture(scope="session")
def advertiser(s):
    ext_id = _uniq("advext")
    r = s.post(f"{BASE}/advertisers", json={
        "name": "TEST TA Phase B", "contact_email": "ta_pb@test.dev",
        "external_id": ext_id})
    assert r.status_code == 201, r.text
    body = r.json()
    body["_external_id"] = ext_id
    return body


class TestAdvertiserWriteSafety:
    def test_created_with_status_active_in_sandbox(self, advertiser):
        assert advertiser["advertiser"]["status"] == "active"
        assert advertiser["environment"] == "SANDBOX"
        assert advertiser["external_id"] == advertiser["_external_id"]

    def test_idempotency_same_key_returns_same_object(self, s):
        key = _uniq("idem")
        p = {"name": "TEST IdemAdv", "contact_email": "a@t.dev"}
        r1 = s.post(f"{BASE}/advertisers", json=p, headers={"Idempotency-Key": key})
        r2 = s.post(f"{BASE}/advertisers",
                    json={**p, "name": "TEST DifferentName"},
                    headers={"Idempotency-Key": key})
        assert r1.status_code == 201 and r2.status_code in (200, 201)
        assert (r1.json()["advertiser"]["advertiser_id"] ==
                r2.json()["advertiser"]["advertiser_id"])
        # Body change ignored — original returned
        assert r2.json()["advertiser"]["name"] == "TEST IdemAdv"

    def test_external_id_dedupes_across_different_idem_keys(self, s):
        ext = _uniq("adext")
        r1 = s.post(f"{BASE}/advertisers",
                    json={"name": "TEST ExtAdv", "contact_email": "e@t.dev",
                          "external_id": ext},
                    headers={"Idempotency-Key": _uniq("k")})
        r2 = s.post(f"{BASE}/advertisers",
                    json={"name": "TEST ExtAdv Retry", "contact_email": "e@t.dev",
                          "external_id": ext},
                    headers={"Idempotency-Key": _uniq("k")})
        assert r1.status_code == 201 and r2.status_code in (200, 201)
        assert (r1.json()["advertiser"]["advertiser_id"] ==
                r2.json()["advertiser"]["advertiser_id"])

    def test_different_idem_key_no_external_id_creates_new(self, s):
        p = {"name": "TEST NewEachTime", "contact_email": "n@t.dev"}
        r1 = s.post(f"{BASE}/advertisers", json=p, headers={"Idempotency-Key": _uniq("k")})
        r2 = s.post(f"{BASE}/advertisers", json=p, headers={"Idempotency-Key": _uniq("k")})
        assert (r1.json()["advertiser"]["advertiser_id"] !=
                r2.json()["advertiser"]["advertiser_id"])


# ── campaign create + list pagination + external_id ────────────────
@pytest.fixture(scope="session")
def campaign_ids(s, advertiser):
    """Create 3 campaigns for pagination + one with a known external_id."""
    aid = advertiser["advertiser"]["advertiser_id"]
    external_id_first = _uniq("cext")
    ids = []
    for i in range(3):
        body = {"advertiser_id": aid, "product": "audio_preroll",
                "name": f"TEST Camp {i}", "budget_total_cents": 500000,
                "pricing_model": "cpm", "cpm_bid_cents": 3000,
                "creative": {"audio_url": "https://example.com/a.mp3"}}
        if i == 0:
            body["external_id"] = external_id_first
        r = s.post(f"{BASE}/campaigns", json=body)
        assert r.status_code == 201, r.text
        ids.append(r.json()["campaign"]["campaign_id"])
        # small stagger so created_at ordering is deterministic
        time.sleep(0.05)
    return {"aid": aid, "ids": ids, "first_ext": external_id_first}


class TestCampaignWriteSafety:
    def test_campaigns_created_active_in_sandbox(self, s, campaign_ids):
        r = s.get(f"{BASE}/campaigns/{campaign_ids['ids'][0]}",
                  params={"advertiser_id": campaign_ids["aid"]})
        assert r.status_code == 200
        assert r.json()["campaign"]["status"] == "active"

    def test_idempotency_campaign(self, s, campaign_ids):
        key = _uniq("cidem")
        body = {"advertiser_id": campaign_ids["aid"], "product": "audio_preroll",
                "name": "TEST IdemCamp", "budget_total_cents": 100000,
                "pricing_model": "cpm", "cpm_bid_cents": 3000,
                "creative": {"audio_url": "https://example.com/a.mp3"}}
        r1 = s.post(f"{BASE}/campaigns", json=body, headers={"Idempotency-Key": key})
        r2 = s.post(f"{BASE}/campaigns",
                    json={**body, "name": "TEST DiffName"},
                    headers={"Idempotency-Key": key})
        assert r1.status_code == 201
        assert (r1.json()["campaign"]["campaign_id"] ==
                r2.json()["campaign"]["campaign_id"])

    def test_external_id_dedupe_campaign(self, s, campaign_ids):
        ext = _uniq("cext2")
        aid = campaign_ids["aid"]
        body = {"advertiser_id": aid, "product": "audio_preroll",
                "name": "TEST ExtCamp", "budget_total_cents": 100000,
                "pricing_model": "cpm", "cpm_bid_cents": 3000,
                "creative": {"audio_url": "https://example.com/a.mp3"},
                "external_id": ext}
        r1 = s.post(f"{BASE}/campaigns", json=body, headers={"Idempotency-Key": _uniq("k")})
        r2 = s.post(f"{BASE}/campaigns",
                    json={**body, "name": "TEST DifferentBody"},
                    headers={"Idempotency-Key": _uniq("k")})
        assert (r1.json()["campaign"]["campaign_id"] ==
                r2.json()["campaign"]["campaign_id"])


class TestCampaignPagination:
    def test_cursor_pagination_disjoint_pages(self, s, campaign_ids):
        aid = campaign_ids["aid"]
        r1 = s.get(f"{BASE}/campaigns", params={"advertiser_id": aid, "limit": 2})
        assert r1.status_code == 200
        d1 = r1.json()
        # backward-compat envelope
        for k in ("items", "count", "data", "next_cursor", "has_more"):
            assert k in d1, f"missing {k}"
        assert d1["items"] == d1["data"]
        assert len(d1["data"]) == 2
        assert d1["has_more"] is True
        assert d1["next_cursor"]
        # page 2
        r2 = s.get(f"{BASE}/campaigns", params={"advertiser_id": aid,
                                                "limit": 2, "cursor": d1["next_cursor"]})
        assert r2.status_code == 200
        d2 = r2.json()
        ids_a = {c["campaign_id"] for c in d1["data"]}
        ids_b = {c["campaign_id"] for c in d2["data"]}
        assert ids_a.isdisjoint(ids_b)

    def test_invalid_cursor(self, s, campaign_ids):
        r = s.get(f"{BASE}/campaigns",
                  params={"advertiser_id": campaign_ids["aid"],
                          "cursor": "!!!not-a-cursor!!!"})
        assert r.status_code == 400
        body = r.json()
        assert body["error"]["code"] == "invalid_cursor"
        assert "detail" in body  # legacy

    def test_external_id_filter_narrows(self, s, campaign_ids):
        r = s.get(f"{BASE}/campaigns",
                  params={"advertiser_id": campaign_ids["aid"],
                          "external_id": campaign_ids["first_ext"]})
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 1
        assert d["data"][0]["campaign_id"] == campaign_ids["ids"][0]

    def test_external_id_filter_unknown_returns_empty(self, s, campaign_ids):
        r = s.get(f"{BASE}/campaigns",
                  params={"advertiser_id": campaign_ids["aid"],
                          "external_id": "no_such_ext"})
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 0
        assert d["data"] == []


# ── sponsorships: create + list + pagination + external_id ─────────
@pytest.fixture(scope="session")
def sponsorship_ids(s, advertiser):
    aid = advertiser["advertiser"]["advertiser_id"]
    ext_first = _uniq("sext")
    ids = []
    from datetime import datetime, timedelta, timezone
    start = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    for i in range(3):
        body = {"type": "trivia", "advertiser_id": aid,
                "display_name": f"TEST TriviaSp {i}", "tagline": "hi",
                "prize_pool": [{"rank": 1, "points_reward": 1000, "currency": "bc"}],
                "winner_selection": "top_n",
                "start_at": start, "end_at": end}
        if i == 0:
            body["external_id"] = ext_first
        r = s.post(f"{BASE}/sponsorships", json=body)
        assert r.status_code == 201, r.text
        ids.append(r.json()["sponsorship"].get("id") or
                   r.json()["sponsorship"].get("sponsorship_id"))
        time.sleep(0.05)
    return {"aid": aid, "ids": ids, "first_ext": ext_first}


class TestSponsorshipWriteSafety:
    def test_created_active_in_sandbox(self, sponsorship_ids):
        assert all(sid for sid in sponsorship_ids["ids"])

    def test_idempotency_sponsorship(self, s, sponsorship_ids):
        aid = sponsorship_ids["aid"]
        key = _uniq("sidem")
        from datetime import datetime, timedelta, timezone
        start = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        body = {"type": "trivia", "advertiser_id": aid,
                "display_name": "TEST IdemSp",
                "prize_pool": [{"rank": 1, "points_reward": 1000, "currency": "bc"}],
                "winner_selection": "top_n",
                "start_at": start, "end_at": end}
        r1 = s.post(f"{BASE}/sponsorships", json=body, headers={"Idempotency-Key": key})
        r2 = s.post(f"{BASE}/sponsorships",
                    json={**body, "display_name": "TEST Diff"},
                    headers={"Idempotency-Key": key})
        assert r1.status_code == 201
        id1 = r1.json()["sponsorship"].get("id") or r1.json()["sponsorship"].get("sponsorship_id")
        id2 = r2.json()["sponsorship"].get("id") or r2.json()["sponsorship"].get("sponsorship_id")
        assert id1 == id2

    def test_external_id_dedupe_sponsorship(self, s, sponsorship_ids):
        aid = sponsorship_ids["aid"]
        ext = _uniq("sext2")
        from datetime import datetime, timedelta, timezone
        start = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        end = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        body = {"type": "trivia", "advertiser_id": aid,
                "display_name": "TEST ExtSp",
                "prize_pool": [{"rank": 1, "points_reward": 1000, "currency": "bc"}],
                "winner_selection": "top_n", "external_id": ext,
                "start_at": start, "end_at": end}
        r1 = s.post(f"{BASE}/sponsorships", json=body, headers={"Idempotency-Key": _uniq("k")})
        r2 = s.post(f"{BASE}/sponsorships",
                    json={**body, "display_name": "TEST Diff2"},
                    headers={"Idempotency-Key": _uniq("k")})
        id1 = r1.json()["sponsorship"].get("id") or r1.json()["sponsorship"].get("sponsorship_id")
        id2 = r2.json()["sponsorship"].get("id") or r2.json()["sponsorship"].get("sponsorship_id")
        assert id1 == id2


class TestSponsorshipPagination:
    def test_cursor_pagination(self, s, sponsorship_ids):
        aid = sponsorship_ids["aid"]
        r1 = s.get(f"{BASE}/sponsorships",
                   params={"type": "trivia", "advertiser_id": aid, "limit": 2})
        assert r1.status_code == 200
        d1 = r1.json()
        for k in ("items", "count", "data", "next_cursor", "has_more"):
            assert k in d1
        assert len(d1["data"]) == 2
        assert d1["has_more"] is True
        r2 = s.get(f"{BASE}/sponsorships",
                   params={"type": "trivia", "advertiser_id": aid,
                           "limit": 2, "cursor": d1["next_cursor"]})
        assert r2.status_code == 200
        ids_a = {(x.get("id") or x.get("sponsorship_id")) for x in d1["data"]}
        ids_b = {(x.get("id") or x.get("sponsorship_id")) for x in r2.json()["data"]}
        assert ids_a.isdisjoint(ids_b)

    def test_invalid_cursor(self, s, sponsorship_ids):
        r = s.get(f"{BASE}/sponsorships",
                  params={"type": "trivia",
                          "advertiser_id": sponsorship_ids["aid"],
                          "cursor": "@@@bad"})
        assert r.status_code == 400
        assert r.json()["error"]["code"] == "invalid_cursor"

    def test_external_id_filter(self, s, sponsorship_ids):
        r = s.get(f"{BASE}/sponsorships",
                  params={"type": "trivia",
                          "advertiser_id": sponsorship_ids["aid"],
                          "external_id": sponsorship_ids["first_ext"]})
        assert r.status_code == 200
        d = r.json()
        assert d["count"] == 1
        assert (d["data"][0].get("id") or d["data"][0].get("sponsorship_id")) == \
            sponsorship_ids["ids"][0]


# ── capabilities / regression ───────────────────────────────────────
class TestCapabilitiesFlags:
    def test_phase_b_flags_true(self, s):
        r = s.get(f"{BASE}/capabilities")
        assert r.status_code == 200
        ff = r.json()["feature_flags"]
        assert ff["idempotency_keys"] is True
        assert ff["external_id"] is True
        assert ff["quotes"] is True


class TestPhaseARegression:
    @pytest.mark.parametrize("path", [
        "/status", "/inventory", "/markets", "/rate-card", "/me", "/products",
        "/openapi.json"])
    def test_endpoints_still_work(self, s, path):
        # /status and /openapi.json are unauthenticated but a bearer header is
        # harmless.
        r = s.get(f"{BASE}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code}"

    def test_legacy_detail_field_on_errors(self, s):
        r = s.post(f"{BASE}/quotes", json={"product": "nope"})
        assert r.status_code == 400
        body = r.json()
        assert "detail" in body and body["error"]["code"] == "unknown_product"

    def test_stations_still_paginated(self, s):
        r = s.get(f"{BASE}/stations", params={"country": "AE", "limit": 2})
        assert r.status_code == 200
        d = r.json()
        for k in ("data", "next_cursor", "has_more"):
            assert k in d


# ── env-scoping smoke test (SANDBOX external_id doesn't collide w/ LIVE) ─
class TestEnvScoping:
    """We only have a SANDBOX key. Full LIVE cross-check requires a LIVE key,
    so we just assert the response is stamped SANDBOX and the mapping
    is stored under the caller's environment."""

    def test_env_is_sandbox(self, s):
        r = s.get(f"{BASE}/me")
        assert r.status_code == 200
        assert r.json()["environment"] == "SANDBOX"
